"""
Candidate Resource Ranker & Free-Tier Capacity Optimizer.
Ranks candidates based on zero-cost, native compatibility, and maximum capacity.
"""

from dataclasses import dataclass
from enum import Enum
import logging
from typing import List, Optional
from .free_tier_validator import FreeTierValidator, CostVerificationResult
from .quota_calculator import RemainingAllowances
from .reforger_compatibility import ReforgerCompatibilityEngine, CompatibilityStatus, ReforgerCompatibilityReport
from .storage_optimizer import StorageOptimizer, StorageAllocationPlan

logger = logging.getLogger("free_tier_hunter.candidate_ranker")


@dataclass
class LaunchCandidate:
    candidate_id: str
    shape_name: str
    architecture: str
    ocpus: float
    memory_in_gbs: float
    boot_volume_size_gb: int
    availability_domain: str

    # Verification Reports
    cost_result: CostVerificationResult
    compatibility_report: ReforgerCompatibilityReport
    storage_plan: StorageAllocationPlan

    # Overall Verdict
    is_launchable: bool
    rank_score: float
    verdict_status: str  # "ELIGIBLE", "INCOMPATIBLE_ARCHITECTURE", "INSUFFICIENT_RAM", "NO_CAPACITY", "COST_UNCERTAIN", "PAID_RESOURCE_BLOCKED"
    verdict_summary: str


class CandidateRanker:
    """Ranks and optimizes candidate instance configurations according to strict zero-cost and game workload priorities."""

    @classmethod
    def evaluate_and_rank_candidates(
        cls,
        allowances: RemainingAllowances,
        availability_domains: List[str],
        requested_boot_volume_gb: int = 50,
        require_native_compatibility: bool = True,
        allow_arm64_emulation: bool = False,
    ) -> List[LaunchCandidate]:
        candidates: List[LaunchCandidate] = []

        used_a1_ocpus = max(0.0, 4.0 - allowances.remaining_a1_ocpus)
        used_a1_ram = max(0.0, 24.0 - allowances.remaining_a1_ram_gb)

        for ad in availability_domains:
            # -------------------------------------------------------------
            # Option A: Maximum Free Ampere A1.Flex (4 OCPU / 24 GB RAM)
            # -------------------------------------------------------------
            if allowances.can_launch_a1:
                target_ocpus = min(4.0, allowances.max_launchable_a1_ocpus)
                target_ram = min(24.0, allowances.max_launchable_a1_ram_gb)
                storage_plan = StorageOptimizer.plan_boot_volume(
                    requested_boot_volume_gb,
                    allowances.remaining_storage_gb,
                )

                cost_res = FreeTierValidator.validate_instance_configuration(
                    shape="VM.Standard.A1.Flex",
                    ocpus=target_ocpus,
                    memory_in_gbs=target_ram,
                    boot_volume_size_gb=storage_plan.boot_volume_size_gb,
                    tenancy_used_a1_ocpus=used_a1_ocpus,
                    tenancy_used_a1_ram=used_a1_ram,
                    tenancy_used_storage_gb=allowances.used_storage_gb,
                )

                compat_rep = ReforgerCompatibilityEngine.evaluate_candidate(
                    architecture="aarch64",
                    ram_gb=target_ram,
                    ocpus=target_ocpus,
                    storage_gb=storage_plan.boot_volume_size_gb,
                    allow_arm64_emulation=allow_arm64_emulation,
                )

                # Determine launchability
                is_launchable = (
                    cost_res.is_verified_zero_cost
                    and storage_plan.is_valid
                    and (compat_rep.is_compatible if require_native_compatibility else True)
                )

                # Scoring: RAM prioritized (10 pts per GB) + CPU (20 pts per core) - penalties for incompatibility
                score = (target_ram * 10.0) + (target_ocpus * 20.0)
                if not compat_rep.is_compatible:
                    score -= 500.0
                if not cost_res.is_verified_zero_cost:
                    score -= 10000.0

                verdict_status = "ELIGIBLE" if is_launchable else compat_rep.status.value

                candidates.append(
                    LaunchCandidate(
                        candidate_id=f"a1-max-{ad}",
                        shape_name="VM.Standard.A1.Flex",
                        architecture="aarch64",
                        ocpus=target_ocpus,
                        memory_in_gbs=target_ram,
                        boot_volume_size_gb=storage_plan.boot_volume_size_gb,
                        availability_domain=ad,
                        cost_result=cost_res,
                        compatibility_report=compat_rep,
                        storage_plan=storage_plan,
                        is_launchable=is_launchable,
                        rank_score=score,
                        verdict_status=verdict_status,
                        verdict_summary=(
                            f"Ampere A1 Flex ({target_ocpus:.0f} OCPU, {target_ram:.0f} GB RAM, {storage_plan.boot_volume_size_gb} GB disk): "
                            f"{compat_rep.details}"
                        ),
                    )
                )

            # -------------------------------------------------------------
            # Option B: AMD E2.1.Micro (x86_64, 1/8 OCPU, 1 GB RAM)
            # -------------------------------------------------------------
            if allowances.can_launch_e2:
                storage_plan_e2 = StorageOptimizer.plan_boot_volume(
                    requested_boot_volume_gb,
                    allowances.remaining_storage_gb,
                )

                cost_res_e2 = FreeTierValidator.validate_instance_configuration(
                    shape="VM.Standard.E2.1.Micro",
                    ocpus=0.125,
                    memory_in_gbs=1.0,
                    boot_volume_size_gb=storage_plan_e2.boot_volume_size_gb,
                    tenancy_used_storage_gb=allowances.used_storage_gb,
                )

                compat_rep_e2 = ReforgerCompatibilityEngine.evaluate_candidate(
                    architecture="x86_64",
                    ram_gb=1.0,
                    ocpus=0.125,
                    storage_gb=storage_plan_e2.boot_volume_size_gb,
                )

                is_launchable_e2 = (
                    cost_res_e2.is_verified_zero_cost
                    and storage_plan_e2.is_valid
                    and (compat_rep_e2.is_compatible if require_native_compatibility else True)
                )

                score_e2 = (1.0 * 10.0) + (0.125 * 20.0)
                if not compat_rep_e2.is_compatible:
                    score_e2 -= 500.0

                candidates.append(
                    LaunchCandidate(
                        candidate_id=f"e2-micro-{ad}",
                        shape_name="VM.Standard.E2.1.Micro",
                        architecture="x86_64",
                        ocpus=0.125,
                        memory_in_gbs=1.0,
                        boot_volume_size_gb=storage_plan_e2.boot_volume_size_gb,
                        availability_domain=ad,
                        cost_result=cost_res_e2,
                        compatibility_report=compat_rep_e2,
                        storage_plan=storage_plan_e2,
                        is_launchable=is_launchable_e2,
                        rank_score=score_e2,
                        verdict_status=compat_rep_e2.status.value,
                        verdict_summary=(
                            f"AMD E2.1.Micro (0.125 OCPU, 1 GB RAM): {compat_rep_e2.details}"
                        ),
                    )
                )

        # Sort descending by rank score
        candidates.sort(key=lambda c: c.rank_score, reverse=True)
        return candidates
