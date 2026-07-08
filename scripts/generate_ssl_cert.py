"""
Generate a self-signed SSL certificate for local / LAN mobile access.

Browsers block camera (getUserMedia) on HTTP except localhost.
Phones must open https://<PC-IP>:8443 to use the device camera.

Usage:
    python scripts/generate_ssl_cert.py
"""

from __future__ import annotations

import datetime
import ipaddress
import re
import socket
import subprocess
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parent.parent
CERTS_DIR = ROOT / "certs"
KEY_PATH = CERTS_DIR / "key.pem"
CERT_PATH = CERTS_DIR / "cert.pem"


def collect_local_ips() -> list[str]:
    """Collect LAN IPv4 addresses for the certificate SAN list."""
    ips: set[str] = {"127.0.0.1"}

    try:
        hostname = socket.gethostname()
        ips.add(socket.gethostbyname(hostname))
    except OSError:
        pass

    try:
        output = subprocess.check_output(
            ["ipconfig"],
            text=True,
            errors="ignore",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for line in output.splitlines():
            match = re.search(r"IPv4[^:]*:\s*(\d+\.\d+\.\d+\.\d+)", line)
            if match:
                ip = match.group(1)
                if not ip.startswith("169.254."):
                    ips.add(ip)
    except Exception:
        pass

    return sorted(ips)


def generate_cert() -> tuple[Path, Path]:
    CERTS_DIR.mkdir(parents=True, exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "UZ"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "FaceID Local"),
        x509.NameAttribute(NameOID.COMMON_NAME, "FaceID Attendance"),
    ])

    local_ips = collect_local_ips()
    san_entries: list[x509.GeneralName] = [
        x509.DNSName("localhost"),
        x509.DNSName(socket.gethostname()),
    ]

    for ip in local_ips:
        try:
            san_entries.append(x509.IPAddress(ipaddress.ip_address(ip)))
        except ValueError:
            pass

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .sign(key, hashes.SHA256())
    )

    KEY_PATH.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    CERT_PATH.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    return KEY_PATH, CERT_PATH


def main() -> int:
    key_path, cert_path = generate_cert()
    ips = collect_local_ips()

    print("SSL certificate generated:")
    print(f"  Key : {key_path}")
    print(f"  Cert: {cert_path}")
    print()
    print("Start HTTPS server:")
    print(
        "  .\\run_https.ps1"
    )
    print("  — or —")
    print(
        "  python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 "
        f"--ssl-keyfile {key_path} --ssl-certfile {cert_path} --reload"
    )
    print()
    print("Open on phone (same Wi-Fi, use HTTPS not HTTP):")
    for ip in ips:
        if ip != "127.0.0.1":
            print(f"  https://{ip}:8000")
    print()
    print("Accept the browser security warning (self-signed cert).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
