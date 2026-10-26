"""
Unit tests for Free Tier validation and Always Free rules.
Covers Scenarios: 2, 4, 15, 19
"""

import pytest
from free_tier_hunter.free_tier_validator import (
    FreeTierValidator,
    ShapeFamily,
    ALWAYS_FREE_STORAGE_GB_TOTAL,
)


def test_scenario_2_visible_shape_not_always_free():
    """Scenario 2: A shape is visible but not Always Free eligible (e.g. E4.Flex, E2.1)."""
    paid_shapes = ["VM.Standard.E4.Flex", "VM.Standard.E2.1", "VM.Standard.E2.2", "VM.Standard.E5.Flex"]
    for shape in paid_shapes:
        assert not FreeTierValidator.is_shape_always_free(shape)
        result = FreeTierValidator.validate_instance_configuration(
            shape=shape,
            ocpus=2.0,
            memory_in_gbs=16.0,
            boot_volume_size_gb=50,
        )
        assert not result.is_verified_zero_cost
        assert result.status_label == "PAID_RESOURCE_BLOCKED"
        assert result.projected_monthly_cost_inr > 0


def test_scenario_15_paid_upgrade_blocked():
    """Scenario 15: A paid upgrade would be required (strictly blocked)."""
    # Attempting to request more than 4 OCPUs or 24 GB RAM on A1
    result = FreeTierValidator.validate_instance_configuration(
        shape="VM.Standard.A1.Flex",
        ocpus=8.0,
        memory_in_gbs=48.0,
        boot_volume_size_gb=50,
    )
    assert not result.is_verified_zero_cost
    assert result.status_label == "COST_UNCERTAIN"


def test_scenario_4_and_19_uncertain_cost_blocked():
    """Scenario 4 & 19: Candidate has uncertain projected cost / cannot be verified as zero."""
    # Negative or 0 OCPUs
    result_invalid_cpu = FreeTierValidator.validate_instance_configuration(
        shape="VM.Standard.A1.Flex",
        ocpus=0.0,
        memory_in_gbs=12.0,
        boot_volume_size_gb=50,
    )
    assert not result_invalid_cpu.is_verified_zero_cost
    assert result_invalid_cpu.status_label == "COST_UNCERTAIN"

    # Boot volume below OCI minimum (47 GB)
    result_invalid_disk = FreeTierValidator.validate_instance_configuration(
        shape="VM.Standard.A1.Flex",
        ocpus=2.0,
        memory_in_gbs=12.0,
        boot_volume_size_gb=20,
    )
    assert not result_invalid_disk.is_verified_zero_cost
    assert result_invalid_disk.status_label == "COST_UNCERTAIN"


def test_always_free_shapes_recognized():
    """Verify that only A1.Flex and E2.1.Micro are recognized as Always Free."""
    assert FreeTierValidator.is_shape_always_free("VM.Standard.A1.Flex")
    assert FreeTierValidator.is_shape_always_free("VM.Standard.E2.1.Micro")
    assert not FreeTierValidator.is_shape_always_free("VM.Standard2.1")
    assert not FreeTierValidator.is_shape_always_free("VM.GPU.A10.1")
