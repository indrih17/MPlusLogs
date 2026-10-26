"""Browser sign-in, automatic clipboard processing, Windows tray. No client secret."""
from pathlib import Path
from http.client import HTTPException
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
import cache_maintenance
import local_settings
import realm_resolver
import wcl_oauth
import windows_integration as windows
import appearance
import companion_i18n as i18n
import companion_notifications
import companion_audio
import companion_update as updates
import personal_api

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = local_settings.PATH.parent if getattr(sys, "frozen", False) else ROOT
UPDATE_CHECK_INTERVAL = 60 * 60 * 1000
UPDATE_RETRY_INTERVAL = 5 * 60 * 1000
UPDATE_REMINDER_INTERVAL = 6 * 60 * 60


class App:
    def __init__(self, root, instance=None):
        self.root, self.instance = root, instance
        self.messages = queue.Queue()
        self.config_lock = threading.RLock()
        self.config = {}
        self.textvars = []
        self.language_menu = None
        self.session = self.worker = self.auth_worker = self.result = None
        self.stop, self.auth_cancel = threading.Event(), threading.Event()
        self.want_running = self.exiting = False
        self.clipboard_sequence, self.clipboard_events = None, []
        self.notification_characters=[]
        self.last_heartbeat = 0
        # The no-WCL transport test is available only through an explicit
        # development launch from source, never in the packaged application.
        self.mode_diagnostic = not getattr(sys, "frozen", False) and "--diagnostic" in sys.argv
        self.settings_window = None
        self.personal_setup = None
        self.update_worker = None
        self.available_update = self.update_installer = None
        self.installing_update = False
        self.failed_update_version = None
        self.preview=updates.local_preview()
        root.title("MPlusLogs Companion"+(" / Local preview" if self.preview else ""))
        root.geometry("500x360")
        root.resizable(False, False)
        root.iconbitmap(default=str(Path(__file__).with_name("assets") / "mpluslogs.ico"))
        root.protocol("WM_DELETE_WINDOW", self.hide)
        root.bind("<Unmap>", self.minimized)
        self.status = self.textvar("Войдите в Warcraft Logs, чтобы загружать данные.")
        self.account = self.textvar("Warcraft Logs не подключён")
        self.sound = tk.BooleanVar()
        self.notifications = tk.BooleanVar()
        try:
            self.config = local_settings.load()
        except (ValueError, OSError, KeyError, TypeError):
            self.status.set("Не удалось прочитать настройки. Войдите в Warcraft Logs заново.")
        try:
            self.config = local_settings.initialize_notifications(self.config)
        except (ValueError,OSError):
            self.config["notifications"] = True
        preference = self.config.get("language", "system")
        self.language = tk.StringVar(value=preference if preference == "system" or preference in i18n.LANGUAGES else "system")
        i18n.set_language(self.language.get())
        for variable in self.textvars:
            variable.refresh()
        bundled = json.loads(Path(__file__).with_name("oauth_client.json").read_text(encoding="utf-8"))
        self.shared_client_id = bundled["client_id"]
        self.api_mode = "personal" if self.config.get("api_mode") == "personal" else "shared"
        self.config["api_mode"] = self.api_mode
        self.config.pop("service_url", None)
        if (self.config.get("oauth") or {}).get("_service_url"):
            self.config.pop("oauth", None)
            self.config.pop("oauth_dpapi", None)
        self.client_id = self.config.get("personal_client_id", "") if self.api_mode == "personal" else self.shared_client_id
        self.sound.set(self.config.get("sound", True))
        self.notifications.set(self.config.get("notifications", True))
        theme = self.config.get("theme", "system")
        self.theme = tk.StringVar(value=theme if theme in {"system","light","dark"} else "system")
        self.applied_theme = None
        self.last_theme_check = 0
        self.startup_mode = tk.StringVar(value=self.current_startup_mode())
        if self.startup_mode.get() == "retail":
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
        self.loading_area = ttk.Frame(frame)
        self.loading_area.pack(fill="x")
        ttk.Label(self.loading_area, textvariable=self.status, wraplength=420, justify="left").pack(anchor="w", fill="x")
        self.progress_bar = ttk.Progressbar(self.loading_area, mode="determinate", maximum=1)
        buttons = ttk.Frame(frame)
        buttons.pack(anchor="w", pady=16)
        self.login_text = self.textvar('Войти через Warcraft Logs')
        self.settings_button = ttk.Button(buttons, textvariable=self.textvar('Настройки'), command=self.settings)
        self.settings_button.pack(side="left")
        self.api_banner = ttk.Frame(frame)
        self.api_banner.pack(fill="x", before=buttons, pady=(16, 0))
        self.api_title = self.textvar("")
        self.api_description = self.textvar("")
        self.api_quota = self.textvar("")
        ttk.Label(self.api_banner, textvariable=self.api_title, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(self.api_banner, textvariable=self.api_description, wraplength=440).pack(anchor="w", fill="x", pady=(4, 8))
        self.personal_button_text = self.textvar("")
        api_buttons = ttk.Frame(self.api_banner)
        api_buttons.pack(anchor="w")
        self.personal_button = ttk.Button(api_buttons, textvariable=self.personal_button_text, command=self.show_personal_setup)
        self.personal_button.pack(side="left")
        self.login_button = ttk.Button(api_buttons, textvariable=self.login_text, command=self.sign_in)
        if not self.session:
            self.login_button.pack(side="left", padx=(8, 0))
        ttk.Label(self.api_banner, textvariable=self.api_quota, wraplength=440, style="Muted.TLabel").pack(anchor="w", pady=(8, 0))
        self.refresh_api_display()
        self.copy_button = ttk.Button(frame, textvariable=self.textvar('Скопировать последний ответ'), command=self.copy)
        ttk.Label(frame, textvariable=self.textvar('В WoW: скопируйте запрос (Ctrl+C), дождитесь ответа\nи вставьте его (Ctrl+V).'), justify="left", style="Muted.TLabel").pack(anchor="w", pady=(4, 0))
        self.version_text = self.textvar("Local preview / not published" if self.preview else "Companion version: " + updates.current_version())
        ttk.Label(frame, textvariable=self.version_text, style="Muted.TLabel").pack(anchor="w", pady=(12, 0))
        self.update_status = self.textvar("")
        self.update_check_state = "idle"
        self.settings_update_text = self.textvar("Check Companion updates")
        self.settings_update_button = None
        self.notification_test_status = self.textvar("")
        ttk.Label(frame, textvariable=self.update_status, wraplength=440).pack(anchor="w")
        self.update_button = ttk.Button(frame, textvariable=self.textvar("Install update and restart"), command=self.install_update)
        outcome = updates.last_result()
        if outcome and not outcome["success"] and updates.version_tuple(outcome["expected_version"]) >= updates.version_tuple(updates.current_version()):
            self.failed_update_version = outcome["expected_version"]
            self.update_status.set("Companion update failed. Open the installation log in Settings.")
        self.refresh_theme()
        self.popup = companion_notifications.PopupNotifications(root,self.show,lambda:self.applied_theme)
        self.tray = None
        try:
            self.tray = windows.Tray(self.messages)
        except OSError:
            self.status.set("Трей недоступен. Оставьте окно свёрнутым во время игры.")
        root.after(200, self.poll)
        self.want_running = True
        root.after(300, self.start)
        if "--background" in sys.argv and self.tray and self.session:
            root.after(400, self.hide)
        if "--login" in sys.argv:
            root.after(500, self.sign_in)
        self.automatic_updates = getattr(sys, "frozen", False) and (not self.preview or updates.portable_build())
        if self.automatic_updates:
            self.schedule_update_check(1500)

    def schedule_update_check(self, delay=UPDATE_CHECK_INTERVAL):
        if getattr(self,"exiting",False) or not getattr(self,"automatic_updates",True):
            return
        timer=getattr(self,"update_check_after",None)
        if timer is not None:
            self.root.after_cancel(timer)
        self.update_check_after=self.root.after(delay,self.scheduled_update_check)

    def scheduled_update_check(self):
        self.update_check_after=None
        if getattr(self,"exiting",False): return
        self.check_updates()
        self.schedule_update_check()

    def notify_update(self, data, ready=False, force=False):
        now=time.monotonic()
        previous=getattr(self,"last_update_notice",None)
        if not force and previous and previous[0]==data["version"] and now-previous[1]<UPDATE_REMINDER_INTERVAL:
            return
        message=("Companion update is ready. Click to install and restart." if ready else
                 "A new Companion version is available. Open Companion for details.")
        if self.show_notification("MPlusLogs Companion "+data["version"],i18n.tr(message),
                                  required=True,on_click=self.install_update if ready else self.show):
            self.last_update_notice=(data["version"],now)

    def check_updates(self, manual=False):
        if getattr(self,"preview",False) and not updates.portable_build() and not manual: return
        if self.installing_update or (self.update_worker and self.update_worker.is_alive()):
            return
        if self.update_installer:
            try:
                present=Path(self.update_installer).is_file()
            except OSError:
                present=False
            if not present:
                self.update_installer=None
                self.update_button.pack_forget()
        ready_version=self.available_update["version"] if self.available_update and self.update_installer else None
        if manual:
            self.update_status.set("Checking Companion updates…")
        self.set_update_check_state("checking")
        def run():
            updates.record_check("checking")
            try:
                data = updates.check()
                if data:
                    updates.record_check("available",version=data["version"])
                    if data["version"]==ready_version:
                        updates.record_check("ready",version=data["version"])
                        self.messages.put(("update_reminder", data))
                        return
                    self.messages.put(("update_available", data))
                    if not manual and data["version"] == self.failed_update_version:
                        self.messages.put(("update_check_idle", None))
                        return
                    self.messages.put(("update_downloading", None))
                    try:
                        target = updates.download(data)
                    except (ValueError, OSError, KeyError, TypeError, HTTPException) as error:
                        updates.record_check("download_error",version=data["version"],error=error)
                        self.messages.put(("update_download_error", None))
                        return
                    updates.record_check("ready",version=data["version"])
                    self.messages.put(("update_ready", (data, target)))
                elif manual:
                    updates.record_check("current")
                    self.messages.put(("update_current", None))
                else:
                    updates.record_check("current")
                    self.messages.put(("update_check_idle", None))
            except (ValueError, OSError, KeyError, TypeError, HTTPException) as error:
                updates.record_check("check_error",error=error)
                self.messages.put(("update_error", manual))
        self.update_worker = threading.Thread(target=run, daemon=True)
        self.update_worker.start()

    def set_update_check_state(self,state):
        self.update_check_state = state
        labels = {"idle":"Check Companion updates", "checking":"Checking Companion updates…",
                  "downloading":"Downloading Companion update…", "current":"No updates found",
                  "ready":"Update available — install and restart", "installing":"Installing update…",
                  "error":"Update check failed — retry"}
        text = getattr(self,"settings_update_text",None)
        if text is not None:
            text.set(labels[state])
        button = getattr(self,"settings_update_button",None)
        if button is not None and button.winfo_exists():
            button.configure(state="disabled" if state in {"checking","downloading","installing"} else "normal")

    def settings_update_action(self):
        if self.available_update and self.update_installer:
            self.install_update()
        else:
            self.check_updates(manual=True)

    def close_settings(self):
        self.settings_window.destroy()
        self.settings_window = None
        self.settings_update_button = None
        if self.update_check_state in {"current","error"}:
            self.set_update_check_state("idle")

    def open_update_log(self):
        path = local_settings.PATH.parent / "update-install.log"
        try:
            os.startfile(str(path))
        except OSError:
            messagebox.showerror("MPlusLogs", i18n.tr("No installation log is available yet."), parent=self.root)

    def install_update(self):
        if self.installing_update:
            return
        if not self.update_installer or not self.available_update:
            self.show()
            self.check_updates(manual=True)
            return
        if self.auth_worker and self.auth_worker.is_alive():
            self.update_status.set("Finish Warcraft Logs sign-in before updating.")
            self.show()
            return
        self.installing_update = True
        self.set_update_check_state("installing")
        self.update_button.configure(state="disabled")
        self.want_running = False
        self.stop.set()
        self.update_status.set("Finishing the current request before updating…")
        self.finish_update()

    def finish_update(self):
        if self.worker and self.worker.is_alive():
            self.root.after(200, self.finish_update)
            return
        try:
            updates.launch_installer(self.update_installer, self.available_update)
        except (ValueError, OSError):
            self.installing_update = False
            self.want_running = bool(self.session) or self.mode_diagnostic
            self.update_button.configure(state="normal")
            self.set_update_check_state("ready")
            self.update_status.set("Could not start the update. Try again.")
            self.show()
            return
        self.exit()

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

    def show_personal_setup(self):
        if self.installing_update or self.auth_worker and self.auth_worker.is_alive():
            return
        if self.personal_setup:
            self.personal_setup.window.deiconify()
            self.personal_setup.window.lift()
            return
        self.personal_setup = personal_api.Wizard(self)
        appearance.apply(self.root, self.applied_theme or "light", self.personal_setup.window)
        self.personal_setup.canvas.configure(background=appearance.PALETTES[self.applied_theme or "light"]["background"])

    def refresh_api_display(self):
        if self.api_mode == "personal":
            self.api_title.set("Personal API connected" if self.session else "Personal API selected")
            self.api_description.set("Requests use your configured WCL client. WCL determines its available quota.")
            self.personal_button_text.set("Change personal Client ID")
        elif self.session:
            self.api_title.set("Shared API connected")
            self.api_description.set("You use the shared MPlusLogs client. Connect your own WCL client to avoid relying on the shared allowance.")
            self.personal_button_text.set("Switch to personal API")
        else:
            self.api_title.set("Connect personal API — recommended")
            self.api_description.set("A short guide will help you create your own WCL client. You only need to do this once.")
            self.personal_button_text.set("Set up personal API")
        self.login_text.set("Войти через Warcraft Logs" if self.api_mode == "personal" else "Use shared API")
        quota = (self.config.get("oauth") or {}).get("_api_budget")
        if quota and quota.get("reset_at", 0) > time.time():
            self.api_quota.set_format("WCL allowance: {remaining} / {limit} points. Reset in {minutes} min.",
                remaining=round(quota["remaining"], 1), limit=quota["limit"], minutes=max(0, int((quota["reset_at"] - time.time() + 59) / 60)))
        else:
            self.api_quota.set("WCL allowance updates when loading logs." if self.session else "The available WCL allowance is shown after connection.")

    def sign_in(self, candidate=None, mode=None):
        if self.installing_update:
            return False
        if self.auth_worker and self.auth_worker.is_alive():
            return False
        selected_id = candidate or self.client_id
        selected_mode = mode or self.api_mode
        self.want_running = False
        self.stop.set()
        self.auth_cancel = threading.Event()
        cancel = self.auth_cancel
        self.login_button.configure(state="disabled")
        self.status.set("Завершите вход в браузере. Пароль вводится только на сайте Warcraft Logs.")
        def authenticate():
            try:
                tokens = wcl_oauth.login(selected_id, cancel)
                if cancel.is_set():
                    return
                quota = personal_api.quota_record(wcl_oauth.validate_access(tokens), time.time())
                if quota:
                    tokens["_api_budget"] = quota
                self.messages.put(("configured_auth", (tokens, cancel, selected_id, selected_mode)))
            except (ValueError, OSError, KeyError, TypeError) as exc:
                self.messages.put(("auth_error", (str(exc), cancel)))
        self.auth_worker = threading.Thread(target=authenticate, daemon=True)
        self.auth_worker.start()
        return True

    def sign_out(self):
        with self.config_lock:
            config = {key: value for key, value in self.config.items() if key not in {"oauth", "oauth_dpapi", "secret", "secret_dpapi"}}
            try:
                local_settings.save_config(config)
            except (ValueError, OSError) as exc:
                messagebox.showerror("MPlusLogs", i18n.tr(str(exc)), parent=self.root)
                return
            # Cancellation belongs to the successful sign-out transaction. A
            # failed settings write must leave an in-flight browser login alive.
            self.auth_cancel.set()
            self.session, self.config = None, config
        self.want_running = True
        self.stop.set()
        self.account.set("Warcraft Logs не подключён")
        self.status.set("Вы вышли. Сохранённые токены удалены с этого компьютера.")
        self.login_button.configure(state="normal")
        self.login_button.pack(side="left", padx=(8, 0))
        self.refresh_api_display()

    def settings(self):
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.deiconify()
            self.settings_window.lift()
            return
        window = self.settings_window = tk.Toplevel(self.root)
        window.protocol("WM_DELETE_WINDOW",self.close_settings)
        if self.update_check_state in {"current","error"}:
            self.set_update_check_state("idle")
        window.title(i18n.tr("Настройки MPlusLogs"))
        window.resizable(False, False)
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, textvariable=self.version_text, style="Muted.TLabel").pack(anchor="w", pady=(0, 12))
        ttk.Label(frame, textvariable=self.textvar("Language")).pack(anchor="w", pady=(0,6))
        self.language_label = self.textvar("Follow Windows" if self.language.get() == "system" else i18n.LANGUAGES[self.language.get()])
        language_picker = ttk.Menubutton(frame, textvariable=self.language_label, direction="below")
        self.language_menu = tk.Menu(language_picker, tearoff=False)
        language_picker.configure(menu=self.language_menu)
        language_picker.pack(fill="x", pady=(0,16))
        self.fill_language_menu()
        ttk.Label(frame, textvariable=self.textvar('Тема оформления')).pack(anchor="w", pady=(0,6))
        names = {"system":"Как в Windows", "light":"Светлая", "dark":"Тёмная"}
        theme_buttons = ttk.Frame(frame)
        theme_buttons.pack(fill="x", pady=(0,16))
        def select_theme():
            self.refresh_theme(force=True)
            self.save_preferences()
        for index, (value, label) in enumerate(names.items()):
            ttk.Radiobutton(theme_buttons, textvariable=self.textvar(label), value=value, variable=self.theme,
                            command=select_theme, style="Theme.TRadiobutton").grid(row=0,column=index,sticky="ew",padx=(0,4))
            theme_buttons.columnconfigure(index, weight=1)
        ttk.Label(frame, textvariable=self.textvar('Автозапуск')).pack(anchor="w", pady=(0, 4))
        for value, label in (("windows", 'Запускать при входе в Windows'),
                             ("retail", 'Запускать вместе с WoW Retail'),
                             ("manual", 'Не запускать автоматически')):
            ttk.Radiobutton(frame, textvariable=self.textvar(label), value=value,
                            variable=self.startup_mode, command=self.save_preferences).pack(anchor="w", pady=3)
        ttk.Label(frame, textvariable=self.textvar('Фоновое ожидание запуска Retail. Classic и PTR\nне запускают помощник.'), style="Muted.TLabel").pack(anchor="w", pady=(0,8))
        ttk.Checkbutton(frame, textvariable=self.textvar('Звук готовности ответа'), variable=self.sound, command=self.save_preferences).pack(anchor="w", pady=6)
        ttk.Button(frame,textvariable=self.textvar('Прослушать звук'),command=companion_audio.play_ready).pack(anchor="w",pady=(0,4))
        ttk.Checkbutton(frame, textvariable=self.textvar('Всплывающие уведомления'), variable=self.notifications, command=self.save_preferences).pack(anchor="w", pady=6)
        ttk.Button(frame,textvariable=self.textvar('Проверить уведомление'),command=self.test_notification).pack(anchor="w",pady=(0,4))
        ttk.Label(frame,textvariable=self.notification_test_status,wraplength=440,style="Muted.TLabel").pack(anchor="w")
        account_actions = ttk.Frame(frame)
        account_actions.pack(fill="x", pady=(12, 0))
        ttk.Label(account_actions, text="Warcraft Logs", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Button(account_actions, textvariable=self.textvar('Переподключить Warcraft Logs'), command=self.sign_in).pack(fill="x", pady=4)
        ttk.Button(account_actions, textvariable=self.textvar('Выйти из Warcraft Logs'), command=self.sign_out).pack(fill="x", pady=4)
        companion_actions = ttk.Frame(frame)
        companion_actions.pack(fill="x", pady=(12, 0))
        ttk.Label(companion_actions, text="Companion", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.settings_update_button = ttk.Button(companion_actions, textvariable=self.settings_update_text, command=self.settings_update_action)
        self.settings_update_button.pack(fill="x", pady=4)
        self.set_update_check_state(self.update_check_state)
        if self.failed_update_version:
            ttk.Button(companion_actions, textvariable=self.textvar('Open update installation log'), command=self.open_update_log).pack(fill="x", pady=4)
        ttk.Button(companion_actions, textvariable=self.textvar('Завершить помощник'), command=self.exit).pack(fill="x", pady=4)
        ttk.Label(companion_actions, textvariable=self.textvar('Закрытие окна оставляет помощник в трее.\nДля завершения: ПКМ по значку → Выйти.'), style="Muted.TLabel").pack(anchor="w", pady=(4, 0))
        window.update_idletasks()
        self.refresh_theme(force=True)

    def show_notification(self,title,text,*,required=False,on_click=None,reply=False):
        if not required and not self.notifications.get():return False
        try:
            if reply:self.popup.show_reply(title,text)
            elif on_click is None:self.popup.show(title,text)
            else:self.popup.show(title,text,on_click=on_click)
            return True
        except (OSError,tk.TclError) as exc:
            self.notification_test_status.set('Не удалось показать уведомление: '+str(exc))
            return False

    def reply_notification_title(self):
        characters=getattr(self,'notification_characters',[])
        summary=clipboard_protocol.reply_summary(getattr(self,'result',None))
        if summary is None:
            return i18n.tr('Reply ready')
        if summary['failed']:
            if not summary['available']:
                return i18n.tr('Logs unavailable · {count} characters').format(count=summary['failed'])
            return i18n.tr('Profiles available: {loaded} · errors: {failed}').format(
                loaded=summary['available'],failed=summary['failed'])
        if summary['choices'] or not summary['available']:
            return i18n.tr('Reply ready')
        if summary['available']>1 or len(characters)!=1:
            return i18n.tr('Group logs ready · {count} characters').format(count=summary['available'])
        character=characters[0]
        template='Logs ready · {character} — {realm}' if character['realm'] else 'Logs ready · {character}'
        return i18n.tr(template).format(character=character['name'],realm=character['realm'])

    def test_notification(self):
        if not self.notifications.get():
            self.notification_test_status.set('Сначала включите всплывающие уведомления.')
            return
        if self.show_notification('MPlusLogs Companion',i18n.tr('Это тестовое уведомление MPlusLogs Companion.')):
            self.notification_test_status.set('Показано тестовое уведомление Companion.')

    def save_preferences(self):
        previous = windows.autostart_enabled()
        previous_retail = windows.retail_autostart_enabled()
        mode = self.startup_mode.get()
        try:
            windows.set_autostart(mode == "windows")
            windows.set_retail_autostart(mode == "retail")
            # Complete fallible startup changes before committing preferences.
            # Rolling back an old whole-config snapshot could restore a token
            # superseded by a concurrent OAuth refresh.
            windows.ensure_retail_watcher()
            with self.config_lock:
                config = dict(self.config, sound=self.sound.get(), notifications=self.notifications.get(), autostart=mode == "windows", retail_autostart=mode == "retail", theme=self.theme.get(), language=self.language.get())
                local_settings.save_config(config)
                self.config = config
                if not self.notifications.get():self.popup.close()
        except (ValueError, OSError) as exc:
            try:
                windows.set_autostart(previous)
                windows.set_retail_autostart(previous_retail)
            except (ValueError, OSError):
                pass
            self.startup_mode.set(self.current_startup_mode())
            messagebox.showerror("MPlusLogs", i18n.tr("Не удалось сохранить настройки: " + str(exc)), parent=self.root)

    @staticmethod
    def current_startup_mode():
        if windows.retail_autostart_enabled():
            return "retail"
        if windows.autostart_enabled():
            return "windows"
        return "manual"

    def start(self):
        if self.installing_update or not self.want_running or (self.worker and self.worker.is_alive()):
            return
        self.stop = threading.Event()
        self.worker = threading.Thread(target=self.watch, args=(self.stop, self.session, self.mode_diagnostic, self.root.winfo_id()), daemon=True)
        self.worker.start()

    def watch(self, stop, session, diagnostic, owner):
        def post(kind, value):
            self.messages.put(("worker", (stop, kind, value)))
        try:
            clipboard = bridge.WindowsClipboard(owner=owner)
            if session:
                # Do not reuse user-endpoint data between accounts.
                scope = session.cache_scope()
                state_path = personal_api.budget_path(DATA_ROOT, self.api_mode, self.client_id)
                client = bridge.Client(3600 if self.api_mode == "personal" else 120,
                    token_provider=session.access_token, invalidate_token=session.invalidate,
                    state_path=state_path, cache_scope=scope, auth_generation=session.auth_generation())
                client.api_mode = self.api_mode
                client.cancel = stop
                client.search_status = lambda message: post("status",message)
                quota = session.tokens.get("_api_budget")
                if quota and quota.get("reset_at", 0) > time.time() and not client.budget.snapshot()["limitPerHour"]:
                    client.budget.observe({"limitPerHour": quota["limit"], "pointsSpentThisHour": quota["limit"] - quota["remaining"], "pointsResetIn": quota["reset_at"] - time.time()})
            else:
                client = None
            mapping = realm_resolver.load_mappings()
            post("status", "Проверка связи: ожидаю запрос из WoW." if diagnostic else "Готов к работе. Ожидаю запрос из WoW.")
            last_sequence = None
            while not stop.wait(0.3):
                cache_maintenance.maintain(DATA_ROOT / ".wcl-cache")
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
                    if clipboard_protocol.is_open_updates_command(text):
                        post("open_updates",None)
                        continue
                    if not clipboard_protocol.unwrap_request(text):
                        if text.startswith(("MPLQ1", "MPLQ2")) or (text.startswith("MPLS1") and "MPLQ" in text):
                            post("status", "Запрос скопирован не полностью. Выделите поле в WoW (Ctrl+A), затем Ctrl+C.")
                        continue
                    post("request_started",clipboard_protocol.request_characters(text))
                    post("progress", dict(stage="preparing"))
                    if not session and not diagnostic:
                        request_id=clipboard_protocol.unwrap_request(text)[0]
                        from urllib.parse import quote
                        response="MPLE1\n"+request_id+"\n"+quote("Сначала войдите в Warcraft Logs.",safe="")
                    else:
                        response = clipboard_protocol.reply(text, mapping, DATA_ROOT / ".wcl-cache", client, diagnostic,
                            progress=lambda value: post("progress", value))
                    if isinstance(client, bridge.Client):
                        client.save_request_metrics(DATA_ROOT / '.wcl-cache' / 'request-metrics.json')
                        snapshot = client.budget.snapshot()
                        if snapshot["limitPerHour"]:
                            post("quota", {"remaining": max(0, snapshot["limitPerHour"] - snapshot["pointsSpentThisHour"]), "limit": snapshot["limitPerHour"], "reset_at": snapshot["resetAt"]})
                    if stop.is_set() and not self.installing_update:
                        break
                    post("progress", dict(stage="finalizing"))
                    try:
                        build_database.atomic_write(DATA_ROOT / "last-result.mpl", response)
                    except OSError:
                        # A locked/local result file must not discard a completed
                        # response; retain it in the UI and deliver the clipboard.
                        pass
                    post("result", response)
                    if clipboard.reply_if_unchanged(text, response):
                        post("ready", "Ответ в буфере. Вернитесь в WoW и нажмите Ctrl+V.")
                    else:
                        post("ready", "Ответ готов. Буфер изменился — нажмите «Скопировать последний ответ».")
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    post("status", str(exc))
        except (ValueError, OSError, KeyError, TypeError) as exc:
            post("fatal", "Помощник остановлен: " + str(exc))

    def clear_progress(self):
        self.progress_bar.stop()
        self.progress_bar.pack_forget()

    def show_progress(self, value):
        stages = {
            "preparing": "Preparing request…",
            "profiles": "Loading characters: {completed}/{total}\n{character}",
            "overview": "Loading character overview: {completed}/{total}\n{character}",
            "specializations": "Loading specializations: {completed}/{total}\n{character}",
            "realm_lookup": "Determining character realms: {completed}/{total}",
            "search": "Finding group members: {completed}/{total}\n{character}",
            "finalizing": "Preparing reply…",
        }
        stage = stages[value["stage"]]
        self.progress_bar.stop()
        total = value.get("total", 0)
        if total:
            character = value.get("character", "")
            if value.get("realm"):
                character += " — " + value["realm"]
            if value.get("spec"):
                character += " (" + value["spec"] + ")"
            self.status.set_format(stage, completed=value["completed"], total=total, character=character)
            self.progress_bar.configure(mode="determinate", maximum=total, value=value["completed"])
        else:
            self.status.set(stage)
            self.progress_bar.configure(mode="indeterminate", maximum=100, value=0)
            self.progress_bar.start(40)
        self.progress_bar.pack(fill="x", pady=(8, 0))

    def poll(self):
        if self.exiting:
            return
        if self.stop.is_set():
            self.clear_progress()
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
            if kind in {"status", "ready", "fatal", "auth", "configured_auth", "auth_error"}:
                self.clear_progress()
            if kind == "request_started":
                self.notification_characters=value
                self.popup.clear_reply()
            elif kind == "progress":
                self.show_progress(value)
            elif kind == "quota":
                # Display upstream observations without an extra API request or disk write.
                self.config.setdefault("oauth", {})["_api_budget"] = value
                self.refresh_api_display()
            elif kind == "show":
                self.show()
            elif kind == "open_updates":
                self.show()
                self.settings()
                self.settings_window.lift()
                self.settings_window.focus_force()
                self.check_updates(manual=True)
            elif kind == "update_available":
                self.available_update=value
                self.update_installer=None
                self.update_button.pack_forget()
                self.update_status.set("A new Companion version is available. Open Companion for details.")
                self.notify_update(value)
            elif kind == "update_reminder":
                self.update_status.set("Companion update is ready.")
                self.set_update_check_state("ready")
                self.notify_update(value,ready=True)
                self.schedule_update_check()
            elif kind == "update_downloading":
                self.update_status.set("Downloading Companion update…")
                self.set_update_check_state("downloading")
            elif kind == "update_ready":
                self.available_update, self.update_installer = value
                self.update_status.set("Companion update is ready.")
                self.set_update_check_state("ready")
                self.update_button.pack(anchor="w", pady=(6, 0))
                self.notify_update(value[0],ready=True,force=True)
                self.schedule_update_check()
            elif kind == "update_current":
                self.update_status.set("Companion is up to date.")
                self.set_update_check_state("current")
                self.schedule_update_check()
            elif kind == "update_check_idle":
                self.set_update_check_state("idle")
                self.schedule_update_check()
            elif kind == "update_error":
                self.set_update_check_state("error")
                self.update_status.set("Could not check updates. Try again later.")
                self.schedule_update_check(UPDATE_RETRY_INTERVAL)
            elif kind == "update_download_error":
                self.set_update_check_state("error")
                self.update_status.set("Could not download the update. Retrying in 5 minutes.")
                self.schedule_update_check(UPDATE_RETRY_INTERVAL)
            elif kind == "exit":
                self.exit()
                return
            elif kind in {"auth", "configured_auth"}:
                if kind == "auth":
                    tokens, cancel = value
                    selected_id, selected_mode = self.client_id, self.api_mode
                else:
                    tokens, cancel, selected_id, selected_mode = value
                if cancel is not self.auth_cancel or cancel.is_set():
                    continue
                try:
                    with self.config_lock:
                        config = dict(self.config, oauth_client_id=selected_id, oauth=tokens, api_mode=selected_mode)
                        if selected_mode == "personal": config["personal_client_id"] = selected_id
                        local_settings.save_config(config)
                        self.client_id, self.api_mode = selected_id, selected_mode
                        self.config = config
                        self.session = self.make_session(tokens)
                    self.account.set("Warcraft Logs подключён")
                    self.login_button.pack_forget()
                    self.mode_diagnostic, self.want_running = False, True
                    self.status.set("Вход выполнен. Помощник готов к работе.")
                    self.refresh_api_display()
                    if self.personal_setup:
                        self.personal_setup.pending = False
                        self.personal_setup.close()
                except (ValueError, OSError) as exc:
                    self.status.set("Не удалось сохранить вход: " + str(exc))
                    self.want_running = True
                    if self.personal_setup: self.personal_setup.failed("Could not save the connection. Your previous connection is still available.")
                self.login_button.configure(state="normal")
            elif kind == "auth_error":
                error, cancel = value
                if cancel is self.auth_cancel and not cancel.is_set():
                    self.status.set("Не удалось войти: " + error)
                    self.login_button.configure(state="normal")
                    self.want_running = True
                    if self.personal_setup: self.personal_setup.failed("Could not connect. Check Client ID, Public Client and Redirect URIs on WCL.")
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
                if kind == "ready":
                    self.show_notification(self.reply_notification_title(),self.status.get(),reply=True)
                    if self.sound.get():
                        companion_audio.play_ready()
        if not self.installing_update:
            self.start()
        self.root.update_idletasks()
        height = max(330, self.body.winfo_reqheight())
        if self.root.winfo_height() != height:
            self.root.geometry(f"500x{height}")
        if time.time() - self.last_heartbeat >= 1:
            self.last_heartbeat = time.time()
            self.refresh_api_display()
            notification=self.popup.status
            if not isinstance(notification,dict): notification=None
            try:
                build_database.atomic_write(DATA_ROOT / "companion-status.json", json.dumps({
                    "updated": self.last_heartbeat, "pid": os.getpid(), "status": self.status.get(),
                    "worker_alive": bool(self.worker and self.worker.is_alive()), "diagnostic": self.mode_diagnostic,
                    "clipboard_sequence": self.clipboard_sequence, "clipboard_events": self.clipboard_events,
                    "oauth_connected": bool(self.session), "tray": bool(self.tray),
                    "notification": notification}, ensure_ascii=False, indent=2))
            except OSError:
                pass
        self.root.after(200, self.poll)

    def refresh_theme(self, force=False):
        mode = appearance.system_theme() if self.theme.get() == "system" else self.theme.get()
        if force or mode != self.applied_theme:
            appearance.apply(self.root, mode, self.settings_window)
            if self.personal_setup:
                appearance.apply(self.root, mode, self.personal_setup.window)
                self.personal_setup.canvas.configure(background=appearance.PALETTES[mode]["background"])
            self.applied_theme = mode
            self.root.after_idle(lambda: appearance.titlebar(self.root, mode == "dark"))
            self.style_language_menu()

    def textvar(self, text):
        variable = i18n.TextVar(self.root, text)
        self.textvars.append(variable)
        return variable

    def change_language(self):
        i18n.set_language(self.language.get())
        for variable in self.textvars:
            variable.refresh()
        if self.tray:
            self.tray.refresh_language()
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.title(i18n.tr("Настройки MPlusLogs"))
            self.language_label.set("Follow Windows" if self.language.get() == "system" else i18n.LANGUAGES[self.language.get()])
            self.fill_language_menu()
        if self.personal_setup:
            self.personal_setup.window.title(i18n.tr("Personal API setup"))
            self.personal_setup.show(self.personal_setup.step)
        self.refresh_api_display()
        self.save_preferences()

    def fill_language_menu(self):
        self.language_menu.delete(0, "end")
        for value, label in {"system":i18n.tr("Follow Windows"), **i18n.LANGUAGES}.items():
            self.language_menu.add_radiobutton(label=label, value=value, variable=self.language, command=self.change_language)
        self.style_language_menu()

    def style_language_menu(self):
        if self.language_menu and self.language_menu.winfo_exists():
            palette = appearance.PALETTES[self.applied_theme or "light"]
            self.language_menu.configure(background=palette["control"], foreground=palette["text"],
                                         activebackground=palette["accent"], activeforeground="#ffffff",
                                         selectcolor=palette["text"], font=("Segoe UI",10), borderwidth=0)

    def copy(self):
        if self.result:
            try:
                bridge.WindowsClipboard(owner=self.root.winfo_id()).write_private(self.result)
                self.status.set("Ответ скопирован. В WoW нажмите Ctrl+V.")
            except OSError as exc:
                self.status.set(str(exc))

    def minimized(self, event):
        if event.widget is self.root and self.root.state() == "iconic" and self.tray:
            self.root.after_idle(self.hide)

    def hide(self):
        if self.tray:
            self.root.withdraw()
            if self.settings_window and self.settings_window.winfo_exists():
                self.settings_window.withdraw()
            if self.personal_setup:
                self.personal_setup.window.withdraw()
        else:
            self.root.iconify()

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        if self.personal_setup:
            self.personal_setup.window.deiconify()

    def exit(self):
        self.exiting = True
        timer=getattr(self,"update_check_after",None)
        if timer is not None:
            self.root.after_cancel(timer)
            self.update_check_after=None
        self.popup.close()
        self.want_running = False
        self.stop.set()
        self.auth_cancel.set()
        if self.tray:
            self.tray.close()
        self.root.destroy()


def main():
    if "--set-notifications" in sys.argv:
        index=sys.argv.index("--set-notifications")
        if index+1>=len(sys.argv) or sys.argv[index+1] not in {"on","off"}:
            raise SystemExit(2)
        try:
            local_settings.set_notifications(sys.argv[index+1]=="on")
        except (ValueError,OSError):
            raise SystemExit(1)
        return
    if "--self-test-report" in sys.argv:
        import release_smoke
        release_smoke.run(sys.argv[sys.argv.index("--self-test-report") + 1])
        return
    import companion_location
    if companion_location.guard():
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
