"""Визначення публічного IP провайдера (без API-ключа)."""

from __future__ import annotations

import re

import requests

TRACE_URL = "https://1.1.1.1/cdn-cgi/trace"
CONNECT_TIMEOUT_S = 5
READ_TIMEOUT_S = 5
USER_AGENT = "SpetTest/0.1 (+portable netinfo)"
_IP_RE = re.compile(r"^ip=(.+)$", re.MULTILINE)


def fetch_public_ip() -> str | None:
    """
    Повернути публічний IP або None, якщо визначити не вдалося.
    Не кидає виняток користувачу — виклик опційний для історії/GUI.
    """
    try:
        response = requests.get(
            TRACE_URL,
            timeout=(CONNECT_TIMEOUT_S, READ_TIMEOUT_S),
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
        match = _IP_RE.search(response.text)
        if not match:
            return None
        ip = match.group(1).strip()
        return ip or None
    except requests.RequestException:
        return None
