# Deployment & Operating Guide

This guide walks through configuring OCI credentials, running the Hunter on Windows, enabling auto-provisioning, and setting up the Arma Reforger dedicated server.

---

## 1. Setting Up OCI API Authentication on Windows

1. Install the official OCI CLI or generate an RSA key pair:
   ```powershell
   # Create .oci directory in your Windows user profile
   mkdir "$HOME\.oci" -Force
   cd "$HOME\.oci"

   # Generate RSA private key (2048-bit minimum)
   openssl genrsa -out oci_api_key.pem 2048

   # Extract public key
   openssl rsa -pubout -in oci_api_key.pem -out oci_api_key_public.pem
   ```

2. Upload the Public Key to OCI Console:
   - Log into [cloud.oracle.com](https://cloud.oracle.com).
   - In the top right corner, click your **User Profile Icon** -> **My Profile** (or **User Settings**).
   - Under **Resources** on the left menu, select **API Keys**.
   - Click **Add API Key** -> **Paste Public Key** -> paste contents of `oci_api_key_public.pem`.
   - Click **Add**. OCI displays a configuration snippet containing your user OCID, tenancy OCID, fingerprint, and region.

3. Save the Config Snippet:
   - Create or edit `$HOME\.oci\config` in Notepad:
     ```ini
     [DEFAULT]
     user=ocid1.user.oc1..aaaaaaa...
     fingerprint=aa:bb:cc:dd:ee:...
     key_file=C:\Users\YourUser\.oci\oci_api_key.pem
     tenancy=ocid1.tenancy.oc1..aaaaaaa...
     region=ap-hyderabad-1
     ```

---

## 2. Running in WATCH_ONLY Mode (Safe Exploration)

By default, `config.yaml` is set to `WATCH_ONLY` mode. In this mode, the tool:
- Reads your tenancy inventory.
- Calculates remaining Always Free allowances.
- Ranks candidates and evaluates Arma Reforger compatibility.
- **NEVER** creates or modifies any cloud resource.

Run with:
```powershell
.\run_watcher.ps1 -Once
```
Or run the continuous watcher:
```powershell
.\run_watcher.ps1
```

---

## 3. Deliberately Enabling Immediate Automatic Provisioning

When you are ready to allow the tool to capture capacity the moment it becomes available:

1. Open `config.yaml`.
2. Change the operating mode and toggle:
   ```yaml
   mode: "AUTO_PROVISION_FREE"
   auto_provision_enabled: true
   ```
3. Run the watcher:
   ```powershell
   .\run_watcher.ps1
   ```

As soon as a valid, 100% free opportunity is detected, the Hunter will immediately provision the instance without asking for per-opportunity manual approval.

---

## 4. Post-Provisioning Arma Reforger Dedicated Server Setup

Once your instance is provisioned:
1. Connect via SSH using the public IPv4 shown on the dashboard:
   ```bash
   ssh -i ~/.ssh/id_rsa ubuntu@<PUBLIC_IP>
   ```
2. Download and run the setup script:
   ```bash
   curl -O https://raw.githubusercontent.com/.../reforger_server_setup.sh
   # Or upload deployment/reforger_server_setup.sh
   chmod +x reforger_server_setup.sh
   sudo ./reforger_server_setup.sh
   ```
3. Start the game server:
   ```bash
   sudo systemctl start reforger-server
   sudo journalctl -u reforger-server -f
   ```
