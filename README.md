# Oracle Free-Tier Hunter

## Download and move to another computer

Download this repository from https://github.com/crusheR-058/oracle-free-tier-hunter
using **Code > Download ZIP**, then extract it. See [the migration guide](docs/move-to-another-computer.md)
for transferring your private OCI credentials and SSH key separately.
No GitHub key is needed to download this public repository.
Personal `config.yaml`, credentials, logs, and runtime state are excluded from Git.
The example configuration checks approximately every three minutes (5% jitter),
and starts in `WATCH_ONLY` mode.

### Autonomous OCI Capacity Monitor, Free Resource Optimizer & Immediate Auto-Provisioner for VIAF Arma Reforger Dedicated Server

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Budget: ₹0 Always Free](https://img.shields.io/badge/budget-%E2%82%B90%20Always%20Free-brightgreen.svg)](#fail-closed-zero-cost-budget-guarantee)
[![Reforger Target: 8 Players](https://img.shields.io/badge/target-Arma%20Reforger%208%20Players-orange.svg)](#arma-reforger-dedicated-server-compatibility)
[![Tests: 25 Passed](https://img.shields.io/badge/tests-25%20passed-green.svg)](#test-suite-verification)

---

## 1. Executive Summary & Objective

**Oracle Free-Tier Hunter** is a production-grade automation system that continuously monitors your Oracle Cloud Infrastructure (OCI) tenancy for the maximum genuinely free compute capacity in your home region (**India South - Hyderabad / `ap-hyderabad-1`**) and automatically provisions the best suitable compute instance as soon as capacity becomes available.

### Non-Negotiable Directives & Safety Rules
- **Strictly ₹0 Budget:** Absolutely zero cloud expenditure. No paid upgrades, no paid compute, storage, or networking charges. Any paid or uncertain resource is blocked fail-closed before API submission.
- **Autonomous Immediate Auto-Provisioning:** When enabled (`AUTO_PROVISION_FREE`), captures valid opportunities immediately upon detection without requiring manual per-opportunity confirmations.
- **Safe Exploration:** Defaults to `WATCH_ONLY` mode during development.
- **Arma Reforger Optimization:** Evaluates host eligibility against Bohemia Interactive's dedicated server requirements (8-player target, ports `2001 UDP`, `17777 UDP`, `19999 UDP`).
- **No Telegram Bot:** System alerts are delivered via native Windows desktop notifications and optional SMTP email.

---

## 2. Technical & Architectural Reality: Arma Reforger vs OCI Always Free

Based on official Bohemia Interactive documentation, SteamCMD (App ID `1874900`), and OCI specifications:

| Resource Family | Specs | Architecture | Reforger Eligibility | Verdict |
| :--- | :--- | :--- | :--- | :--- |
| **`VM.Standard.A1.Flex`** | 4 OCPU / 24 GB RAM | **ARM64 (aarch64)** | Bohemia **only releases x86_64 binaries**. No native ARM64 build exists. | **`INCOMPATIBLE_FOR_PRODUCTION`** *(Eligible only if experimental Box64 emulation is explicitly enabled in config)* |
| **`VM.Standard.E2.1.Micro`** | 0.125 OCPU / 1 GB RAM | **x86_64** | Reforger requires >= 8 GB RAM and >= 1 OCPU. Server will crash on boot. | **`INSUFFICIENT_RAM` / `INSUFFICIENT_CPU`** |
| **`VM.Standard.E4.Flex` / Other** | Configurable | **x86_64** | Has adequate RAM and CPU, but is **NOT Always Free**. | **`PAID_RESOURCE_BLOCKED`** *(Strictly rejected by ₹0 cost engine)* |

The Hunter explicitly surfaces these real-world architectural realities in its real-time dashboard and validation reports, protecting your tenancy from billable charges or deploying unviable hosts.

---

## 3. The 9 Pre-Launch Safety Gates

Every candidate configuration must pass all 9 validation gates before `ComputeClient.launch_instance` is called:

```
[Candidate Configuration]
          │
          ▼
   1. Shape is Always Free? ───────────────► NO  ──► REJECT (PAID_RESOURCE_BLOCKED)
          │ YES
   2. Projected Cost == ₹0? ───────────────► NO  ──► REJECT (COST_UNCERTAIN)
          │ YES
   3. Workload Compatible?  ───────────────► NO  ──► REJECT (INCOMPATIBLE_ARCHITECTURE)
          │ YES
   4. Storage <= 200 GB Free? ─────────────► NO  ──► REJECT (INSUFFICIENT_STORAGE)
          │ YES
   5. No Duplicate Instance? ──────────────► NO  ──► REJECT (PROVISIONING_SUCCEEDED / SKIP)
          │ YES
   6. Below Tool Instance Cap? ────────────► NO  ──► REJECT (QUOTA_EXCEEDED)
          │ YES
   7. Remaining Quota Available? ──────────► NO  ──► REJECT (QUOTA_EXCEEDED)
          │ YES
   8. Valid Ubuntu LTS Image? ─────────────► NO  ──► REJECT (INCOMPATIBLE_OS)
          │ YES
   9. Valid Public Subnet? ────────────────► NO  ──► REJECT (COST_UNCERTAIN)
          │ YES
          ▼
 [ACQUIRE FILELOCK (provisioning.lock)]
          │
          ▼
 [EXECUTE IDEMPOTENT LAUNCH WITH opc-retry-token]
```

---

## 4. Quick Start (Windows)

### Prerequisites
- Windows 10/11 with Python 3.10+ installed.
- Valid OCI configuration in `~/.oci/config` with your API key. (See [docs/deployment.md](docs/deployment.md) for step-by-step OCI key setup).

### Installation
```powershell
git clone https://github.com/crusheR-058/oracle-free-tier-hunter.git "C:\Projects\Oracle Setup"
cd "C:\Projects\Oracle Setup"

# Install dependencies
pip install -r requirements.txt
Copy-Item config.example.yaml config.yaml
```

### Running in Safe Exploration Mode (`WATCH_ONLY`)
Inspect your tenancy inventory, free allowances, and candidate verdicts without creating any resources:
```powershell
.\run_watcher.ps1 -Once
```
Or with Python directly:
```powershell
python main.py --once
```

### Enabling Continuous Immediate Auto-Provisioning
To arm the autonomous watcher to immediately capture free capacity as soon as it appears:
1. Open `config.yaml` and set:
   ```yaml
   mode: "AUTO_PROVISION_FREE"
   auto_provision_enabled: true
   ```
2. Launch the continuous watcher:
   ```powershell
   .\run_watcher.ps1
   ```
   *Keep the terminal open. The watcher checks approximately every three minutes with the supplied configuration and attempts provisioning when eligible.*

---

## 5. Post-Provisioning Arma Reforger Server Deployment

Once your instance is provisioned:
1. SSH into the instance using the public IP shown on the dashboard:
   ```bash
   ssh -i ~/.ssh/id_rsa ubuntu@<PUBLIC_IP>
   ```
2. Run the automated deployment script located in `deployment/reforger_server_setup.sh`:
   ```bash
   curl -O https://raw.githubusercontent.com/.../deployment/reforger_server_setup.sh
   chmod +x reforger_server_setup.sh
   sudo ./reforger_server_setup.sh
   ```
3. The script configures:
   - Non-root user `reforger`
   - SteamCMD and automated download of App ID `1874900`
   - Least-privilege UFW firewall rules (`22/tcp`, `2001/udp`, `17777/udp`, `19999/udp`)
   - 8-player scenario configuration (`ArmaReforgerServer.json`)
   - Systemd unit (`reforger-server.service`) with auto-restart on failure.

---

## 6. Project Structure

```
Oracle Setup/
├── config.example.yaml          # Standard configuration template (fail-closed ₹0 defaults)
├── config.yaml                  # Active user configuration
├── main.py                      # CLI entry point
├── run_watcher.bat              # Windows batch launcher
├── run_watcher.ps1              # Windows PowerShell launcher
├── requirements.txt             # Pinned dependencies
├── pyproject.toml               # Setuptools package metadata & pytest config
├── deployment/
│   ├── reforger_server_setup.sh # Ubuntu dedicated server setup script
│   └── reforger-server.service  # Production systemd unit file
├── docs/
│   ├── official_sources.md      # Authoritative citations, links, dates
│   ├── architecture.md          # 9-gate safety architecture & state machine
│   ├── deployment.md            # Windows setup & OCI API key configuration
│   └── troubleshooting.md      # Capacity errors & resolution
├── src/
│   └── free_tier_hunter/
│       ├── __init__.py
│       ├── account_inventory.py   # Live OCI tenancy resource aggregator
│       ├── architecture_checker.py # Ubuntu LTS platform image discovery
│       ├── candidate_ranker.py    # Zero-cost candidate evaluation engine
│       ├── capacity_monitor.py    # Continuous monitoring loop & backoff
│       ├── config.py              # Pydantic v2 configuration & safety validators
│       ├── dashboard.py           # Rich terminal dashboard
│       ├── free_tier_validator.py # Always Free rules & cost calculator
│       ├── idempotency.py         # Collision-resistant naming & opc-retry-token
│       ├── logging_config.py      # Secret redaction & rotating file logs
│       ├── networking.py          # Zero-cost VCN & public subnet inspector
│       ├── notifier.py            # Windows desktop toasts & SMTP email
│       ├── oci_client.py          # OCI SDK client manager & error classifier
│       ├── provisioning_engine.py # 9-gate preflight & launch execution
│       ├── quota_calculator.py    # Headroom & storage calculator
│       ├── reforger_compatibility.py # Bohemia Reforger compatibility engine
│       ├── shape_discovery.py     # AD & shape enumerator
│       ├── state_store.py         # Atomic state.json persistence
│       └── storage_optimizer.py   # Boot volume sizing (<= 200 GB)
└── tests/
    ├── test_architecture.py       # ARM64 vs x86_64, memory, CPU tests
    ├── test_candidate_ranking.py  # Ranking & scoring tests
    ├── test_cost_guard.py         # ₹0 budget invariant & validation tests
    ├── test_free_tier_validation.py # Paid shapes & free tier rules tests
    ├── test_idempotency.py        # Duplicate prevention & retry token tests
    ├── test_provisioning_safety.py# Lock contention, timeout recovery, error classification
    └── test_quota_calculation.py  # Storage and OCPU headroom tests
```

---

## 7. Test Suite Verification

Run the full automated test suite covering all 20 specified technical scenarios:
```powershell
python -m pytest -v
```

Output:
```
tests/test_architecture.py::test_scenario_6_arm64_incompatible_with_native_reforger PASSED
tests/test_architecture.py::test_arm64_experimental_emulation_allowed PASSED
tests/test_architecture.py::test_e2_micro_insufficient_ram_and_cpu PASSED
tests/test_architecture.py::test_scenario_20_incompatible_os_or_server_requirements PASSED
tests/test_candidate_ranking.py::test_scenario_1_and_ranking_priority PASSED
tests/test_cost_guard.py::test_budget_invariant_strictly_zero PASSED
tests/test_cost_guard.py::test_allow_paid_resources_must_be_false PASSED
tests/test_cost_guard.py::test_allow_account_upgrade_must_be_false PASSED
tests/test_cost_guard.py::test_allow_uncertain_cost_must_be_false PASSED
tests/test_cost_guard.py::test_auto_provisioning_mode_coherence PASSED
tests/test_free_tier_validation.py::test_scenario_2_visible_shape_not_always_free PASSED
tests/test_free_tier_validation.py::test_scenario_15_paid_upgrade_blocked PASSED
tests/test_free_tier_validation.py::test_scenario_4_and_19_uncertain_cost_blocked PASSED
tests/test_free_tier_validation.py::test_always_free_shapes_recognized PASSED
tests/test_idempotency.py::test_scenario_10_watcher_restarts_detects_existing_instance PASSED
tests/test_idempotency.py::test_deterministic_instance_naming PASSED
tests/test_idempotency.py::test_retry_token_reproducible_in_same_hour PASSED
tests/test_provisioning_safety.py::test_scenario_7_and_12_out_of_host_capacity_error_classification PASSED
tests/test_provisioning_safety.py::test_scenario_8_timeout_or_network_error_classification PASSED
tests/test_provisioning_safety.py::test_scenario_17_authentication_failed_classification PASSED
tests/test_provisioning_safety.py::test_scenario_11_lock_contention PASSED
tests/test_provisioning_safety.py::test_scenario_9_timeout_recovery_detects_created_instance PASSED
tests/test_quota_calculation.py::test_scenario_3_quota_exceeded PASSED
tests/test_quota_calculation.py::test_scenario_5_insufficient_storage PASSED
tests/test_quota_calculation.py::test_scenario_14_existing_resources_consume_part_of_allocation PASSED

============================= 25 passed in 10.95s =============================
```
