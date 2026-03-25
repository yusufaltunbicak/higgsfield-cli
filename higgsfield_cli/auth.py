"""Authentication for Higgsfield CLI.

Clerk-based JWT auth with 60s token lifetime.

Login flow:
1. User runs `higgsfield login`
2. Pastes `document.cookie` output from browser console
3. CLI extracts __session JWT + datadome cookie
4. JWT is used for API calls (valid ~60s)
5. When expired, CLI auto-opens browser to get fresh cookies

For most commands (history, credits, download), 60s is plenty.
For long operations (generate+wait, batch), the CLI refreshes mid-operation.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import time
from base64 import urlsafe_b64decode
from pathlib import Path

import httpx

from .constants import API_BASE, CACHE_DIR, CLERK_BASE, COOKIE_FILE, TOKEN_FILE, USER_AGENT
from .exceptions import AuthRequiredError, TokenExpiredError


def get_token() -> str:
    """Return a valid bearer token, auto-refreshing via Clerk API or Chrome."""
    env_token = os.environ.get("HIGGSFIELD_TOKEN")
    if env_token:
        return env_token

    cached = _load_cached_token()
    if cached:
        return cached

    # Auto-refresh via Clerk API (no Chrome needed)
    clerk_fresh = _refresh_via_clerk()
    if clerk_fresh:
        _save_token(clerk_fresh)
        return clerk_fresh

    # Fallback: get fresh JWT from Chrome via AppleScript (only if running)
    fresh = _get_token_from_chrome()
    if fresh:
        _save_token(fresh)
        # Also grab __client cookie for future Clerk refreshes
        _try_save_clerk_client(fresh)
        return fresh

    # Last resort: try Chrome cookie DB extraction
    extracted = _extract_from_chrome()
    if extracted:
        _save_token(extracted["jwt"])
        _save_cookies(extracted)
        return extracted["jwt"]

    raise AuthRequiredError(
        "Session expired.\n"
        "Run: higgsfield login"
    )


def login_with_cookies(cookie_string: str) -> str:
    """Parse browser cookie string and save JWT + datadome."""
    cookies = _parse_cookie_string(cookie_string)

    # Extract __session JWT
    session_jwt = cookies.get("__session", "")
    if not session_jwt or not session_jwt.startswith("eyJ"):
        raise AuthRequiredError(
            "Could not find __session JWT in cookies.\n"
            "Make sure you're on higgsfield.ai and logged in."
        )

    # Verify it works
    _verify_token(session_jwt)

    # Extract other useful cookies
    datadome = cookies.get("datadome", "")
    session_id = ""
    active_context = cookies.get("clerk_active_context", "")
    if active_context:
        session_id = active_context.rstrip(":").split(":")[0]
    if not session_id:
        payload = decode_jwt_payload(session_jwt)
        session_id = payload.get("sid", "")

    _save_token(session_jwt)
    _save_cookies({
        "jwt": session_jwt,
        "datadome": datadome,
        "session_id": session_id,
        "client_uat": cookies.get("__client_uat", ""),
    })

    # Grab Clerk __client cookie for future token refresh (no Chrome needed)
    _try_save_clerk_client(session_jwt)

    return session_jwt


def login_with_token(token: str) -> str:
    """Direct JWT token login."""
    _validate_jwt(token)
    _verify_token(token)
    _save_token(token)
    return token


def refresh_token() -> str | None:
    """Try to get a fresh token. Returns None if can't auto-refresh."""
    # Prefer Clerk API (no Chrome needed)
    clerk_fresh = _refresh_via_clerk()
    if clerk_fresh:
        _save_token(clerk_fresh)
        return clerk_fresh

    fresh = _get_token_from_chrome()
    if fresh:
        _save_token(fresh)
        _try_save_clerk_client(fresh)
        return fresh

    extracted = _extract_from_chrome()
    if extracted:
        _save_token(extracted["jwt"])
        _save_cookies(extracted)
        return extracted["jwt"]
    return None


