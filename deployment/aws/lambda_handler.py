"""AWS Lambda entry point: one hunter cycle, then switch off once enough instances exist."""

import logging
import os
from types import SimpleNamespace

import boto3

from free_tier_hunter.account_inventory import AccountInventoryCollector
from free_tier_hunter.capacity_monitor import CapacityMonitor
from free_tier_hunter.config import HunterConfig
from free_tier_hunter.notifier import Notifier
from free_tier_hunter.oci_client import OciClientManager
from free_tier_hunter.quota_calculator import QuotaCalculator

logger = logging.getLogger("free_tier_hunter.lambda")
logging.getLogger().setLevel(logging.INFO)

# shortcut: overrides the 4/24 limits still hard-coded in the package, because Oracle's docs now say 2/12.
# Move these into the package if the local watcher should use them too.
QuotaCalculator.A1_MAX_OCPUS = float(os.environ.get("A1_OCPUS", "2"))
QuotaCalculator.A1_MAX_RAM_GB = float(os.environ.get("A1_RAM_GB", "12"))

PREFIX = os.environ.get("INSTANCE_PREFIX", "viaf-reforger-free-")
DESIRED = int(os.environ.get("DESIRED_INSTANCES", "1"))


def count_ready(inventory) -> int:
    # PROVISIONING can still fail, so it doesn't count yet. Stopped instances do, so they aren't replaced.
    return sum(i.lifecycle_state != "PROVISIONING" for i in inventory.existing_reforger_instances)


def build_monitor(watch_only: bool = False) -> CapacityMonitor:
    key = boto3.client("ssm").get_parameter(
        Name=os.environ["OCI_KEY_PARAMETER"], WithDecryption=True
    )["Parameter"]["Value"]
    manager = OciClientManager(
        region=os.environ["OCI_REGION"],
        custom_config={
            "user": os.environ["OCI_USER"],
            "fingerprint": os.environ["OCI_FINGERPRINT"],
            "tenancy": os.environ["OCI_TENANCY"],
            "region": os.environ["OCI_REGION"],
            "key_content": key,
        },
    )
    manager.initialize()
    config = HunterConfig(
        region=os.environ["OCI_REGION"],
        mode="WATCH_ONLY" if watch_only else "AUTO_PROVISION_FREE",
        auto_provision_enabled=not watch_only,
        experimental_arm64_emulation=True,
        instance_name_prefix=PREFIX,
        maximum_instances_created_by_this_tool=DESIRED,
        ssh_public_key=os.environ["SSH_PUBLIC_KEY"],
        enable_desktop_notifications=False,
        lock_file_path="/tmp/provisioning.lock",
        state_file_path="/tmp/state.json",
    )
    return CapacityMonitor(
        config=config,
        oci_manager=manager,
        dashboard=SimpleNamespace(render=lambda **_: None),  # terminal UI would only fill the logs
        notifier=Notifier(enable_desktop=False),
    )


def stop_if_done(inventory, events, sns, rule_name: str, topic_arn: str) -> bool:
    """Disables the schedule and sends the alert once the desired count is reached."""
    ready = count_ready(inventory)
    logger.info("Ready instances: %s of %s", ready, DESIRED)
    if ready < DESIRED:
        return False
    # Disable first: a failed alert must not leave the hunter running.
    events.disable_rule(Name=rule_name)
    names = ", ".join(i.display_name for i in inventory.existing_reforger_instances)
    sns.publish(
        TopicArn=topic_arn,
        Subject="Oracle instance ready, hunter stopped",
        Message=f"{ready} of {DESIRED} Oracle instance(s) ready: {names}. The AWS schedule is now disabled.",
    )
    return True


def handler(event, context):
    # {"watch_only": true} tests credentials and packaging without launching anything.
    monitor = build_monitor(watch_only=bool(event.get("watch_only")))
    result = monitor.run_single_cycle()
    inventory = AccountInventoryCollector(monitor.oci_manager).collect(name_prefix=PREFIX)
    stopped = stop_if_done(
        inventory,
        boto3.client("events"),
        boto3.client("sns"),
        os.environ["RULE_NAME"],
        os.environ["TOPIC_ARN"],
    )
    return {"verdict": result["verdict"], "stopped": stopped}
