"""Small login service used by Nginx auth_request in the Ubuntu deployment."""

import hashlib
import html
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response


COOKIE_NAME = "math_page_session"
SESSION_SECONDS = 7 * 24 * 60 * 60
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PASSWORD_HASHER = PasswordHasher()
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def _db_path() -> Path:
    return Path(os.environ.get("AUTH_DB_PATH", "auth.sqlite3"))


def _origin() -> str:
    return os.environ.get("APP_ORIGIN", "http://localhost:8001").rstrip("/")


@contextmanager
def _db():
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        "id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, created_at INTEGER NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS sessions ("
        "token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
        "expires_at INTEGER NOT NULL)"
    )
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def _page(title: str, body: str) -> HTMLResponse:
    content = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} — Math Page Vision Lab</title>
<style>body{{font:16px system-ui,sans-serif;background:#f4f6fa;color:#1c2735;margin:0}}
main{{max-width:420px;margin:8vh auto;padding:32px;background:white;border-radius:14px;
box-shadow:0 8px 30px #16253a18}}h1{{font-size:25px;margin:0 0 10px}}
p{{line-height:1.5}}label{{display:block;margin:18px 0 5px}}input{{box-sizing:border-box;
width:100%;padding:11px;border:1px solid #9ca9b8;border-radius:7px;font:inherit}}
button{{margin-top:22px;background:#1769aa;border:0;border-radius:7px;color:white;
padding:11px 18px;font:inherit;cursor:pointer}}a{{color:#1769aa}}.error{{color:#a22222}}</style>
</head><body><main>{body}</main></body></html>"""
    return HTMLResponse(content, headers={
        "Cache-Control": "no-store",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "same-origin",
    })


def _form(action: str, title: str, submit: str, alternate: str, alternate_href: str,
          error: str = "", email: str = "") -> HTMLResponse:
    message = f'<p class="error" role="alert">{html.escape(error)}</p>' if error else ""
    body = f"""<h1>{html.escape(title)}</h1>{message}
<form action="/auth/{action}" method="post">
<label for="email">Электронная почта</label>
<input id="email" name="email" type="email" value="{html.escape(email, quote=True)}"
autocomplete="email" maxlength="254" required>
<label for="password">Пароль</label>
<input id="password" name="password" type="password" autocomplete="{'new-password' if action == 'register' else 'current-password'}"
minlength="8" maxlength="128" required>
<button type="submit">{html.escape(submit)}</button></form>
<p><a href="{alternate_href}">{html.escape(alternate)}</a></p>"""
    return _page(title, body)


async def _form_values(request: Request) -> tuple[str, str]:
    body = await request.body()
    if len(body) > 4096:
        return "", ""
    data = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
    email = data.get("email", [""])[0].strip().lower()
    password = data.get("password", [""])[0]
    return email, password


def _same_origin(request: Request) -> bool:
    expected = urlparse(_origin())
    source = request.headers.get("origin") or request.headers.get("referer", "")
    actual = urlparse(source)
    return actual.scheme == expected.scheme and actual.netloc == expected.netloc


def _session_response(user_id: int) -> RedirectResponse:
    token = secrets.token_urlsafe(32)
    with _db() as db:
        db.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))
        db.execute("INSERT INTO sessions(token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                   (hashlib.sha256(token.encode()).hexdigest(), user_id, int(time.time()) + SESSION_SECONDS))
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(COOKIE_NAME, token, max_age=SESSION_SECONDS, secure=_origin().startswith("https://"),
                        httponly=True, samesite="lax", path="/")
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/auth/login")
def login_page():
    return _form("login", "Вход", "Войти", "Создать учётную запись", "/auth/register")


@app.post("/auth/login")
async def login(request: Request):
    if not _same_origin(request):
        return Response(status_code=403)
    email, password = await _form_values(request)
    with _db() as db:
        row = db.execute("SELECT id, password_hash FROM users WHERE email = ?", (email,)).fetchone()
    if row:
        try:
            if PASSWORD_HASHER.verify(row[1], password):
                return _session_response(row[0])
        except (VerifyMismatchError, VerificationError):
            pass
    return _form("login", "Вход", "Войти", "Создать учётную запись", "/auth/register",
                 "Неверная почта или пароль.", email)


@app.get("/auth/register")
def register_page():
    return _form("register", "Регистрация", "Зарегистрироваться", "Уже есть учётная запись? Войти", "/auth/login")


@app.post("/auth/register")
async def register(request: Request):
    if not _same_origin(request):
        return Response(status_code=403)
    email, password = await _form_values(request)
    if len(email) > 254 or not EMAIL_RE.fullmatch(email):
        return _form("register", "Регистрация", "Зарегистрироваться", "Войти", "/auth/login",
                     "Укажите корректный адрес электронной почты.", email)
    if not 8 <= len(password) <= 128:
        return _form("register", "Регистрация", "Зарегистрироваться", "Войти", "/auth/login",
                     "Пароль должен содержать от 8 до 128 символов.", email)
    try:
        with _db() as db:
            cursor = db.execute("INSERT INTO users(email, password_hash, created_at) VALUES (?, ?, ?)",
                                (email, PASSWORD_HASHER.hash(password), int(time.time())))
            user_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        return _form("register", "Регистрация", "Зарегистрироваться", "Войти", "/auth/login",
                     "Этот адрес уже зарегистрирован.", email)
    return _session_response(user_id)


@app.get("/auth/logout")
def logout_page():
    return _page("Выход", '<h1>Выйти из приложения?</h1><form action="/auth/logout" method="post">'
                 '<button type="submit">Выйти</button></form><p><a href="/">Вернуться</a></p>')


@app.post("/auth/logout")
def logout(request: Request):
    if not _same_origin(request):
        return Response(status_code=403)
    token = request.cookies.get(COOKIE_NAME, "")
    if token:
        with _db() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (hashlib.sha256(token.encode()).hexdigest(),))
    response = RedirectResponse("/auth/login", status_code=303)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@app.get("/auth/check")
def check(request: Request):
    token = request.cookies.get(COOKIE_NAME, "")
    if not token:
        return Response(status_code=401)
    with _db() as db:
        row = db.execute(
            "SELECT users.email FROM sessions JOIN users ON sessions.user_id = users.id "
            "WHERE sessions.token_hash = ? AND sessions.expires_at > ?",
            (hashlib.sha256(token.encode()).hexdigest(), int(time.time())),
        ).fetchone()
    return Response(status_code=204 if row else 401)
