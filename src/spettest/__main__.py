"""Точка входу CLI: speed | stable [seconds]."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from spettest.errors import SpetTestError
from spettest.report import (
    configure_console_utf8,
    print_error,
    print_info,
    print_speed,
    print_stable,
)
from spettest.speed import run_speed_test
from spettest.stable import DEFAULT_DURATION_S, run_stable_test


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spettest",
        description="Портативний замір швидкості та стабільності інтернету.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("speed", help="Замір швидкості (download / upload / ping)")

    stable = sub.add_parser("stable", help="Перевірка стабільності каналу")
    stable.add_argument(
        "seconds",
        nargs="?",
        type=int,
        default=DEFAULT_DURATION_S,
        help=f"Тривалість у секундах (типово {DEFAULT_DURATION_S})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    configure_console_utf8()
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        if args.command == "speed":
            print_info("Замір швидкості…")
            print_speed(run_speed_test())
            return 0

        if args.command == "stable":
            if args.seconds <= 0:
                raise SpetTestError("Тривалість має бути додатним числом секунд.")
            print_info(f"Перевірка стабільності ({args.seconds} с)…")
            print_stable(run_stable_test(args.seconds))
            return 0

        print_error("Невідома команда.")
        return 2

    except SpetTestError as exc:
        print_error(exc.message)
        return 1
    except KeyboardInterrupt:
        print_error("Перервано користувачем.")
        return 130
    except Exception:
        print_error("Неочікувана помилка. Перевірте з’єднання з інтернетом і спробуйте ще раз.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
