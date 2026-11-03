"""Standalone username/password and best-progress service for the cloud server.

Run this file directly on the server; it needs aiohttp, not OpenCV or the game.
"""
import argparse
import asyncio
from collections import deque
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
import time
import unicodedata
import uuid

from aiohttp import web

if __package__:
    from .progress_store import ProgressStore
else:
    from progress_store import ProgressStore

SESSION_SECONDS = 7 * 24 * 3600


class AccountError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def credentials(data):
    username, password = data.get('username'), data.get('password')
    if not isinstance(username, str) or not isinstance(password, str):
        raise AccountError(400, '请输入用户名和密码')
    username = unicodedata.normalize('NFKC', username).strip()
    if not 3 <= len(username) <= 24 or not all(c.isalnum() or c == '_' for c in username):
        raise AccountError(400, '用户名需为3～24位文字、字母、数字或下划线')
    if not 8 <= len(password) <= 128:
        raise AccountError(400, '密码长度需为8～128位')
    return username, username.casefold(), password


def password_hash(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode('utf-8'), salt=salt,
                             n=32768, r=8, p=3, maxmem=64 * 1024 * 1024, dklen=32)
    return 'scrypt$32768$8$3$' + salt.hex() + '$' + derived.hex()


def password_matches(password, encoded):
    algorithm, n, r, p, salt, expected = encoded.split('$')
    if (algorithm, n, r, p) != ('scrypt', '32768', '8', '3'):
        return False
    derived = password_hash(password, bytes.fromhex(salt)).rsplit('$', 1)[1]
    return hmac.compare_digest(derived, expected)


class AccountDatabase(ProgressStore):
    def __init__(self, path):
        super().__init__(path)
        with self.connection() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, username TEXT NOT NULL,
                canonical TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                expires_at INTEGER NOT NULL REFERENCES users(id));''')
        self.dummy_hash = password_hash('not-a-real-account-password')

    def issue_session(self, user):
        token = secrets.token_urlsafe(32)
        expires_at = int(time.time()) + SESSION_SECONDS
        with self.connection() as db:
            db.execute('DELETE FROM sessions WHERE expires_at<=?', (int(time.time()),))
            db.execute('INSERT INTO sessions VALUES (?,?,?)',
                       (hashlib.sha256(token.encode()).hexdigest(), user['id'], expires_at))
        return dict(user=dict(user), token=token, expires_at=expires_at)

    def register(self, data):
        username, canonical, password = credentials(data)
        user = dict(id=str(uuid.uuid4()), username=username)
        encoded = password_hash(password)
        try:
            with self.connection() as db:
                db.execute('INSERT INTO users VALUES (?,?,?,?)',
                           (user['id'], username, canonical, encoded))
        except sqlite3.IntegrityError:
            raise AccountError(409, '该用户名已被使用') from None
        return self.issue_session(user)

    def login(self, data):
        _, canonical, password = credentials(data)
        with self.connection() as db:
            row = db.execute('SELECT * FROM users WHERE canonical=?', (canonical,)).fetchone()
        valid = password_matches(password, row['password_hash'] if row else self.dummy_hash)
        if not row or not valid:
            raise AccountError(401, '用户名或密码错误')
        return self.issue_session(dict(id=row['id'], username=row['username']))

    def user(self, token):
        if not token or len(token) > 256:
            raise AccountError(401, '请先登录账号')
        with self.connection() as db:
            row = db.execute('''SELECT users.id,users.username FROM sessions
                JOIN users ON users.id=sessions.user_id
                WHERE token_hash=? AND expires_at>?''',
                (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
        if not row:
            raise AccountError(401, '登录已过期，请重新登录')
        return dict(row)

    def revoke(self, token):
        with self.connection() as db:
            db.execute('DELETE FROM sessions WHERE token_hash=?',
                       (hashlib.sha256(token.encode()).hexdigest(),))


def create_app(database):
    database = AccountDatabase(database)
    auth_slots = asyncio.Semaphore(2)
    attempts = deque()

    @web.middleware
    async def errors(request, handler):
        try:
            response = await handler(request)
        except AccountError as error:
            response = web.json_response(dict(error=error.message), status=error.status)
        except (ValueError, TypeError, KeyError):
            response = web.json_response(dict(error='请求数据格式错误'), status=400)
        response.headers['Cache-Control'] = 'no-store'
        return response

    app = web.Application(client_max_size=8192, middlewares=[errors])

    def bearer(request):
        header = request.headers.get('Authorization', '')
        return header[7:] if header.startswith('Bearer ') else ''

    async def user(request):
        return await asyncio.to_thread(database.user, bearer(request))

    async def authenticate(request):
        now = time.monotonic()
        while attempts and now-attempts[0] >= 60:
            attempts.popleft()
        if len(attempts) >= 30:
            raise AccountError(429, '登录请求较多，请稍后重试')
        attempts.append(now)
        data = await request.json()
        if not isinstance(data, dict):
            raise AccountError(400, '请求数据格式错误')
        operation = database.register if request.path.endswith('/register') else database.login
        async with auth_slots:
            result = await asyncio.to_thread(operation, data)
        return web.json_response(result)

    async def me(request):
        return web.json_response(dict(user=await user(request)))

    async def logout(request):
        await asyncio.to_thread(database.revoke, bearer(request))
        return web.json_response(dict(ok=True))

    def public_records(user_id):
        return [{key: row[key] for key in ('level_id', 'best_stars', 'best_elapsed_ms')}
                for row in database.records(user_id)]

    async def progress(request):
        owner = await user(request)
        if request.method == 'POST':
            data = await request.json()
            records = data.get('records') if isinstance(data, dict) else None
            if not isinstance(records, list) or not 1 <= len(records) <= 3:
                raise AccountError(400, '关卡记录格式错误')
            for row in records:
                database.validate(owner['id'], row['level_id'], row['best_stars'], row['best_elapsed_ms'])
            for row in records:
                await asyncio.to_thread(database.save_cleared, owner['id'], row['level_id'],
                                        row['best_stars'], row['best_elapsed_ms'])
        return web.json_response(dict(records=await asyncio.to_thread(public_records, owner['id'])))

    async def health(request):
        return web.json_response(dict(ok=True))

    app.router.add_get('/healthz', health)
    app.router.add_post('/v1/register', authenticate)
    app.router.add_post('/v1/login', authenticate)
    app.router.add_get('/v1/me', me)
    app.router.add_post('/v1/logout', logout)
    app.router.add_get('/v1/progress', progress)
    app.router.add_post('/v1/progress', progress)
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8787)
    args = parser.parse_args()
    web.run_app(create_app(args.database), host=args.host, port=args.port)


if __name__ == '__main__':
    main()
