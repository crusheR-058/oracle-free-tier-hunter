"""
OCI Account Resource Inventory and live usage aggregator.
"""

from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Optional
import oci

logger = logging.getLogger("free_tier_hunter.account_inventory")


@dataclass
class InstanceInfo:
    id: str
    display_name: str
    shape: str
    lifecycle_state: str
    availability_domain: str
    ocpus: float
    memory_in_gbs: float
    time_created: str
    public_ips: List[str] = field(default_factory=list)


@dataclass
class VolumeInfo:
    id: str
    display_name: str
    size_in_gbs: int
    lifecycle_state: str
    is_boot_volume: bool


@dataclass
class TenancyInventory:
    tenancy_id: str
    region: str
    active_instances: List[InstanceInfo]
    boot_volumes: List[VolumeInfo]
    block_volumes: List[VolumeInfo]
    used_a1_ocpus: float
    used_a1_ram_gb: float
    used_e2_count: int
    used_storage_gb: int
    existing_reforger_instances: List[InstanceInfo]


class AccountInventoryCollector:
    """Collects real-time resource consumption across the OCI compartment/tenancy."""

    def __init__(self, oci_manager: Any):
        self.oci_manager = oci_manager

    def collect(self, compartment_id: Optional[str] = None, name_prefix: str = "viaf-reforger-free-") -> TenancyInventory:
        target_compartment = compartment_id or self.oci_manager.tenancy_id
        compute_client = self.oci_manager.compute_client
        blockstorage_client = self.oci_manager.blockstorage_client

        logger.info(f"Collecting inventory for compartment {target_compartment} in {self.oci_manager.region}...")

        # 1. Collect Instances
        active_instances: List[InstanceInfo] = []
        used_a1_ocpus = 0.0
        used_a1_ram_gb = 0.0
        used_e2_count = 0
        existing_reforger_instances: List[InstanceInfo] = []

        try:
            instances_response = compute_client.list_instances(compartment_id=target_compartment)
            raw_instances = instances_response.data if hasattr(instances_response, "data") else []

            for inst in raw_instances:
                # Ignore terminated instances
                state = getattr(inst, "lifecycle_state", "").upper()
                if state in ["TERMINATED", "TERMINATING"]:
                    continue

                shape = getattr(inst, "shape", "")
                display_name = getattr(inst, "display_name", "")
                ad = getattr(inst, "availability_domain", "")
                inst_id = getattr(inst, "id", "")
                time_created = str(getattr(inst, "time_created", ""))

                # Extract OCPUs and RAM
                shape_config = getattr(inst, "shape_config", None)
                if shape_config:
                    ocpus = float(getattr(shape_config, "ocpus", 0.0) or 0.0)
                    ram_gb = float(getattr(shape_config, "memory_in_gbs", 0.0) or 0.0)
                else:
                    # Non-flexible shapes fallback
                    if shape == "VM.Standard.E2.1.Micro":
                        ocpus = 0.125
                        ram_gb = 1.0
                    else:
                        ocpus = 1.0
                        ram_gb = 1.0

                inst_info = InstanceInfo(
                    id=inst_id,
                    display_name=display_name,
                    shape=shape,
                    lifecycle_state=state,
                    availability_domain=ad,
                    ocpus=ocpus,
                    memory_in_gbs=ram_gb,
                    time_created=time_created,
                )
                active_instances.append(inst_info)

                # Check if this matches the tool's deployment prefix
                if display_name.startswith(name_prefix):
                    existing_reforger_instances.append(inst_info)

                # Tally Always Free usage
                if shape == "VM.Standard.A1.Flex":
                    used_a1_ocpus += ocpus
                    used_a1_ram_gb += ram_gb
                elif shape == "VM.Standard.E2.1.Micro":
                    used_e2_count += 1

        except Exception as e:
            logger.error(f"Error querying instances: {e}")
            raise

        # 2. Collect Boot Volumes
        boot_volumes: List[VolumeInfo] = []
        used_storage_gb = 0

        # Query ADs to list boot volumes
        try:
            identity_client = self.oci_manager.identity_client
            ad_response = identity_client.list_availability_domains(compartment_id=target_compartment)
            ads = [ad.name for ad in ad_response.data] if hasattr(ad_response, "data") else []

            for ad_name in ads:
                bv_response = blockstorage_client.list_boot_volumes(
                    availability_domain=ad_name,
                    compartment_id=target_compartment,
                )
                raw_bvs = bv_response.data if hasattr(bv_response, "data") else []
                for bv in raw_bvs:
                    bv_state = getattr(bv, "lifecycle_state", "").upper()
                    if bv_state in ["TERMINATED", "TERMINATING"]:
                        continue
                    size_gb = int(getattr(bv, "size_in_gbs", 0) or 0)
                    used_storage_gb += size_gb
                    boot_volumes.append(
                        VolumeInfo(
                            id=getattr(bv, "id", ""),
                            display_name=getattr(bv, "display_name", ""),
                            size_in_gbs=size_gb,
                            lifecycle_state=bv_state,
                            is_boot_volume=True,
                        )
                    )

            # Block Volumes
            block_volumes: List[VolumeInfo] = []
            blk_response = blockstorage_client.list_volumes(compartment_id=target_compartment)
            raw_blks = blk_response.data if hasattr(blk_response, "data") else []
            for blk in raw_blks:
                blk_state = getattr(blk, "lifecycle_state", "").upper()
                if blk_state in ["TERMINATED", "TERMINATING"]:
                    continue
                size_gb = int(getattr(blk, "size_in_gbs", 0) or 0)
                used_storage_gb += size_gb
                block_volumes.append(
                    VolumeInfo(
                        id=getattr(blk, "id", ""),
                        display_name=getattr(blk, "display_name", ""),
                        size_in_gbs=size_gb,
                        lifecycle_state=blk_state,
                        is_boot_volume=False,
                    )
                )

        except Exception as e:
            logger.warning(f"Error querying storage volumes: {e}")
            # If storage query fails, do not corrupt inventory, just log
            block_volumes = []

        return TenancyInventory(
            tenancy_id=target_compartment,
            region=self.oci_manager.region,
            active_instances=active_instances,
            boot_volumes=boot_volumes,
            block_volumes=block_volumes,
            used_a1_ocpus=used_a1_ocpus,
            used_a1_ram_gb=used_a1_ram_gb,
            used_e2_count=used_e2_count,
            used_storage_gb=used_storage_gb,
            existing_reforger_instances=existing_reforger_instances,
        )
