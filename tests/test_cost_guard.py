"""
Unit tests for strict zero-cost budget invariants.
Covers Scenarios: 4, 15, 19
"""

import pytest
from pydantic import ValidationError
from free_tier_hunter.config import HunterConfig, OperatingMode, ConfigValidationError


def test_budget_invariant_strictly_zero():
    """Verify that any configuration specifying a monthly cost > 0 fails validation."""
    with pytest.raises((ConfigValidationError, ValidationError)):
        HunterConfig(maximum_monthly_cost=10.0)


def test_allow_paid_resources_must_be_false():
    """Verify that setting allow_paid_resources to True fails validation."""
    with pytest.raises((ConfigValidationError, ValidationError), match="allow_paid_resources must be False"):
        HunterConfig(allow_paid_resources=True)


def test_allow_account_upgrade_must_be_false():
    """Verify that setting allow_account_upgrade to True fails validation."""
    with pytest.raises((ConfigValidationError, ValidationError), match="allow_account_upgrade must be False"):
        HunterConfig(allow_account_upgrade=True)


def test_allow_uncertain_cost_must_be_false():
    """Verify that setting allow_uncertain_cost to True fails validation."""
    with pytest.raises((ConfigValidationError, ValidationError), match="allow_uncertain_cost must be False"):
        HunterConfig(allow_uncertain_cost=True)


def test_auto_provisioning_mode_coherence():
    """Verify mode and auto_provision_enabled flag coherence."""
    # AUTO_PROVISION_FREE without auto_provision_enabled=True must fail
    with pytest.raises((ConfigValidationError, ValidationError), match="mode is set to AUTO_PROVISION_FREE but auto_provision_enabled is False"):
        HunterConfig(mode=OperatingMode.AUTO_PROVISION_FREE, auto_provision_enabled=False)

    # auto_provision_enabled=True while mode is WATCH_ONLY must fail
    with pytest.raises((ConfigValidationError, ValidationError), match="auto_provision_enabled is true but mode is WATCH_ONLY"):
        HunterConfig(mode=OperatingMode.WATCH_ONLY, auto_provision_enabled=True)
