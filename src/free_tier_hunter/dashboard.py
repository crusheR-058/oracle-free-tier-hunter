"""
Terminal Dashboard powered by Rich.
Renders real-time capacity, quota, candidates, and deployment status.
"""

from datetime import datetime
from typing import List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .account_inventory import TenancyInventory
from .candidate_ranker import LaunchCandidate
from .config import HunterConfig
from .quota_calculator import RemainingAllowances
from .state_store import HunterState


class HunterDashboard:
    """Renders comprehensive terminal dashboard visualizing free-tier status and watch loop state."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def render(
        self,
        config: HunterConfig,
        state: HunterState,
        inventory: Optional[TenancyInventory],
        allowances: Optional[RemainingAllowances],
        candidates: List[LaunchCandidate],
        capacity_status: str = "CAPACITY_UNKNOWN",
    ) -> None:
        self.console.clear()

        # Header Title
        title_text = Text()
        title_text.append("ORACLE FREE-TIER HUNTER ", style="bold cyan")
        title_text.append("- Autonomous Capacity Monitor & Immediate Provisioner\n", style="bold white")
        title_text.append(f"Workload: VIAF Arma Reforger Dedicated Server (8 Players) | Region: {config.region} | Budget: INR 0", style="dim green")
        self.console.print(Panel(title_text, border_style="cyan"))

        # Section 1: System Status Table
        sys_table = Table(title="System & Runtime Status", expand=True, border_style="blue")
        sys_table.add_column("Property", style="bold white")
        sys_table.add_column("Value", style="bold")

        mode_style = "bold yellow" if config.mode.value == "WATCH_ONLY" else "bold green"
        sys_table.add_row("Operating Mode", Text(config.mode.value, style=mode_style))
        sys_table.add_row(
            "Auto-Provisioning Enabled",
            Text("TRUE (Armed)" if config.auto_provision_enabled else "FALSE (Watch Only)", style="bold green" if config.auto_provision_enabled else "bold yellow"),
        )
        sys_table.add_row("Polling Interval", f"{config.poll_interval_minutes} minutes")
        sys_table.add_row("Last Successful Check", state.last_check_time or "N/A")
        sys_table.add_row("Next Scheduled Check", state.next_check_time or "N/A")
        sys_table.add_row("Capacity Status", self._format_status(capacity_status))
        sys_table.add_row("Last Cycle Verdict", self._format_status(state.last_verdict))
        if state.last_error:
            sys_table.add_row("Last Error", Text(state.last_error[:80] + ("..." if len(state.last_error) > 80 else ""), style="bold red"))

        self.console.print(sys_table)

        # Section 2: Quota & Always Free Allowance Table
        if inventory and allowances:
            quota_table = Table(title="Always Free Resource Inventory & Headroom (INR 0 Entitlement)", expand=True, border_style="green")
            quota_table.add_column("Resource Type", style="bold white")
            quota_table.add_column("Allocated / Used", style="yellow")
            quota_table.add_column("Always Free Max", style="cyan")
            quota_table.add_column("Remaining Headroom", style="bold green")
            quota_table.add_column("Status", style="bold")

            a1_status = "Available" if allowances.can_launch_a1 else "Full"
            quota_table.add_row(
                "Ampere A1 OCPUs",
                f"{inventory.used_a1_ocpus:.1f} OCPU",
                "4.0 OCPU",
                f"{allowances.remaining_a1_ocpus:.1f} OCPU",
                Text(a1_status, style="green" if allowances.can_launch_a1 else "red"),
            )
            quota_table.add_row(
                "Ampere A1 RAM",
                f"{inventory.used_a1_ram_gb:.1f} GB",
                "24.0 GB",
                f"{allowances.remaining_a1_ram_gb:.1f} GB",
                Text(a1_status, style="green" if allowances.can_launch_a1 else "red"),
            )
            e2_status = "Available" if allowances.can_launch_e2 else "Full"
            quota_table.add_row(
                "AMD E2.1.Micro Instances",
                f"{inventory.used_e2_count} instances",
                "2 instances",
                f"{allowances.remaining_e2_instances} instances",
                Text(e2_status, style="green" if allowances.can_launch_e2 else "red"),
            )
            quota_table.add_row(
                "Block / Boot Storage",
                f"{inventory.used_storage_gb} GB",
                f"{allowances.total_storage_allowance_gb} GB",
                f"{allowances.remaining_storage_gb} GB",
                Text("Safe" if allowances.remaining_storage_gb >= 47 else "Exhausted", style="green" if allowances.remaining_storage_gb >= 47 else "red"),
            )
            self.console.print(quota_table)

        # Section 3: Candidate Evaluation & Ranking Table
        cand_table = Table(title="Candidate Evaluation & Compatibility Verdicts", expand=True, border_style="magenta")
        cand_table.add_column("Shape", style="bold white")
        cand_table.add_column("Arch", style="cyan")
        cand_table.add_column("Specs", style="yellow")
        cand_table.add_column("Cost Check", style="bold green")
        cand_table.add_column("Reforger Compatibility", style="bold")
        cand_table.add_column("Verdict", style="bold")

        if candidates:
            for c in candidates:
                specs = f"{c.ocpus:.1f} OCPU, {c.memory_in_gbs:.0f} GB RAM, {c.boot_volume_size_gb} GB disk"
                cost_str = "INR 0 Verified" if c.cost_result.is_verified_zero_cost else "Non-Free/Uncertain"
                cand_table.add_row(
                    c.shape_name,
                    c.architecture,
                    specs,
                    Text(cost_str, style="green" if c.cost_result.is_verified_zero_cost else "red"),
                    self._format_status(c.compatibility_report.status.value),
                    self._format_status(c.verdict_status),
                )
        else:
            cand_table.add_row("No Candidates", "-", "-", "-", "-", "INSUFFICIENT_STORAGE / QUOTA_EXCEEDED")

        self.console.print(cand_table)

        # Section 4: Active Deployment Details (if provisioned)
        if state.provisioned_instance_id:
            dep_table = Table(title="Active Cloud Deployment (Arma Reforger Host)", expand=True, border_style="bright_yellow")
            dep_table.add_column("Field", style="bold white")
            dep_table.add_column("Value", style="bold green")

            dep_table.add_row("Instance Name", state.provisioned_instance_name or "N/A")
            dep_table.add_row("Instance OCID", state.provisioned_instance_id)
            dep_table.add_row("Lifecycle State", state.provisioned_instance_state or "RUNNING")
            dep_table.add_row("Public IPv4", state.provisioned_public_ip or "Pending / Resolving")
            dep_table.add_row("Provisioned At", state.provisioned_at or "N/A")
            dep_table.add_row("Game Port (UDP)", "2001 (Enfusion Network)")
            dep_table.add_row("Steam Query Port (UDP)", "17777 (A2S Browser)")
            self.console.print(dep_table)

    def _format_status(self, status: str) -> Text:
        """Applies consistent status colors."""
        green_statuses = ["ELIGIBLE", "CAPACITY_AVAILABLE", "PROVISIONING_SUCCEEDED", "GAME_SERVER_READY", "COMPATIBLE"]
        yellow_statuses = ["CAPACITY_UNKNOWN", "PROVISIONING_IN_PROGRESS", "INITIALIZING", "WATCH_ONLY"]
        red_statuses = [
            "NO_CAPACITY",
            "OUT_OF_HOST_CAPACITY",
            "QUOTA_EXCEEDED",
            "COST_UNCERTAIN",
            "PAID_RESOURCE_BLOCKED",
            "INCOMPATIBLE_ARCHITECTURE",
            "INCOMPATIBLE_OS",
            "INSUFFICIENT_RAM",
            "INSUFFICIENT_CPU",
            "INSUFFICIENT_STORAGE",
            "INCOMPATIBLE_FOR_PRODUCTION",
            "PROVISIONING_FAILED",
        ]

        if status in green_statuses:
            return Text(status, style="bold green")
        elif status in yellow_statuses:
            return Text(status, style="bold yellow")
        elif status in red_statuses:
            return Text(status, style="bold red")
        return Text(status, style="white")
