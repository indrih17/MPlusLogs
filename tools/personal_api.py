"""Three-step personal WCL client setup; examples contain no real credentials."""
from pathlib import Path
import hashlib
import math
import re
import tkinter as tk
from tkinter import ttk
import webbrowser

from PIL import Image, ImageTk

import companion_i18n as i18n
import wcl_oauth

CLIENTS_URL = "https://www.warcraftlogs.com/api/clients"
CLIENT_NAME = "MPlusLogs Companion"
EXAMPLE_ID = "12345678-abcd-4ef0-9876-123456789abc"


def load_guide_images(master):
    images = {}
    for name in ("personal-api-clients.png", "personal-api-form.png", "personal-api-id.png"):
        with Image.open(Path(__file__).with_name("assets") / name) as source:
            height = round(source.height * 680 / source.width)
            images[name] = ImageTk.PhotoImage(
                source.resize((680, height), Image.Resampling.LANCZOS), master=master)
    return images


def budget_path(root, mode, client_id):
    name = "api-state-" + hashlib.sha256(client_id.encode()).hexdigest()[:16] + ".sqlite3" if mode == "personal" else "api-state.sqlite3"
    return root / ".wcl-cache" / name


def quota_record(quota, now):
    if not isinstance(quota, dict):
        return None
    try:
        cap, spent, reset = (float(quota[key]) for key in ("limitPerHour", "pointsSpentThisHour", "pointsResetIn"))
        if not all(math.isfinite(value) for value in (cap, spent, reset)) or cap <= 0 or spent < 0 or not 0 <= reset <= 86400:
            return None
        return {"remaining": max(0, cap - spent), "limit": cap, "reset_at": now + reset}
    except (KeyError, ValueError, TypeError):
        return None


def validate_client_id(value, shared_id=None):
    value = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) or value == EXAMPLE_ID:
        raise ValueError("Paste your Client ID, not the example or Client Secret.")
    if value == shared_id:
        raise ValueError("This is the shared MPlusLogs client. Create your own client on WCL.")
    return value


