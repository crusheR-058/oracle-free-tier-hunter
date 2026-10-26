# Official Technical Sources & Evidence Verification

This document catalogs all authoritative official sources, APIs, and technical references used to build **Oracle Free-Tier Hunter**. Every fact has been verified against official vendor documentation.

---

## 1. Oracle Cloud Infrastructure (OCI) Official Documentation

### 1.1 OCI Always Free Resources
- **Source:** Oracle Help Center — *Always Free Resources*
- **URL:** [https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
- **Verified Entitlements:**
  - **Ampere A1 Compute (`VM.Standard.A1.Flex`):** Up to 4 OCPUs and 24 GB of RAM total per tenancy per month (equivalent to 3,000 OCPU hours and 18,000 GB hours). Can be provisioned as 1 instance with 4 OCPUs/24 GB, or split across up to 4 instances.
  - **AMD Micro Compute (`VM.Standard.E2.1.Micro`):** Up to 2 instances. Each instance has fixed specifications of 1/8 OCPU (0.125 OCPU) and 1 GB of RAM.
  - **Block Storage:** 200 GB total Always Free block storage across boot volumes and block volumes. Up to 5 free volume backups. Minimum boot volume size is 47 GB.
  - **Networking:** 10 TB/month outbound internet data transfer free. 1 free Always Free flexible load balancer (10 Mbps). Free VCNs, subnets, route tables, internet gateways, and ephemeral public IPs. Up to 1 reserved public IPv4 address free.

### 1.2 OCI Compute Shapes & Sizing
- **Source:** Oracle Help Center — *Compute Shapes*
- **URL:** [https://docs.oracle.com/en-us/iaas/Content/Compute/References/computeshapes.htm](https://docs.oracle.com/en-us/iaas/Content/Compute/References/computeshapes.htm)
- **Verified Facts:**
  - Non-eligible shapes visible in console (`VM.Standard.E2.1`, `VM.Standard.E2.2`, `VM.Standard.E4.Flex`, `VM.Standard.E5.Flex`) are **paid shapes** and incur hourly billable compute charges.
  - OCI provides no standalone API endpoint to query compute capacity availability beforehand. The only authoritative indication of host capacity is returned during instance launch (`launch_instance`). If capacity is exhausted, OCI returns HTTP 500 `OutOfHostCapacity`.

### 1.3 OCI Python SDK & API
- **Source:** Oracle Help Center — *OCI Python SDK Documentation*
- **URL:** [https://docs.oracle.com/en-us/iaas/tools/python/latest/](https://docs.oracle.com/en-us/iaas/tools/python/latest/)
- **Core APIs:**
  - `oci.core.ComputeClient.launch_instance`: Launches compute instances with idempotency support via `opc_retry_token`.
  - `oci.core.ComputeClient.list_instances`: Enumerates active instances in compartment.
  - `oci.core.BlockstorageClient.list_boot_volumes`: Enumerates boot volumes and allocated sizes.
  - `oci.identity.IdentityClient.list_availability_domains`: Enumerates regional availability domains (e.g. `ap-hyderabad-1`).

---

## 2. Bohemia Interactive — Arma Reforger Official Documentation

### 2.1 Server Hosting & Hardware Sizing
- **Source:** Bohemia Interactive Community Wiki — *Arma Reforger: Server Hosting*
- **URL:** [https://community.bistudio.com/wiki/Arma_Reforger:Server_Hosting](https://community.bistudio.com/wiki/Arma_Reforger:Server_Hosting)
- **Verified Facts:**
  - **Minimum RAM:** **8 GB** official minimum. Idle unmodded server consumes 3 to 4 GB upon initial world spawn; dynamic AI spooling and player connections scale RAM to 6–8 GB.
  - **Recommended RAM:** **16 GB** for production servers.
  - **CPU:** Requires high single-thread clock speed. 1/8 OCPU on E2.Micro causes extreme tick rate drops and server timeouts.
  - **Framerate cap:** Bohemia recommends `-maxFPS 60` or `-maxFPS 120` to prevent unbounded CPU cycles.

### 2.2 Dedicated Server Port Requirements
- **Source:** Bohemia Interactive Community Wiki — *Arma Reforger: Server Config*
- **URL:** [https://community.bistudio.com/wiki/Arma_Reforger:Server_Config](https://community.bistudio.com/wiki/Arma_Reforger:Server_Config)
- **Required Ports:**
  - `2001 UDP`: Game / Public Enfusion networking port (required for player connections).
  - `17777 UDP`: Steam Query (A2S) port (used by in-game and Steam server browsers).
  - `19999 UDP`: RCON remote administration port (optional).

### 2.3 Binary Architecture & ARM64 Support Analysis
- **Source:** SteamCMD Dedicated Server Package (App ID: `1874900`), Bohemia Interactive Forums, and LinuxGSM
- **URL:** [https://steamdb.info/app/1874900/](https://steamdb.info/app/1874900/)
- **Authoritative Findings:**
  - Bohemia Interactive releases **x86_64 Linux ELF binaries ONLY** (`ArmaReforgerServer`).
  - **There is NO native ARM64 / aarch64 server binary** provided by Bohemia Interactive.
  - Running on ARM64 requires user-space binary translation (Box64 or FEX-Emu).
  - **Production Verdict:** Emulation introduces severe latency, tick drops, and potential crashes under multiplayer load. Therefore, `VM.Standard.A1.Flex` is classified as `INCOMPATIBLE_FOR_PRODUCTION` unless the user explicitly enables experimental emulation testing.
