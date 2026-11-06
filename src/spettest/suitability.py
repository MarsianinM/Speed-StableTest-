"""v2.1 — придатність каналу для типових онлайн-задач (ТЗ F7)."""

from __future__ import annotations

from dataclasses import dataclass

from spettest.report import SpeedResult, StableResult

Status = str  # ОКЧАТНО | СУМНІВНО | НІ

# HTTPS ping: лише попередження / м'яке зниження, ніколи самостійне «НІ».
PING_WARN_MS = 100.0
PING_SOFT_DOWNGRADE_MS = 150.0

PING_NOTE = (
    "Ping у нас через HTTPS і зазвичай вищий за ICMP / у грі — це попередження, не вирок."
)


@dataclass(frozen=True)
class TaskVerdict:
    name: str
    status: Status
    reason: str


@dataclass(frozen=True)
class SuitabilityReport:
    tasks: list[TaskVerdict]
    ping_warning: str | None
    incomplete_note: str | None


def _worse(a: Status, b: Status) -> Status:
    order = {"ОКЧАТНО": 0, "СУМНІВНО": 1, "НІ": 2}
    return a if order[a] >= order[b] else b


def _apply_ping_soft(
    status: Status,
    ping_ms: float | None,
    reasons: list[str],
) -> Status:
    """Ping не ставить НІ; може знизити ОКЧАТНО → СУМНІВНО і додати попередження."""
    if ping_ms is None:
        return status
    if ping_ms >= PING_SOFT_DOWNGRADE_MS:
        reasons.append(f"HTTPS-ping {ping_ms:.0f} мс (завищений замір — лише попередження)")
        if status == "ОКЧАТНО":
            return "СУМНІВНО"
    elif ping_ms >= PING_WARN_MS:
        reasons.append(f"HTTPS-ping {ping_ms:.0f} мс (попередження, не заборона)")
    return status


def _ping_value(speed: SpeedResult | None, stable: StableResult | None) -> float | None:
    if speed is not None:
        return speed.ping_ms
    if stable is not None:
        return stable.ping_avg_ms
    return None


def _video_call(speed: SpeedResult | None, stable: StableResult | None) -> TaskVerdict:
    reasons: list[str] = []
    status: Status = "СУМНІВНО"

    if speed is None:
        return TaskVerdict(
            "Відеодзвінок",
            "СУМНІВНО",
            "немає заміру швидкості (потрібен upload) · оцінка неповна",
        )

    up = speed.upload_mbps
    if up < 1.5:
        status = "НІ"
        reasons.append(f"upload {up:.1f} < 1.5 Мбіт/с")
    elif up < 3.0:
        status = "СУМНІВНО"
        reasons.append(f"upload {up:.1f} Мбіт/с (бажано ≥ 3)")
    else:
        status = "ОКЧАТНО"
        reasons.append(f"upload {up:.1f} Мбіт/с")

    if stable is None:
        reasons.append("немає стабільності — оцінка неповна")
        if status == "ОКЧАТНО":
            status = "СУМНІВНО"
    else:
        if stable.loss_percent > 3.0:
            status = "НІ"
            reasons.append(f"втрати {stable.loss_percent:.1f}%")
        elif stable.loss_percent > 2.0 or stable.jitter_ms > 30.0:
            status = _worse(status, "СУМНІВНО")
            reasons.append(
                f"jitter {stable.jitter_ms:.1f} / втрати {stable.loss_percent:.1f}%"
            )
        else:
            reasons.append(
                f"jitter {stable.jitter_ms:.1f}, втрати {stable.loss_percent:.1f}%"
            )

    status = _apply_ping_soft(status, _ping_value(speed, stable), reasons)
    return TaskVerdict("Відеодзвінок", status, " · ".join(reasons))


def _stream(speed: SpeedResult | None, stable: StableResult | None) -> TaskVerdict:
    reasons: list[str] = []
    if speed is None:
        return TaskVerdict(
            "Стрім",
            "СУМНІВНО",
            "немає заміру швидкості (потрібен upload) · оцінка неповна",
        )

    up = speed.upload_mbps
    if up < 4.0:
        status: Status = "НІ"
        reasons.append(f"upload {up:.1f} < 4 Мбіт/с")
    elif up < 6.0:
        status = "СУМНІВНО"
        reasons.append(f"upload {up:.1f} Мбіт/с (слабо для 720p)")
    elif up < 10.0:
        status = "ОКЧАТНО"
        reasons.append(f"upload {up:.1f} Мбіт/с ≈ 720p")
    else:
        status = "ОКЧАТНО"
        reasons.append(f"upload {up:.1f} Мбіт/с ≈ 1080p")

    if stable is None:
        reasons.append("немає стабільності — оцінка неповна")
        if status == "ОКЧАТНО":
            status = "СУМНІВНО"
    else:
        if stable.loss_percent > 3.0:
            status = "НІ"
            reasons.append(f"втрати {stable.loss_percent:.1f}%")
        elif stable.loss_percent > 1.0 or stable.jitter_ms > 30.0:
            status = _worse(status, "СУМНІВНО")
            reasons.append(
                f"jitter {stable.jitter_ms:.1f} / втрати {stable.loss_percent:.1f}%"
            )
        else:
            reasons.append("стабільність ок для стріму")

    status = _apply_ping_soft(status, _ping_value(speed, stable), reasons)
    return TaskVerdict("Стрім", status, " · ".join(reasons))