def _refresh_via_clerk() -> str | None:
    """Refresh JWT via Clerk Frontend API using saved __client cookie.

    This allows token refresh without Chrome being open.
    Requires __client cookie saved from a previous login.
    """
    clerk_file = CACHE_DIR / "clerk_client.json"
    if not clerk_file.exists():
        return None

    try:
        clerk_data = json.loads(clerk_file.read_text())
        client_cookie = clerk_data.get("__client", "")
        session_id = clerk_data.get("session_id", "")

        if not client_cookie or not session_id:
            return None

        resp = httpx.post(
            f"{CLERK_BASE}/v1/client/sessions/{session_id}/tokens",
            cookies={"__client": client_cookie},
            headers={
                "Origin": "https://higgsfield.ai",
                "Referer": "https://higgsfield.ai/",
                "User-Agent": USER_AGENT,
            },
            timeout=10,
        )

        if resp.status_code == 200:
            data = resp.json()
            jwt = data.get("jwt", "")
            if jwt and jwt.startswith("eyJ"):
                # Update __client cookie if refreshed in response
                for sc in resp.headers.get_list("set-cookie"):
                    if "__client=" in sc:
                        new_client = sc.split("__client=")[1].split(";")[0]
                        if new_client:
                            clerk_data["__client"] = new_client
                            clerk_file.write_text(json.dumps(clerk_data))
                            _chmod_600(clerk_file)
                return jwt
    except Exception:
        pass
    return None


def _try_save_clerk_client(valid_jwt: str) -> None:
    """Save Clerk __client cookie from Chrome DB for future token refresh."""
    try:
        payload = decode_jwt_payload(valid_jwt)
        session_id = payload.get("sid", "")
        if not session_id:
            return

        # Get __client from Chrome cookie DB (clerk.higgsfield.ai domain)
        client_cookie = _get_clerk_client_from_chrome()
        if not client_cookie:
            return

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        clerk_file = CACHE_DIR / "clerk_client.json"
        clerk_file.write_text(json.dumps({
            "__client": client_cookie,
            "session_id": session_id,
            "saved_at": time.time(),
        }))
        _chmod_600(clerk_file)
    except Exception:
        pass


