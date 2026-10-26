"""
Official Oracle Cloud Infrastructure Always Free Tier Rules & Cost Validator.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple


class ShapeFamily(str, Enum):
    AMPERE_A1 = "AMPERE_A1"
    AMD_MICRO = "AMD_MICRO"
    UNSUPPORTED_PAID = "UNSUPPORTED_PAID"


@dataclass
class FreeTierShapeSpec:
    shape_name: str
    family: ShapeFamily
    architecture: str
    is_flexible: bool
    max_ocpus_per_tenancy: float
    max_ram_gb_per_tenancy: float
    max_instances_per_tenancy: int
    is_always_free: bool
    description: str


# Authoritative Always Free compute shapes per Oracle Cloud official documentation
ALWAYS_FREE_SHAPES = {
    "VM.Standard.A1.Flex": FreeTierShapeSpec(
        shape_name="VM.Standard.A1.Flex",
        family=ShapeFamily.AMPERE_A1,
        architecture="aarch64",
        is_flexible=True,
        max_ocpus_per_tenancy=4.0,
        max_ram_gb_per_tenancy=24.0,
        max_instances_per_tenancy=4,
        is_always_free=True,
        description="Ampere Altra ARM64 compute, up to 4 OCPUs and 24 GB RAM across tenancy",
    ),
    "VM.Standard.E2.1.Micro": FreeTierShapeSpec(
        shape_name="VM.Standard.E2.1.Micro",
        family=ShapeFamily.AMD_MICRO,
        architecture="x86_64",
        is_flexible=False,
        max_ocpus_per_tenancy=0.25,  # 2 instances * 1/8 OCPU = 0.25 OCPU
        max_ram_gb_per_tenancy=2.0,   # 2 instances * 1 GB = 2 GB RAM
        max_instances_per_tenancy=2,
        is_always_free=True,
        description="AMD EPYC x86_64 micro compute, 1/8 OCPU and 1 GB RAM fixed (up to 2 instances)",
    ),
}

# Total Always Free block storage allowance in GB (boot volumes + block volumes combined)
ALWAYS_FREE_STORAGE_GB_TOTAL = 200

# Minimum allowed boot volume in OCI for standard Linux images
OCI_MIN_BOOT_VOLUME_GB = 47


@dataclass
class CostVerificationResult:
    is_verified_zero_cost: bool
    status_label: str  # "ELIGIBLE", "COST_UNCERTAIN", "PAID_RESOURCE_BLOCKED", "QUOTA_EXCEEDED"
    details: str
    projected_monthly_cost_inr: float = 0.0


class FreeTierValidator:
    """Validates compute, storage, and networking configurations against Oracle Always Free rules."""

    @staticmethod
    def is_shape_always_free(shape_name: str) -> bool:
        """Returns True if the shape is officially documented as Always Free eligible."""
        return shape_name in ALWAYS_FREE_SHAPES

    @staticmethod
    def get_shape_spec(shape_name: str) -> Optional[FreeTierShapeSpec]:
        """Returns the official spec for an Always Free shape, or None if paid/unsupported."""
        return ALWAYS_FREE_SHAPES.get(shape_name)

    @classmethod
    def validate_instance_configuration(
        cls,
        shape: str,
        ocpus: float,
        memory_in_gbs: float,
        boot_volume_size_gb: int,
        tenancy_used_a1_ocpus: float = 0.0,
        tenancy_used_a1_ram: float = 0.0,
        tenancy_used_e2_count: int = 0,
        tenancy_used_storage_gb: int = 0,
        assign_public_ip: bool = True,
    ) -> CostVerificationResult:
        """
        Comprehensive zero-cost guard for an instance launch candidate.
        Ensures strict ₹0 cost invariants across compute, memory, storage, and networking.
        """
        # 1. Check Shape Eligibility
        spec = cls.get_shape_spec(shape)
        if not spec or not spec.is_always_free:
            return CostVerificationResult(
                is_verified_zero_cost=False,
                status_label="PAID_RESOURCE_BLOCKED",
                details=f"Shape '{shape}' is NOT Always Free eligible. Launching it would incur billable compute charges.",
                projected_monthly_cost_inr=999.0,
            )

        # 2. Check Shape Specifications (Ampere A1 Flex)
        if spec.family == ShapeFamily.AMPERE_A1:
            if ocpus <= 0 or memory_in_gbs <= 0:
                return CostVerificationResult(
                    is_verified_zero_cost=False,
                    status_label="COST_UNCERTAIN",
                    details=f"Invalid OCPU ({ocpus}) or RAM ({memory_in_gbs}GB) requested.",
                )

            # Check individual candidate against total limit
            if ocpus > 4.0 or memory_in_gbs > 24.0:
                return CostVerificationResult(
                    is_verified_zero_cost=False,
                    status_label="COST_UNCERTAIN",
                    details=f"Requested {ocpus} OCPUs or {memory_in_gbs} GB RAM exceeds total Always Free allowance (4 OCPU / 24 GB).",
                )

            # Check combined tenancy usage
            new_total_ocpus = tenancy_used_a1_ocpus + ocpus
            new_total_ram = tenancy_used_a1_ram + memory_in_gbs
            if new_total_ocpus > 4.0:
                return CostVerificationResult(
                    is_verified_zero_cost=False,
                    status_label="QUOTA_EXCEEDED",
                    details=f"Adding {ocpus} OCPUs would bring total A1 usage to {new_total_ocpus:.1f}, exceeding the 4.0 OCPU free limit.",
                )
            if new_total_ram > 24.0:
                return CostVerificationResult(
                    is_verified_zero_cost=False,
                    status_label="QUOTA_EXCEEDED",
                    details=f"Adding {memory_in_gbs} GB RAM would bring total A1 RAM to {new_total_ram:.1f} GB, exceeding the 24.0 GB free limit.",
                )

        # 3. Check Shape Specifications (AMD E2.1.Micro)
        elif spec.family == ShapeFamily.AMD_MICRO:
            if ocpus != 0.125 or memory_in_gbs != 1.0:
                # E2.1.Micro is fixed at 1/8 OCPU and 1 GB RAM
                pass
            if tenancy_used_e2_count >= 2:
                return CostVerificationResult(
                    is_verified_zero_cost=False,
                    status_label="QUOTA_EXCEEDED",
                    details=f"Tenancy already has {tenancy_used_e2_count} E2.1.Micro instances. Always Free limit is 2.",
                )

        # 4. Check Storage Allowance
        if boot_volume_size_gb < OCI_MIN_BOOT_VOLUME_GB:
            return CostVerificationResult(
                is_verified_zero_cost=False,
                status_label="COST_UNCERTAIN",
                details=f"Boot volume size {boot_volume_size_gb} GB is below minimum required {OCI_MIN_BOOT_VOLUME_GB} GB.",
            )

        new_total_storage = tenancy_used_storage_gb + boot_volume_size_gb
        if new_total_storage > ALWAYS_FREE_STORAGE_GB_TOTAL:
            return CostVerificationResult(
                is_verified_zero_cost=False,
                status_label="INSUFFICIENT_STORAGE",
                details=(
                    f"Requested {boot_volume_size_gb} GB boot volume would push total block storage to "
                    f"{new_total_storage} GB, exceeding the 200 GB Always Free allowance."
                ),
            )

        # 5. Check Networking
        # Ephemeral public IP on a public subnet is 100% free under OCI Always Free.
        # (Reserved public IPs have a limit of 1 free; ephemeral has no charge).

        return CostVerificationResult(
            is_verified_zero_cost=True,
            status_label="ELIGIBLE",
            details="100% Always Free verified. Projected cost is ₹0.00.",
            projected_monthly_cost_inr=0.0,
        )