class Wizard:
    def __init__(self, owner):
        self.owner = owner
        self.window = tk.Toplevel(owner.root)
        self.window.title(i18n.tr("Personal API setup"))
        self.window.geometry("780x820")
        self.window.minsize(740, 480)
        self.window.transient(owner.root)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.step = 0
        self.pending = False
        self.client_id = tk.StringVar(value=owner.config.get("personal_client_id", ""))
        self.images = load_guide_images(self.window)
        outer = ttk.Frame(self.window, padding=20)
        outer.pack(fill="both", expand=True)
        self.progress = owner.textvar("")
        ttk.Label(outer, textvariable=self.progress, style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
        self.title = owner.textvar("")
        ttk.Label(outer, textvariable=self.title, font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 8))
        self.description = owner.textvar("")
        ttk.Label(outer, textvariable=self.description, wraplength=700).pack(anchor="w", fill="x", pady=(0, 12))
        nav = ttk.Frame(outer)
        nav.pack(side="bottom", fill="x", pady=(12, 0))
        self.back = ttk.Button(nav, textvariable=owner.textvar("Back"), command=lambda: self.show(self.step - 1))
        self.next_text = owner.textvar("Next")
        self.next = ttk.Button(nav, textvariable=self.next_text, command=self.advance)
        self.next.pack(side="right")
        self.status = owner.textvar("")
        status_label = ttk.Label(outer, textvariable=self.status, wraplength=700)
        status_label.pack(side="bottom", anchor="w", fill="x", pady=(8, 0))
        status_label.bind("<Configure>", lambda _: self.fit_content())
        viewport = ttk.Frame(outer)
        viewport.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(viewport, highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.content = ttk.Frame(self.canvas)
        self.content_id = self.canvas.create_window(0, 0, anchor="nw", window=self.content)
        self.content.bind("<Configure>", lambda _: self.fit_content())
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(self.content_id, width=event.width))
        self.show(0)

    def fit_content(self):
        if self.canvas.winfo_height() <= 1:
            return
        overhead = self.window.winfo_height() - self.canvas.winfo_height()
        height = max(480, overhead + self.content.winfo_reqheight() + 4)
        self.window.minsize(740, height)
        if self.window.winfo_height() < height:
            self.window.geometry(f"{self.window.winfo_width()}x{height}")

    def label(self, text, **options):
        label = ttk.Label(self.content, textvariable=self.owner.textvar(text), wraplength=680, **options)
        label.pack(anchor="w", fill="x", pady=(0, 10))
        return label

    def copy(self, value):
        self.window.clipboard_clear()
        self.window.clipboard_append(value)
        self.status.set("Copied. Open this address in your browser." if value == CLIENTS_URL else "Copied. Paste into the matching field on WCL.")

    def field(self, title, value):
        row = ttk.Frame(self.content)
        row.pack(fill="x", pady=(0, 12))
        ttk.Label(row, text=title, width=15).pack(side="left")
        field = ttk.Entry(row)
        field.insert(0, value)
        field.configure(state="readonly")
        field.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(row, textvariable=self.owner.textvar("Copy"), command=lambda: self.copy(value)).pack(side="right")

    def open_wcl(self):
        if not webbrowser.open(CLIENTS_URL):
            self.status.set("Could not open WCL. Open this address in your browser:")
            self.field("WCL", CLIENTS_URL)

    def show(self, step):
        if self.pending:
            return
        self.step = max(0, min(2, step))
        for widget in self.content.winfo_children(): widget.destroy()
        self.status.set("")
        self.progress.set_format("Step {step} of 3", step=self.step + 1)
        if self.step:
            self.back.pack(side="left")
            self.back.configure(state="normal")
        else:
            self.back.pack_forget()
        self.next_text.set("Connect and check" if self.step == 2 else "Next")
        titles = ("1. Open Warcraft Logs", "2. Create a public client", "3. Paste your Client ID")
        descriptions = (
            "Sign in to your WCL account, then click Create Client. Keep Companion open.",
            "Fill in the fields as shown below. Enable Public Client, then click Create.",
            "Copy Client ID from your new WCL client and paste it here. Client Secret is not needed.")
        self.title.set(titles[self.step])
        self.description.set(descriptions[self.step])
        if self.step == 0:
            ttk.Button(self.content, textvariable=self.owner.textvar("Open WCL client page"), command=self.open_wcl).pack(anchor="w", pady=(4, 16))
            self.field("WCL", CLIENTS_URL)
            ttk.Label(self.content, image=self.images["personal-api-clients.png"]).pack(anchor="center", pady=(0, 8))
            self.label("If WCL asks you to sign in, sign in on its website and return to the client page.")
            self.label("Your client is created in your own WCL account. WCL determines its available quota.")
            ttk.Button(self.content, textvariable=self.owner.textvar("I already have a Client ID"), command=lambda: self.show(2)).pack(anchor="w", pady=12)
        elif self.step == 1:
            image = self.images["personal-api-form.png"]
            preview = tk.Canvas(self.content, width=image.width(), height=image.height(), highlightthickness=0)
            preview.pack(anchor="center", pady=(0, 8))
            preview.create_image(0, 0, anchor="nw", image=image)
            # Bounds in the original WCL screenshot; keep the fields unobscured.
            scale = image.width() / 1082
            for bounds in ((276, 184, 594, 218), (428, 286, 746, 319), (193, 375, 217, 398)):
                preview.create_rectangle(*(coordinate * scale for coordinate in bounds), outline="#ff3030", width=2)
            self.label("Illustrated example, not a screenshot of your account.", style="Muted.TLabel")
            self.field("Name", CLIENT_NAME)
            self.field("Redirect URIs", wcl_oauth.REDIRECT_URI)
            self.label("Copy the complete redirect address without changing it.\nPUBLIC CLIENT MUST BE ENABLED.")
        else:
            image = self.images["personal-api-id.png"]
            preview = tk.Canvas(self.content, width=image.width(), height=image.height(), highlightthickness=0)
            preview.pack(anchor="center", pady=(0, 8))
            preview.create_image(0, 0, anchor="nw", image=image)
            scale = image.width() / 1143
            preview.create_rectangle(*(coordinate * scale for coordinate in (328, 504, 728, 530)), outline="#ff3030", width=2)
            self.label("The pictured ID is only an example. Use the ID created in your account.", style="Muted.TLabel")
            ttk.Label(self.content, text="Client ID").pack(anchor="w", pady=(6, 4))
            row = ttk.Frame(self.content)
            row.pack(fill="x", pady=(0, 12))
            self.entry = ttk.Entry(row, textvariable=self.client_id)
            self.entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
            self.entry.bind("<Return>", lambda _: self.advance())
            ttk.Button(row, textvariable=self.owner.textvar("Paste"), command=self.paste).pack(side="right")
            self.label("Next, your browser will ask you to authorize your client. Your password stays on WCL.")
            self.label("Your current connection stays available until the new connection is checked successfully.")
            self.entry.focus_set()
        self.canvas.yview_moveto(0)

    def paste(self):
        try:
            self.client_id.set(self.window.clipboard_get().strip())
        except tk.TclError:
            self.status.set("The clipboard contains no text. Copy Client ID on WCL first.")

    def advance(self):
        if self.pending:
            return
        if self.step < 2:
            self.show(self.step + 1)
            return
        try:
            candidate = validate_client_id(self.client_id.get(), self.owner.shared_client_id)
        except ValueError as exc:
            self.status.set(str(exc))
            return
        if self.owner.sign_in(candidate, mode="personal"):
            self.pending = True
            self.next.configure(state="disabled")
            self.back.configure(state="disabled")
            self.status.set("Finish sign-in in your browser. Companion will check the connection.")

    def failed(self, message):
        self.pending = False
        self.next.configure(state="normal")
        self.back.configure(state="normal")
        self.status.set(message)

    def close(self):
        if self.pending:
            self.owner.auth_cancel.set()
            self.owner.want_running = bool(self.owner.session)
            self.owner.login_button.configure(state="normal")
            self.owner.status.set("Connection setup cancelled. Your previous connection is still available.")
        self.owner.personal_setup = None
        self.window.destroy()
