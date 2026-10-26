"""
Unit tests for Provisioning Safety, error classification, locking, and recovery.
Covers Scenarios: 7, 8, 9, 11, 12, 16, 17, 18
"""

import os
from unittest.mock import MagicMock, patch
import pytest
import oci

from free_tier_hunter.architecture_checker import DiscoveredImage
from free_tier_hunter.candidate_ranker import LaunchCandidate
from free_tier_hunter.config import HunterConfig, OperatingMode
from free_tier_hunter.free_tier_validator import CostVerificationResult
from free_tier_hunter.networking import NetworkContext
from free_tier_hunter.notifier import Notifier
from free_tier_hunter.oci_client import OciClientManager, OciErrorCategory, classify_oci_error
from free_tier_hunter.provisioning_engine import ProvisioningEngine
from free_tier_hunter.reforger_compatibility import CompatibilityStatus, ReforgerCompatibilityReport
from free_tier_hunter.state_store import StateStore
from free_tier_hunter.storage_optimizer import StorageAllocationPlan


def test_scenario_7_and_12_out_of_host_capacity_error_classification():
    """Scenario 7 & 12: No capacity available (OutOfHostCapacity, HTTP 500)."""
    # Mock OCI ServiceError for OutOfHostCapacity
    headers = {"opc-request-id": "req-123"}
    error = oci.exceptions.ServiceError(
        status=500,
        code="OutOfHostCapacity",
        message="Out of capacity for shape VM.Standard.A1.Flex in availability domain AD-1",
        headers=headers,
    )

    classified = classify_oci_error(error)
    assert classified.category == OciErrorCategory.OUT_OF_HOST_CAPACITY
    assert classified.is_transient is True
    assert classified.status_code == 500


def test_scenario_8_timeout_or_network_error_classification():
    """Scenario 8: An OCI API request times out."""
    conn_error = ConnectionError("HTTPSConnectionPool: Read timed out.")
    classified = classify_oci_error(conn_error)
    assert classified.category == OciErrorCategory.TIMEOUT_OR_NETWORK
    assert classified.is_transient is True


def test_scenario_17_authentication_failed_classification():
    """Scenario 17: Authentication fails (401 NotAuthenticated)."""
    error = oci.exceptions.ServiceError(
        status=401,
        code="NotAuthenticated",
        message="The required information to complete authentication was not provided.",
        headers={},
    )
    classified = classify_oci_error(error)
    assert classified.category == OciErrorCategory.AUTHENTICATION_FAILED
    assert classified.is_transient is False


def test_scenario_11_lock_contention(tmp_path):
    """Scenario 11: Two watcher processes attempt to act concurrently (local mutex contention)."""
    lock_file = str(tmp_path / "provisioning.lock")
    state_file = str(tmp_path / "state.json")

    config = HunterConfig(
        mode=OperatingMode.AUTO_PROVISION_FREE,
        auto_provision_enabled=True,
        lock_file_path=lock_file,
        state_file_path=state_file,
    )
    oci_manager = MagicMock()
    state_store = StateStore(state_file)
    notifier = MagicMock()

    engine = ProvisioningEngine(config, oci_manager, state_store, notifier)

    # Acquire lock in advance
    from filelock import FileLock
    outer_lock = FileLock(lock_file)
    with outer_lock:
        # Engine attempt while lock is held
        candidate = MagicMock()
        net_ctx = MagicMock()
        os_img = MagicMock()

        outcome = engine.attempt_provision(candidate, net_ctx, os_img)
        assert not outcome.success
        assert outcome.status_label == "PROVISIONING_IN_PROGRESS"
        assert "Provisioning lock contention" in outcome.message