def _get_clerk_client_from_chrome() -> str:
    """Extract __client cookie from Chrome's cookie DB for clerk.higgsfield.ai."""
    try:
        import sqlite3
        import shutil
        import tempfile
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes

        chrome_base = Path.home() / "Library/Application Support/Google/Chrome"
        cookie_files = list(chrome_base.glob("*/Cookies"))
        if not cookie_files:
            return ""

        result = subprocess.run(
            ["security", "find-generic-password", "-s", "Chrome Safe Storage", "-w"],
            capture_output=True, text=True,
        )
        chrome_password = result.stdout.strip()
        if not chrome_password:
            return ""

        kdf = PBKDF2HMAC(algorithm=hashes.SHA1(), length=16, salt=b"saltysalt", iterations=1003)
        key = kdf.derive(chrome_password.encode())

        def decrypt(enc_val: bytes) -> str:
            if enc_val[:3] == b"v10":
                iv = b" " * 16
                cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
                decryptor = cipher.decryptor()
                decrypted = decryptor.update(enc_val[3:]) + decryptor.finalize()
                pad_len = decrypted[-1]
                if 0 < pad_len <= 16:
                    return decrypted[:-pad_len].decode("utf-8", errors="replace")
                return decrypted.decode("utf-8", errors="replace")
            return enc_val.decode("utf-8", errors="replace")

        for db_path in cookie_files:
            tmp_fd, tmp = tempfile.mkstemp(suffix=".db")
            os.close(tmp_fd)
            try:
                shutil.copy2(str(db_path), tmp)
                for ext in ("-wal", "-shm"):
                    src = str(db_path) + ext
                    if os.path.exists(src):
                        shutil.copy2(src, tmp + ext)

                conn = sqlite3.connect(tmp)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT name, encrypted_value
                    FROM cookies
                    WHERE host_key LIKE '%clerk.higgsfield%'
                      AND name = '__client'
                """)
                for name, enc_val in cursor.fetchall():
                    val = decrypt(enc_val)
                    if val and "eyJ" in val:
                        # Clean decryption artifacts before the JWT
                        idx = val.index("eyJ")
                        clean = ""
                        for ch in val[idx:]:
                            if 32 <= ord(ch) < 127:
                                clean += ch
                            else:
                                break
                        if clean:
                            conn.close()
                            return clean
                conn.close()
            finally:
                for ext in ("", "-wal", "-shm"):
                    p = tmp + ext
                    if os.path.exists(p):
                        os.unlink(p)
    except Exception:
        pass
    return ""


def _is_chrome_running() -> bool:
    """Check if Chrome is already running (don't launch it)."""
    try:
        result = subprocess.run(
            ["pgrep", "-x", "Google Chrome"],
            capture_output=True, timeout=3,
        )
        return result.returncode == 0
    except Exception:
        return False


def _get_token_from_chrome() -> str | None:
    """Get fresh JWT from Chrome via AppleScript.

    Requires:
    - Chrome running with higgsfield.ai open (any tab)
    - View > Developer > Allow JavaScript from Apple Events enabled
    """
    import platform
    if platform.system() != "Darwin":
        return None

    if not _is_chrome_running():
        return None

    try:
        # Find a higgsfield tab and extract __session cookie
        script = '''
tell application "Google Chrome"
    repeat with w in windows
        repeat with t in tabs of w
            if URL of t contains "higgsfield.ai" then
                tell t
                    set tok to execute javascript "
                        (function() {
                            var m = document.cookie.match(/__session=([^;]+)/);
                            return m ? m[1] : '';
                        })()
                    "
                    if tok is not "" then return tok
                end tell
            end if
        end repeat
    end repeat
    return ""
end tell
'''
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5,
        )
        token = result.stdout.strip()
        if token and token.startswith("eyJ") and len(token) > 100:
            # Verify not expired
            exp = _decode_exp(token)
            if time.time() < exp - 5:
                return token
    except Exception:
        pass
    return None


def get_datadome_cookie() -> str:
    """Get saved datadome cookie for POST requests."""
    if not COOKIE_FILE.exists():
        return ""
    try:
        data = json.loads(COOKIE_FILE.read_text())
        return data.get("datadome", "")
    except Exception:
        return ""


