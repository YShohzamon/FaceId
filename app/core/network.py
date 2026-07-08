"""Helpers for detecting local network addresses."""

from __future__ import annotations

import re
import socket
import subprocess


def get_wifi_ipv4_addresses() -> list[str]:
    """Return likely Wi-Fi/LAN IPv4 addresses (excludes localhost and Docker)."""
    ips: set[str] = set()

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
            if not match:
                continue
            ip = match.group(1)
            if ip.startswith("127.") or ip.startswith("169.254."):
                continue
            if ip.startswith("172.29.") or ip.startswith("172.17."):
                continue
            ips.add(ip)
    except Exception:
        pass

    return sorted(ips)
