"""Stop logic and the 2 OCPU / 12 GB request used by the AWS Lambda deployment."""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

from free_tier_hunter.candidate_ranker import CandidateRanker
from free_tier_hunter.quota_calculator import QuotaCalculator


@pytest.fixture
def handler_module(monkeypatch):
    monkeypatch.setitem(sys.modules, "boto3", ModuleType("boto3"))
    monkeypatch.setattr(QuotaCalculator, "A1_MAX_OCPUS", QuotaCalculator.A1_MAX_OCPUS)
    monkeypatch.setattr(QuotaCalculator, "A1_MAX_RAM_GB", QuotaCalculator.A1_MAX_RAM_GB)
    path = Path(__file__).parent.parent / "deployment" / "aws" / "lambda_handler.py"
    spec = importlib.util.spec_from_file_location("lambda_handler", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inventory(*states):
    instances = [SimpleNamespace(lifecycle_state=s, display_name=f"i{n}") for n, s in enumerate(states)]
    return SimpleNamespace(
        existing_reforger_instances=instances,
        used_a1_ocpus=0.0,
        used_a1_ram_gb=0.0,
        used_e2_count=0,
        used_storage_gb=0,
    )


@pytest.mark.parametrize(
    "states, expected",
    [
        ((), False),
        (("PROVISIONING",), False),
        (("RUNNING",), True),
        (("STOPPED",), True),
    ],
)
def test_stops_only_when_desired_count_is_ready(handler_module, states, expected):
    events, sns = MagicMock(), MagicMock()
    stopped = handler_module.stop_if_done(inventory(*states), events, sns, "rule", "topic")
    assert stopped is expected
    assert events.disable_rule.called is expected
    assert sns.publish.called is expected


def test_schedule_is_disabled_even_if_the_alert_fails(handler_module):
    events, sns = MagicMock(), MagicMock()
    sns.publish.side_effect = RuntimeError("alert failed")
    with pytest.raises(RuntimeError):
        handler_module.stop_if_done(inventory("RUNNING"), events, sns, "rule", "topic")
    events.disable_rule.assert_called_once_with(Name="rule")


def test_requests_2_ocpu_12_gb_and_it_stays_launchable(handler_module):
    candidates = CandidateRanker.evaluate_and_rank_candidates(
        allowances=QuotaCalculator.calculate(inventory()),
        availability_domains=["AD-1"],
        requested_boot_volume_gb=50,
        require_native_compatibility=True,
        allow_arm64_emulation=True,
    )
    best = next(c for c in candidates if c.is_launchable)
    assert (best.shape_name, best.ocpus, best.memory_in_gbs) == ("VM.Standard.A1.Flex", 2.0, 12.0)
