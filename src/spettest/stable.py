"""F2 — перевірка стабільності каналу (HTTPS latency, без download/upload)."""

from __future__ import annotations

import time

import requests

from spettest.errors import SpetTestError
from spettest.report import StableResult, print_info

DEFAULT_DURATION_S = 60
LATENCY_URL = "https://speed.cloudflare.com/__down?bytes=0"
SAMPLE_INTERVAL_S = 0.5
CONNECT_TIMEOUT_S = 5
READ_TIMEOUT_S = 5
USER_AGENT = "SpetTest/0.1 (+portable stability test)"

# Пороги вердикту (ТЗ §5.2)
GOOD_LOSS_PCT = 1.0
GOOD_JITTER_MS = 10.0
GOOD_PING_MS = 50.0
OK_LOSS_PCT = 5.0
OK_JITTER_MS = 30.0
OK_PING_MS = 100.0


def _friendly_network_error(exc: BaseException) -> SpetTestError:
    if isinstance(exc, requests.Timeout):
        return SpetTestError("Час очікування відповіді вичерпано. Перевірте з’єднання з інтернетом.")
    if isinstance(exc, requests.ConnectionError):
        return SpetTestError("Немає з’єднання з інтернетом або сервер недоступний.")
    if isinstance(exc, requests.RequestException):
        return SpetTestError("Помилка мережі під час перевірки стабільності. Спробуйте ще раз.")
    return SpetTestError("Не вдалося виконати перевірку стабільності. Спробуйте ще раз.")


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def _one_latency_ms(session: requests.Session) -> float | None:
    """Один короткий HTTPS GET. None = втрата / помилка спроби."""
    try:
        started = time.perf_counter()
        response = session.get(
            LATENCY_URL,
            timeout=(CONNECT_TIMEOUT_S, READ_TIMEOUT_S),
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if response.status_code >= 400:
            return None
        return elapsed_ms
    except requests.RequestException:
        return None


def _rfc3550_jitter_ms(samples_ms: list[float]) -> float:
    """
    Jitter за RFC 3550:
    J = J + (|D(i-1,i)| - J) / 16,
    де D ≈ різниця RTT сусідніх успішних замірів.
    """
    if len(samples_ms) < 2:
        return 0.0
    jitter = 0.0
    prev = samples_ms[0]
    for current in samples_ms[1:]:
        d = abs(current - prev)
        jitter += (d - jitter) / 16.0
        prev = current
    return jitter


def _verdict(loss_percent: float, jitter_ms: float, ping_avg_ms: float) -> str:
    if (
        loss_percent <= GOOD_LOSS_PCT
        and jitter_ms <= GOOD_JITTER_MS
        and ping_avg_ms <= GOOD_PING_MS
    ):
        return "добра"
    if (
        loss_percent <= OK_LOSS_PCT
        and jitter_ms <= OK_JITTER_MS
        and ping_avg_ms <= OK_PING_MS
    ):
        return "помірна"
    return "погана"


def run_stable_test(duration_s: int = DEFAULT_DURATION_S) -> StableResult:
    """Серія HTTPS-замірів затримки. Без ICMP і без великих download/upload."""
    if duration_s <= 0:
        raise SpetTestError("Тривалість має бути додатним числом секунд.")

    successes: list[float] = []
    attempts = 0
    deadline = time.perf_counter() + duration_s
    last_progress_bucket = -1

    with _session() as session:
        # Warm-up: встановлюємо TCP/TLS, щоб серія міряла канал, а не хендшейк.
        try:
            warm = session.get(
                LATENCY_URL,
                timeout=(CONNECT_TIMEOUT_S, READ_TIMEOUT_S),
            )
            warm.raise_for_status()
        except requests.RequestException as exc:
            raise _friendly_network_error(exc) from exc

        print_info(f"  Збір замірів протягом {duration_s} с…")

        while True:
            now = time.perf_counter()
            if now >= deadline:
                break

            attempts += 1
            sample = _one_latency_ms(session)
            if sample is not None:
                successes.append(sample)

            elapsed = int(now - (deadline - duration_s))
            bucket = elapsed // 5
            if bucket > last_progress_bucket and elapsed > 0:
                last_progress_bucket = bucket
                print_info(
                    f"  …{min(elapsed, duration_s)}/{duration_s} с, "
                    f"успішних {len(successes)}/{attempts}"
                )

            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                break
            time.sleep(min(SAMPLE_INTERVAL_S, remaining))

    if attempts == 0:
        raise SpetTestError("Не вдалося виконати жодної спроби заміру.")

    loss_percent = (attempts - len(successes)) / attempts * 100.0

    if not successes:
        raise SpetTestError(
            "Усі спроби заміру затримки невдалі. Перевірте з’єднання з інтернетом."
        )

    ping_avg = sum(successes) / len(successes)
    ping_min = min(successes)
    ping_max = max(successes)
    jitter = _rfc3550_jitter_ms(successes)
    verdict = _verdict(loss_percent, jitter, ping_avg)

    return StableResult(
        duration_s=duration_s,
        ping_avg_ms=ping_avg,
        ping_min_ms=ping_min,
        ping_max_ms=ping_max,
        jitter_ms=jitter,
        loss_percent=loss_percent,
        verdict=verdict,
    )
