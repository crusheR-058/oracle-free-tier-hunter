"""
Always Free Quota & Remaining Allowance Calculator.
"""

from dataclasses import dataclass
import logging
from typing import Any, Optional
from .account_inventory import TenancyInventory
from .free_tier_validator import ALWAYS_FREE_STORAGE_GB_TOTAL

logger = logging.getLogger("free_tier_hunter.quota_calculator")


@dataclass
class RemainingAllowances:
    # Ampere A1
    remaining_a1_ocpus: float
    remaining_a1_ram_gb: float
    max_launchable_a1_ocpus: float
    max_launchable_a1_ram_gb: float

    # AMD E2 Micro
    remaining_e2_instances: int

    # Block Storage
    total_storage_allowance_gb: int
    used_storage_gb: int
    remaining_storage_gb: int

    # Summaries
    can_launch_a1: bool
    can_launch_e2: bool


class QuotaCalculator:
    """Calculates available headroom within Always Free limits."""

    A1_MAX_OCPUS: float = 4.0
    A1_MAX_RAM_GB: float = 24.0
    E2_MAX_INSTANCES: int = 2
    MAX_STORAGE_GB: int = ALWAYS_FREE_STORAGE_GB_TOTAL

    @classmethod
    def calculate(cls, inventory: TenancyInventory) -> RemainingAllowances:
        rem_a1_ocpus = max(0.0, cls.A1_MAX_OCPUS - inventory.used_a1_ocpus)
        rem_a1_ram = max(0.0, cls.A1_MAX_RAM_GB - inventory.used_a1_ram_gb)
        rem_e2_inst = max(0, cls.E2_MAX_INSTANCES - inventory.used_e2_count)
        rem_storage = max(0, cls.MAX_STORAGE_GB - inventory.used_storage_gb)

        # Minimum required to launch an A1 instance is 1 OCPU and 1 GB RAM
        can_a1 = (rem_a1_ocpus >= 1.0) and (rem_a1_ram >= 1.0) and (rem_storage >= 47)
        can_e2 = (rem_e2_inst >= 1) and (rem_storage >= 47)

        # Truncate floating values to safe whole or half units
        launchable_a1_ocpus = float(int(rem_a1_ocpus))
        launchable_a1_ram = float(int(rem_a1_ram))

        return RemainingAllowances(
            remaining_a1_ocpus=rem_a1_ocpus,
            remaining_a1_ram_gb=rem_a1_ram,
            max_launchable_a1_ocpus=launchable_a1_ocpus,
            max_launchable_a1_ram_gb=launchable_a1_ram,
            remaining_e2_instances=rem_e2_inst,
            total_storage_allowance_gb=cls.MAX_STORAGE_GB,
            used_storage_gb=inventory.used_storage_gb,
            remaining_storage_gb=rem_storage,
            can_launch_a1=can_a1,
            can_launch_e2=can_e2,
        )
