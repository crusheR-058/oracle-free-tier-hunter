# Troubleshooting & Operational Guide

This document covers common operational scenarios, error handling, and recovery procedures.

---

## 1. OCI API Error Troubleshooting

### `OutOfHostCapacity` (HTTP 500)
- **Symptom:** The console or tool reports `Out of capacity for shape VM.Standard.A1.Flex in availability domain...`
- **Root Cause:** In high-demand regions like Hyderabad (`ap-hyderabad-1`), all physical Ampere A1 servers in the Always Free compute pool are currently allocated to active tenants.
- **Hunter Behavior:** The tool classifies the error as transient, applies exponential backoff with jitter (up to 60 minutes), records the failure in `state.json`, and continues monitoring patiently. When an existing user terminates their instance, the tool immediately captures the freed capacity.

### `NotAuthenticated` / 401 Unauthorized
- **Symptom:** `Authentication failed. Check your API key, user OCID, or fingerprint.`
- **Checklist:**
  1. Verify `~/.oci/config` contains valid `user`, `fingerprint`, `key_file`, and `tenancy`.
  2. Verify the private key file path exists and has read permissions.
  3. Verify the public key (`oci_api_key_public.pem`) was uploaded to your OCI User in Console: *Profile -> User Settings -> API Keys*.

### `LimitExceeded` (HTTP 400)
- **Symptom:** `The following service limits were exceeded: standard-a1-core-count...`
- **Root Cause:** Your tenancy already has instances consuming the 4 OCPU or 24 GB RAM limit, or another region is consuming tenancy limits.
- **Checklist:** Inspect active instances in OCI Console under *Compute -> Instances*. Terminate any stopped or unused A1 instances to restore your 4 OCPU / 24 GB allowance.

---

## 2. Arma Reforger Game Server Troubleshooting

### Server Not Appearing in Server Browser
- **Check Ports:** Verify OCI Security List allows `2001 UDP` and `17777 UDP`.
- **Check UFW:** On the server, run `sudo ufw status` and ensure `2001/udp` and `17777/udp` are allowed.
- **Check Service Status:** Run `sudo systemctl status reforger-server`.
- **Check Logs:** Run `sudo journalctl -u reforger-server -n 100 --no-pager`.

### RAM Consumption
- Arma Reforger dedicated server consumes ~3.5 GB on boot and 6–8 GB with 8 players and dynamic AI.
- Ensure the server has at least 8 GB of RAM allocated.