def _extract_from_chrome() -> dict | None:
    """Try to extract fresh JWT from Chrome's cookie database."""
    try:
        import sqlite3
        import shutil
        import tempfile
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes

        # Find Chrome cookie DB
        chrome_base = Path.home() / "Library/Application Support/Google/Chrome"
        cookie_files = list(chrome_base.glob("*/Cookies"))
        if not cookie_files:
            return None

        # Get Chrome encryption key
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "Chrome Safe Storage", "-w"],
            capture_output=True, text=True,
        )
        chrome_password = result.stdout.strip()
        if not chrome_password:
            return None

        kdf = PBKDF2HMAC(algorithm=hashes.SHA1(), length=16, salt=b"saltysalt", iterations=1003)
        key = kdf.derive(chrome_password.encode())

        def decrypt(enc_val: bytes) -> str:
            if enc_val[:3] == b"v10":
                iv = b" " * 16
                cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
                decryptor = cipher.decryptor()
                decrypted = decryptor.update(enc_val[3:]) + decryptor.finalize()
                pad_len = decrypted[-1]
                if 0 < pad_len <= 16:
                    return decrypted[:-pad_len].decode("utf-8", errors="replace")
                return decrypted.decode("utf-8", errors="replace")
            return enc_val.decode("utf-8", errors="replace")

        # Search all profiles for higgsfield cookies
        for db_path in cookie_files:
            tmp_fd, tmp = tempfile.mkstemp(suffix=".db")
            os.close(tmp_fd)
            try:
                shutil.copy2(str(db_path), tmp)
                # Also copy WAL
                for ext in ("-wal", "-shm"):
                    src = str(db_path) + ext
                    if os.path.exists(src):
                        shutil.copy2(src, tmp + ext)

                conn = sqlite3.connect(tmp)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT name, encrypted_value
                    FROM cookies
                    WHERE host_key LIKE '%higgsfield%'
                      AND name IN ('__session', 'datadome', 'clerk_active_context', '__client_uat')
                """)
                cookies = {}
                for name, enc_val in cursor.fetchall():
                    cookies[name] = decrypt(enc_val)
                conn.close()

                session_jwt = cookies.get("__session", "")
                # Clean JWT
                if "eyJ" in session_jwt:
                    idx = session_jwt.index("eyJ")
                    clean = ""
                    for ch in session_jwt[idx:]:
                        if 32 <= ord(ch) < 127:
                            clean += ch
                        else:
                            break
                    session_jwt = clean

                if session_jwt and session_jwt.startswith("eyJ"):
                    # Check if not expired
                    exp = _decode_exp(session_jwt)
                    if time.time() < exp - 5:
                        session_id = ""
                        ctx = cookies.get("clerk_active_context", "")
                        if ctx:
                            session_id = ctx.rstrip(":").split(":")[0]
                        return {
                            "jwt": session_jwt,
                            "datadome": cookies.get("datadome", ""),
                            "session_id": session_id,
                            "client_uat": cookies.get("__client_uat", ""),
                        }
            finally:
                for ext in ("", "-wal", "-shm"):
                    p = tmp + ext
                    if os.path.exists(p):
                        os.unlink(p)
    except Exception:
        pass
    return None


def _parse_cookie_string(cookie_string: str) -> dict[str, str]:
    cookies = {}
    raw = cookie_string.strip().strip("'\"")
    for pair in raw.split(";"):
        pair = pair.strip()
        if "=" not in pair:
            continue
        key, _, value = pair.partition("=")
        cookies[key.strip()] = value.strip()
    return cookies


def _validate_jwt(token: str) -> None:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid token format. Expected JWT with 3 parts.")


def _verify_token(token: str) -> dict:
    resp = httpx.get(
        f"{API_BASE}/user",
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
        },
        timeout=10,
    )
    if resp.status_code == 401:
        raise TokenExpiredError("Token expired or invalid.")
    if resp.status_code != 200:
        raise AuthRequiredError(f"Token verification failed (HTTP {resp.status_code})")
    return resp.json()


def _save_token(token: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "token": token,
        "expires_at": _decode_exp(token),
        "saved_at": time.time(),
    }
    TOKEN_FILE.write_text(json.dumps(data))
    _chmod_600(TOKEN_FILE)


def _save_cookies(data: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data["saved_at"] = time.time()
    COOKIE_FILE.write_text(json.dumps(data))
    _chmod_600(COOKIE_FILE)


def _load_cached_token() -> str | None:
    if not TOKEN_FILE.exists():
        return None
    try:
        data = json.loads(TOKEN_FILE.read_text())
        token = data["token"]
        expires_at = data.get("expires_at", 0)
        if time.time() < expires_at - 10:
            return token
        return None
    except (json.JSONDecodeError, KeyError):
        return None


def decode_jwt_payload(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        payload += "=" * (4 - len(payload) % 4)
        return json.loads(urlsafe_b64decode(payload))
    except Exception:
        return {}


def _decode_exp(token: str) -> float:
    payload = decode_jwt_payload(token)
    return float(payload.get("exp", time.time() + 60))


def _chmod_600(path: Path) -> None:
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
