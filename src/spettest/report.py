"""Форматування виводу українською та налаштування UTF-8 для Windows."""

from __future__ import annotations

import sys
from dataclasses import dataclass


def configure_console_utf8() -> None:
    """Увімкнути UTF-8 у stdout/stderr (кирилиця на Windows)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except Exception:
                pass


@dataclass(frozen=True)
class SpeedResult:
    download_mbps: float
    upload_mbps: float
    ping_ms: float


@dataclass(frozen=True)
class StableResult:
    duration_s: int
    ping_avg_ms: float
    ping_min_ms: float
    ping_max_ms: float
    jitter_ms: float
    loss_percent: float
    verdict: str


def print_info(message: str) -> None:
    print(message)


def print_error(message: str) -> None:
    print(f"Помилка: {message}", file=sys.stderr)


def print_speed(result: SpeedResult) -> None:
    print("=== Швидкість ===")
    print(f"Download:  {result.download_mbps:.1f} Мбіт/с")
    print(f"Upload:    {result.upload_mbps:.1f} Мбіт/с")
    print(f"Ping:      {result.ping_ms:.0f} мс")


def print_stable(result: StableResult) -> None:
    print("=== Стабільність ===")
    print(f"Тривалість: {result.duration_s} с")
    print(
        f"Ping:       {result.ping_avg_ms:.0f} мс "
        f"(мін {result.ping_min_ms:.0f}, макс {result.ping_max_ms:.0f})"
    )
    print(f"Jitter:     {result.jitter_ms:.1f} мс")
    print(f"Втрати:     {result.loss_percent:.1f}%")
    print(f"Стабільність: {result.verdict}")
