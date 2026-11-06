"""GUI v2: CustomTkinter, темна тема, проста візуалізація ходу заміру."""

from __future__ import annotations

import threading
import tkinter as tk
from datetime import date, datetime

import customtkinter as ctk

from spettest.errors import SpetTestError
from spettest.netinfo import fetch_public_ip
from spettest.report import SpeedResult, StableResult
from spettest.speed import run_speed_test
from spettest.stable import DEFAULT_DURATION_S, run_stable_test
from spettest.storage import HistoryRow, count_history, list_history, save_speed, save_stable
from spettest.suitability import evaluate_suitability, format_suitability


class SpetTestApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title("SpetTest")
        self.geometry("760x700")
        self.minsize(660, 600)

        self._busy = False
        self._public_ip: str | None = None
        self._showing_history = True
        self._last_speed: SpeedResult | None = None
        self._last_stable: StableResult | None = None

        self._build()
        self.after(100, self._refresh_ip)
        self.after(150, self._show_history_view)

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="SpetTest",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        self.ip_label = ctk.CTkLabel(
            header,
            text="Публічний IP: …",
            font=ctk.CTkFont(size=13),
            text_color=("gray70", "gray70"),
        )
        self.ip_label.grid(row=1, column=0, sticky="w", pady=(4, 0))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", padx=16, pady=8)
        actions.grid_columnconfigure((0, 1), weight=1)

        self.btn_speed = ctk.CTkButton(
            actions,
            text="Швидкість",
            height=40,
            command=self._start_speed,
        )
        self.btn_speed.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.btn_stable = ctk.CTkButton(
            actions,
            text=f"Стабільність ({DEFAULT_DURATION_S} с)",
            height=40,
            command=self._start_stable,
        )
        self.btn_stable.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        progress_box = ctk.CTkFrame(self)
        progress_box.grid(row=2, column=0, sticky="ew", padx=16, pady=8)
        progress_box.grid_columnconfigure(0, weight=1)

        self.stage_label = ctk.CTkLabel(
            progress_box,
            text="Готово",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        )
        self.stage_label.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 2))

        self.detail_label = ctk.CTkLabel(
            progress_box,
            text="Оберіть тест або перегляньте історію.",
            font=ctk.CTkFont(size=12),
            text_color=("gray70", "gray70"),
            anchor="w",
        )
        self.detail_label.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))

        self.progress = ctk.CTkProgressBar(progress_box)
        self.progress.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 6))
        self.progress.set(0)

        self.mbps_label = ctk.CTkLabel(
            progress_box,
            text="",
            font=ctk.CTkFont(size=20, weight="bold"),
            anchor="w",
        )
        self.mbps_label.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 10))

        body = ctk.CTkFrame(self)
        body.grid(row=3, column=0, sticky="nsew", padx=16, pady=(0, 8))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        body_header = ctk.CTkFrame(body, fg_color="transparent")
        body_header.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        body_header.grid_columnconfigure(0, weight=1)

        self.body_title = ctk.CTkLabel(
            body_header,
            text="Історія",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        )
        self.body_title.grid(row=0, column=0, sticky="w")

        self.btn_earlier = ctk.CTkButton(
            body_header,
            text="Показати раніші",
            width=140,
            state="disabled",
            command=self._show_history_view,
        )
        self.btn_earlier.grid(row=0, column=1, sticky="e")

        self.result_box = ctk.CTkTextbox(body, height=220, activate_scrollbars=True)
        self.result_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        self.result_box.configure(state="disabled")

        filters = ctk.CTkFrame(body, fg_color="transparent")
        filters.grid(row=2, column=0, sticky="ew", padx=8, pady=(4, 8))
        filters.grid_columnconfigure((1, 3), weight=1)

        ctk.CTkLabel(filters, text="Дата").grid(row=0, column=0, padx=(0, 6))
        self.date_entry = ctk.CTkEntry(filters, placeholder_text="РРРР-ММ-ДД")
        self.date_entry.grid(row=0, column=1, sticky="ew", padx=(0, 10))

        ctk.CTkLabel(filters, text="IP").grid(row=0, column=2, padx=(0, 6))
        self.ip_entry = ctk.CTkEntry(filters, placeholder_text="публічний IP")
        self.ip_entry.grid(row=0, column=3, sticky="ew", padx=(0, 10))

        self.btn_filter = ctk.CTkButton(
            filters,
            text="Шукати",
            width=100,
            command=self._apply_history_filter,
        )
        self.btn_filter.grid(row=0, column=4)

        footer = ctk.CTkLabel(
            self,
            text="Проста візуалізація ходу · історія лише локально (spettest.db)",
            font=ctk.CTkFont(size=11),
            text_color=("gray60", "gray60"),
        )
        footer.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 12))

    def _set_text(self, widget: ctk.CTkTextbox, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.btn_speed.configure(state=state)
        self.btn_stable.configure(state=state)
        if not busy:
            self._update_earlier_button()

    def _update_earlier_button(self) -> None:
        has = count_history() > 0
        if self._showing_history:
            self.btn_earlier.configure(state="disabled", text="Показати раніші")
        else:
            self.btn_earlier.configure(
                state="normal" if has else "disabled",
                text="Показати раніші",
            )

    def _refresh_ip(self) -> None:
        def work() -> None:
            ip = fetch_public_ip()
            self.after(0, lambda: self._on_ip(ip))

        threading.Thread(target=work, daemon=True).start()

    def _on_ip(self, ip: str | None) -> None:
        self._public_ip = ip
        if ip:
            self.ip_label.configure(text=f"Публічний IP: {ip}")
        else:
            self.ip_label.configure(text="Публічний IP: не визначено")

    def _ui_progress(
        self,
        stage: str,
        *,
        progress: float | None = None,
        mbps: float | None = None,
        detail: str = "",
    ) -> None:
        def apply() -> None:
            self.stage_label.configure(text=stage)
            self.detail_label.configure(text=detail or "")
            if progress is not None:
                self.progress.set(max(0.0, min(1.0, progress)))
            if mbps is not None:
                self.mbps_label.configure(text=f"{mbps:.1f} Мбіт/с")
            elif stage in {"Ping", "Збір замірів", "Готово"}:
                if "мс" in detail:
                    self.mbps_label.configure(text=detail)
                elif stage == "Збір замірів":
                    self.mbps_label.configure(text=detail.split("·")[0].strip() if detail else "")

        self.after(0, apply)

    def _start_speed(self) -> None:
        if self._busy:
            return
        self._set_busy(True)
        self._showing_history = False
        self.body_title.configure(text="Результат")
        self._set_text(self.result_box, "Йде замір швидкості…")
        self.mbps_label.configure(text="")
        self.progress.set(0)
        self._update_earlier_button()

        def work() -> None:
            try:
                ip = fetch_public_ip()
                self.after(0, lambda: self._on_ip(ip))
                result = run_speed_test(on_progress=self._ui_progress)
                try:
                    save_speed(result, ip)
                except Exception:
                    pass
                self.after(0, lambda: self._on_speed_done(result, ip))
            except SpetTestError as exc:
                self.after(0, lambda: self._on_error(exc.message))
            except Exception:
                self.after(
                    0,
                    lambda: self._on_error(
                        "Неочікувана помилка. Перевірте з’єднання з інтернетом."
                    ),
                )

        threading.Thread(target=work, daemon=True).start()

    def _start_stable(self) -> None:
        if self._busy:
            return
        self._set_busy(True)
        self._showing_history = False
        self.body_title.configure(text="Результат")
        self._set_text(self.result_box, f"Перевірка стабільності ({DEFAULT_DURATION_S} с)…")
        self.mbps_label.configure(text="")
        self.progress.set(0)
        self._update_earlier_button()

        def work() -> None:
            try:
                ip = fetch_public_ip()
                self.after(0, lambda: self._on_ip(ip))
                result = run_stable_test(
                    DEFAULT_DURATION_S,
                    on_progress=self._ui_progress,
                )
                try:
                    save_stable(result, ip)
                except Exception:
                    pass
                self.after(0, lambda: self._on_stable_done(result, ip))
            except SpetTestError as exc:
                self.after(0, lambda: self._on_error(exc.message))
            except Exception:
                self.after(
                    0,
                    lambda: self._on_error(
                        "Неочікувана помилка. Перевірте з’єднання з інтернетом."
                    ),
                )

        threading.Thread(target=work, daemon=True).start()

    def _suitability_text(self) -> str:
        report = evaluate_suitability(
            speed=self._last_speed,
            stable=self._last_stable,
        )
        return format_suitability(report)

    def _on_speed_done(self, result: SpeedResult, ip: str | None) -> None:
        self._last_speed = result
        text = (
            "=== Швидкість ===\n"
            f"Публічний IP: {ip or 'не визначено'}\n"
            f"Download:  {result.download_mbps:.1f} Мбіт/с\n"
            f"Upload:    {result.upload_mbps:.1f} Мбіт/с\n"
            f"Ping:      {result.ping_ms:.0f} мс\n"
            f"\n{self._suitability_text()}\n"
        )
        self._set_text(self.result_box, text)
        self.stage_label.configure(text="Готово")
        self.detail_label.configure(text="Замір швидкості завершено")
        self.progress.set(1)
        self.mbps_label.configure(
            text=f"↓ {result.download_mbps:.1f}  ↑ {result.upload_mbps:.1f} Мбіт/с"
        )
        self._set_busy(False)

    def _on_stable_done(self, result: StableResult, ip: str | None) -> None:
        self._last_stable = result
        text = (
            "=== Стабільність ===\n"
            f"Публічний IP: {ip or 'не визначено'}\n"
            f"Тривалість: {result.duration_s} с\n"
            f"Ping:       {result.ping_avg_ms:.0f} мс "
            f"(мін {result.ping_min_ms:.0f}, макс {result.ping_max_ms:.0f})\n"
            f"Jitter:     {result.jitter_ms:.1f} мс\n"
            f"Втрати:     {result.loss_percent:.1f}%\n"
            f"Стабільність: {result.verdict}\n"
            f"\n{self._suitability_text()}\n"
        )
        self._set_text(self.result_box, text)
        self.stage_label.configure(text="Готово")
        self.detail_label.configure(text="Перевірка стабільності завершена")
        self.progress.set(1)
        self.mbps_label.configure(text=f"Вердикт: {result.verdict}")
        self._set_busy(False)

    def _on_error(self, message: str) -> None:
        self._set_text(self.result_box, f"Помилка: {message}")
        self.stage_label.configure(text="Помилка")
        self.detail_label.configure(text=message)
        self.progress.set(0)
        self.mbps_label.configure(text="")
        self._set_busy(False)

    def _show_history_view(self) -> None:
        self._showing_history = True
        self.body_title.configure(text="Історія")
        self._update_earlier_button()
        self._apply_history_filter()

    def _apply_history_filter(self) -> None:
        ip_q = self.ip_entry.get().strip() or None
        date_q = self.date_entry.get().strip()
        on_date: date | None = None
        if date_q:
            try:
                on_date = date.fromisoformat(date_q)
            except ValueError:
                self._set_text(
                    self.result_box,
                    "Невірний формат дати. Використовуйте РРРР-ММ-ДД.",
                )
                return

        rows = list_history(public_ip=ip_q, on_date=on_date, limit=200)
        self._set_text(self.result_box, self._format_history(rows))

    def _format_history(self, rows: list[HistoryRow]) -> str:
        if not rows:
            return "Записів немає."
        lines: list[str] = []
        for row in rows:
            when = row.created_at
            try:
                when = datetime.fromisoformat(row.created_at).strftime("%Y-%m-%d %H:%M")
            except ValueError:
                pass
            ip = row.public_ip or "IP ?"
            if row.test_type == "speed":
                lines.append(
                    f"{when}  |  speed  |  {ip}  |  "
                    f"↓{row.download_mbps:.1f} ↑{row.upload_mbps:.1f}  ping {row.ping_ms:.0f} мс"
                )
            else:
                lines.append(
                    f"{when}  |  stable |  {ip}  |  "
                    f"ping {row.ping_avg_ms:.0f}  jitter {row.jitter_ms:.1f}  "
                    f"втрати {row.loss_percent:.1f}%  → {row.verdict}"
                )
        return "\n".join(lines)


def run_gui() -> None:
    app = SpetTestApp()
    app.mainloop()


def main() -> None:
    run_gui()


if __name__ == "__main__":
    main()
