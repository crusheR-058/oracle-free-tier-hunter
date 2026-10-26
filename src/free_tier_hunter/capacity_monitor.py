"""
Continuous Capacity Watcher & Opportunity Monitoring Loop.
"""

from datetime import datetime, timedelta, timezone
import logging
import random
import signal
import sys
import time
from typing import Any, List, Optional

from .account_inventory import AccountInventoryCollector, TenancyInventory
from .architecture_checker import ArchitectureChecker, DiscoveredImage
from .candidate_ranker import CandidateRanker, LaunchCandidate
from .config import HunterConfig, OperatingMode
from .dashboard import HunterDashboard
from .networking import NetworkContext, NetworkManager
from .notifier import Notifier
from .oci_client import OciClientManager
from .provisioning_engine import ProvisioningEngine, ProvisioningOutcome
from .quota_calculator import QuotaCalculator, RemainingAllowances
from .shape_discovery import ShapeDiscoveryEngine
from .state_store import StateStore

logger = logging.getLogger("free_tier_hunter.capacity_monitor")


class CapacityMonitor:
    """Orchestrates continuous tenancy capacity monitoring and immediate auto-provisioning."""

    def __init__(
        self,
        config: HunterConfig,
        oci_manager: OciClientManager,
        dashboard: Optional[HunterDashboard] = None,
        notifier: Optional[Notifier] = None,
        state_store: Optional[StateStore] = None,
    ):
        self.config = config
        self.oci_manager = oci_manager
        self.dashboard = dashboard or HunterDashboard()
        self.state_store = state_store or StateStore(config.state_file_path)
        self.notifier = notifier or Notifier(
            enable_desktop=config.enable_desktop_notifications,
            enable_email=config.enable_email_notifications,
            smtp_host=config.smtp_host,
            smtp_port=config.smtp_port,
            smtp_user=config.smtp_user,
            smtp_password=config.smtp_password,
            smtp_from=config.smtp_from,
            notification_email=config.notification_email,
        )
        self.provisioning_engine = ProvisioningEngine(
            config=self.config,
            oci_manager=self.oci_manager,
            state_store=self.state_store,
            notifier=self.notifier,
        )

        self._running = False
        self._consecutive_capacity_failures = 0

    def run_single_cycle(self) -> dict:
        """Executes a single monitoring cycle. Returns cycle summary dictionary."""
        logger.info(f"Starting capacity check cycle for region {self.config.region}...")
        now_dt = datetime.now(timezone.utc)
        now_str = now_dt.isoformat()

        state = self.state_store.load()
        state.last_error = None
        state.last_check_time = now_str
        state.operating_mode = self.config.mode.value

        # 1. Collect live inventory
        collector = AccountInventoryCollector(self.oci_manager)
        inventory: TenancyInventory = collector.collect(
            compartment_id=self.config.compartment_id,
            name_prefix=self.config.instance_name_prefix,
        )

        # 2. Check if instance already exists
        if inventory.existing_reforger_instances:
            existing_inst = inventory.existing_reforger_instances[0]
            logger.info(f"Discovered existing instance: {existing_inst.display_name} ({existing_inst.lifecycle_state})")
            state.provisioned_instance_id = existing_inst.id
            state.provisioned_instance_name = existing_inst.display_name
            state.provisioned_instance_state = existing_inst.lifecycle_state
            state.last_verdict = "PROVISIONING_SUCCEEDED"
            self.state_store.save(state)

        # 3. Calculate quota allowances
        allowances: RemainingAllowances = QuotaCalculator.calculate(inventory)

        # 4. Discover ADs and shapes
        shape_engine = ShapeDiscoveryEngine(self.oci_manager)
        ads = shape_engine.list_availability_domains(self.config.compartment_id)
        ad_names = [ad.name for ad in ads] if ads else [f"{self.config.region.upper()}-AD-1"]

        # 5. Discover compatible OS image & network context
        arch_checker = ArchitectureChecker(self.oci_manager)
        net_manager = NetworkManager(self.oci_manager)

        # 6. Rank candidates
        candidates: List[LaunchCandidate] = CandidateRanker.evaluate_and_rank_candidates(
            allowances=allowances,
            availability_domains=ad_names,
            requested_boot_volume_gb=self.config.boot_volume_size_gb,
            require_native_compatibility=self.config.require_native_reforger_compatibility,
            allow_arm64_emulation=self.config.experimental_arm64_emulation,
        )

        capacity_status = "CAPACITY_UNKNOWN"

        # 7. Check if best candidate is launchable
        best_candidate: Optional[LaunchCandidate] = None
        for c in candidates:
            if c.is_launchable:
                best_candidate = c
                break

        provisioning_outcome: Optional[ProvisioningOutcome] = None

        if best_candidate:
            logger.info(
                f"Valid opportunity detected! Best candidate: {best_candidate.shape_name} "
                f"in {best_candidate.availability_domain} ({best_candidate.rank_score:.0f} pts)"
            )
            capacity_status = "CAPACITY_AVAILABLE"

            if self.config.mode == OperatingMode.AUTO_PROVISION_FREE and self.config.auto_provision_enabled:
                # Resolve OS image matching candidate architecture
                os_image = arch_checker.find_ubuntu_lts_image(
                    target_architecture=best_candidate.architecture,
                    target_version=self.config.preferred_os_version,
                    compartment_id=self.config.compartment_id,
                )

                # Resolve public subnet
                network_ctx = net_manager.find_or_prepare_public_subnet(
                    compartment_id=self.config.compartment_id,
                    ad_name=best_candidate.availability_domain,
                )

                if os_image and network_ctx:
                    logger.info("Executing immediate automatic provisioning...")
                    provisioning_outcome = self.provisioning_engine.attempt_provision(
                        candidate=best_candidate,
                        network_ctx=network_ctx,
                        os_image=os_image,
                    )
                    state.last_verdict = provisioning_outcome.status_label
                    if provisioning_outcome.success:
                        capacity_status = "PROVISIONING_SUCCEEDED"
                        self._consecutive_capacity_failures = 0
                    elif provisioning_outcome.status_label == "OUT_OF_HOST_CAPACITY":
                        capacity_status = "NO_CAPACITY"
                        self._consecutive_capacity_failures += 1
                else:
                    msg = "Missing OS image or public subnet for launch."
                    logger.error(msg)
                    state.last_error = msg
                    state.last_verdict = "INCOMPATIBLE_OS" if not os_image else "COST_UNCERTAIN"
            else:
                state.last_verdict = "ELIGIBLE"
        else:
            # No candidate was launchable
            if candidates:
                state.last_verdict = candidates[0].verdict_status
                if "INCOMPATIBLE" in state.last_verdict:
                    capacity_status = state.last_verdict
                elif "INSUFFICIENT" in state.last_verdict or "QUOTA" in state.last_verdict:
                    capacity_status = "QUOTA_EXCEEDED"
            else:
                state.last_verdict = "QUOTA_EXCEEDED"
                capacity_status = "QUOTA_EXCEEDED"

        # Calculate next check time
        backoff_minutes = self._calculate_backoff_minutes()
        next_dt = now_dt + timedelta(minutes=backoff_minutes)
        state.next_check_time = next_dt.isoformat()
        self.state_store.save(state)

        # 8. Render dashboard
        self.dashboard.render(
            config=self.config,
            state=state,
            inventory=inventory,
            allowances=allowances,
            candidates=candidates,
            capacity_status=capacity_status,
        )

        return {
            "timestamp": now_str,
            "capacity_status": capacity_status,
            "verdict": state.last_verdict,
            "best_candidate": best_candidate.candidate_id if best_candidate else None,
            "provisioning_outcome": provisioning_outcome,
            "next_check_minutes": backoff_minutes,
        }

    def start_monitoring_loop(self) -> None:
        """Starts continuous monitoring loop with graceful shutdown handling."""
        self._running = True

        def _signal_handler(signum, frame):
            logger.info("Shutdown signal received. Exiting watcher gracefully...")
            self._running = False
            sys.exit(0)

        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

        logger.info(f"Starting continuous capacity watcher (Poll interval: {self.config.poll_interval_minutes}m)...")
        while self._running:
            try:
                cycle_result = self.run_single_cycle()
                sleep_seconds = cycle_result["next_check_minutes"] * 60
                logger.info(f"Sleeping for {sleep_seconds / 60:.1f} minutes until next cycle...")

                # Interruptible sleep in 1-second chunks
                sleep_end = time.time() + sleep_seconds
                while time.time() < sleep_end and self._running:
                    time.sleep(1)

            except Exception as e:
                logger.error(f"Unexpected error in monitoring cycle: {e}", exc_info=True)
                time.sleep(60)

    def _calculate_backoff_minutes(self) -> float:
        """Calculates backoff with jitter on consecutive capacity exhaustion."""
        base = float(self.config.poll_interval_minutes)
        if self._consecutive_capacity_failures > 0:
            multiplier = self.config.backoff_factor ** min(self._consecutive_capacity_failures, 4)
            base = min(base * multiplier, float(self.config.max_backoff_minutes))

        # Add jitter
        jitter = base * self.config.jitter_ratio * (random.random() * 2 - 1)
        return max(1.0, round(base + jitter, 1))
