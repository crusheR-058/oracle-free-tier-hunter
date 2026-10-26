"""
Unit tests for Idempotency, collision resistance, and duplicate prevention.
Covers Scenarios: 10, 18
"""

import pytest
from free_tier_hunter.account_inventory import InstanceInfo
from free_tier_hunter.idempotency import IdempotencyEngine


def test_scenario_10_watcher_restarts_detects_existing_instance():
    """Scenario 10: The watcher restarts after an instance has already been created."""
    existing_instances = [
        InstanceInfo(
            id="ocid1.instance.oc1..alreadycreated",
            display_name="viaf-reforger-free-a1-ad1-9f2b",
            shape="VM.Standard.A1.Flex",
            lifecycle_state="RUNNING",
            availability_domain="AD-1",
            ocpus=4.0,
            memory_in_gbs=24.0,
            time_created="2026-10-25T12:00:00Z",
        )
    ]

    detected = IdempotencyEngine.find_existing_deployment(
        existing_instances=existing_instances,
        prefix="viaf-reforger-free-",
    )
    assert detected is not None
    assert detected.id == "ocid1.instance.oc1..alreadycreated"
    assert detected.lifecycle_state == "RUNNING"


def test_deterministic_instance_naming():
    """Verify instance naming is deterministic and collision-resistant."""
    name1 = IdempotencyEngine.generate_instance_name("viaf-reforger-free-", "VM.Standard.A1.Flex", "AD-1")
    name2 = IdempotencyEngine.generate_instance_name("viaf-reforger-free-", "VM.Standard.A1.Flex", "AD-1")
    assert name1 == name2
    assert name1.startswith("viaf-reforger-free-a1-")


def test_retry_token_reproducible_in_same_hour():
    """Verify opc-retry-token is deterministic within same hourly bucket."""
    t1 = IdempotencyEngine.generate_retry_token("cand-1", "tenancy-1", attempt_epoch_bucket=100)
    t2 = IdempotencyEngine.generate_retry_token("cand-1", "tenancy-1", attempt_epoch_bucket=100)
    assert t1 == t2

    # Different bucket produces different token
    t3 = IdempotencyEngine.generate_retry_token("cand-1", "tenancy-1", attempt_epoch_bucket=101)
    assert t1 != t3
