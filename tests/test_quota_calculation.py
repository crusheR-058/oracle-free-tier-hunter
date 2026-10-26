"""
Unit tests for quota calculation and storage allowance tracking.
Covers Scenarios: 3, 5, 13, 14
"""

import pytest
from free_tier_hunter.account_inventory import InstanceInfo, TenancyInventory, VolumeInfo
from free_tier_hunter.quota_calculator import QuotaCalculator
from free_tier_hunter.storage_optimizer import StorageOptimizer


def test_scenario_3_quota_exceeded():
    """Scenario 3: A shape is labelled Always Free but exceeds remaining quota."""
    # Tenancy currently using all 4 A1 OCPUs and 24 GB RAM
    inv = TenancyInventory(
        tenancy_id="ocid1.tenancy.test",
        region="ap-hyderabad-1",
        active_instances=[
            InstanceInfo(
                id="inst-1",
                display_name="existing-a1",
                shape="VM.Standard.A1.Flex",
                lifecycle_state="RUNNING",
                availability_domain="AD-1",
                ocpus=4.0,
                memory_in_gbs=24.0,
                time_created="2026-01-01",
            )
        ],
        boot_volumes=[],
        block_volumes=[],
        used_a1_ocpus=4.0,
        used_a1_ram_gb=24.0,
        used_e2_count=0,
        used_storage_gb=50,
        existing_reforger_instances=[],
    )

    allowances = QuotaCalculator.calculate(inv)
    assert allowances.remaining_a1_ocpus == 0.0
    assert allowances.remaining_a1_ram_gb == 0.0
    assert not allowances.can_launch_a1
    assert allowances.can_launch_e2  # E2 Micro still available


def test_scenario_5_insufficient_storage():
    """Scenario 5: Candidate has insufficient storage (> 200 GB total allowance)."""
    # Tenancy already has 180 GB storage used
    inv = TenancyInventory(
        tenancy_id="ocid1.tenancy.test",
        region="ap-hyderabad-1",
        active_instances=[],
        boot_volumes=[],
        block_volumes=[],
        used_a1_ocpus=0.0,
        used_a1_ram_gb=0.0,
        used_e2_count=0,
        used_storage_gb=180,
        existing_reforger_instances=[],
    )

    allowances = QuotaCalculator.calculate(inv)
    assert allowances.remaining_storage_gb == 20  # 200 - 180 = 20 GB remaining

    # Minimum boot volume is 47 GB; 20 GB available is insufficient
    plan = StorageOptimizer.plan_boot_volume(
        requested_size_gb=50,
        remaining_free_storage_gb=allowances.remaining_storage_gb,
    )
    assert not plan.is_valid
    assert "Insufficient remaining free storage" in plan.rejection_reason


def test_scenario_14_existing_resources_consume_part_of_allocation():
    """Scenario 14: Existing resources consume part of the free allocation."""
    inv = TenancyInventory(
        tenancy_id="ocid1.tenancy.test",
        region="ap-hyderabad-1",
        active_instances=[
            InstanceInfo(
                id="inst-small-a1",
                display_name="small-a1",
                shape="VM.Standard.A1.Flex",
                lifecycle_state="RUNNING",
                availability_domain="AD-1",
                ocpus=1.0,
                memory_in_gbs=6.0,
                time_created="2026-01-01",
            )
        ],
        boot_volumes=[],
        block_volumes=[],
        used_a1_ocpus=1.0,
        used_a1_ram_gb=6.0,
        used_e2_count=0,
        used_storage_gb=47,
        existing_reforger_instances=[],
    )

    allowances = QuotaCalculator.calculate(inv)
    assert allowances.remaining_a1_ocpus == 3.0
    assert allowances.remaining_a1_ram_gb == 18.0
    assert allowances.max_launchable_a1_ocpus == 3.0
    assert allowances.max_launchable_a1_ram_gb == 18.0
    assert allowances.can_launch_a1
