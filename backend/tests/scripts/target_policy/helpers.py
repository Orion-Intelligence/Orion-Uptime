from __future__ import annotations

import socket


def _addrinfo(*addresses):
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 0)) for address in addresses]
