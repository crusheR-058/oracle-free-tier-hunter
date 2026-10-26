"""
Storage optimizer and boot volume sizing engine for Always Free tier.
"""

from dataclasses import dataclass
import logging
from typing import Optional

logger = logging.getLogger("free_tier_hunter.storage_optimizer")


@dataclass
class StorageAllocationPlan:
    is_valid: bool
    boot_volume_size_gb: int
    vpu_per_gb: int  # 10 VPU/GB is Balanced tier (Always Free standard)
    remaining_after_allocation_gb: int
    rejection_reason: Optional[str] = None


class StorageOptimizer:
    """
    Optimizes boot volume sizing to fit comfortably within the 200 GB Always Free tier
    while providing adequate space for Ubuntu Server LTS + SteamCMD + Arma Reforger.
    """

    DEFAULT_TARGET_SIZE_GB: int = 50
    MIN_SAFE_SIZE_GB: int = 47
    BALANCED_VPU: int = 10  # 10 VPUs/GB is default balanced performance

    @classmethod
    def plan_boot_volume(
        cls,
        requested_size_gb: int,
        remaining_free_storage_gb: int,
    ) -> StorageAllocationPlan:
        # Determine base candidate size
        candidate_size = max(requested_size_gb, cls.MIN_SAFE_SIZE_GB)

        # Check if requested size fits in remaining storage
        if candidate_size <= remaining_free_storage_gb:
            return StorageAllocationPlan(
                is_valid=True,
                boot_volume_size_gb=candidate_size,
                vpu_per_gb=cls.BALANCED_VPU,
                remaining_after_allocation_gb=remaining_free_storage_gb - candidate_size,
            )

        # If candidate size does not fit, try compact minimum 47 GB
        if cls.MIN_SAFE_SIZE_GB <= remaining_free_storage_gb:
            logger.info(
                f"Requested boot volume {candidate_size} GB exceeds remaining {remaining_free_storage_gb} GB, "
                f"falling back to compact {cls.MIN_SAFE_SIZE_GB} GB."
            )
            return StorageAllocationPlan(
                is_valid=True,
                boot_volume_size_gb=cls.MIN_SAFE_SIZE_GB,
                vpu_per_gb=cls.BALANCED_VPU,
                remaining_after_allocation_gb=remaining_free_storage_gb - cls.MIN_SAFE_SIZE_GB,
            )

        # Insufficient storage in free allowance
        return StorageAllocationPlan(
            is_valid=False,
            boot_volume_size_gb=0,
            vpu_per_gb=cls.BALANCED_VPU,
            remaining_after_allocation_gb=remaining_free_storage_gb,
            rejection_reason=(
                f"Insufficient remaining free storage ({remaining_free_storage_gb} GB available). "
                f"Minimum required is {cls.MIN_SAFE_SIZE_GB} GB to stay within the 200 GB Always Free limit."
            ),
        )
