"""Browser sign-in, automatic clipboard processing, Windows tray. No client secret."""
from pathlib import Path
import json
import os
import queue
import threading
import time
import sys
import tkinter as tk
from tkinter import messagebox, ttk
import clipboard_companion as bridge
import clipboard_protocol
import build_database
import local_settings
import realm_resolver
import wcl_oauth
import windows_integration as windows
import appearance

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = local_settings.PATH.parent if getattr(sys, "frozen", False) else ROOT


class App:
    def __init__(self, root, instance=None):
        self.root, self.instance = root, instance
        self.messages = queue.Queue()
        self.config_lock = threading.RLock()
        self.config = {}
        self.session = self.worker = self.auth_worker = self.result = None
        self.stop, self.auth_cancel = threading.Event(), threading.Event()
        self.want_running = self.exiting = False
        self.clipboard_sequence, self.clipboard_events = None, []
        self.last_heartbeat = 0
        self.mode_diagnostic = "--diagnostic" in sys.argv
        self.settings_window = None
        root.title("MPlusLogs Companion")
        root.geometry("500x360")
        root.resizable(False, False)
        root.iconbitmap(default=str(Path(__file__).with_name("assets") / "mpluslogs.ico"))
        root.protocol("WM_DELETE_WINDOW", self.hide)
        root.bind("<Unmap>", self.minimized)
        self.status = tk.StringVar(value="Войдите в Warcraft Logs, чтобы загружать данные.")
        self.account = tk.StringVar(value="Warcraft Logs не подключён")
        self.sound = tk.BooleanVar()
        try:
            self.config = local_settings.load()
        except (ValueError, OSError, KeyError, TypeError):
            self.status.set("Не удалось прочитать настройки. Войдите в Warcraft Logs заново.")
        bundled = json.loads(Path(__file__).with_name("oauth_client.json").read_text(encoding="utf-8"))
        self.client_id = bundled["client_id"]
        self.sound.set(self.config.get("sound", False))
        theme = self.config.get("theme", "system")
        self.theme = tk.StringVar(value=theme if theme in {"system","light","dark"} else "system")
        self.applied_theme = None
        self.last_theme_check = 0
        self.autostart = tk.BooleanVar(value=windows.autostart_enabled())
        self.retail_autostart = tk.BooleanVar(value=windows.retail_autostart_enabled())
        if self.retail_autostart.get():
            try:
                windows.ensure_retail_watcher()
            except OSError:
                self.status.set("Не удалось запустить ожидание WoW Retail. Проверьте настройку автозапуска.")
        if self.config.get("oauth") and self.config.get("oauth_client_id") == self.client_id:
            self.session = self.make_session(self.config["oauth"])
            self.account.set("Warcraft Logs подключён")
        frame = ttk.Frame(root, padding=24)
        self.body = frame
        frame.pack(fill="both", expand=True)
        header = ttk.Frame(frame)
        header.pack(anchor="w", pady=(0,8))
        self.logo = tk.PhotoImage(file=str(Path(__file__).with_name("assets") / "mpluslogs.png")).subsample(4,4)
        ttk.Label(header, image=self.logo).pack(side="left", padx=(0,12))
        ttk.Label(header, text="MPlusLogs", font=("Segoe UI", 22, "bold")).pack(side="left")
        ttk.Label(frame, textvariable=self.account, style="Muted.TLabel").pack(anchor="w", pady=(4, 14))
        ttk.Label(frame, textvariable=self.status, wraplength=420, justify="left").pack(anchor="w", fill="x")
        buttons = ttk.Frame(frame)
        buttons.pack(anchor="w", pady=16)
        self.login_button = ttk.Button(buttons, text="Войти через Warcraft Logs", command=self.sign_in)
        self.login_button.pack(side="left")
        self.settings_button = ttk.Button(buttons, text="Настройки", command=self.settings)
        self.settings_button.pack(side="left", padx=(8, 0))
        if self.session:
            self.login_button.pack_forget()
        self.copy_button = ttk.Button(frame, text="Скопировать последний ответ", command=self.copy)
        ttk.Label(frame, text="В WoW: скопируйте запрос (Ctrl+C), дождитесь ответа\nи вставьте его (Ctrl+V).", justify="left", style="Muted.TLabel").pack(anchor="w", pady=(4, 0))
        self.refresh_theme()
        self.tray = None
        try:
            self.tray = windows.Tray(self.messages)
        except OSError:
            self.status.set("Трей недоступен. Оставьте окно свёрнутым во время игры.")
        root.after(200, self.poll)
        if self.session or self.mode_diagnostic:
            self.want_running = True
            root.after(300, self.start)
        if "--background" in sys.argv and self.tray and self.session:
            root.after(400, self.hide)
        if "--login" in sys.argv:
            root.after(500, self.sign_in)

    def make_session(self, tokens):
        def persist(updated):
            with self.config_lock:
                if self.session is not session:
                    raise ValueError("Сессия завершена. Войдите в Warcraft Logs заново.")
                config = dict(self.config, oauth=updated, oauth_client_id=self.client_id)
                local_settings.save_config(config)
                self.config = config
        session = wcl_oauth.Session(self.client_id, tokens, persist)
        return session

    def sign_in(self):
        if self.auth_worker and self.auth_worker.is_alive():
            return
        self.want_running = False
        self.stop.set()
        self.auth_cancel = threading.Event()
        cancel = self.auth_cancel
        self.login_button.configure(state="disabled")
        self.status.set("Завершите вход в браузере. Пароль вводится только на сайте Warcraft Logs.")
        def authenticate():
            try:
                tokens = wcl_oauth.login(self.client_id, cancel)
                if cancel.is_set():
                    return
                wcl_oauth.validate_access(tokens)
                self.messages.put(("auth", (tokens, cancel)))
            except (ValueError, OSError, KeyError, TypeError) as exc:
                self.messages.put(("auth_error", (str(exc), cancel)))
        self.auth_worker = threading.Thread(target=authenticate, daemon=True)
        self.auth_worker.start()

    def sign_out(self):
        self.auth_cancel.set()
        with self.config_lock:
            config = {key: value for key, value in self.config.items() if key not in {"oauth", "oauth_dpapi", "secret", "secret_dpapi"}}
            try:
                local_settings.save_config(config)
            except (ValueError, OSError) as exc:
                messagebox.showerror("MPlusLogs", str(exc), parent=self.root)
                return
            self.session, self.config = None, config
        self.want_running = False
        self.stop.set()
        self.account.set("Warcraft Logs не подключён")
        self.status.set("Вы вышли. Сохранённые токены удалены с этого компьютера.")
        self.login_button.configure(state="normal")
        self.login_button.pack(side="left", before=self.settings_button)

    def settings(self):
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.deiconify()
            self.settings_window.lift()
            return
        window = self.settings_window = tk.Toplevel(self.root)
        window.title("Настройки MPlusLogs")
        window.resizable(False, False)
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Тема оформления").pack(anchor="w", pady=(0,6))
        names = {"system":"Как в Windows", "light":"Светлая", "dark":"Тёмная"}
        theme_buttons = ttk.Frame(frame)
        theme_buttons.pack(fill="x", pady=(0,16))
        def select_theme():
            self.refresh_theme(force=True)
            self.save_preferences()
        for index, (value, label) in enumerate(names.items()):
            ttk.Radiobutton(theme_buttons, text=label, value=value, variable=self.theme,
                            command=select_theme, style="Theme.TRadiobutton").grid(row=0,column=index,sticky="ew",padx=(0,4))
            theme_buttons.columnconfigure(index, weight=1)
        ttk.Checkbutton(frame, text="Запускать при входе в Windows", variable=self.autostart, command=self.save_preferences).pack(anchor="w", pady=6)
        ttk.Checkbutton(frame, text="Запускать вместе с WoW Retail", variable=self.retail_autostart, command=self.save_preferences).pack(anchor="w", pady=6)
        ttk.Label(frame, text="Фоновое ожидание запуска Retail. Classic и PTR\nне запускают помощник.", style="Muted.TLabel").pack(anchor="w", pady=(0,8))
        ttk.Checkbutton(frame, text="Звук готовности ответа", variable=self.sound, command=self.save_preferences).pack(anchor="w", pady=6)
        ttk.Label(frame, text="Закрытие окна оставляет помощник в трее.\nДля завершения: ПКМ по значку → Выйти.").pack(anchor="w", pady=12)
        ttk.Button(frame, text="Переподключить Warcraft Logs", command=self.sign_in).pack(anchor="w", pady=4)
        ttk.Button(frame, text="Выйти из Warcraft Logs", command=self.sign_out).pack(anchor="w", pady=4)
        ttk.Label(frame, text="Диагностика", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(20, 4))
        ttk.Button(frame, text="Проверить связь с аддоном без WCL", command=self.toggle_diagnostic).pack(anchor="w", pady=4)
        ttk.Button(frame, text="Завершить помощник", command=self.exit).pack(anchor="w", pady=8)
        window.update_idletasks()
        self.refresh_theme(force=True)

    def save_preferences(self):
        previous = windows.autostart_enabled()
        previous_retail = windows.retail_autostart_enabled()
        previous_config = dict(self.config)
        try:
            windows.set_autostart(self.autostart.get())
            windows.set_retail_autostart(self.retail_autostart.get())
            with self.config_lock:
                config = dict(self.config, sound=self.sound.get(), autostart=self.autostart.get(), retail_autostart=self.retail_autostart.get(), theme=self.theme.get())
                local_settings.save_config(config)
                self.config = config
            windows.ensure_retail_watcher()
        except (ValueError, OSError) as exc:
            try:
                windows.set_autostart(previous)
                windows.set_retail_autostart(previous_retail)
                with self.config_lock:
                    local_settings.save_config(previous_config)
                    self.config = previous_config
            except (ValueError, OSError):
                pass
            self.autostart.set(windows.autostart_enabled())
            self.retail_autostart.set(windows.retail_autostart_enabled())
            messagebox.showerror("MPlusLogs", "Не удалось сохранить настройки: " + str(exc), parent=self.root)

    def toggle_diagnostic(self):
        self.mode_diagnostic = not self.mode_diagnostic
        self.stop.set()
        self.want_running = self.mode_diagnostic or bool(self.session)
        self.status.set("Проверка связи включена: WCL не запрашивается." if self.mode_diagnostic else "Проверка связи выключена.")

    def toggle(self):
        if self.want_running:
            self.want_running = False
            self.stop.set()
            self.status.set("Обработка приостановлена.")
        elif self.session or self.mode_diagnostic:
            self.want_running = True
            self.start()
        else:
            self.show()
            self.status.set("Сначала войдите в Warcraft Logs.")

    def start(self):
        if not self.want_running or (self.worker and self.worker.is_alive()) or (not self.session and not self.mode_diagnostic):
            return
        self.stop = threading.Event()
        self.worker = threading.Thread(target=self.watch, args=(self.stop, self.session, self.mode_diagnostic, self.root.winfo_id()), daemon=True)
        self.worker.start()

    def watch(self, stop, session, diagnostic, owner):
        def post(kind, value):
            self.messages.put(("worker", (stop, kind, value)))
        try:
            clipboard = bridge.WindowsClipboard(owner=owner)
            client = bridge.Client(token_provider=session.access_token, invalidate_token=session.invalidate) if session else None
            mapping = realm_resolver.load_mappings()
            post("status", "Проверка связи: ожидаю запрос из WoW." if diagnostic else "Готов к работе. Ожидаю запрос из WoW.")
            last_sequence = None
            while not stop.wait(0.3):
                sequence = clipboard.sequence()
                self.clipboard_sequence = sequence
                if sequence == last_sequence:
                    continue
                try:
                    text = clipboard.read()
                    last_sequence = sequence
                    event = clipboard_protocol.describe_clipboard(text)
                    event.update(sequence=sequence, time=time.time())
                    self.clipboard_events = (self.clipboard_events + [event])[-12:]
                    if not clipboard_protocol.unwrap_request(text):
                        if text.startswith(("MPLQ1", "MPLQ2")) or (text.startswith("MPLS1") and "MPLQ" in text):
                            post("status", "Запрос скопирован не полностью. Выделите поле в WoW (Ctrl+A), затем Ctrl+C.")
                        continue
                    post("status", "Загружаю данные Warcraft Logs…")
                    response = clipboard_protocol.reply(text, mapping, DATA_ROOT / ".wcl-cache", client, diagnostic)
                    if stop.is_set():
                        break
                    build_database.atomic_write(DATA_ROOT / "last-result.mpl", response)
                    post("result", response)
                    if clipboard.reply_if_unchanged(text, response):
                        post("ready", "Ответ в буфере. Вернитесь в WoW и нажмите Ctrl+V.")
                    else:
                        post("ready", "Ответ готов. Буфер изменился — нажмите «Скопировать последний ответ».")
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    post("status", str(exc))
        except (ValueError, OSError, KeyError, TypeError) as exc:
            post("fatal", "Помощник остановлен: " + str(exc))

    def poll(self):
        if self.exiting:
            return
        if time.monotonic() - self.last_theme_check >= 2:
            self.last_theme_check = time.monotonic()
            self.refresh_theme()
        if self.instance and self.instance.show_requested():
            self.show()
        while not self.messages.empty():
            kind, value = self.messages.get()
            if kind == "worker":
                stop, kind, value = value
                if stop is not self.stop or stop.is_set():
                    continue
            if kind == "show":
                self.show()
            elif kind == "toggle":
                self.toggle()
            elif kind == "exit":
                self.exit()
                return
            elif kind == "auth":
                tokens, cancel = value
                if cancel is not self.auth_cancel or cancel.is_set():
                    continue
                try:
                    with self.config_lock:
                        config = dict(self.config, oauth_client_id=self.client_id, oauth=tokens)
                        local_settings.save_config(config)
                        self.config = config
                        self.session = self.make_session(tokens)
                    self.account.set("Warcraft Logs подключён")
                    self.login_button.pack_forget()
                    self.mode_diagnostic, self.want_running = False, True
                    self.status.set("Вход выполнен. Помощник готов к работе.")
                except (ValueError, OSError) as exc:
                    self.status.set("Не удалось сохранить вход: " + str(exc))
                self.login_button.configure(state="normal")
            elif kind == "auth_error":
                error, cancel = value
                if cancel is self.auth_cancel and not cancel.is_set():
                    self.status.set("Не удалось войти: " + error)
                    self.login_button.configure(state="normal")
                    self.want_running = bool(self.session)
            elif kind == "result":
                self.result = value
                self.copy_button.pack(anchor="w", pady=(0, 6))
            elif kind == "fatal":
                self.want_running = False
                self.status.set(value)
                self.show()
            elif kind == "tray_error":
                self.tray = None
                self.status.set(value)
                self.show()
            else:
                self.status.set(value)
                if kind == "ready" and self.sound.get():
                    self.root.bell()
        self.start()
        self.root.update_idletasks()
        height = max(330, self.body.winfo_reqheight())
        if self.root.winfo_height() != height:
            self.root.geometry(f"500x{height}")
        if time.time() - self.last_heartbeat >= 1:
            self.last_heartbeat = time.time()
            try:
                build_database.atomic_write(DATA_ROOT / "companion-status.json", json.dumps({
                    "updated": self.last_heartbeat, "pid": os.getpid(), "status": self.status.get(),
                    "worker_alive": bool(self.worker and self.worker.is_alive()), "diagnostic": self.mode_diagnostic,
                    "clipboard_sequence": self.clipboard_sequence, "clipboard_events": self.clipboard_events,
                    "oauth_connected": bool(self.session), "tray": bool(self.tray)}, ensure_ascii=False, indent=2))
            except OSError:
                pass
        self.root.after(200, self.poll)

    def refresh_theme(self, force=False):
        mode = appearance.system_theme() if self.theme.get() == "system" else self.theme.get()
        if force or mode != self.applied_theme:
            appearance.apply(self.root, mode, self.settings_window)
            self.applied_theme = mode
            self.root.after_idle(lambda: appearance.titlebar(self.root, mode == "dark"))

    def copy(self):
        if self.result:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.result)
            self.status.set("Ответ скопирован. В WoW нажмите Ctrl+V.")

    def minimized(self, event):
        if event.widget is self.root and self.root.state() == "iconic" and self.tray:
            self.root.after_idle(self.hide)

    def hide(self):
        if self.tray:
            self.root.withdraw()
            if self.settings_window and self.settings_window.winfo_exists():
                self.settings_window.withdraw()
        else:
            self.root.iconify()

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def exit(self):
        self.exiting = True
        self.want_running = False
        self.stop.set()
        self.auth_cancel.set()
        if self.tray:
            self.tray.close()
        self.root.destroy()


def main():
    if "--self-test-report" in sys.argv:
        import release_smoke
        release_smoke.run(sys.argv[sys.argv.index("--self-test-report") + 1])
        return
    if "--watch-retail" in sys.argv:
        import retail_launcher
        retail_launcher.watch()
        return
    instance = windows.SingleInstance(notify="--background" not in sys.argv)
    if not instance.primary:
        instance.close()
        return
    try:
        root = tk.Tk()
        App(root, instance)
        root.mainloop()
    finally:
        instance.close()


if __name__ == "__main__":
    main()
