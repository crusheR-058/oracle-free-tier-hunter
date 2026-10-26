"""
Arma Reforger Dedicated Server Hardware & Architecture Compatibility Validator.
Based on official Bohemia Interactive documentation and SteamCMD release analysis.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CompatibilityStatus(str, Enum):
    COMPATIBLE = "COMPATIBLE"
    INCOMPATIBLE_ARCHITECTURE = "INCOMPATIBLE_ARCHITECTURE"
    INCOMPATIBLE_OS = "INCOMPATIBLE_OS"
    INSUFFICIENT_RAM = "INSUFFICIENT_RAM"
    INSUFFICIENT_CPU = "INSUFFICIENT_CPU"
    INSUFFICIENT_STORAGE = "INSUFFICIENT_STORAGE"
    INCOMPATIBLE_FOR_PRODUCTION = "INCOMPATIBLE_FOR_PRODUCTION"
    COMPATIBILITY_UNKNOWN = "COMPATIBILITY_UNKNOWN"


@dataclass
class ReforgerCompatibilityReport:
    status: CompatibilityStatus
    is_compatible: bool
    architecture: str
    ram_gb: float
    ocpus: float
    storage_gb: int
    details: str
    remedy: Optional[str] = None


class ReforgerCompatibilityEngine:
    """
    Evaluates instance candidates against official Bohemia Interactive Arma Reforger
    dedicated server specifications.
    
    Verified Technical Facts (Bohemia Interactive & SteamCMD App ID 1874900):
    1. Executable format: x86_64 Linux ELF binary ('ArmaReforgerServer').
    2. Native ARM64 (aarch64) Linux binaries: NONE provided by Bohemia.
    3. Minimum RAM requirement: 8 GB (idle server takes 3-4 GB; Enfusion spawns dynamic AI).
    4. Recommended RAM: 16 GB.
    5. Minimum CPU: At least 1.0 OCPU (2 vCPUs) with high single-thread clock.
       1/8 OCPU on E2.Micro causes extreme tick rate drops and server timeouts.
    6. Minimum disk footprint: ~30-40 GB for OS, SteamCMD, server files, and mission cache.
    """

    MIN_RAM_GB: float = 8.0
    RECOMMENDED_RAM_GB: float = 16.0
    MIN_OCPUS: float = 1.0
    MIN_STORAGE_GB: int = 45

    @classmethod
    def evaluate_candidate(
        cls,
        architecture: str,
        ram_gb: float,
        ocpus: float,
        storage_gb: int,
        os_type: str = "Linux",
        allow_arm64_emulation: bool = False,
    ) -> ReforgerCompatibilityReport:
        # OS Check
        if "linux" not in os_type.lower():
            return ReforgerCompatibilityReport(
                status=CompatibilityStatus.INCOMPATIBLE_OS,
                is_compatible=False,
                architecture=architecture,
                ram_gb=ram_gb,
                ocpus=ocpus,
                storage_gb=storage_gb,
                details=f"Arma Reforger dedicated server requires Linux; received {os_type}.",
                remedy="Select Canonical Ubuntu Server LTS image.",
            )

        # Architecture Check
        norm_arch = architecture.lower()
        if norm_arch in ["aarch64", "arm64", "arm"]:
            if allow_arm64_emulation:
                # Experimental Box64 emulation enabled by explicit configuration
                if ram_gb < cls.MIN_RAM_GB:
                    return ReforgerCompatibilityReport(
                        status=CompatibilityStatus.INSUFFICIENT_RAM,
                        is_compatible=False,
                        architecture=architecture,
                        ram_gb=ram_gb,
                        ocpus=ocpus,
                        storage_gb=storage_gb,
                        details=(
                            f"ARM64 emulation mode enabled, but {ram_gb:.1f} GB RAM is below "
                            f"minimum {cls.MIN_RAM_GB} GB."
                        ),
                    )
                return ReforgerCompatibilityReport(
                    status=CompatibilityStatus.COMPATIBLE,
                    is_compatible=True,
                    architecture=architecture,
                    ram_gb=ram_gb,
                    ocpus=ocpus,
                    storage_gb=storage_gb,
                    details=(
                        "ARM64 architecture running under experimental Box64 emulation. "
                        "Note: Bohemia Interactive does not officially support ARM64."
                    ),
                )
            else:
                return ReforgerCompatibilityReport(
                    status=CompatibilityStatus.INCOMPATIBLE_FOR_PRODUCTION,
                    is_compatible=False,
                    architecture=architecture,
                    ram_gb=ram_gb,
                    ocpus=ocpus,
                    storage_gb=storage_gb,
                    details=(
                        "Bohemia Interactive does NOT supply native ARM64 Linux binaries for "
                        "Arma Reforger Dedicated Server (SteamCMD App ID 1874900). "
                        "The official server executable is strictly x86_64."
                    ),
                    remedy=(
                        "For native production hosting, an x86_64 shape is required. "
                        "Alternatively, set experimental_arm64_emulation: true in config to test Box64 emulation."
                    ),
                )

        if norm_arch not in ["x86_64", "amd64", "x64"]:
            return ReforgerCompatibilityReport(
                status=CompatibilityStatus.INCOMPATIBLE_ARCHITECTURE,
                is_compatible=False,
                architecture=architecture,
                ram_gb=ram_gb,
                ocpus=ocpus,
                storage_gb=storage_gb,
                details=f"Architecture '{architecture}' is unsupported. Only x86_64 is supported natively.",
            )

        # CPU Check
        if ocpus < cls.MIN_OCPUS:
            return ReforgerCompatibilityReport(
                status=CompatibilityStatus.INSUFFICIENT_CPU,
                is_compatible=False,
                architecture=architecture,
                ram_gb=ram_gb,
                ocpus=ocpus,
                storage_gb=storage_gb,
                details=(
                    f"Allocated CPU ({ocpus} OCPU) is insufficient for the Enfusion engine. "
                    f"Minimum required is {cls.MIN_OCPUS} OCPU (e.g. E2.Micro has only 1/8 OCPU = 0.125 OCPU)."
                ),
                remedy="Increase OCPUs or choose a shape with at least 1 OCPU.",
            )

        # RAM Check
        if ram_gb < cls.MIN_RAM_GB:
            return ReforgerCompatibilityReport(
                status=CompatibilityStatus.INSUFFICIENT_RAM,
                is_compatible=False,
                architecture=architecture,
                ram_gb=ram_gb,
                ocpus=ocpus,
                storage_gb=storage_gb,
                details=(
                    f"Allocated RAM ({ram_gb:.1f} GB) is below official Bohemia minimum of {cls.MIN_RAM_GB} GB. "
                    "Server would fail during world load and AI spawning."
                ),
                remedy=f"Allocate at least {cls.MIN_RAM_GB} GB RAM.",
            )

        # Storage Check
        if storage_gb < cls.MIN_STORAGE_GB:
            return ReforgerCompatibilityReport(
                status=CompatibilityStatus.INSUFFICIENT_STORAGE,
                is_compatible=False,
                architecture=architecture,
                ram_gb=ram_gb,
                ocpus=ocpus,
                storage_gb=storage_gb,
                details=(
                    f"Boot volume size ({storage_gb} GB) is below minimum recommended {cls.MIN_STORAGE_GB} GB "
                    "for Ubuntu Server + SteamCMD + Arma Reforger workshop content."
                ),
                remedy=f"Set boot volume to at least {cls.MIN_STORAGE_GB} GB.",
            )

        return ReforgerCompatibilityReport(
            status=CompatibilityStatus.COMPATIBLE,
            is_compatible=True,
            architecture=architecture,
            ram_gb=ram_gb,
            ocpus=ocpus,
            storage_gb=storage_gb,
            details="Fully compatible with official native Arma Reforger dedicated server binary.",
        )
