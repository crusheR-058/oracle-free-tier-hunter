"""
Persistent State Store for Oracle Free-Tier Hunter.
Stores cycle history, active provisioned instances, and cooldown status.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("free_tier_hunter.state_store")


@dataclass
class ProvisioningRecord:
    timestamp: str
    candidate_id: str
    shape: str
    ad: str
    status: str
    details: str
    instance_id: Optional[str] = None


@dataclass
class HunterState:
    last_check_time: Optional[str] = None
    next_check_time: Optional[str] = None
    operating_mode: str = "WATCH_ONLY"
    last_verdict: str = "INITIALIZING"
    last_error: Optional[str] = None
    cooldown_until: Optional[str] = None

    # Provisioned instance tracking
    provisioned_instance_id: Optional[str] = None
    provisioned_instance_name: Optional[str] = None
    provisioned_instance_state: Optional[str] = None
    provisioned_public_ip: Optional[str] = None
    provisioned_at: Optional[str] = None

    # History
    history: List[Dict[str, Any]] = field(default_factory=list)


class StateStore:
    """Manages persistent reading and atomic writing of hunter state to state.json."""

    def __init__(self, state_file_path: str = "state.json"):
        self.path = Path(state_file_path)

    def load(self) -> HunterState:
        """Loads state from disk, or initializes defaults if not present."""
        if not self.path.exists():
            return HunterState()

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return HunterState(**data)
        except Exception as e:
            logger.warning(f"Failed to load state from {self.path}, initializing fresh state: {e}")
            return HunterState()

    def save(self, state: HunterState) -> None:
        """Atomically saves state to disk."""
        data = asdict(state)
        # Limit history to 50 most recent records
        if len(data.get("history", [])) > 50:
            data["history"] = data["history"][-50:]

        temp_path = self.path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            temp_path.replace(self.path)
        except Exception as e:
            logger.error(f"Failed to save state to {self.path}: {e}")
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

    def record_attempt(
        self,
        candidate_id: str,
        shape: str,
        ad: str,
        status: str,
        details: str,
        instance_id: Optional[str] = None,
    ) -> None:
        """Appends a provisioning attempt record to persistent state."""
        state = self.load()
        now_str = datetime.now(timezone.utc).isoformat()
        rec = ProvisioningRecord(
            timestamp=now_str,
            candidate_id=candidate_id,
            shape=shape,
            ad=ad,
            status=status,
            details=details,
            instance_id=instance_id,
        )
        state.history.append(asdict(rec))
        state.last_verdict = status
        if status in ["PROVISIONING_FAILED", "OUT_OF_HOST_CAPACITY"]:
            state.last_error = details
        self.save(state)
