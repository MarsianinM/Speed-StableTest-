"""F1 — замір швидкості (download / upload / ping). Без виміру стабільності."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait

import requests

from spettest.errors import SpetTestError
from spettest.progress import OnProgress, default_console_progress
from spettest.report import SpeedResult

DOWN_URL = "https://speed.cloudflare.com/__down"
UP_URL = "https://speed.cloudflare.com/__up"
LATENCY_URL = "https://speed.cloudflare.com/__down?bytes=0"

DOWNLOAD_THREADS = 8
UPLOAD_THREADS = 6
WARMUP_S = 2.0
MEASURE_S = 10.0
# Після дедлайну ще трохи чекаємо завершення потоків, далі — примусово закриваємо.
PHASE_GRACE_S = 1.0

DOWN_CHUNK_BYTES = 25_000_000
# Помірні шматки upload: без довгого POST після дедлайну, але з нормальним насиченням.
UP_CHUNK_BYTES = 1_000_000
UP_CHUNK_BLOCK = 64 * 1024
UP_MIN_REMAINING_S = 0.3

CONNECT_TIMEOUT_S = 10
READ_TIMEOUT_S = 90
UPLOAD_CONNECT_TIMEOUT_S = 5
UPLOAD_READ_TIMEOUT_S = 8
PING_CONNECT_TIMEOUT_S = 2
PING_READ_TIMEOUT_S = 2
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


def _measure_ping_ms(
    session: requests.Session,
    on_progress: OnProgress | None = None,
) -> float:
    """Кілька HTTPS RTT з проміжним прогресом (щоб GUI не виглядав «завислим»)."""
    samples: list[float] = []
    total_steps = LATENCY_WARMUPS + LATENCY_SAMPLES
    try:
        for i in range(LATENCY_WARMUPS):
            if on_progress:
                on_progress(
                    "Ping",
                    progress=0.02 + 0.08 * (i / max(total_steps, 1)),
                    mbps=None,
                    detail=f"прогрів {i + 1}/{LATENCY_WARMUPS}",
                )
            session.get(
                LATENCY_URL,
                timeout=(PING_CONNECT_TIMEOUT_S, PING_READ_TIMEOUT_S),
            )
        for i in range(LATENCY_SAMPLES):
            started = time.perf_counter()
            response = session.get(
                LATENCY_URL,
                timeout=(PING_CONNECT_TIMEOUT_S, PING_READ_TIMEOUT_S),
            )
            response.raise_for_status()
            _ = response.content
            sample_ms = (time.perf_counter() - started) * 1000.0
            samples.append(sample_ms)
            if on_progress:
                step = LATENCY_WARMUPS + i + 1
                on_progress(
                    "Ping",
                    progress=0.02 + 0.12 * (step / max(total_steps, 1)),
                    mbps=None,
                    detail=f"зразок {i + 1}/{LATENCY_SAMPLES} · {sample_ms:.0f} мс",
                )
    except requests.RequestException as exc:
        raise _friendly_network_error(exc) from exc

    if not samples:
        raise SpetTestError("Не вдалося виміряти затримку (ping).")
    return float(min(samples))


def _download_worker(
    session: requests.Session,
    t0: float,
    measure_start: float,
    deadline: float,
    counter: list[int],
    lock: threading.Lock,
) -> None:
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
            if time.perf_counter() >= deadline:
                break
        except requests.RequestException:
            if time.perf_counter() >= deadline:
                break
            time.sleep(0.05)


def _upload_body(nbytes: int, deadline: float, sent_holder: list[int]):
    sent = 0
    block = b"0" * UP_CHUNK_BLOCK
    while sent < nbytes and time.perf_counter() < deadline:
        left = min(UP_CHUNK_BLOCK, nbytes - sent)
        yield block if left == UP_CHUNK_BLOCK else block[:left]
        sent += left
        sent_holder[0] = sent


def _upload_worker(
    session: requests.Session,
    t0: float,
    measure_start: float,
    deadline: float,
    counter: list[int],
    lock: threading.Lock,
) -> None:
    """Короткі POST; не стартуємо новий, якщо часу майже не лишилось."""
    while True:
        remaining = deadline - time.perf_counter()
        if remaining < UP_MIN_REMAINING_S:
            break
        try:
            before = time.perf_counter()
            sent_holder = [0]
            # Таймаут лише трохи довший за залишок фази — без очікування 90 с.
            read_timeout = max(1.0, min(UPLOAD_READ_TIMEOUT_S, remaining + PHASE_GRACE_S))
            response = session.post(
                UP_URL,
                data=_upload_body(UP_CHUNK_BYTES, deadline, sent_holder),
                headers={"Content-Type": "application/octet-stream"},
                timeout=(UPLOAD_CONNECT_TIMEOUT_S, read_timeout),
            )
            response.raise_for_status()
            after = time.perf_counter()
            sent = sent_holder[0]
            if sent <= 0:
                continue
            # Зараховуємо лише байти в межах вікна виміру.
            overlap_start = max(before, measure_start)
            overlap_end = min(after, deadline)
            if overlap_end > overlap_start and after > before:
                fraction = (overlap_end - overlap_start) / (after - before)
                credited = int(sent * fraction)
                if credited > 0:
                    with lock:
                        counter[0] += credited
        except requests.RequestException:
            if time.perf_counter() >= deadline:
                break
            time.sleep(0.05)


def _timed_parallel_transfer(
    label: str,
    worker,
    threads: int,
    on_progress: OnProgress,
) -> float:
    total_s = WARMUP_S + MEASURE_S
    on_progress(label, progress=0.0, mbps=None, detail=f"~{total_s:.0f} с, {threads} потоків")

    sessions = [_session() for _ in range(threads)]
    counter = [0]
    lock = threading.Lock()
    t0 = time.perf_counter()
    measure_start = t0 + WARMUP_S
    deadline = t0 + total_s
    hard_stop = deadline + PHASE_GRACE_S
    stop = threading.Event()

    def _reporter() -> None:
        while not stop.wait(0.4):
            now = time.perf_counter()
            frac = min(1.0, max(0.0, (now - t0) / total_s))
            measured = max(0.0, min(now, deadline) - measure_start)
            with lock:
                bytes_now = counter[0]
            mbps = None
            if measured > 0.3 and bytes_now > 0:
                mbps = (bytes_now * 8) / measured / 1_000_000
            on_progress(label, progress=frac, mbps=mbps, detail="")

    reporter = threading.Thread(target=_reporter, daemon=True)
    reporter.start()

    pool = ThreadPoolExecutor(max_workers=threads)
    errors: list[BaseException] = []
    try:
        futures = [
            pool.submit(worker, sessions[i], t0, measure_start, deadline, counter, lock)
            for i in range(threads)
        ]
        pending = set(futures)
        # Чекаємо максимум до hard_stop — upload більше не «тягне» фазу.
        while pending and time.perf_counter() < hard_stop:
            done, pending = wait(pending, timeout=0.2)
            for future in done:
                exc = future.exception()
                if exc is not None:
                    errors.append(exc)
        # Обриваємо з’єднання, щоб звільнити потоки, що ще в POST/GET.
        for session in sessions:
            try:
                session.close()
            except Exception:
                pass
        if counter[0] <= 0 and errors:
            raise _friendly_network_error(errors[0])
    finally:
        stop.set()
        reporter.join(timeout=1.0)
        pool.shutdown(wait=False, cancel_futures=True)
        for session in sessions:
            try:
                session.close()
            except Exception:
                pass

    if counter[0] <= 0:
        raise SpetTestError(f"Не вдалося виміряти {label.lower()}.")

    # Швидкість завжди відносно фіксованого MEASURE_S (не wall-clock з хвостиком).
    mbps = (counter[0] * 8) / MEASURE_S / 1_000_000
    on_progress(label, progress=1.0, mbps=mbps, detail="готово")
    return mbps


def run_speed_test(on_progress: OnProgress | None = None) -> SpeedResult:
    """Download + upload + ping. Джиттер / втрати тут не рахуються."""
    progress = on_progress or default_console_progress

    progress("Ping", progress=0.02, mbps=None, detail="старт")
    with _session() as session:
        ping_ms = _measure_ping_ms(session, on_progress=progress)
    progress("Ping", progress=0.15, mbps=None, detail=f"готово · {ping_ms:.0f} мс")

    download_mbps = _timed_parallel_transfer(
        "Download", _download_worker, DOWNLOAD_THREADS, progress
    )
    upload_mbps = _timed_parallel_transfer(
        "Upload", _upload_worker, UPLOAD_THREADS, progress
    )

    return SpeedResult(
        download_mbps=download_mbps,
        upload_mbps=upload_mbps,
        ping_ms=ping_ms,
    )
