"""
Shape Discovery and Availability Domain Enumeration Engine.
"""

from dataclasses import dataclass
import logging
from typing import Any, Dict, List, Optional
import oci
from .free_tier_validator import FreeTierValidator

logger = logging.getLogger("free_tier_hunter.shape_discovery")


@dataclass
class DiscoveredShape:
    name: str
    is_always_free: bool
    is_flexible: bool
    architecture: str
    ocpus: float
    memory_in_gbs: float
    gpu_description: Optional[str] = None


@dataclass
class AvailabilityDomainInfo:
    name: str
    id: str


class ShapeDiscoveryEngine:
    """Discovers compute shapes and availability domains in the target compartment."""

    def __init__(self, oci_manager: Any):
        self.oci_manager = oci_manager

    def list_availability_domains(self, compartment_id: Optional[str] = None) -> List[AvailabilityDomainInfo]:
        """Lists availability domains in the region."""
        identity_client = self.oci_manager.identity_client
        target_compartment = compartment_id or self.oci_manager.tenancy_id

        try:
            response = identity_client.list_availability_domains(compartment_id=target_compartment)
            raw_ads = response.data if hasattr(response, "data") else []
            ads = [
                AvailabilityDomainInfo(name=getattr(ad, "name", ""), id=getattr(ad, "id", ""))
                for ad in raw_ads
            ]
            logger.info(f"Discovered {len(ads)} availability domains: {[ad.name for ad in ads]}")
            return ads
        except Exception as e:
            logger.error(f"Failed to list availability domains: {e}")
            return []

    def discover_shapes(
        self,
        availability_domain: Optional[str] = None,
        compartment_id: Optional[str] = None,
    ) -> List[DiscoveredShape]:
        """Discovers shapes available in the specified availability domain and compartment."""
        compute_client = self.oci_manager.compute_client
        target_compartment = compartment_id or self.oci_manager.tenancy_id

        try:
            kwargs: Dict[str, Any] = {"compartment_id": target_compartment}
            if availability_domain:
                kwargs["availability_domain"] = availability_domain

            response = compute_client.list_shapes(**kwargs)
            raw_shapes = response.data if hasattr(response, "data") else []

            discovered: List[DiscoveredShape] = []
            for s in raw_shapes:
                shape_name = getattr(s, "shape", "")
                is_free = FreeTierValidator.is_shape_always_free(shape_name)
                spec = FreeTierValidator.get_shape_spec(shape_name)

                # Determine architecture and flexibility
                if spec:
                    arch = spec.architecture
                    is_flex = spec.is_flexible
                else:
                    is_flex = "Flex" in shape_name
                    arch = "aarch64" if "A1" in shape_name else "x86_64"

                ocpus = float(getattr(s, "ocpus", 1.0) or 1.0)
                mem = float(getattr(s, "memory_in_gbs", 1.0) or 1.0)

                discovered.append(
                    DiscoveredShape(
                        name=shape_name,
                        is_always_free=is_free,
                        is_flexible=is_flex,
                        architecture=arch,
                        ocpus=ocpus,
                        memory_in_gbs=mem,
                    )
                )

            logger.info(f"Discovered {len(discovered)} shapes (Always Free count: {sum(1 for s in discovered if s.is_always_free)})")
            return discovered

        except Exception as e:
            logger.error(f"Failed to list compute shapes: {e}")
            return []
