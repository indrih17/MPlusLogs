"""Native-app WCL login: external browser, loopback callback, S256 PKCE. No secret."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import secrets
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit
import webbrowser

import wcl_sync as wcl

REDIRECT_URI = "http://127.0.0.1:43827/callback"


def challenge(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")


def callback_code(path, state):
    parsed = urlsplit(path)
    if parsed.path != "/callback":
        raise ValueError("Unexpected callback path")
    params = parse_qs(parsed.query)
    received = params.get("state", [])
    if len(received) != 1 or not secrets.compare_digest(received[0], state):
        raise ValueError("Invalid OAuth state")
    if "error" in params:
        raise PermissionError("Вход отменён на сайте Warcraft Logs.")
    codes = params.get("code", [])
    if len(codes) != 1 or not codes[0] or len(codes[0]) > 8192:
        raise ValueError("Missing OAuth code")
    return codes[0]


def token_record(response, previous=None):
    if not isinstance(response.get("access_token"), str) or not response["access_token"]:
        raise ValueError("Warcraft Logs не вернул токен. Повторите вход.")
    if response.get("token_type", "Bearer").lower() != "bearer":
        raise ValueError("Unsupported OAuth token type")
    try:
        lifetime = int(response["expires_in"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("Warcraft Logs не сообщил срок действия токена.") from None
    if lifetime <= 0:
        raise ValueError("OAuth token already expired")
    return {"access_token": response["access_token"],
            "refresh_token": response.get("refresh_token") or (previous or {}).get("refresh_token"),
            "expires_at": time.time() + lifetime}


def exchange(fields):
    return wcl.request_json(wcl.ROOT + "/oauth/token", urlencode(fields).encode(),
                            {"Content-Type": "application/x-www-form-urlencoded"})


def login(client_id, cancel=None, opener=webbrowser.open, timeout=180):
    if not client_id or any(c.isspace() for c in client_id):
        raise ValueError("Нужен Client ID публичного приложения WCL.")
    cancel = cancel or threading.Event()
    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(32)
    result = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # The callback URL contains a one-use authorization code.

        def do_GET(self):
            try:
                result["code"] = callback_code(self.path, state)
                status, message = 200, "Вход получен. Вернитесь в MPlusLogs — программа проверит подключение. Эту вкладку можно закрыть."
            except PermissionError as exc:
                result["error"] = exc
                status, message = 200, "Вход в MPlusLogs отменён. Эту вкладку можно закрыть."
            except ValueError:
                status, message = 400, "Invalid MPlusLogs callback."
            body = message.encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    class Server(HTTPServer):
        def get_request(self):
            connection, address = super().get_request()
            connection.settimeout(2)
            return connection, address

    try:
        server = Server(("127.0.0.1", 43827), Handler)
    except OSError:
        raise ValueError("Не удалось открыть локальный порт 43827 для входа. Закройте другое приложение, использующее этот порт.") from None
    with server:
        server.timeout = 0.5
        url = wcl.ROOT + "/oauth/authorize?" + urlencode({
            "client_id": client_id, "redirect_uri": REDIRECT_URI, "response_type": "code",
            "state": state, "code_challenge": challenge(verifier), "code_challenge_method": "S256"})
        if not opener(url):
            raise ValueError("Не удалось открыть браузер для входа в Warcraft Logs.")
        deadline = time.monotonic() + timeout
        while not result and not cancel.is_set() and time.monotonic() < deadline:
            server.handle_request()
    if cancel.is_set():
        raise ValueError("Вход отменён.")
    if "error" in result:
        raise result["error"]
    if "code" not in result:
        raise ValueError("Время ожидания входа истекло. Нажмите «Войти» ещё раз.")
    return token_record(exchange({"client_id": client_id, "redirect_uri": REDIRECT_URI,
                                 "grant_type": "authorization_code", "code": result["code"],
                                 "code_verifier": verifier}))


class Session:
    def __init__(self, client_id, tokens, persist):
        self.client_id, self.tokens, self.persist = client_id, dict(tokens), persist
        self.lock = threading.Lock()

    def access_token(self):
        with self.lock:
            if time.time() < self.tokens.get("expires_at", 0) - 60:
                return self.tokens["access_token"]
            if not self.tokens.get("refresh_token"):
                raise ValueError("Сессия Warcraft Logs истекла. Войдите ещё раз.")
            updated = token_record(exchange({"grant_type": "refresh_token", "client_id": self.client_id,
                                            "refresh_token": self.tokens["refresh_token"]}), self.tokens)
            self.persist(updated)
            self.tokens = updated
            return updated["access_token"]

    def invalidate(self):
        with self.lock:
            self.tokens["expires_at"] = 0


def validate_access(tokens):
    """Verify authentication and character API before persisting a new login."""
    data = wcl.request_json(wcl.ROOT + "/api/v2/user",
                           b'{"query":"{ rateLimitData { limitPerHour } characterData { __typename } }"}',
                           {"Authorization": "Bearer " + tokens["access_token"], "Content-Type": "application/json"})
    if data.get("errors") or not data.get("data", {}).get("characterData"):
        raise ValueError("Вход выполнен, но доступ к API персонажей WCL не подтверждён.")
