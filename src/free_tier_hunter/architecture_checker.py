"""
Operating System and Architecture Image Compatibility Checker.
Discovers and verifies official Canonical Ubuntu LTS images for x86_64 and aarch64.
"""

from dataclasses import dataclass
import logging
from typing import Any, List, Optional
import oci

logger = logging.getLogger("free_tier_hunter.architecture_checker")


@dataclass
class DiscoveredImage:
    id: str
    display_name: str
    operating_system: str
    operating_system_version: str
    architecture: str  # "x86_64" or "aarch64"
    time_created: str


class ArchitectureChecker:
    """Discovers and validates base OS images for target compute shapes."""

    def __init__(self, oci_manager: Any):
        self.oci_manager = oci_manager

    def find_ubuntu_lts_image(
        self,
        target_architecture: str,
        target_version: str = "22.04",
        compartment_id: Optional[str] = None,
    ) -> Optional[DiscoveredImage]:
        """
        Discovers official Canonical Ubuntu LTS platform image for the specified architecture.
        target_architecture must be 'x86_64' or 'aarch64'.
        """
        compute_client = self.oci_manager.compute_client
        target_compartment = compartment_id or self.oci_manager.tenancy_id

        norm_arch = "aarch64" if target_architecture.lower() in ["arm", "arm64", "aarch64"] else "x86_64"
        logger.info(
            f"Searching for official Canonical Ubuntu {target_version} LTS image for {norm_arch}..."
        )

        try:
            # Query official platform images
            images_response = compute_client.list_images(
                compartment_id=target_compartment,
                operating_system="Canonical Ubuntu",
                operating_system_version=target_version,
                shape=None,
                sort_by="TIMECREATED",
                sort_order="DESC",
            )
            raw_images = images_response.data if hasattr(images_response, "data") else []

            for img in raw_images:
                # Filter by architecture and state
                state = getattr(img, "lifecycle_state", "").upper()
                if state != "AVAILABLE":
                    continue

                display_name = getattr(img, "display_name", "")
                img_arch = ""

                # Some images specify architecture or display_name contains -aarch64
                if hasattr(img, "launch_options") and getattr(img, "launch_options", None):
                    # LaunchOptions or custom attributes
                    pass

                if "aarch64" in display_name.lower() or "arm" in display_name.lower():
                    img_arch = "aarch64"
                else:
                    img_arch = "x86_64"

                if img_arch == norm_arch:
                    discovered = DiscoveredImage(
                        id=getattr(img, "id", ""),
                        display_name=display_name,
                        operating_system=getattr(img, "operating_system", "Canonical Ubuntu"),
                        operating_system_version=getattr(img, "operating_system_version", target_version),
                        architecture=img_arch,
                        time_created=str(getattr(img, "time_created", "")),
                    )
                    logger.info(f"Selected image: {discovered.display_name} (OCID: {discovered.id[:18]}...)")
                    return discovered

            # If specific version not found, broaden search to any Ubuntu LTS
            logger.warning(f"Ubuntu {target_version} for {norm_arch} not found, checking all available Ubuntu images...")
            broad_response = compute_client.list_images(
                compartment_id=target_compartment,
                operating_system="Canonical Ubuntu",
                sort_by="TIMECREATED",
                sort_order="DESC",
            )
            broad_images = broad_response.data if hasattr(broad_response, "data") else []
            for img in broad_images:
                if getattr(img, "lifecycle_state", "").upper() != "AVAILABLE":
                    continue
                display_name = getattr(img, "display_name", "")
                img_arch = "aarch64" if ("aarch64" in display_name.lower() or "arm" in display_name.lower()) else "x86_64"
                if img_arch == norm_arch:
                    return DiscoveredImage(
                        id=getattr(img, "id", ""),
                        display_name=display_name,
                        operating_system=getattr(img, "operating_system", "Canonical Ubuntu"),
                        operating_system_version=getattr(img, "operating_system_version", ""),
                        architecture=img_arch,
                        time_created=str(getattr(img, "time_created", "")),
                    )

            logger.error(f"No available Canonical Ubuntu image found for architecture {norm_arch}.")
            return None

        except Exception as e:
            logger.error(f"Error querying OCI images: {e}")
            return None
