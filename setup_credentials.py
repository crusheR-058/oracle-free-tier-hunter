"""
Helper script to generate OCI RSA API Key Pair and initialize ~/.oci/config.
"""

from pathlib import Path
import sys
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate_oci_keys():
    oci_dir = Path.home() / ".oci"
    oci_dir.mkdir(parents=True, exist_ok=True)

    priv_key_path = oci_dir / "oci_api_key.pem"
    pub_key_path = oci_dir / "oci_api_key_public.pem"
    config_path = oci_dir / "config"

    print("=======================================================================")
    print("           ORACLE CLOUD API CREDENTIALS SETUP ASSISTANT                ")
    print("=======================================================================\n")

    if not priv_key_path.exists():
        print(f"[1/3] Generating 2048-bit RSA key pair in {oci_dir}...")
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend(),
        )

        # Serialize private key
        priv_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        with open(priv_key_path, "wb") as f:
            f.write(priv_pem)

        # Serialize public key
        public_key = private_key.public_key()
        pub_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        with open(pub_key_path, "wb") as f:
            f.write(pub_pem)

        print(f"      Private key saved: {priv_key_path}")
        print(f"      Public key saved:  {pub_key_path}")
    else:
        print(f"[1/3] Key pair already exists at {priv_key_path}.")
        with open(pub_key_path, "rb") as f:
            pub_pem = f.read()

    print("\n[2/3] Upload your Public Key to Oracle Cloud Console:")
    print("      1. Log in to https://cloud.oracle.com")
    print("      2. In the top-right corner, click your User Profile icon -> 'My Profile' (or 'User Settings')")
    print("      3. On the left menu, click 'API Keys' -> 'Add API Key'")
    print("      4. Select 'Paste Public Key' and paste the block below:\n")
    print("------------------------- COPY PUBLIC KEY BELOW -------------------------")
    print(pub_pem.decode("utf-8").strip())
    print("-------------------------------------------------------------------------\n")

    print("[3/3] Configure ~/.oci/config:")
    print("      After clicking 'Add' in Oracle Cloud Console, Oracle will display")
    print("      a 'Configuration File' snippet with your user OCID, fingerprint, and tenancy OCID.")
    print(f"      Paste that snippet into: {config_path}\n")

    if not config_path.exists():
        template = f"""[DEFAULT]
user=ocid1.user.oc1..<REPLACE_WITH_YOUR_USER_OCID>
fingerprint=<REPLACE_WITH_FINGERPRINT_FROM_CONSOLE>
key_file={priv_key_path}
tenancy=ocid1.tenancy.oc1..<REPLACE_WITH_YOUR_TENANCY_OCID>
region=ap-hyderabad-1
"""
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(template)
        print(f"      Template config file generated at: {config_path}")
        print("      Open that file and fill in your user, fingerprint, and tenancy values.")
    else:
        print(f"      Existing config file found at: {config_path}")


if __name__ == "__main__":
    generate_oci_keys()
