"""
OCI Python SDK Client Wrapper with error classification and credential safety.
"""

from dataclasses import dataclass
from enum import Enum
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import oci

logger = logging.getLogger("free_tier_hunter.oci_client")


class OciErrorCategory(str, Enum):
    OUT_OF_HOST_CAPACITY = "OUT_OF_HOST_CAPACITY"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    RATE_LIMITED = "RATE_LIMITED"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    TIMEOUT_OR_NETWORK = "TIMEOUT_OR_NETWORK"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


@dataclass
class ClassifiedOciError:
    category: OciErrorCategory
    status_code: int
    code: str
    message: str
    is_transient: bool


def classify_oci_error(error: Exception) -> ClassifiedOciError:
    """Classifies an OCI ServiceError or network exception into a structured error category."""
    if isinstance(error, oci.exceptions.ServiceError):
        status = error.status
        code = str(error.code or "")
        message = str(error.message or "")

        # Capacity errors in OCI (HTTP 500 with OutOfHostCapacity or InternalError referencing capacity)
        if status == 500 and ("OutOfHostCapacity" in code or "capacity" in message.lower()):
            return ClassifiedOciError(
                category=OciErrorCategory.OUT_OF_HOST_CAPACITY,
                status_code=status,
                code=code,
                message=message,
                is_transient=True,
            )

        # Quota and service limits
        if status == 400 and ("LimitExceeded" in code or "QuotaExceeded" in code or "limit" in message.lower()):
            return ClassifiedOciError(
                category=OciErrorCategory.QUOTA_EXCEEDED,
                status_code=status,
                code=code,
                message=message,
                is_transient=False,
            )

        # Rate limits
        if status == 429 or "TooManyRequests" in code:
            return ClassifiedOciError(
                category=OciErrorCategory.RATE_LIMITED,
                status_code=status,
                code=code,
                message=message,
                is_transient=True,
            )

        # Authentication / Authorization
        if status == 401 or "NotAuthenticated" in code:
            return ClassifiedOciError(
                category=OciErrorCategory.AUTHENTICATION_FAILED,
                status_code=status,
                code=code,
                message="OCI API Authentication failed. Check your API key, user OCID, or fingerprint.",
                is_transient=False,
            )

        if status == 404 or "NotAuthorizedOrNotFound" in code or status == 403:
            return ClassifiedOciError(
                category=OciErrorCategory.NOT_AUTHORIZED,
                status_code=status,
                code=code,
                message=message,
                is_transient=False,
            )

        return ClassifiedOciError(
            category=OciErrorCategory.UNKNOWN_ERROR,
            status_code=status,
            code=code,
            message=message,
            is_transient=(status >= 500),
        )

    # Network, connection, or timeout errors
    msg = str(error)
    return ClassifiedOciError(
        category=OciErrorCategory.TIMEOUT_OR_NETWORK,
        status_code=0,
        code="NetworkError",
        message=f"Network or timeout communication error: {msg}",
        is_transient=True,
    )


class OciClientManager:
    """Manages OCI SDK clients, config loading, and authenticated API operations."""

    def __init__(
        self,
        config_file: str = "~/.oci/config",
        profile_name: str = "DEFAULT",
        region: Optional[str] = None,
        custom_config: Optional[Dict[str, Any]] = None,
        compute_client: Optional[Any] = None,
        blockstorage_client: Optional[Any] = None,
        network_client: Optional[Any] = None,
        limits_client: Optional[Any] = None,
        identity_client: Optional[Any] = None,
    ):
        self.config_file = config_file
        self.profile_name = profile_name
        self.target_region = region
        self._custom_config = custom_config

        # Allow injected clients for testing without real credentials
        self._compute_client = compute_client
        self._blockstorage_client = blockstorage_client
        self._network_client = network_client
        self._limits_client = limits_client
        self._identity_client = identity_client
        self._config: Optional[Dict[str, Any]] = None

    def initialize(self) -> None:
        """Loads OCI configuration and verifies credential files."""
        if self._custom_config:
            self._config = dict(self._custom_config)
        elif self._config is None:
            config_path = Path(os.path.expanduser(self.config_file))
            if not config_path.exists():
                raise FileNotFoundError(
                    f"OCI config file not found at {config_path}. "
                    "Run 'oci setup config' or create the file with user, fingerprint, key_file, and tenancy OCIDs."
                )
            try:
                self._config = oci.config.from_file(
                    file_location=str(config_path),
                    profile_name=self.profile_name,
                )
            except Exception as e:
                raise ValueError(f"Failed to load OCI config profile '{self.profile_name}': {e}")

        # Override region if target_region was specified
        if self.target_region and self._config:
            self._config["region"] = self.target_region

        # Verify key_file exists
        key_file = self._config.get("key_file")
        if key_file:
            key_path = Path(os.path.expanduser(key_file))
            if not key_path.exists():
                raise FileNotFoundError(
                    f"OCI API private key file specified in config was not found: {key_path}"
                )

        logger.info(
            f"OCI initialized successfully for tenancy OCID={self.tenancy_id[:15]}... in region={self.region}"
        )

    @property
    def config(self) -> Dict[str, Any]:
        if self._config is None:
            self.initialize()
        return self._config  # type: ignore

    @property
    def tenancy_id(self) -> str:
        return self.config.get("tenancy", "")

    @property
    def region(self) -> str:
        return self.config.get("region", self.target_region or "ap-hyderabad-1")

    @property
    def compute_client(self) -> oci.core.ComputeClient:
        if self._compute_client is None:
            self._compute_client = oci.core.ComputeClient(self.config)
        return self._compute_client

    @property
    def blockstorage_client(self) -> oci.core.BlockstorageClient:
        if self._blockstorage_client is None:
            self._blockstorage_client = oci.core.BlockstorageClient(self.config)
        return self._blockstorage_client

    @property
    def network_client(self) -> oci.core.VirtualNetworkClient:
        if self._network_client is None:
            self._network_client = oci.core.VirtualNetworkClient(self.config)
        return self._network_client

    @property
    def limits_client(self) -> oci.limits.LimitsClient:
        if self._limits_client is None:
            self._limits_client = oci.limits.LimitsClient(self.config)
        return self._limits_client

    @property
    def identity_client(self) -> oci.identity.IdentityClient:
        if self._identity_client is None:
            self._identity_client = oci.identity.IdentityClient(self.config)
        return self._identity_client
