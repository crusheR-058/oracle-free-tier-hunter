"""
Immediate Auto-Provisioning Engine with 9-Gate Safety Protection and Lock Concurrency.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import os
import time
from typing import Any, List, Optional
from filelock import FileLock, Timeout
import oci

from .account_inventory import AccountInventoryCollector, InstanceInfo
from .architecture_checker import ArchitectureChecker, DiscoveredImage
from .candidate_ranker import LaunchCandidate
from .config import HunterConfig, OperatingMode
from .idempotency import IdempotencyEngine
from .networking import NetworkContext, NetworkManager
from .notifier import Notifier
from .oci_client import OciClientManager, OciErrorCategory, classify_oci_error
from .quota_calculator import QuotaCalculator
from .state_store import HunterState, StateStore

logger = logging.getLogger("free_tier_hunter.provisioning_engine")


@dataclass
class ProvisioningOutcome:
    success: bool
    status_label: str  # "PROVISIONING_SUCCEEDED", "OUT_OF_HOST_CAPACITY", "BLOCKED_BY_SAFETY_GATE", etc.
    instance_id: Optional[str]
    instance_name: Optional[str]
    public_ip: Optional[str]
    message: str


class ProvisioningEngine:
    """Safely executes automated instance provisioning under strict zero-cost and concurrency guards."""

    def __init__(
        self,
        config: HunterConfig,
        oci_manager: OciClientManager,
        state_store: StateStore,
        notifier: Notifier,
    ):
        self.config = config
        self.oci_manager = oci_manager
        self.state_store = state_store
        self.notifier = notifier
        self.lock_path = config.lock_file_path

    def attempt_provision(
        self,
        candidate: LaunchCandidate,
        network_ctx: NetworkContext,
        os_image: DiscoveredImage,
    ) -> ProvisioningOutcome:
        """
        Executes the immediate auto-provisioning workflow with local mutex locking,
        pre-flight revalidation, and idempotent instance creation.
        """
        if self.config.mode != OperatingMode.AUTO_PROVISION_FREE or not self.config.auto_provision_enabled:
            return ProvisioningOutcome(
                success=False,
                status_label="WATCH_ONLY",
                instance_id=None,
                instance_name=None,
                public_ip=None,
                message="Auto-provisioning is disabled by configuration (operating mode is WATCH_ONLY).",
            )

        logger.info(f"Acquiring local provisioning lock ({self.lock_path})...")
        lock = FileLock(self.lock_path, timeout=5)

        try:
            with lock:
                return self._guarded_launch(candidate, network_ctx, os_image)
        except Timeout:
            logger.warning("Another process currently holds the provisioning lock. Skipping this cycle.")
            return ProvisioningOutcome(
                success=False,
                status_label="PROVISIONING_IN_PROGRESS",
                instance_id=None,
                instance_name=None,
                public_ip=None,
                message="Provisioning lock contention: another worker is active.",
            )

    def _guarded_launch(
        self,
        candidate: LaunchCandidate,
        network_ctx: NetworkContext,
        os_image: DiscoveredImage,
    ) -> ProvisioningOutcome:
        # -------------------------------------------------------------
        # GATE 1 TO 9: Pre-Flight Safety Verification
        # -------------------------------------------------------------
        logger.info("Executing 9-Gate Safety Validation...")

        # Gate 1: Shape Always Free
        if not candidate.cost_result.is_verified_zero_cost:
            msg = f"Gate 1 Failed: Cost is not verified zero: {candidate.cost_result.details}"
            logger.error(msg)
            return ProvisioningOutcome(False, "COST_UNCERTAIN", None, None, None, msg)

        # Gate 2: Projected Monthly Cost
        if candidate.cost_result.projected_monthly_cost_inr > 0:
            msg = f"Gate 2 Failed: Projected monthly cost is ₹{candidate.cost_result.projected_monthly_cost_inr} > ₹0."
            logger.error(msg)
            return ProvisioningOutcome(False, "PAID_RESOURCE_BLOCKED", None, None, None, msg)

        # Gate 3: Workload Architecture Compatibility
        if self.config.require_native_reforger_compatibility and not candidate.compatibility_report.is_compatible:
            msg = f"Gate 3 Failed: Incompatible architecture for Reforger: {candidate.compatibility_report.details}"
            logger.warning(msg)
            return ProvisioningOutcome(False, candidate.compatibility_report.status.value, None, None, None, msg)

        # Gate 4: Storage Validation
        if not candidate.storage_plan.is_valid:
            msg = f"Gate 4 Failed: Storage plan invalid: {candidate.storage_plan.rejection_reason}"
            logger.error(msg)
            return ProvisioningOutcome(False, "INSUFFICIENT_STORAGE", None, None, None, msg)

        # Gate 5: Re-Check Account Live Inventory for Duplicates
        collector = AccountInventoryCollector(self.oci_manager)
        inventory = collector.collect(self.config.compartment_id, self.config.instance_name_prefix)
        existing = IdempotencyEngine.find_existing_deployment(
            inventory.active_instances,
            self.config.instance_name_prefix,
        )
        if existing:
            msg = (
                f"Gate 5 Failed: Active deployment already exists ({existing.display_name}, "
                f"OCID: {existing.id[:18]}..., State: {existing.lifecycle_state}). Duplicate creation blocked."
            )
            logger.info(msg)
            return ProvisioningOutcome(
                success=True,
                status_label="PROVISIONING_SUCCEEDED",
                instance_id=existing.id,
                instance_name=existing.display_name,
                public_ip=None,
                message=msg,
            )

        # Gate 6: Maximum Instances Safety Cap
        if len(inventory.existing_reforger_instances) >= self.config.maximum_instances_created_by_this_tool:
            msg = f"Gate 6 Failed: Maximum instances limit ({self.config.maximum_instances_created_by_this_tool}) reached."
            logger.warning(msg)
            return ProvisioningOutcome(False, "QUOTA_EXCEEDED", None, None, None, msg)

        # Gate 7: Free Quota Verification
        allowances = QuotaCalculator.calculate(inventory)
        if "A1" in candidate.shape_name and not allowances.can_launch_a1:
            msg = f"Gate 7 Failed: Insufficient A1 quota remaining (OCPUs={allowances.remaining_a1_ocpus}, RAM={allowances.remaining_a1_ram_gb}GB)."
            logger.error(msg)
            return ProvisioningOutcome(False, "QUOTA_EXCEEDED", None, None, None, msg)

        # Gate 8: Verified OS Image
        if not os_image or not os_image.id:
            msg = "Gate 8 Failed: Valid OS image could not be resolved."
            logger.error(msg)
            return ProvisioningOutcome(False, "INCOMPATIBLE_OS", None, None, None, msg)

        # Gate 9: Verified Public Subnet
        if not network_ctx or not network_ctx.subnet_id:
            msg = "Gate 9 Failed: Valid public subnet could not be resolved."
            logger.error(msg)
            return ProvisioningOutcome(False, "COST_UNCERTAIN", None, None, None, msg)

        logger.info("All 9 Safety Gates Passed. Proceeding with launch...")

        # -------------------------------------------------------------
        # Launch Preparation
        # -------------------------------------------------------------
        instance_name = IdempotencyEngine.generate_instance_name(
            prefix=self.config.instance_name_prefix,
            shape=candidate.shape_name,
            ad=candidate.availability_domain,
        )
        retry_token = IdempotencyEngine.generate_retry_token(
            candidate_id=candidate.candidate_id,
            tenancy_id=self.oci_manager.tenancy_id,
        )

        metadata = {}
        if self.config.ssh_public_key:
            metadata["ssh_authorized_keys"] = self.config.ssh_public_key

        # Build Launch Details
        source_details = oci.core.models.InstanceSourceViaImageDetails(
            source_type="image",
            image_id=os_image.id,
            boot_volume_size_in_gbs=candidate.boot_volume_size_gb,
            boot_volume_vpus_per_gb=candidate.storage_plan.vpu_per_gb,
        )

        vnic_details = oci.core.models.CreateVnicDetails(
            subnet_id=network_ctx.subnet_id,
            assign_public_ip=True,
            display_name=f"{instance_name}-vnic",
        )

        launch_kwargs: dict = {
            "compartment_id": self.config.compartment_id or self.oci_manager.tenancy_id,
            "availability_domain": candidate.availability_domain,
            "display_name": instance_name,
            "shape": candidate.shape_name,
            "source_details": source_details,
            "create_vnic_details": vnic_details,
            "metadata": metadata,
            "freeform_tags": {
                "ManagedBy": "OracleFreeTierHunter",
                "Workload": "ArmaReforger",
            },
        }

        # Shape configuration for flexible shapes (A1)
        if "Flex" in candidate.shape_name:
            launch_kwargs["shape_config"] = oci.core.models.LaunchInstanceShapeConfigDetails(
                ocpus=candidate.ocpus,
                memory_in_gbs=candidate.memory_in_gbs,
            )

        launch_details = oci.core.models.LaunchInstanceDetails(**launch_kwargs)

        # -------------------------------------------------------------
        # Execution with OCI Error & Capacity Handling
        # -------------------------------------------------------------
        compute_client = self.oci_manager.compute_client
        logger.info(f"Submitting launch request for {instance_name} in {candidate.availability_domain}...")

        try:
            response = compute_client.launch_instance(
                launch_instance_details=launch_details,
                opc_retry_token=retry_token,
            )
            created_inst = response.data
            instance_id = getattr(created_inst, "id", "")
            logger.info(f"Launch request accepted! Instance OCID: {instance_id}")

            # Record attempt in state
            self.state_store.record_attempt(
                candidate_id=candidate.candidate_id,
                shape=candidate.shape_name,
                ad=candidate.availability_domain,
                status="PROVISIONING_IN_PROGRESS",
                details="Instance launched; waiting for RUNNING state.",
                instance_id=instance_id,
            )

            # Bounded polling for RUNNING state (up to 5 minutes)
            public_ip = self._wait_for_running_and_get_ip(instance_id)

            # Update persistent state
            state = self.state_store.load()
            state.provisioned_instance_id = instance_id
            state.provisioned_instance_name = instance_name
            state.provisioned_instance_state = "RUNNING" if public_ip else "PROVISIONING"
            state.provisioned_public_ip = public_ip
            state.provisioned_at = datetime.now(timezone.utc).isoformat()
            self.state_store.save(state)

            self.notifier.notify(
                title="OCI Instance Provisioned Successfully!",
                message=f"Instance {instance_name} created in {candidate.availability_domain}. Public IP: {public_ip or 'Pending'}",
                level="INFO",
            )

            return ProvisioningOutcome(
                success=True,
                status_label="PROVISIONING_SUCCEEDED",
                instance_id=instance_id,
                instance_name=instance_name,
                public_ip=public_ip,
                message=f"Successfully provisioned Always Free instance {instance_name}.",
            )

        except Exception as e:
            classified = classify_oci_error(e)
            logger.warning(
                f"Launch attempt returned {classified.category.value} "
                f"(Status: {classified.status_code}, Code: {classified.code}): {classified.message}"
            )

            # If network error or timeout, re-check account before failing to avoid duplicate launch
            if classified.category == OciErrorCategory.TIMEOUT_OR_NETWORK:
                logger.info("Checking if instance was created despite timeout...")
                time.sleep(5)
                re_inv = collector.collect(self.config.compartment_id, self.config.instance_name_prefix)
                created_after = IdempotencyEngine.find_existing_deployment(
                    re_inv.active_instances,
                    self.config.instance_name_prefix,
                )
                if created_after:
                    logger.info(f"Recovered instance {created_after.display_name} created during timeout!")
                    return ProvisioningOutcome(
                        success=True,
                        status_label="PROVISIONING_SUCCEEDED",
                        instance_id=created_after.id,
                        instance_name=created_after.display_name,
                        public_ip=None,
                        message="Instance created successfully despite initial network timeout.",
                    )

            self.state_store.record_attempt(
                candidate_id=candidate.candidate_id,
                shape=candidate.shape_name,
                ad=candidate.availability_domain,
                status=classified.category.value,
                details=classified.message,
            )

            return ProvisioningOutcome(
                success=False,
                status_label=classified.category.value,
                instance_id=None,
                instance_name=None,
                public_ip=None,
                message=classified.message,
            )

    def _wait_for_running_and_get_ip(self, instance_id: str, timeout_seconds: int = 300) -> Optional[str]:
        """Polls instance until RUNNING and extracts public IPv4 address."""
        start_time = time.time()
        compute_client = self.oci_manager.compute_client
        net_client = self.oci_manager.network_client

        logger.info(f"Waiting for instance {instance_id[:18]}... to reach RUNNING state...")
        while time.time() - start_time < timeout_seconds:
            try:
                inst_resp = compute_client.get_instance(instance_id=instance_id)
                state = getattr(inst_resp.data, "lifecycle_state", "").upper()
                if state == "RUNNING":
                    logger.info("Instance is now RUNNING. Resolving public IP...")
                    # Query VNIC attachments
                    vnics_resp = compute_client.list_vnic_attachments(
                        compartment_id=self.config.compartment_id or self.oci_manager.tenancy_id,
                        instance_id=instance_id,
                    )
                    vnics = vnics_resp.data if hasattr(vnics_resp, "data") else []
                    for vnic_att in vnics:
                        vnic_id = getattr(vnic_att, "vnic_id", None)
                        if vnic_id:
                            vnic = net_client.get_vnic(vnic_id=vnic_id).data
                            public_ip = getattr(vnic, "public_ip", None)
                            if public_ip:
                                logger.info(f"Resolved Public IP: {public_ip}")
                                return public_ip
                    return None
                elif state in ["TERMINATED", "TERMINATING"]:
                    logger.error(f"Instance transitioned to unexpected state: {state}")
                    return None
            except Exception as e:
                logger.debug(f"Polling check error: {e}")

            time.sleep(10)

        logger.warning(f"Timeout waiting for instance {instance_id} to reach RUNNING state.")
        return None
