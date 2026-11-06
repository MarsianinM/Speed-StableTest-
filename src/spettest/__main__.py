"""Точка входу: без аргументів → GUI; speed | stable → CLI."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from spettest.errors import SpetTestError
from spettest.netinfo import fetch_public_ip
from spettest.report import (
    configure_console_utf8,
    print_error,
    print_info,
    print_public_ip,
    print_speed,
    print_stable,
)
from spettest.speed import run_speed_test
from spettest.stable import DEFAULT_DURATION_S, run_stable_test
from spettest.storage import save_speed, save_stable


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


def _run_cli(argv: Sequence[str]) -> int:
    configure_console_utf8()
    parser = _build_parser()
    args = parser.parse_args(list(argv))

    try:
        if args.command == "speed":
            print_info("Замір швидкості…")
            public_ip = fetch_public_ip()
            print_public_ip(public_ip)
            result = run_speed_test()
            print_speed(result)
            try:
                save_speed(result, public_ip)
                print_info("Результат збережено в локальну історію.")
            except Exception:
                print_info("Не вдалося зберегти результат у історію (файл БД).")
            return 0

        if args.command == "stable":
            if args.seconds <= 0:
                raise SpetTestError("Тривалість має бути додатним числом секунд.")
            print_info(f"Перевірка стабільності ({args.seconds} с)…")
            public_ip = fetch_public_ip()
            print_public_ip(public_ip)
            result = run_stable_test(args.seconds)
            print_stable(result)
            try:
                save_stable(result, public_ip)
                print_info("Результат збережено в локальну історію.")
            except Exception:
                print_info("Не вдалося зберегти результат у історію (файл БД).")
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


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    if not args:
        from spettest.gui import run_gui

        run_gui()
        return 0
    return _run_cli(args)


if __name__ == "__main__":
    sys.exit(main())
