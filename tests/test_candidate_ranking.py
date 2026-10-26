"""
Unit tests for Candidate Evaluation and Priority Ranking.
Covers Scenarios: 1, 6
"""

import pytest
from free_tier_hunter.candidate_ranker import CandidateRanker
from free_tier_hunter.quota_calculator import RemainingAllowances


def test_scenario_1_and_ranking_priority():
    """Scenario 1: Evaluates and ranks candidates when allowances are full."""
    allowances = RemainingAllowances(
        remaining_a1_ocpus=4.0,
        remaining_a1_ram_gb=24.0,
        max_launchable_a1_ocpus=4.0,
        max_launchable_a1_ram_gb=24.0,
        remaining_e2_instances=2,
        total_storage_allowance_gb=200,
        used_storage_gb=0,
        remaining_storage_gb=200,
        can_launch_a1=True,
        can_launch_e2=True,
    )

    # When require_native_compatibility is True:
    # A1 is marked INCOMPATIBLE_FOR_PRODUCTION
    # E2 is marked INSUFFICIENT_CPU / INSUFFICIENT_RAM
    candidates = CandidateRanker.evaluate_and_rank_candidates(
        allowances=allowances,
        availability_domains=["AP-HYDERABAD-1-AD-1"],
        requested_boot_volume_gb=50,
        require_native_compatibility=True,
        allow_arm64_emulation=False,
    )

    assert len(candidates) >= 1
    # Both shapes are present
    shapes = [c.shape_name for c in candidates]
    assert "VM.Standard.A1.Flex" in shapes
    assert "VM.Standard.E2.1.Micro" in shapes

    # When experimental_arm64_emulation is True:
    emul_candidates = CandidateRanker.evaluate_and_rank_candidates(
        allowances=allowances,
        availability_domains=["AP-HYDERABAD-1-AD-1"],
        requested_boot_volume_gb=50,
        require_native_compatibility=True,
        allow_arm64_emulation=True,
    )
    a1_candidate = [c for c in emul_candidates if "A1" in c.shape_name][0]
    assert a1_candidate.is_launchable
    assert a1_candidate.verdict_status == "ELIGIBLE"
