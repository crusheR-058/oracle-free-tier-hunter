"""
Networking and Security List Manager for Always Free OCI VCN and Subnets.
Configures least-privilege firewall rules for Arma Reforger dedicated server.
"""

from dataclasses import dataclass
import logging
import time
from typing import Any, List, Optional
import oci

logger = logging.getLogger("free_tier_hunter.networking")

# Reforger Official Network Ports
REFORGER_GAME_PORT_UDP = 2001      # Enfusion public connection port
REFORGER_STEAM_QUERY_UDP = 17777   # Steam A2S query port
REFORGER_RCON_PORT_UDP = 19999     # Remote Console
SSH_PORT_TCP = 22                  # Administration


@dataclass
class NetworkContext:
    vcn_id: str
    subnet_id: str
    is_public: bool
    assign_public_ip: bool = True


class NetworkManager:
    """Manages zero-cost VCN, public subnets, and Reforger firewall ingress rules."""

    def __init__(self, oci_manager: Any):
        self.oci_manager = oci_manager

    def find_or_prepare_public_subnet(
        self,
        compartment_id: Optional[str] = None,
        ad_name: Optional[str] = None,
        auto_create_if_missing: bool = True,
    ) -> Optional[NetworkContext]:
        """
        Discovers an existing public subnet in the compartment.
        If no public subnet exists and auto_create_if_missing is True,
        creates an Always Free VCN, Internet Gateway, Route Table, and Public Subnet.
        """
        net_client = self.oci_manager.network_client
        target_compartment = compartment_id or self.oci_manager.tenancy_id

        try:
            # 1. Look for existing public subnets
            subnets_resp = net_client.list_subnets(compartment_id=target_compartment)
            subnets = subnets_resp.data if hasattr(subnets_resp, "data") else []

            for subnet in subnets:
                prohibit_public = getattr(subnet, "prohibit_public_ip_on_vnic", False)
                state = getattr(subnet, "lifecycle_state", "").upper()

                if state == "AVAILABLE" and not prohibit_public:
                    subnet_id = getattr(subnet, "id", "")
                    vcn_id = getattr(subnet, "vcn_id", "")
                    logger.info(f"Found existing public subnet: {getattr(subnet, 'display_name', '')} (OCID: {subnet_id[:18]}...)")
                    return NetworkContext(
                        vcn_id=vcn_id,
                        subnet_id=subnet_id,
                        is_public=True,
                        assign_public_ip=True,
                    )

            if not auto_create_if_missing:
                logger.warning("No existing public subnet found in compartment.")
                return None

            # 2. Create Always Free VCN, Gateway, Route Table, and Subnet
            logger.info("No public subnet found. Provisioning zero-cost Always Free VCN and subnet...")
            return self._create_free_networking(target_compartment)

        except Exception as e:
            logger.error(f"Error checking or creating network infrastructure: {e}")
            return None

    def _create_free_networking(self, compartment_id: str) -> Optional[NetworkContext]:
        net_client = self.oci_manager.network_client

        # 1. Create VCN (10.0.0.0/16)
        logger.info("Creating Always Free VCN (10.0.0.0/16)...")
        vcn_details = oci.core.models.CreateVcnDetails(
            cidr_block="10.0.0.0/16",
            display_name="viaf-reforger-vcn",
            compartment_id=compartment_id,
        )
        vcn = net_client.create_vcn(vcn_details).data
        vcn_id = getattr(vcn, "id", "")
        time.sleep(2)

        # 2. Create Internet Gateway
        logger.info("Creating Internet Gateway...")
        igw_details = oci.core.models.CreateInternetGatewayDetails(
            compartment_id=compartment_id,
            display_name="viaf-reforger-igw",
            is_enabled=True,
            vcn_id=vcn_id,
        )
        igw = net_client.create_internet_gateway(igw_details).data
        igw_id = getattr(igw, "id", "")
        time.sleep(2)

        # 3. Create Route Table with default route to Internet Gateway
        logger.info("Creating Route Table...")
        route_rule = oci.core.models.RouteRule(
            destination="0.0.0.0/0",
            destination_type="CIDR_BLOCK",
            network_entity_id=igw_id,
            description="Default route to internet gateway",
        )
        rt_details = oci.core.models.CreateRouteTableDetails(
            compartment_id=compartment_id,
            display_name="viaf-reforger-rt",
            route_rules=[route_rule],
            vcn_id=vcn_id,
        )
        rt = net_client.create_route_table(rt_details).data
        rt_id = getattr(rt, "id", "")
        time.sleep(2)

        # 4. Create Security List with Reforger + SSH ports
        logger.info("Creating Security List with Reforger game ports...")
        egress_rule = oci.core.models.EgressSecurityRule(
            destination="0.0.0.0/0",
            protocol="all",
            description="Allow all outbound traffic",
        )

        ingress_rules = [
            oci.core.models.IngressSecurityRule(
                protocol="6",  # TCP
                source="0.0.0.0/0",
                tcp_options=oci.core.models.TcpOptions(
                    destination_port_range=oci.core.models.PortRange(min=22, max=22)
                ),
                description="SSH management",
            ),
            oci.core.models.IngressSecurityRule(
                protocol="17",  # UDP
                source="0.0.0.0/0",
                udp_options=oci.core.models.UdpOptions(
                    destination_port_range=oci.core.models.PortRange(min=REFORGER_GAME_PORT_UDP, max=REFORGER_GAME_PORT_UDP)
                ),
                description="Arma Reforger game connection port",
            ),
            oci.core.models.IngressSecurityRule(
                protocol="17",  # UDP
                source="0.0.0.0/0",
                udp_options=oci.core.models.UdpOptions(
                    destination_port_range=oci.core.models.PortRange(min=REFORGER_STEAM_QUERY_UDP, max=REFORGER_STEAM_QUERY_UDP)
                ),
                description="Steam query A2S port",
            ),
            oci.core.models.IngressSecurityRule(
                protocol="17",  # UDP
                source="0.0.0.0/0",
                udp_options=oci.core.models.UdpOptions(
                    destination_port_range=oci.core.models.PortRange(min=REFORGER_RCON_PORT_UDP, max=REFORGER_RCON_PORT_UDP)
                ),
                description="RCON port",
            ),
        ]

        sec_details = oci.core.models.CreateSecurityListDetails(
            compartment_id=compartment_id,
            display_name="viaf-reforger-sec-list",
            vcn_id=vcn_id,
            egress_security_rules=[egress_rule],
            ingress_security_rules=ingress_rules,
        )
        sec_list = net_client.create_security_list(sec_details).data
        sec_id = getattr(sec_list, "id", "")
        time.sleep(2)

        # 5. Create Public Subnet (10.0.1.0/24)
        logger.info("Creating Public Subnet (10.0.1.0/24)...")
        subnet_details = oci.core.models.CreateSubnetDetails(
            cidr_block="10.0.1.0/24",
            display_name="viaf-reforger-public-subnet",
            compartment_id=compartment_id,
            vcn_id=vcn_id,
            route_table_id=rt_id,
            security_list_ids=[sec_id],
            prohibit_public_ip_on_vnic=False,
        )
        subnet = net_client.create_subnet(subnet_details).data
        subnet_id = getattr(subnet, "id", "")

        logger.info(f"Successfully provisioned public subnet: {subnet_id[:18]}...")
        return NetworkContext(
            vcn_id=vcn_id,
            subnet_id=subnet_id,
            is_public=True,
            assign_public_ip=True,
        )

    @staticmethod
    def get_required_ingress_security_rules() -> List[dict]:
        """
        Returns OCI security list ingress rules strictly required for Arma Reforger + SSH.
        Only least-privilege ports are opened.
        """
        return [
            # SSH
            {
                "protocol": "6",  # TCP
                "source": "0.0.0.0/0",
                "tcp_options": {"destination_port_range": {"min": 22, "max": 22}},
                "description": "SSH remote management",
            },
            # Reforger Game Port
            {
                "protocol": "17",  # UDP
                "source": "0.0.0.0/0",
                "udp_options": {"destination_port_range": {"min": REFORGER_GAME_PORT_UDP, "max": REFORGER_GAME_PORT_UDP}},
                "description": "Arma Reforger Enfusion game connection port",
            },
            # Steam Query Port
            {
                "protocol": "17",  # UDP
                "source": "0.0.0.0/0",
                "udp_options": {"destination_port_range": {"min": REFORGER_STEAM_QUERY_UDP, "max": REFORGER_STEAM_QUERY_UDP}},
                "description": "Arma Reforger Steam query / A2S browser discovery",
            },
            # RCON Port
            {
                "protocol": "17",  # UDP
                "source": "0.0.0.0/0",
                "udp_options": {"destination_port_range": {"min": REFORGER_RCON_PORT_UDP, "max": REFORGER_RCON_PORT_UDP}},
                "description": "Arma Reforger RCON remote administration",
            },
        ]
