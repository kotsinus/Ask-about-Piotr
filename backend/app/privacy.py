# Copyright 2026 Piotr Synak
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Purpose:
# Privacy helpers for client metadata.
#
# Notes:
# - MUST NOT persist raw IPs.
# - X-Forwarded-For is honored only when a trusted proxy CIDR list is configured
#   AND the immediate peer (request.client.host) matches that list.

from __future__ import annotations

import hashlib
import ipaddress
from collections.abc import Iterable

from fastapi import Request

from app.config import Settings


def hash_ip(*, ip: str, salt: str) -> str:
    data = (salt + ip).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def anonymize_ip_prefix(ip: str) -> str | None:
    """Return an anonymized prefix string: IPv4 /24, IPv6 /48."""

    try:
        ip_obj = ipaddress.ip_address(ip)
    except ValueError:
        return None

    if isinstance(ip_obj, ipaddress.IPv4Address):
        net = ipaddress.ip_network(f"{ip_obj}/24", strict=False)
        return str(net)

    net = ipaddress.ip_network(f"{ip_obj}/48", strict=False)
    return str(net)


def _parse_trusted_proxies(cidrs: Iterable[str]) -> list[ipaddress._BaseNetwork]:
    networks: list[ipaddress._BaseNetwork] = []
    for item in cidrs:
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            continue
    return networks


def _is_trusted_proxy(peer_ip: str, trusted_proxy_cidrs: list[str]) -> bool:
    if not trusted_proxy_cidrs:
        return False
    try:
        peer = ipaddress.ip_address(peer_ip)
    except ValueError:
        return False
    for net in _parse_trusted_proxies(trusted_proxy_cidrs):
        if peer in net:
            return True
    return False


def _parse_x_forwarded_for(value: str) -> list[str]:
    # Standard: comma-separated list, left-most is original client.
    parts = [part.strip() for part in (value or "").split(",")]
    return [part for part in parts if part]


def extract_client_ip(request: Request, settings: Settings) -> str | None:
    """Extract client IP, honoring proxy headers only when explicitly trusted."""

    peer_ip = request.client.host if request.client else None
    if not peer_ip:
        return None

    if _is_trusted_proxy(peer_ip, settings.trusted_proxy_cidrs):
        xff = request.headers.get("x-forwarded-for")
        if xff:
            candidates = _parse_x_forwarded_for(xff)
            if candidates:
                # We intentionally do not attempt deep validation here beyond
                # ipaddress parsing; if parsing fails, fall back to peer_ip.
                candidate = candidates[0]
                try:
                    ipaddress.ip_address(candidate)
                except ValueError:
                    return peer_ip
                return candidate

    return peer_ip