def _watch_video(speed: SpeedResult | None, stable: StableResult | None) -> TaskVerdict:
    reasons: list[str] = []
    if speed is None:
        return TaskVerdict(
            "Перегляд відео",
            "СУМНІВНО",
            "немає заміру швидкості (потрібен download)",
        )

    down = speed.download_mbps
    if down < 3.0:
        status: Status = "НІ"
        reasons.append(f"download {down:.1f} < 3 Мбіт/с")
    elif down < 5.0:
        status = "СУМНІВНО"
        reasons.append(f"download {down:.1f} Мбіт/с (нижче HD)")
    elif down < 15.0:
        status = "ОКЧАТНО"
        reasons.append(f"download {down:.1f} Мбіт/с ≈ HD")
    elif down < 25.0:
        status = "ОКЧАТНО"
        reasons.append(f"download {down:.1f} Мбіт/с ≈ Full HD")
    else:
        status = "ОКЧАТНО"
        reasons.append(f"download {down:.1f} Мбіт/с ≈ 4K орієнтир")

    status = _apply_ping_soft(status, _ping_value(speed, stable), reasons)
    return TaskVerdict("Перегляд відео", status, " · ".join(reasons))


def _online_game(speed: SpeedResult | None, stable: StableResult | None) -> TaskVerdict:
    reasons: list[str] = []
    if stable is None:
        return TaskVerdict(
            "Онлайн-гра",
            "СУМНІВНО",
            "потрібна перевірка стабільності (jitter/втрати) · оцінка неповна",
        )

    jitter = stable.jitter_ms
    loss = stable.loss_percent
    if loss > 2.0 or jitter > 40.0:
        status: Status = "НІ"
        reasons.append(f"jitter {jitter:.1f} мс / втрати {loss:.1f}%")
    elif loss > 1.0 or jitter > 20.0:
        status = "СУМНІВНО"
        reasons.append(f"jitter {jitter:.1f} мс / втрати {loss:.1f}%")
    else:
        status = "ОКЧАТНО"
        reasons.append(f"jitter {jitter:.1f} мс, втрати {loss:.1f}%")

    # Ping — лише попередження / м'яке зниження, ніколи НІ через ping.
    status = _apply_ping_soft(status, _ping_value(speed, stable), reasons)
    return TaskVerdict("Онлайн-гра", status, " · ".join(reasons))


def _download_task(speed: SpeedResult | None, stable: StableResult | None) -> TaskVerdict:
    reasons: list[str] = []
    if speed is None:
        return TaskVerdict(
            "Скачування",
            "СУМНІВНО",
            "немає заміру швидкості (потрібен download)",
        )

    down = speed.download_mbps
    if down < 5.0:
        status: Status = "НІ"
        reasons.append(f"download {down:.1f} < 5 Мбіт/с — дуже повільно")
    elif down < 20.0:
        status = "СУМНІВНО"
        reasons.append(f"download {down:.1f} Мбіт/с — повільно/середньо")
    elif down < 50.0:
        status = "ОКЧАТНО"
        reasons.append(f"download {down:.1f} Мбіт/с — зручно")
    else:
        status = "ОКЧАТНО"
        reasons.append(f"download {down:.1f} Мбіт/с — швидко")

    status = _apply_ping_soft(status, _ping_value(speed, stable), reasons)
    return TaskVerdict("Скачування", status, " · ".join(reasons))


def evaluate_suitability(
    speed: SpeedResult | None = None,
    stable: StableResult | None = None,
) -> SuitabilityReport:
    tasks = [
        _video_call(speed, stable),
        _stream(speed, stable),
        _watch_video(speed, stable),
        _online_game(speed, stable),
        _download_task(speed, stable),
    ]

    ping = _ping_value(speed, stable)
    ping_warning: str | None = None
    if ping is not None and ping >= PING_WARN_MS:
        ping_warning = PING_NOTE

    incomplete: str | None = None
    if speed is None or stable is None:
        missing = []
        if speed is None:
            missing.append("швидкість")
        if stable is None:
            missing.append("стабільність")
        incomplete = (
            "Для повної оцінки бажано обидва тести: зараз немає — "
            + " і ".join(missing)
            + "."
        )

    return SuitabilityReport(
        tasks=tasks,
        ping_warning=ping_warning,
        incomplete_note=incomplete,
    )


def format_suitability(report: SuitabilityReport) -> str:
    lines = ["=== Для ваших задач зараз ==="]
    width = max(len(t.name) for t in report.tasks)
    for task in report.tasks:
        lines.append(f"  {task.name:<{width}}  — {task.status}")
        lines.append(f"    {task.reason}")
    if report.incomplete_note:
        lines.append("")
        lines.append(report.incomplete_note)
    if report.ping_warning:
        lines.append("")
        lines.append(report.ping_warning)
    return "\n".join(lines)
