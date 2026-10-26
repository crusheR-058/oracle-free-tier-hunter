"""
CLI Entrypoint for Oracle Free-Tier Hunter.
"""

import argparse
import logging
from pathlib import Path
import sys

# Ensure src directory is on python path when running main.py directly
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from free_tier_hunter.capacity_monitor import CapacityMonitor
from free_tier_hunter.config import HunterConfig, OperatingMode, load_config
from free_tier_hunter.logging_config import setup_logging
from free_tier_hunter.oci_client import OciClientManager


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Oracle Free-Tier Hunter: Autonomous Capacity Monitor & Free Resource Optimizer for Arma Reforger",
    )
    parser.add_argument(
        "-c",
        "--config",
        default="config.yaml",
        help="Path to YAML configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single inspection/provisioning cycle and exit (useful for testing & dry runs)",
    )
    parser.add_argument(
        "--mode",
        choices=["WATCH_ONLY", "AUTO_PROVISION_FREE", "GAME_SERVER_DEPLOYMENT"],
        help="Override operating mode from configuration",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check OCI authentication, permissions, and free-tier headroom, then exit",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()

    try:
        config = load_config(args.config)
    except Exception as e:
        print(f"\n[FATAL] Configuration Error: {e}", file=sys.stderr)
        return 1

    # Override mode from CLI if specified
    if args.mode:
        config.mode = OperatingMode(args.mode)
        if config.mode == OperatingMode.AUTO_PROVISION_FREE:
            config.auto_provision_enabled = True

    # Setup Logging
    logger = setup_logging(log_level=config.log_level)
    logger.info("Initializing Oracle Free-Tier Hunter v1.0.0...")

    # Initialize OCI SDK Manager
    oci_manager = OciClientManager(
        config_file=config.oci_config_file,
        profile_name=config.oci_profile,
        region=config.region,
    )

    try:
        oci_manager.initialize()
    except Exception as e:
        logger.error(f"OCI Authentication Setup Failed: {e}")
        print(f"\n[ERROR] OCI Authentication Failed: {e}", file=sys.stderr)
        print("Please verify ~/.oci/config exists and your API key is correctly configured.", file=sys.stderr)
        return 2

    # Instantiate Monitor
    monitor = CapacityMonitor(config=config, oci_manager=oci_manager)

    if args.check or args.once:
        logger.info("Executing single monitoring cycle...")
        result = monitor.run_single_cycle()
        logger.info(f"Cycle completed with verdict: {result['verdict']}")
        return 0
    else:
        logger.info("Entering persistent capacity monitoring loop...")
        monitor.start_monitoring_loop()
        return 0


def cli_entrypoint() -> None:
    sys.exit(main())


if __name__ == "__main__":
    cli_entrypoint()
