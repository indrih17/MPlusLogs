"""Companion client for the optional shared public-profile service. No WCL secrets."""
import json
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen, HTTPRedirectHandler, build_opener
import webbrowser

import wcl_sync as wcl


def service_url(value):
    parts = urlsplit(value)
    local = parts.hostname in {"localhost", "127.0.0.1", "::1"}
    if (parts.scheme != "https" and not (local and parts.scheme == "http") or not parts.netloc
            or parts.username or parts.password or parts.query or parts.fragment or parts.path not in {"", "/"}):
        raise ValueError("Profile server URL must be HTTPS (HTTP is allowed only on localhost)")
    return value.rstrip("/")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # Never forward a bearer token to another origin.


def request(base, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = Request(service_url(base) + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    try:
        with build_opener(NoRedirect()).open(req, timeout=50) as response:
            payload = response.read(500001)
        if len(payload) > 500000:
            raise ValueError("Profile server response is too large")
        result = json.loads(payload)
        if not isinstance(result, dict):
            raise ValueError("Invalid profile server response")
        return result
    except HTTPError as exc:
        # Only interpret authored, bounded JSON fields; never print headers/body.
        retry = wcl.retry_seconds(exc.headers.get("Retry-After"))
        status = exc.code
        exc.close()
        message = f"Profile server HTTP {status}; " + (f"retry after {int(retry)} seconds" if retry else "sign in again or retry later")
        raise wcl.APIError(message, status, retry) from None
    except URLError:
        raise wcl.APIError("Could not connect to profile server") from None


def login(base, cancel=None, opener=webbrowser.open, timeout=180):
    base = service_url(base)
    cancel = cancel or threading.Event()
    start = request(base, "/v1/auth/start", {})
    # The browser also stays on the configured origin before WCL authorization.
    state, poll = start["state"], start["poll_token"]
    if not isinstance(state, str) or len(state) != 64 or any(c not in "0123456789abcdef" for c in state):
        raise ValueError("Invalid profile server authorization")
    if not opener(base + "/auth/authorize?state=" + state):
        raise ValueError("Не удалось открыть браузер для входа в Warcraft Logs.")
    deadline = time.monotonic() + timeout
    while not cancel.wait(2) and time.monotonic() < deadline:
        response = request(base, "/v1/auth/poll", {"poll_token": poll})
        if response.get("status") == "ready":
            tokens = response["session"]
            tokens["_service_url"] = base
            Session(tokens).access_token()  # Reject invalid/expired session before saving.
            return tokens
        if response.get("status") == "failed":
            raise ValueError("Profile server sign-in failed; retry Warcraft Logs sign-in")
    raise ValueError("Вход отменён." if cancel.is_set() else "Время ожидания входа истекло. Нажмите «Войти» ещё раз.")


class Session:
    def __init__(self, tokens):
        self.tokens = dict(tokens)
        self.base = service_url(self.tokens["_service_url"])

    def access_token(self):
        token = self.tokens.get("access_token")
        if not isinstance(token, str) or not 20 <= len(token) <= 256 or time.time() >= self.tokens.get("expires_at", 0):
            raise ValueError("Сессия Warcraft Logs истекла. Войдите ещё раз.")
        return token

    def invalidate(self):
        self.tokens["expires_at"] = 0


class Client:
    def __init__(self, session, cancel=None):
        self.session = session
        self.cancel = cancel or threading.Event()
        self.cache_scope = "public-service:" + session.base

    def __call__(self, args):
        entry = {key: getattr(args, key, None) for key in ("name", "realm", "region", "spec")}
        result = request(self.session.base, "/v1/profile", entry, self.session.access_token())
        deadline = time.monotonic() + 180
        while result.get("status") == "queued":
            if self.cancel.wait(2) or time.monotonic() >= deadline:
                raise ValueError("Profile request is still queued; retry later")
            result = request(self.session.base, "/v1/job", {"job": result["job"]}, self.session.access_token())
        if result.get("negative"):
            error = wcl.NoProfile(result.get("error", "Публичные логи M+ не найдены"))
            error.fetched_at = result["fetched_at"]
            raise error
        if result.get("status") != "ready" or not isinstance(result.get("raw"), dict):
            raise wcl.APIError("Profile server update unavailable; retry later", retry_after=result.get("retry_after", 60))
        raw = result["raw"]
        raw["_mplus_cache"] = {"fetched_at": result["fetched_at"], "error": result.get("error")}
        return raw
