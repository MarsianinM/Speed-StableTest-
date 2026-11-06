"""Діагностика «підвисань»: міряє паузи між callback прогресу.

Запуск з кореня репозиторію:
  $env:PYTHONPATH = "src"
  python scripts/check_progress_gaps.py
  python scripts/check_progress_gaps.py stable 15
"""

from __future__ import annotations

import statistics
import sys
import time


def main() -> int:
    sys.path.insert(0, "src")
    from spettest.speed import run_speed_test
    from spettest.stable import run_stable_test

    mode = sys.argv[1] if len(sys.argv) > 1 else "pingish"
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 12

    stamps: list[float] = []
    events: list[str] = []

    def on_progress(stage: str, *, progress=None, mbps=None, detail: str = "") -> None:
        now = time.perf_counter()
        stamps.append(now)
        gap = 0.0 if len(stamps) < 2 else now - stamps[-2]
        line = f"+{gap:5.2f}s  {stage:14}  p={progress!s:>6}  {detail}"
        if mbps is not None:
            line += f"  {mbps:.1f} Mbps"
        events.append(line)
        print(line)

    print(f"=== check_progress_gaps mode={mode} ===")
    t0 = time.perf_counter()
    if mode == "stable":
        run_stable_test(duration, on_progress=on_progress)
    else:
        # Повний speed дає і ping, і download/upload.
        run_speed_test(on_progress=on_progress)
    total = time.perf_counter() - t0

    gaps = [stamps[i] - stamps[i - 1] for i in range(1, len(stamps))]
    if not gaps:
        print("Немає подій прогресу.")
        return 1

    print("---")
    print(f"Подій: {len(stamps)}, тривалість тесту: {total:.1f} с")
    print(f"Пауза між оновленнями: мін {min(gaps):.2f} с, "
          f"медіана {statistics.median(gaps):.2f} с, макс {max(gaps):.2f} с")
    if max(gaps) > 2.0:
        print("УВАГА: є пауза > 2 с — у GUI це відчувається як підвисання.")
    else:
        print("Ок: великих пауз (>2 с) між оновленнями немає.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
