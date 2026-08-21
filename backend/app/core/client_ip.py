import ipaddress
import os

from dotenv import load_dotenv
from fastapi import Request

TRUSTED_PROXIES_ENV = "TRUSTED_PROXIES"


def _trusted_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    load_dotenv()
    networks = []
    for entry in os.environ.get(TRUSTED_PROXIES_ENV, "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            continue
    return networks


def _is_trusted(address: str, networks) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in network for network in networks)


def client_ip(request: Request) -> str:
    client = request.client
    peer = client.host if client is not None else "unknown"
    networks = _trusted_networks()
    if not networks or not _is_trusted(peer, networks):
        return peer
    forwarded = [part.strip() for part in request.headers.get("x-forwarded-for", "").split(",") if part.strip()]
    for candidate in reversed(forwarded):
        if not _is_trusted(candidate, networks):
            return candidate
    return peer
