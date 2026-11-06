"""F1 — замір швидкості (download / upload / ping). Без виміру стабільності."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from spettest.errors import SpetTestError
from spettest.report import SpeedResult, print_info

DOWN_URL = "https://speed.cloudflare.com/__down"
UP_URL = "https://speed.cloudflare.com/__up"
LATENCY_URL = "https://speed.cloudflare.com/__down?bytes=0"

# Тривалість як у браузерних тестах: прогрів + вимірювальне вікно.
DOWNLOAD_THREADS = 8
UPLOAD_THREADS = 6
WARMUP_S = 2.0
MEASURE_S = 10.0
DOWN_CHUNK_BYTES = 25_000_000  # 25 МБ на запит; повторюємо до кінця вікна
UP_CHUNK_BYTES = 4_000_000  # менший шматок, щоб частіше потрапляти у вікно виміру
UP_CHUNK_BLOCK = 256 * 1024

CONNECT_TIMEOUT_S = 10
READ_TIMEOUT_S = 90
LATENCY_WARMUPS = 2
LATENCY_SAMPLES = 12
USER_AGENT = "SpetTest/0.1 (+portable speed test)"


def _friendly_network_error(exc: BaseException) -> SpetTestError:
    if isinstance(exc, requests.Timeout):
        return SpetTestError("Час очікування відповіді вичерпано. Перевірте з’єднання з інтернетом.")
    if isinstance(exc, requests.ConnectionError):
        return SpetTestError("Немає з’єднання з інтернетом або сервер недоступний.")
    if isinstance(exc, requests.RequestException):
        return SpetTestError("Помилка мережі під час заміру швидкості. Спробуйте ще раз.")
    return SpetTestError("Не вдалося виконати замір швидкості. Спробуйте ще раз.")


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def _measure_ping_ms(session: requests.Session) -> float:
    """HTTPS RTT після warmup. Беремо мінімум (ближче до «найкращого» ping)."""
    samples: list[float] = []
    try:
        for _ in range(LATENCY_WARMUPS):
            session.get(LATENCY_URL, timeout=(CONNECT_TIMEOUT_S, READ_TIMEOUT_S))
        for _ in range(LATENCY_SAMPLES):
            started = time.perf_counter()
            response = session.get(LATENCY_URL, timeout=(CONNECT_TIMEOUT_S, READ_TIMEOUT_S))
            response.raise_for_status()
            # З’їдаємо тіло (bytes=0 — майже порожнє), щоб не змішувати з наступним.
            _ = response.content
            samples.append((time.perf_counter() - started) * 1000.0)
    except requests.RequestException as exc:
        raise _friendly_network_error(exc) from exc

    if not samples:
        raise SpetTestError("Не вдалося виміряти затримку (ping).")
    # Після warmup — мінімум (типово для «ping» у HTTP-тестах).
    return float(min(samples))


def _download_worker(
    session: requests.Session,
    t0: float,
    measure_start: float,
    deadline: float,
    counter: list[int],
    lock: threading.Lock,
) -> None:
    """Качає чанками, поки не скінчиться загальний час; байти після warmup ідуть у лічильник."""
    url = f"{DOWN_URL}?bytes={DOWN_CHUNK_BYTES}"
    while time.perf_counter() < deadline:
        try:
            response = session.get(
                url,
                timeout=(CONNECT_TIMEOUT_S, READ_TIMEOUT_S),
                stream=True,
            )
            response.raise_for_status()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                now = time.perf_counter()
                if now >= deadline:
                    break
                if now >= measure_start:
                    with lock:
                        counter[0] += len(chunk)
        except requests.RequestException:
            # Одна невдала спроба не валить увесь тест — пробуємо далі до deadline.
            if time.perf_counter() >= deadline:
                break
            time.sleep(0.05)


def _upload_body(nbytes: int, deadline: float):
    """Генератор тіла upload; обривається по deadline."""
    sent = 0
    block = b"0" * UP_CHUNK_BLOCK
    while sent < nbytes and time.perf_counter() < deadline:
        left = min(UP_CHUNK_BLOCK, nbytes - sent)
        yield block if left == UP_CHUNK_BLOCK else block[:left]
        sent += left


def _upload_worker(
    session: requests.Session,
    t0: float,
    measure_start: float,
    deadline: float,
    counter: list[int],
    lock: threading.Lock,
) -> None:
    while time.perf_counter() < deadline:
        try:
            before = time.perf_counter()
            response = session.post(
                UP_URL,
                data=_upload_body(UP_CHUNK_BYTES, deadline),
                headers={"Content-Type": "application/octet-stream"},
                timeout=(CONNECT_TIMEOUT_S, READ_TIMEOUT_S),
            )
            response.raise_for_status()
            after = time.perf_counter()
            # У вимірювальне вікно зараховуємо лише перетин [measure_start, deadline].
            overlap_start = max(before, measure_start)
            overlap_end = min(after, deadline)
            if overlap_end > overlap_start and after > before:
                fraction = (overlap_end - overlap_start) / (after - before)
                credited = int(UP_CHUNK_BYTES * fraction)
                if credited > 0:
                    with lock:
                        counter[0] += credited
        except requests.RequestException:
            if time.perf_counter() >= deadline:
                break
            time.sleep(0.05)


def _timed_parallel_transfer(label: str, worker, threads: int) -> float:
    """
    Паралельні потоки протягом WARMUP+MEASURE секунд.
    Швидкість рахується лише за MEASURE_S після прогріву (насичення TCP).
    """
    total_s = WARMUP_S + MEASURE_S
    print_info(f"  {label} (~{total_s:.0f} с, {threads} потоків)…")

    sessions = [_session() for _ in range(threads)]
    counter = [0]
    lock = threading.Lock()
    t0 = time.perf_counter()
    measure_start = t0 + WARMUP_S
    deadline = t0 + total_s

    try:
        with ThreadPoolExecutor(max_workers=threads) as pool:
            futures = [
                pool.submit(worker, sessions[i], t0, measure_start, deadline, counter, lock)
                for i in range(threads)
            ]
            errors: list[BaseException] = []
            for future in as_completed(futures):
                exc = future.exception()
                if exc is not None:
                    errors.append(exc)
            # Якщо жоден байт не зараховано і були винятки — показуємо мережеву помилку.
            if counter[0] <= 0 and errors:
                raise _friendly_network_error(errors[0])
    finally:
        for session in sessions:
            session.close()

    if counter[0] <= 0:
        raise SpetTestError(f"Не вдалося виміряти {label.lower()}.")

    # Час виміру фіксований MEASURE_S (не wall clock усього тесту).
    return (counter[0] * 8) / MEASURE_S / 1_000_000


def run_speed_test() -> SpeedResult:
    """Download + upload + ping. Джиттер / втрати тут не рахуються."""
    print_info("  Ping…")
    with _session() as session:
        ping_ms = _measure_ping_ms(session)

    download_mbps = _timed_parallel_transfer("Download", _download_worker, DOWNLOAD_THREADS)
    upload_mbps = _timed_parallel_transfer("Upload", _upload_worker, UPLOAD_THREADS)

    return SpeedResult(
        download_mbps=download_mbps,
        upload_mbps=upload_mbps,
        ping_ms=ping_ms,
    )
