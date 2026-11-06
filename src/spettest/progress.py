"""Спільний callback прогресу для CLI та GUI."""

from __future__ import annotations

from typing import Callable, Protocol


class ProgressCallback(Protocol):
    def __call__(
        self,
        stage: str,
        *,
        progress: float | None = None,
        mbps: float | None = None,
        detail: str = "",
    ) -> None: ...


def default_console_progress(
    stage: str,
    *,
    progress: float | None = None,
    mbps: float | None = None,
    detail: str = "",
) -> None:
    from spettest.report import print_info

    parts = [f"  {stage}"]
    if detail:
        parts.append(detail)
    if mbps is not None:
        parts.append(f"{mbps:.1f} Мбіт/с")
    if progress is not None:
        parts.append(f"{int(progress * 100)}%")
    print_info(" · ".join(parts))


OnProgress = Callable[..., None]
