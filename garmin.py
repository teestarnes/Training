"""Small read-only client for Garmin's Personal API (built-in libraries only).

The API key is read from .env.local and is never printed or logged.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://personal.connectapi.garmin.com"
TOKEN_PATH = ("/personalapitoken-service/personal-api/"
              "personal-api-key/token")
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
TOKEN_FILE = os.path.join(DATA, "token.json")
MAX_TOKEN_AGE = 20 * 3600  # tokens last 24h; renew after 20h
PAUSE = 0.4                # seconds between calls, to be polite


class KeyProblem(Exception):
    """The key is missing, mistyped or expired."""


class TooBig(Exception):
    """Garmin returned 500, which usually means the answer was over ~256 KB."""


def _read_key():
    path = os.path.join(HERE, ".env.local")
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                if line.startswith("GARMIN_PERSONAL_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    if key:
                        return key
    raise KeyProblem("No key in .env.local yet. Run: python3 setkey.py")


def _new_token():
    key = _read_key()
    req = urllib.request.Request(BASE + TOKEN_PATH, data=b"", method="POST",
                                 headers={"Authorization": "ApiKey " + key,
                                          "Accept": "text/plain"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            token = r.read().decode().strip().strip('"')
    except urllib.error.HTTPError as e:
        raise KeyProblem(
            f"Garmin refused the key (HTTP {e.code}). It may be mistyped or "
            "expired. Run python3 setkey.py and paste it again.") from None
    if not token:
        raise KeyProblem("Garmin sent back an empty token. Try making a new key.")
    os.makedirs(DATA, exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump({"token": token, "obtained_at": time.time()}, f)
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass
    return token


def token(force=False):
    if not force and os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE) as f:
                saved = json.load(f)
            if time.time() - saved["obtained_at"] < MAX_TOKEN_AGE:
                return saved["token"]
        except (ValueError, KeyError, OSError):
            pass
    return _new_token()


def get(path, params=None, retries=4):
    """GET a path and return parsed JSON (or None for an empty body)."""
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    renewed = False
    attempt = 0
    while True:
        time.sleep(PAUSE)
        req = urllib.request.Request(url, headers={
            "Authorization": "Bearer " + token(),
            "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
            return json.loads(body) if body.strip() else None
        except urllib.error.HTTPError as e:
            if e.code == 401 and not renewed:
                token(force=True)
                renewed = True
                continue
            if e.code == 500:
                raise TooBig(path) from None
            if e.code in (429, 502, 503, 504) and attempt < retries:
                attempt += 1
                wait = 5 * attempt
                print(f"  Garmin is busy (HTTP {e.code}), waiting {wait}s...")
                time.sleep(wait)
                continue
            if e.code in (204, 404):
                return None
            raise
        except urllib.error.URLError:
            if attempt < retries:
                attempt += 1
                time.sleep(5 * attempt)
                continue
            raise