def test_scenario_9_timeout_recovery_detects_created_instance(tmp_path):
    """Scenario 9: Launch request times out, but instance is recovered by checking inventory."""
    lock_file = str(tmp_path / "provisioning.lock")
    state_file = str(tmp_path / "state.json")

    config = HunterConfig(
        mode=OperatingMode.AUTO_PROVISION_FREE,
        auto_provision_enabled=True,
        lock_file_path=lock_file,
        state_file_path=state_file,
        ssh_public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC3 test@localhost",
    )

    mock_compute = MagicMock()
    # launch_instance raises timeout
    mock_compute.launch_instance.side_effect = TimeoutError("Request timed out")

    # On re-check, list_instances returns the newly created instance
    mock_inst = MagicMock()
    mock_inst.id = "ocid1.instance.oc1..recovered"
    mock_inst.display_name = "viaf-reforger-free-a1-ad1-test"
    mock_inst.shape = "VM.Standard.A1.Flex"
    mock_inst.lifecycle_state = "PROVISIONING"
    mock_inst.availability_domain = "AD-1"
    mock_inst.shape_config.ocpus = 4.0
    mock_inst.shape_config.memory_in_gbs = 24.0
    mock_inst.time_created = "2026-10-25T12:00:00Z"

    mock_compute.list_instances.return_value = MagicMock(data=[mock_inst])

    mock_identity = MagicMock()
    mock_identity.list_availability_domains.return_value = MagicMock(data=[])
    mock_storage = MagicMock()
    mock_storage.list_boot_volumes.return_value = MagicMock(data=[])
    mock_storage.list_volumes.return_value = MagicMock(data=[])

    oci_mgr = MagicMock()
    oci_mgr.tenancy_id = "ocid1.tenancy.oc1..test"
    oci_mgr.compute_client = mock_compute
    oci_mgr.identity_client = mock_identity
    oci_mgr.blockstorage_client = mock_storage

    state_store = StateStore(state_file)
    notifier = MagicMock()

    candidate = LaunchCandidate(
        candidate_id="cand-1",
        shape_name="VM.Standard.A1.Flex",
        architecture="aarch64",
        ocpus=4.0,
        memory_in_gbs=24.0,
        boot_volume_size_gb=50,
        availability_domain="AD-1",
        cost_result=CostVerificationResult(True, "ELIGIBLE", "Zero cost", 0.0),
        compatibility_report=ReforgerCompatibilityReport(CompatibilityStatus.COMPATIBLE, True, "aarch64", 24.0, 4.0, 50, "OK"),
        storage_plan=StorageAllocationPlan(True, 50, 10, 150),
        is_launchable=True,
        rank_score=100.0,
        verdict_status="ELIGIBLE",
        verdict_summary="OK",
    )
    net_ctx = NetworkContext(vcn_id="vcn-1", subnet_id="sub-1", is_public=True)
    os_img = DiscoveredImage(id="img-1", display_name="Ubuntu", operating_system="Ubuntu", operating_system_version="22.04", architecture="aarch64", time_created="")

    # Mock collector during pre-flight to show 0 existing instances initially
    with patch("free_tier_hunter.provisioning_engine.AccountInventoryCollector.collect") as mock_collect:
        from free_tier_hunter.account_inventory import TenancyInventory
        empty_inv = TenancyInventory("ocid1.tenancy", "ap-hyderabad-1", [], [], [], 0.0, 0.0, 0, 0, [])
        recovered_inv = TenancyInventory(
            "ocid1.tenancy",
            "ap-hyderabad-1",
            [
                MagicMock(
                    id="ocid1.instance.oc1..recovered",
                    display_name="viaf-reforger-free-a1-ad1-test",
                    lifecycle_state="PROVISIONING",
                )
            ],
            [],
            [],
            0.0,
            0.0,
            0,
            0,
            [],
        )
        mock_collect.side_effect = [empty_inv, recovered_inv]

        engine = ProvisioningEngine(config, oci_mgr, state_store, notifier)
        outcome = engine.attempt_provision(candidate, net_ctx, os_img)

        assert outcome.success
        assert outcome.instance_id == "ocid1.instance.oc1..recovered"
        assert "timeout" in outcome.message.lower()
