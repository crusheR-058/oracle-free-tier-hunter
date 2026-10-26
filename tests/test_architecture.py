"""
Unit tests for Architecture and Arma Reforger Compatibility.
Covers Scenarios: 6, 20
"""

import pytest
from free_tier_hunter.reforger_compatibility import (
    ReforgerCompatibilityEngine,
    CompatibilityStatus,
)


def test_scenario_6_arm64_incompatible_with_native_reforger():
    """Scenario 6: An ARM64 candidate is incompatible with native Reforger server binary."""
    report = ReforgerCompatibilityEngine.evaluate_candidate(
        architecture="aarch64",
        ram_gb=24.0,
        ocpus=4.0,
        storage_gb=50,
        os_type="Linux",
        allow_arm64_emulation=False,
    )
    assert not report.is_compatible
    assert report.status == CompatibilityStatus.INCOMPATIBLE_FOR_PRODUCTION
    assert "Bohemia Interactive does NOT supply native ARM64 Linux binaries" in report.details


def test_arm64_experimental_emulation_allowed():
    """Test ARM64 evaluation when experimental emulation flag is explicitly enabled."""
    report = ReforgerCompatibilityEngine.evaluate_candidate(
        architecture="aarch64",
        ram_gb=24.0,
        ocpus=4.0,
        storage_gb=50,
        os_type="Linux",
        allow_arm64_emulation=True,
    )
    assert report.is_compatible
    assert report.status == CompatibilityStatus.COMPATIBLE
    assert "Box64 emulation" in report.details


def test_e2_micro_insufficient_ram_and_cpu():
    """Verify E2.Micro (1/8 OCPU, 1 GB RAM) fails for insufficient RAM and CPU."""
    report = ReforgerCompatibilityEngine.evaluate_candidate(
        architecture="x86_64",
        ram_gb=1.0,
        ocpus=0.125,
        storage_gb=50,
        os_type="Linux",
    )
    assert not report.is_compatible
    assert report.status in [CompatibilityStatus.INSUFFICIENT_CPU, CompatibilityStatus.INSUFFICIENT_RAM]


def test_scenario_20_incompatible_os_or_server_requirements():
    """Scenario 20: Non-Linux OS or invalid requirements."""
    report = ReforgerCompatibilityEngine.evaluate_candidate(
        architecture="x86_64",
        ram_gb=16.0,
        ocpus=2.0,
        storage_gb=50,
        os_type="Windows Server 2022",
    )
    assert not report.is_compatible
    assert report.status == CompatibilityStatus.INCOMPATIBLE_OS
