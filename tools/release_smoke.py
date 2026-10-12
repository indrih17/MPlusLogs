"""Offline validation inside the frozen executable; no account or clipboard access."""
import json
from pathlib import Path
import sys
import tkinter as tk
import realm_resolver
import windows_integration as windows


def run(report_path):
    import companion_update
    companion_update.version_tuple(companion_update.current_version())
    import companion_i18n
    for language in companion_i18n.LANGUAGES:
        assert companion_i18n.catalog(language)["Настройки"]
    import retail_launcher  # Also verify the dynamically imported watcher is bundled.
    import wcl_oauth
    config = json.loads(Path(__file__).with_name("oauth_client.json").read_text(encoding="utf-8"))
    assert set(config) == {"client_id", "redirect_uri"}
    assert config["client_id"] and config["redirect_uri"] == wcl_oauth.REDIRECT_URI
    assert realm_resolver.resolve(realm_resolver.load_mappings(), "eu", "Гордунни") == "gordunni"
    assert windows.startup_args()[0] == sys.executable
    root = tk.Tk()
    root.withdraw()
    try:
        root.iconbitmap(str(Path(__file__).with_name("assets") / "mpluslogs.ico"))
        logo = tk.PhotoImage(file=str(Path(__file__).with_name("assets") / "mpluslogs.png"))
        assert logo.width() == 256
        import personal_api
        assert personal_api.validate_client_id("smoke-personal-client")
        for name in ("personal-api-form.png", "personal-api-id.png"):
            guide = tk.PhotoImage(file=str(Path(__file__).with_name("assets") / name))
            assert guide.width() == 680
        instance = windows.SingleInstance(namespace="PackagingSmoke", notify=False)
        try:
            assert instance.primary
        finally:
            instance.close()
        root.update()
    finally:
        root.destroy()
    Path(report_path).write_text(json.dumps({"ok": True, "frozen": bool(getattr(sys, "frozen", False)),
        "executable": sys.executable, "checks": ["tkinter", "branding", "oauth-config", "realms", "single-instance", "retail-launcher", "startup-path", "companion-locales", "personal-api-guide"]}, indent=2), encoding="utf-8")
