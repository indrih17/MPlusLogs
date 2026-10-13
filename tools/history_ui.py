"""Companion local-history window and scanner; no account, API client or uploads."""
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, ttk

import combat_history
import appearance
import companion_i18n as i18n
import local_settings


class LocalHistory:
    def __init__(self, app, database=None):
        self.app = app
        self.history = combat_history.History(database or local_settings.PATH.parent / "combat-history.sqlite3")
        self.window = self.worker = None
        self.last_check = 0

    def source(self):
        configured=self.app.config.get("combat_log_path")
        if configured: return Path(configured)
        for parent in Path(__file__).resolve().parents:
            if parent.name.lower()=="_retail_": return parent / "Logs/WoWCombatLog.txt"
        return None

    def scan(self):
        source=self.source()
        if not source or not source.is_file():
            raise ValueError("Choose WoWCombatLog.txt or an archived combat log in Local history.")
        return self.history.scan(source,self.app.config.get("combat_log_region","eu"))

    def reply(self, region, realm, name):
        # Import all currently written bytes before answering; no network is used.
        while True:
            progress=self.scan()
            if not progress["remaining"] or not progress["lines"]: break
        return combat_history.export(self.history,region,realm,name)

    def poll(self, now):
        if now-self.last_check<10 or (self.worker and self.worker.is_alive()): return
        self.last_check=now
        source=self.source()
        if not source or not source.is_file(): return
        self.refresh()

    def refresh(self):
        if self.worker and self.worker.is_alive(): return
        def work():
            try:
                progress=self.scan()
                self.app.messages.put(("history_refresh",progress))
            except (ValueError,OSError,KeyError,TypeError) as exc:
                self.app.messages.put(("history_error",str(exc)))
        self.worker=threading.Thread(target=work,daemon=True)
        self.worker.start()

    def choose(self):
        selected=filedialog.askopenfilename(parent=self.window,title=i18n.tr("Choose a combat log"),
            filetypes=[(i18n.tr("Combat log"),"*.txt"),(i18n.tr("All files"),"*.*")])
        if not selected: return
        self.app.config["combat_log_path"]=selected
        local_settings.save_config(self.app.config)
        self.path.set(selected)
        self.last_check=0
        self.refresh()

    def open(self):
        if self.window and self.window.winfo_exists():
            self.window.deiconify(); self.window.lift(); self.render(); return
        self.window=tk.Toplevel(self.app.root)
        self.window.title(i18n.tr("Local combat history")); self.window.geometry("850x590")
        body=ttk.Frame(self.window,padding=16); body.pack(fill="both",expand=True); self.body=body
        ttk.Label(body,textvariable=self.app.textvar("Local files only. These counts are separate from WCL percentiles."),wraplength=790).pack(anchor="w")
        self.path=tk.StringVar(value=str(self.source() or ""))
        ttk.Entry(body,textvariable=self.path,state="readonly").pack(fill="x",pady=8)
        controls=ttk.Frame(body); controls.pack(fill="x")
        ttk.Button(controls,textvariable=self.app.textvar("Choose a combat log"),command=self.choose).pack(side="left")
        ttk.Button(controls,textvariable=self.app.textvar("Refresh history"),command=self.refresh).pack(side="left",padx=8)
        ttk.Label(controls,textvariable=self.app.textvar("Region")).pack(side="left",padx=8)
        self.region=tk.StringVar(value=self.app.config.get("combat_log_region","eu"))
        choice=ttk.Combobox(controls,textvariable=self.region,values=sorted(combat_history.REGIONS),state="readonly",width=5)
        choice.pack(side="left")
        def select_region(_):
            self.app.config["combat_log_region"]=self.region.get()
            local_settings.save_config(self.app.config); self.refresh()
        choice.bind("<<ComboboxSelected>>",select_region)
        self.status=self.app.textvar("Enable /combatlog in WoW to record new runs. Advanced combat logging provides the party roster.")
        ttk.Label(body,textvariable=self.status,wraplength=790).pack(anchor="w",pady=8)
        self.run_list=ttk.Treeview(body,columns=("date","dungeon","key","coverage"),show="headings",height=7)
        for key,label,width in [("date","Date",180),("dungeon","Dungeon",350),("key","Key",60),("coverage","Coverage",160)]:
            self.run_list.heading(key,text=i18n.tr(label)); self.run_list.column(key,width=width,stretch=key=="dungeon")
        self.run_list.pack(fill="x")
        self.run_list.bind("<<TreeviewSelect>>",lambda _:self.render_party())
        self.party=ttk.Treeview(body,columns=("name","spec","interrupts","deaths","dispels"),show="headings",height=5)
        for key,label,width in [("name","Player",300),("spec","Specialization ID",120),("interrupts","Interrupts",100),("deaths","Deaths",100),("dispels","Dispels",100)]:
            self.party.heading(key,text=i18n.tr(label)); self.party.column(key,width=width,stretch=key=="name")
        self.party.pack(fill="x",pady=8)
        self.detail=self.app.textvar("")
        ttk.Label(body,textvariable=self.detail,wraplength=790).pack(anchor="w")
        ttk.Label(body,textvariable=self.app.textvar("In WoW: /mpl history, request local history, then Ctrl+C and Ctrl+V."),wraplength=790).pack(anchor="w",pady=8)
        self.apply_theme(getattr(self.app, "applied_theme", None) or appearance.system_theme())
        self.render(); self.refresh()

    def apply_theme(self, mode):
        if not self.window or not self.window.winfo_exists(): return
        appearance.apply(self.app.root, mode, self.window)
        window = self.window
        def update_titlebar():
            if window.winfo_exists(): appearance.titlebar(window, mode == "dark")
        window.after_idle(update_titlebar)

    def render(self, progress=None, error=None):
        if not self.window or not self.window.winfo_exists(): return
        if error: self.status.set(error)
        elif progress: self.status.set_format("Read {lines} new lines; {remaining} bytes pending.",**{k:progress[k] for k in ("lines","remaining")})
        runs,total=self.history.runs(region=self.app.config.get("combat_log_region","eu"))
        self.runs={r["id"]:r for r in runs}
        selection=self.run_list.selection()
        self.run_list.delete(*self.run_list.get_children())
        for run in runs:
            self.run_list.insert("","end",iid=run["id"],values=(run["started"][:19].replace("T"," "),run["dungeon"],
                "+"+str(run["level"]),i18n.tr("Complete" if run["coverage"]=="complete" else "Partial")))
        if selection and selection[0] in self.runs: self.run_list.selection_set(selection[0])
        elif runs: self.run_list.selection_set(runs[0]["id"])
        self.render_party()

    def render_party(self):
        self.party.delete(*self.party.get_children())
        selected=self.run_list.selection()
        if not selected or selected[0] not in self.runs: self.detail.set(""); return
        run=self.runs[selected[0]]
        for p in run["players"]:
            self.party.insert("","end",values=((p["name"]+"-"+p["realm"]) if p["name"] else p["guid"],
                p["spec_id"] or "—",p["interrupts"],p["deaths"],p["dispels"]))
        source=run["sources"][-1]
        self.detail.set_format("Source: {source}; lines {first}-{last}. Complete observations in view: {count}.",
            source=source["path"],first=source["first_line"],last=source["last_line"],count=sum(r["coverage"]=="complete" for r in self.runs.values()))
        if run["coverage"]!="complete": self.detail.set(self.detail.get()+" "+i18n.tr("Partial counts are observed events, not complete-run totals."))
        if run["year_inferred"]: self.detail.set(self.detail.get()+" "+i18n.tr("Year inferred from file date."))
        self.window.update_idletasks()
        self.window.geometry(f"850x{max(590,self.body.winfo_reqheight())}")

    def close(self):
        if self.window and self.window.winfo_exists(): self.window.destroy()
