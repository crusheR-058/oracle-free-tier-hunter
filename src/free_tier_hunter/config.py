"""
Configuration models and fail-closed validation for Oracle Free-Tier Hunter.
Strictly guarantees ₹0 monthly budget and prevents unauthorized resource creation.
"""

from enum import Enum
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
import yaml

logger = logging.getLogger("free_tier_hunter.config")


class OperatingMode(str, Enum):
    WATCH_ONLY = "WATCH_ONLY"
    AUTO_PROVISION_FREE = "AUTO_PROVISION_FREE"
    GAME_SERVER_DEPLOYMENT = "GAME_SERVER_DEPLOYMENT"


class HunterConfig(BaseModel):
    # OCI Tenancy & Connection
    region: str = Field(default="ap-hyderabad-1", description="OCI Region identifier")
    oci_config_file: str = Field(default="~/.oci/config", description="Path to OCI config file")
    oci_profile: str = Field(default="DEFAULT", description="OCI profile name")
    compartment_id: Optional[str] = Field(default=None, description="Target compartment OCID (defaults to tenancy OCID)")

    # Operating Mode
    mode: OperatingMode = Field(default=OperatingMode.WATCH_ONLY, description="Operating mode")
    auto_provision_enabled: bool = Field(default=False, description="Master auto-provisioning toggle")
    poll_interval_minutes: int = Field(default=15, ge=1, le=1440, description="Polling interval in minutes")
    backoff_factor: float = Field(default=1.5, ge=1.0, le=5.0, description="Exponential backoff factor")
    max_backoff_minutes: int = Field(default=60, ge=1, le=720, description="Max backoff interval in minutes")
    jitter_ratio: float = Field(default=0.2, ge=0.0, le=0.5, description="Random jitter fraction")

    # Strict Zero-Cost Guards (Budget is strictly ₹0)
    maximum_monthly_cost: float = Field(default=0.0, ge=0.0, le=0.0, description="Maximum monthly cost (strictly 0)")
    allow_paid_resources: bool = Field(default=False, description="Disallow paid resources")
    allow_account_upgrade: bool = Field(default=False, description="Disallow account billing upgrade")
    allow_automatic_termination: bool = Field(default=False, description="Disallow automatic instance termination")
    allow_unverified_architecture: bool = Field(default=False, description="Disallow unverified architecture")
    allow_unverified_free_eligibility: bool = Field(default=False, description="Disallow unverified free shapes")
    allow_uncertain_cost: bool = Field(default=False, description="Disallow uncertain costs")

    # Workload Requirements (Arma Reforger Dedicated Server)
    target_players: int = Field(default=8, ge=1, le=128, description="Target player count")
    preferred_os: str = Field(default="Ubuntu", description="Preferred OS distribution")
    preferred_os_version: str = Field(default="22.04", description="Preferred Ubuntu LTS version")
    preferred_architecture: str = Field(default="x86_64", description="Preferred CPU architecture")
    require_native_reforger_compatibility: bool = Field(default=True, description="Require official native binary support")
    experimental_arm64_emulation: bool = Field(default=False, description="Allow testing ARM64 with Box64 emulation")
    maximum_instances_created_by_this_tool: int = Field(default=1, ge=1, le=2, description="Max instances to provision")

    # Storage Quotas
    boot_volume_size_gb: int = Field(default=50, ge=47, le=200, description="Boot volume size in GB")
    total_allowed_block_storage_gb: int = Field(default=200, ge=50, le=200, description="Total tenancy block storage limit")

    # Lock and State Files
    lock_file_path: str = Field(default="provisioning.lock", description="Local filelock path")
    state_file_path: str = Field(default="state.json", description="Persistent state path")
    instance_name_prefix: str = Field(default="viaf-reforger-free-", description="Instance display name prefix")

    # SSH Keys
    ssh_public_key: Optional[str] = Field(default=None, description="Public SSH key content")
    ssh_public_key_path: Optional[str] = Field(default=None, description="Path to public SSH key")

    # Notification & Alert Settings (Strictly no Telegram)
    enable_desktop_notifications: bool = Field(default=True, description="Enable Windows desktop notifications")
    enable_email_notifications: bool = Field(default=False, description="Enable email notifications")
    notification_email: Optional[str] = Field(default=None, description="Destination email address")
    smtp_host: Optional[str] = Field(default=None, description="SMTP server host")
    smtp_port: int = Field(default=587, description="SMTP server port")
    smtp_user: Optional[str] = Field(default=None, description="SMTP username")
    smtp_password: Optional[str] = Field(default=None, description="SMTP password")
    smtp_from: Optional[str] = Field(default=None, description="Sender email address")

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_directory: str = Field(default="logs", description="Directory to store rotating logs")

    @field_validator("allow_paid_resources")
    @classmethod
    def validate_paid_resources(cls, v: bool) -> bool:
        if v is not False:
            raise ValueError("allow_paid_resources must be False for ₹0 Always Free tier operation.")
        return v

    @field_validator("allow_account_upgrade")
    @classmethod
    def validate_account_upgrade(cls, v: bool) -> bool:
        if v is not False:
            raise ValueError("allow_account_upgrade must be False to prevent accidental billable conversion.")
        return v

    @field_validator("allow_uncertain_cost")
    @classmethod
    def validate_uncertain_cost(cls, v: bool) -> bool:
        if v is not False:
            raise ValueError("allow_uncertain_cost must be False; all resources must be verified free.")
        return v

    @model_validator(mode="after")
    def validate_mode_and_toggles(self) -> "HunterConfig":
        if self.mode == OperatingMode.AUTO_PROVISION_FREE and not self.auto_provision_enabled:
            raise ValueError(
                "mode is set to AUTO_PROVISION_FREE but auto_provision_enabled is False. "
                "Set auto_provision_enabled: true to explicitly confirm auto-provisioning."
            )
        if self.auto_provision_enabled and self.mode == OperatingMode.WATCH_ONLY:
            raise ValueError(
                "auto_provision_enabled is true but mode is WATCH_ONLY. "
                "Inconsistent state: switch mode to AUTO_PROVISION_FREE or set auto_provision_enabled to false."
            )
        return self


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""
    pass


def load_config(config_path: str = "config.yaml") -> HunterConfig:
    """Loads and validates configuration from YAML file. Fails closed on error."""
    path = Path(config_path).expanduser().resolve()
    if not path.exists():
        raise ConfigValidationError(f"Configuration file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f) or {}
    except Exception as e:
        raise ConfigValidationError(f"Failed to parse YAML configuration: {e}")

    try:
        return HunterConfig(**raw_data)
    except Exception as e:
        raise ConfigValidationError(f"Configuration validation failed: {e}")
