"""
Idempotency, instance naming, and duplicate-prevention engine.
"""

import hashlib
import time
from typing import List, Optional
import uuid
from .account_inventory import InstanceInfo

IDEMPOTENCY_NAMESPACE = uuid.UUID("35ec8b06-27f1-4701-9ea9-0e2b301196ef")


class IdempotencyEngine:
    """Ensures instance provisioning requests are strictly idempotent and cannot generate duplicate instances."""

    @classmethod
    def generate_retry_token(cls, candidate_id: str, tenancy_id: str, attempt_epoch_bucket: Optional[int] = None) -> str:
        """
        Generates an OCI-compliant opc-retry-token (UUID string).
        Using a 1-hour bucket ensures that if the process restarts within an hour,
        it uses the exact same retry token, allowing OCI to return the existing instance
        rather than launching a second one.
        """
        bucket = attempt_epoch_bucket or int(time.time() // 3600)
        seed_data = f"{tenancy_id}:{candidate_id}:{bucket}"
        return str(uuid.uuid5(IDEMPOTENCY_NAMESPACE, seed_data))

    @classmethod
    def generate_instance_name(cls, prefix: str, shape: str, ad: str) -> str:
        """
        Generates a clean, deterministic, collision-resistant instance display name.
        Example: viaf-reforger-free-a1-ad1-a9f2
        """
        shape_short = "a1" if "A1" in shape else "e2"
        # Extract short AD name (e.g. AD-1 from AP-HYDERABAD-1-AD-1)
        ad_short = ad.split("-")[-1].lower() if "-" in ad else ad[-3:].lower()
        hash_suffix = hashlib.sha256(f"{prefix}:{shape}:{ad}".encode("utf-8")).hexdigest()[:6]
        return f"{prefix}{shape_short}-{ad_short}-{hash_suffix}"

    @classmethod
    def find_existing_deployment(
        cls,
        existing_instances: List[InstanceInfo],
        prefix: str = "viaf-reforger-free-",
    ) -> Optional[InstanceInfo]:
        """
        Inspects existing instances in the tenancy. Returns an existing non-terminated
        reforger instance if one is already running or provisioning.
        """
        for inst in existing_instances:
            if inst.display_name.startswith(prefix):
                state = inst.lifecycle_state.upper()
                if state in ["RUNNING", "PROVISIONING", "STARTING"]:
                    return inst
        return None
