import asyncio
import ipaddress
import os
import socket
from urllib.parse import urlsplit

from dotenv import load_dotenv

from orion.constants.constant import AllowedValues, EnvVars
from orion.shared_models.exceptions import ValidationError



def private_targets_allowed() -> bool:
    load_dotenv()
    return os.environ.get(EnvVars.ALLOW_PRIVATE_TARGETS, "false").strip().lower() in {"1", "true", "yes"}


def _is_public_address(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified)


async def _resolved_addresses(host: str) -> list[str]:
    try:
        ipaddress.ip_address(host)
        return [host]
    except ValueError:
        pass
    loop = asyncio.get_running_loop()
    try:
        results = await loop.run_in_executor(None, lambda: socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP))
    except socket.gaierror:
        return []
    return sorted({str(result[4][0]) for result in results})


async def validate_target_host(host: str) -> None:
    host = host.strip().strip("[]")
    if not host:
        raise ValidationError("A target host is required.")
    if private_targets_allowed():
        return
    addresses = await _resolved_addresses(host)
    blocked = [address for address in addresses if not _is_public_address(address)]
    if blocked:
        raise ValidationError(f"Target '{host}' resolves to a private or internal address ({', '.join(blocked)}), which this deployment does not allow monitoring.")


async def validate_target_url(url: str) -> None:
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in AllowedValues.MONITOR_SCHEMES:
        raise ValidationError("Monitor URLs must use http or https.")
    if not parts.hostname:
        raise ValidationError("Monitor URLs must include a host.")
    if parts.username or parts.password:
        raise ValidationError("Monitor URLs must not embed credentials.")
    await validate_target_host(parts.hostname)
