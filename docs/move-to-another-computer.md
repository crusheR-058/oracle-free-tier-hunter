# Move to another Windows computer

1. Download and extract the public repository ZIP, or clone it with Git.
2. Install Python 3.10 or later, then open PowerShell in the extracted project folder:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Transfer the separately supplied **private transfer bundle** using a trusted USB drive or encrypted transfer. Never upload this bundle or its contents to GitHub. The bundle contains an unencrypted private key; anyone with it may be able to access your Oracle account.
4. Copy the bundle's `oci` directory contents to `$HOME\.oci`. Its `config` references `~/.oci/oci_api_key.pem`; keep that path or update it to the actual private key location. Back up existing files before replacing them.
5. Copy the bundle's `ssh` files to `$HOME\.ssh`. The SSH private key is for logging into a provisioned VM. The OCI API private key is for running the watcher; these are different keys. Preserve any existing SSH keys on the destination computer.
6. Copy the bundle's `config.yaml` to the project folder. This retains your personal settings and **automatic provisioning is enabled**. To inspect without launching, set both `mode: "WATCH_ONLY"` and `auto_provision_enabled: false` before running. The `--once` and `--check` flags alone do not disable provisioning.
7. Copy the bundle's `state.json` into the project folder if included. Stop the old watcher before starting the new one: the provisioning lock is local to each computer.
8. Start the watcher from the project folder:

   ```powershell
   .\run_watcher.ps1
   ```

If PowerShell blocks the script, use `python main.py` instead. Keep the terminal open and the computer awake. The configured delay is three minutes with up to nine seconds of jitter; cycle execution adds some time.

To access a provisioned Ubuntu VM:

```powershell
ssh -i "$HOME\.ssh\id_rsa" ubuntu@<INSTANCE_PUBLIC_IP>
```

The copied keys already correspond to your existing Oracle setup. Do not run `setup_credentials.py` to replace them during migration, and do not upload private keys to the Oracle console. Only a public API key belongs in Oracle's API key registration screen.

No GitHub access token is required to download this public project. Keep the transfer bundle private and remove extra copies after migration. This project attempts to enforce configured free-tier limits; it does not provide a billing guarantee.
