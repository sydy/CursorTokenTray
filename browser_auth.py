"""从本机 Chrome / Edge / Firefox 读取 Cursor Session Cookie，并校验用量。"""

from __future__ import annotations

import base64
import configparser
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from cursor_api import CursorApiError, fetch_usage_summary, normalize_workos_token
from platform_util import IS_MAC, app_log

LOGIN_URL = "https://cursor.com/dashboard"
COOKIE_NAME = "WorkosCursorSessionToken"
COOKIE_HOST_HINTS = ("cursor.com",)

# 拷贝/读库/单次校验的上限，避免浏览器锁文件或网络拖死导入线程
_COPY_TIMEOUT_SEC = 3.0
_SQLITE_TIMEOUT_SEC = 1.0
_VALIDATE_TIMEOUT_SEC = 12.0
_POLL_VALIDATE_TIMEOUT_SEC = 8.0
# 钥匙串弹窗要等用户输入开机密码，「始终允许」也常超过 12 秒
_KEYCHAIN_TIMEOUT_SEC = 180.0
_TOKEN_ASCII = re.compile(r"^[\x21-\x7e]+$")


@dataclass
class _ScanStats:
    chromium_rows: int = 0
    decrypt_ok: int = 0
    decrypt_fail: int = 0
    v20: int = 0
    keychain_ok: bool = False
    keychain_error: str = ""


_SCAN = _ScanStats()


@dataclass
class CookieCandidate:
    browser: str
    profile: str
    token: str
    last_update: int  # Unix 微秒，越大越新


# Chrome last_update_utc：自 1601-01-01 起的微秒；与 Unix 差 11644473600 秒
_CHROME_UNIX_EPOCH_DELTA_US = 11_644_473_600_000_000


def _chrome_to_unix_us(chrome_us: int) -> int:
    v = int(chrome_us or 0)
    if v <= 0:
        return 0
    # 已是 Unix 量级则原样（防御）
    if v < _CHROME_UNIX_EPOCH_DELTA_US // 2:
        return v
    return max(0, v - _CHROME_UNIX_EPOCH_DELTA_US)


def _firefox_to_unix_us(last_accessed: int) -> int:
    """Firefox lastAccessed 多为微秒；偶见毫秒。"""
    v = int(last_accessed or 0)
    if v <= 0:
        return 0
    # 毫秒级（约 1e12）→ 微秒
    if v < 10_000_000_000_000:  # < ~year 2286 in ms
        return v * 1000
    return v


@dataclass
class ImportResult:
    ok: bool
    token: str = ""
    browser: str = ""
    profile: str = ""
    remaining_percent: float | None = None
    membership_type: str = ""
    message: str = ""


def open_login_page() -> None:
    """打开登录页（异步）。优先 Edge / Chrome / Firefox，便于随后读取 Cookie。"""

    def _open() -> None:
        for exe in _browser_executables():
            try:
                subprocess.Popen(
                    [str(exe), LOGIN_URL],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                )
                return
            except OSError:
                continue
        if IS_MAC:
            try:
                subprocess.Popen(
                    ["open", LOGIN_URL],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            except OSError:
                pass
        if os.name == "nt":
            try:
                import ctypes

                rc = ctypes.windll.shell32.ShellExecuteW(
                    None, "open", LOGIN_URL, None, None, 1
                )
                if rc > 32:
                    return
            except Exception:
                pass
            try:
                os.startfile(LOGIN_URL)  # type: ignore[attr-defined]
                return
            except OSError:
                pass
        try:
            webbrowser.open(LOGIN_URL, new=2, autoraise=True)
        except Exception:
            pass

    threading.Thread(target=_open, daemon=True, name="open-login").start()


def _is_plausible_session_token(value: str) -> bool:
    text = (value or "").strip()
    if len(text) < 16 or "\ufffd" in text:
        return False
    try:
        text.encode("latin-1")
    except UnicodeEncodeError:
        return False
    if not _TOKEN_ASCII.match(text):
        return False
    lowered = text.lower()
    return (
        "%3a%3a" in lowered
        or "::" in text
        or text.count(".") >= 2
        or text.startswith("user_")
        or lowered.startswith("workoscursorsessiontoken=")
    )


def _safe_normalize(raw: str) -> str | None:
    try:
        token = normalize_workos_token(raw)
    except CursorApiError:
        return None
    if not token or not _is_plausible_session_token(token):
        return None
    return token


def _scan_failure_note() -> str:
    parts: list[str] = []
    if _SCAN.v20:
        parts.append(
            "Chrome/Edge Cookie 使用了 App-Bound 加密（v20），本工具无法直接解密。"
        )
    if _SCAN.decrypt_fail and not _SCAN.decrypt_ok:
        if _SCAN.keychain_error and not _SCAN.keychain_ok:
            parts.append(
                "已找到 Chrome Cookie，但钥匙串未授权或等待超时，解密失败。"
                "请再点一次导入，弹窗里选「始终允许」（可输入 Mac 开机密码）。"
            )
        else:
            parts.append(
                "已找到 Chrome Cookie，但解密结果无效。"
                "请再点一次导入并「始终允许」钥匙串，或改用 Safari / Firefox / 手动粘贴。"
            )
    return "\n".join(parts)


def find_session_candidates() -> list[CookieCandidate]:
    """扫描本机 Chrome / Edge / Firefox，收集 cursor.com 的 Session Token。"""
    global _SCAN
    _SCAN = _ScanStats()
    found: list[CookieCandidate] = []
    found.extend(_find_chromium_candidates())
    found.extend(_find_firefox_candidates())
    if IS_MAC:
        found.extend(_find_safari_candidates())
    # 新 → 旧
    found.sort(key=lambda c: c.last_update, reverse=True)
    # 同 token 去重，保留最新
    uniq: list[CookieCandidate] = []
    seen: set[str] = set()
    for c in found:
        if c.token in seen:
            continue
        seen.add(c.token)
        uniq.append(c)
    return uniq


def import_and_validate(
    *,
    prefer_browsers: tuple[str, ...] | None = None,
    validate_timeout: float = _VALIDATE_TIMEOUT_SEC,
    skip_tokens: set[str] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> ImportResult:
    """读取本机 Cookie，按新旧尝试校验，返回第一个可用的。"""
    if prefer_browsers is None:
        prefer_browsers = (
            ("safari", "firefox", "edge", "chrome", "brave", "arc")
            if IS_MAC
            else ("firefox", "edge", "chrome")
        )
    if should_cancel and should_cancel():
        return ImportResult(ok=False, message="已取消")
    if on_progress:
        on_progress(_import_progress_label())
    candidates = find_session_candidates()
    if not candidates:
        note = _scan_failure_note()
        message = _no_cookie_message()
        if note:
            message = f"{note}\n\n{message}"
        return ImportResult(ok=False, message=message)

    skip = skip_tokens if skip_tokens is not None else set()
    order = {name: i for i, name in enumerate(prefer_browsers)}
    # 优先最近更新的 Cookie，其次按浏览器偏好
    candidates.sort(
        key=lambda c: (-c.last_update, order.get(c.browser, 99)),
    )
    last_err = "找到 Cookie，但校验均失败"
    tried = 0
    for c in candidates:
        if should_cancel and should_cancel():
            return ImportResult(ok=False, message="已取消")
        if c.token in skip:
            continue
        tried += 1
        if on_progress:
            on_progress(f"正在校验 {c.browser} ({c.profile}) 的 Cookie…")
        try:
            snap = fetch_usage_summary(c.token, timeout=validate_timeout)
            return ImportResult(
                ok=True,
                token=c.token,
                browser=c.browser,
                profile=c.profile,
                remaining_percent=snap.remaining_percent,
                membership_type=snap.membership_type,
                message=(
                    f"已从 {c.browser} ({c.profile}) 导入并校验成功："
                    f"剩余 {snap.remaining_percent:.1f}% · {snap.membership_type}"
                ),
            )
        except CursorApiError as err:
            last_err = str(err)
            skip.add(c.token)
        except Exception as err:  # noqa: BLE001
            last_err = f"校验失败: {err}"
            skip.add(c.token)

    if tried == 0 and skip:
        return ImportResult(
            ok=False,
            message="已读取到 Cookie，但尚未通过校验（仍在等待新的登录态）。",
        )

    return ImportResult(
        ok=False,
        message=f"已读取到 Cookie，但无法通过校验：{last_err}\n请重新登录 cursor.com 后再导入。",
    )


def poll_until_valid(
    *,
    timeout_sec: float = 180.0,
    interval_sec: float = 2.0,
    should_cancel: Callable[[], bool] | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> ImportResult:
    """打开登录后轮询本机 Cookie，直到校验成功或超时。"""
    deadline = time.monotonic() + timeout_sec
    attempt = 0
    failed_tokens: set[str] = set()
    while time.monotonic() < deadline:
        if should_cancel and should_cancel():
            return ImportResult(ok=False, message="已取消")
        attempt += 1
        if on_progress:
            left = max(0, int(deadline - time.monotonic()))
            on_progress(f"正在检测浏览器 Cookie…（第 {attempt} 次，剩余约 {left}s）")
        result = import_and_validate(
            validate_timeout=_POLL_VALIDATE_TIMEOUT_SEC,
            skip_tokens=failed_tokens,
            should_cancel=should_cancel,
            on_progress=None,  # 轮询外层已有进度文案，避免刷屏
        )
        if result.ok:
            return result
        if result.message == "已取消":
            return result
        # 没找到或校验失败都继续等用户登录
        if not _interruptible_sleep(interval_sec, should_cancel):
            return ImportResult(ok=False, message="已取消")

    return ImportResult(
        ok=False,
        message=(
            "等待超时：仍未检测到可用的登录 Cookie。\n"
            "请确认已在浏览器登录 cursor.com，然后点「仅导入 Cookie」重试。"
        ),
    )


def start_browser_login_and_import(
    *,
    timeout_sec: float = 180.0,
    should_cancel: Callable[[], bool] | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> ImportResult:
    if on_progress:
        on_progress("正在打开浏览器…")
    open_login_page()
    if should_cancel and should_cancel():
        return ImportResult(ok=False, message="已取消")
    if on_progress:
        on_progress("已打开浏览器，请登录 Cursor 账号…")
    if not _interruptible_sleep(1.0, should_cancel):
        return ImportResult(ok=False, message="已取消")
    return poll_until_valid(
        timeout_sec=timeout_sec,
        should_cancel=should_cancel,
        on_progress=on_progress,
    )


def _interruptible_sleep(
    seconds: float,
    should_cancel: Callable[[], bool] | None,
    *,
    slice_sec: float = 0.2,
) -> bool:
    """可取消等待。返回 False 表示被取消。"""
    end = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < end:
        if should_cancel and should_cancel():
            return False
        time.sleep(min(slice_sec, max(0.0, end - time.monotonic())))
    return not (should_cancel and should_cancel())


def _import_progress_label() -> str:
    if IS_MAC:
        return "正在从 Safari / Chrome / Edge / Firefox 读取 Cookie…"
    return "正在从 Firefox / Chrome / Edge 读取 Cookie…"


def _no_cookie_message() -> str:
    if IS_MAC:
        return (
            "未在 Safari / Chrome / Edge / Firefox 中找到 WorkosCursorSessionToken。\n"
            "请先在浏览器打开并登录 cursor.com，然后再试。\n"
            "Chrome 系读取 Cookie 会弹出钥匙串授权，请选「始终允许」并输入 Mac 开机密码；"
            "Safari 需在「系统设置 → 隐私与安全性」给予本工具完全磁盘访问权限。"
            "也可在浏览器开发者工具里复制 WorkosCursorSessionToken 后手动粘贴。"
        )
    return (
        "未在 Firefox / Chrome / Edge 中找到 WorkosCursorSessionToken。\n"
        "请先在浏览器打开并登录 cursor.com，然后再试。\n"
        "若刚升级过 Chrome，也可能因 Cookie 加密策略无法读取，可改用 Firefox / Edge，或手动粘贴。"
    )


# ---------- 浏览器路径 ----------


def _browser_executables() -> list[Path]:
    """本机常见浏览器可执行文件（优先 Chromium 系，其次 Firefox）。"""
    if IS_MAC:
        candidates = [
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
            Path("/Applications/Arc.app/Contents/MacOS/Arc"),
            Path("/Applications/Firefox.app/Contents/MacOS/firefox"),
            Path("/Applications/Safari.app/Contents/MacOS/Safari"),
        ]
    else:
        pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        pf86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        candidates = [
            pf86 / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            pf / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            pf / "Google" / "Chrome" / "Application" / "chrome.exe",
            pf86 / "Google" / "Chrome" / "Application" / "chrome.exe",
            local / "Google" / "Chrome" / "Application" / "chrome.exe",
            pf / "Mozilla Firefox" / "firefox.exe",
            pf86 / "Mozilla Firefox" / "firefox.exe",
        ]
    seen: set[str] = set()
    out: list[Path] = []
    for path in candidates:
        key = str(path).lower()
        if key in seen or not path.is_file():
            continue
        seen.add(key)
        out.append(path)
    return out


def _browser_user_data_roots() -> list[tuple[str, Path]]:
    if IS_MAC:
        support = Path.home() / "Library" / "Application Support"
        roots = [
            ("chrome", support / "Google" / "Chrome"),
            ("chrome-beta", support / "Google" / "Chrome Beta"),
            ("chrome-canary", support / "Google" / "Chrome Canary"),
            ("edge", support / "Microsoft Edge"),
            ("brave", support / "BraveSoftware" / "Brave-Browser"),
            ("arc", support / "Arc" / "User Data"),
            ("vivaldi", support / "Vivaldi"),
            ("chromium", support / "Chromium"),
        ]
        return [(name, path) for name, path in roots if path.is_dir()]
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    roots = [
        ("edge", local / "Microsoft" / "Edge" / "User Data"),
        ("chrome", local / "Google" / "Chrome" / "User Data"),
        ("chrome-beta", local / "Google" / "Chrome Beta" / "User Data"),
        ("chromium", local / "Chromium" / "User Data"),
    ]
    return [(name, path) for name, path in roots if path]


def _iter_profiles(user_data: Path) -> list[Path]:
    profiles: list[Path] = []
    default = user_data / "Default"
    if default.is_dir():
        profiles.append(default)
    try:
        children = sorted(user_data.iterdir())
    except OSError:
        return profiles
    for child in children:
        if child.is_dir() and child.name.startswith("Profile "):
            profiles.append(child)
    return profiles


def _cookie_db_paths(profile_dir: Path) -> list[Path]:
    # 新版在 Network/Cookies，旧版在 Cookies
    return [
        profile_dir / "Network" / "Cookies",
        profile_dir / "Cookies",
    ]


def _find_chromium_candidates() -> list[CookieCandidate]:
    found: list[CookieCandidate] = []
    for browser, root in _browser_user_data_roots():
        if not root.is_dir():
            continue
        keys = _browser_keys(browser, root)
        for profile_dir in _iter_profiles(root):
            for db_path in _cookie_db_paths(profile_dir):
                if not db_path.is_file():
                    continue
                try:
                    rows = _read_cookie_rows(db_path)
                except Exception:
                    continue
                for name, host, plain_value, enc, last_update in rows:
                    if name != COOKIE_NAME:
                        continue
                    if not any(h in (host or "").lower() for h in COOKIE_HOST_HINTS):
                        continue
                    _SCAN.chromium_rows += 1
                    raw = ""
                    if _is_plausible_session_token(plain_value):
                        raw = plain_value
                    else:
                        raw = _decrypt_with_keys(enc, keys)
                    token = _safe_normalize(raw)
                    if not token:
                        continue
                    _SCAN.decrypt_ok += 1
                    found.append(
                        CookieCandidate(
                            browser=browser,
                            profile=profile_dir.name,
                            token=token,
                            last_update=_chrome_to_unix_us(int(last_update or 0)),
                        )
                    )
    return found


def _firefox_support_root() -> Path:
    if IS_MAC:
        return Path.home() / "Library" / "Application Support" / "Firefox"
    return Path(os.environ.get("APPDATA", "")) / "Mozilla" / "Firefox"


def _firefox_profiles_root() -> Path:
    return _firefox_support_root() / "Profiles"


def _iter_firefox_profiles() -> list[Path]:
    """返回含 cookies.sqlite 的 Firefox 配置目录。"""
    profiles: list[Path] = []
    seen: set[str] = set()
    support = _firefox_support_root()

    # profiles.ini 更准确（含相对/绝对路径）
    ini = support / "profiles.ini"
    if ini.is_file():
        try:
            cp = configparser.ConfigParser()
            cp.read(ini, encoding="utf-8")
            for section in cp.sections():
                if not section.lower().startswith("profile"):
                    continue
                rel = cp.get(section, "Path", fallback="").strip()
                if not rel:
                    continue
                is_rel = cp.get(section, "IsRelative", fallback="1").strip() == "1"
                path = support / rel if is_rel else Path(rel)
                key = str(path.resolve()) if path.exists() else str(path)
                if key in seen:
                    continue
                seen.add(key)
                if (path / "cookies.sqlite").is_file():
                    profiles.append(path)
        except Exception:
            pass

    root = _firefox_profiles_root()
    if root.is_dir():
        try:
            for child in sorted(root.iterdir()):
                if not child.is_dir():
                    continue
                key = str(child.resolve())
                if key in seen:
                    continue
                if (child / "cookies.sqlite").is_file():
                    seen.add(key)
                    profiles.append(child)
        except OSError:
            pass
    return profiles


def _find_firefox_candidates() -> list[CookieCandidate]:
    found: list[CookieCandidate] = []
    for profile_dir in _iter_firefox_profiles():
        db_path = profile_dir / "cookies.sqlite"
        try:
            rows = _read_firefox_cookie_rows(db_path)
        except Exception:
            continue
        for host, value, last_access in rows:
            if not any(h in (host or "").lower() for h in COOKIE_HOST_HINTS):
                continue
            token = _safe_normalize(value)
            if not token:
                continue
            found.append(
                CookieCandidate(
                    browser="firefox",
                    profile=profile_dir.name,
                    token=token,
                    last_update=_firefox_to_unix_us(int(last_access or 0)),
                )
            )
    return found


def _read_firefox_cookie_rows(db_path: Path) -> list[tuple[str, str, int]]:
    """返回 (host, value, lastAccessed)。Firefox Cookie 值为明文。"""
    tmp_dir = tempfile.mkdtemp(prefix="cursor_tray_ffcookies_")
    try:
        dst = Path(tmp_dir) / "cookies.sqlite"
        _copy_with_timeout(db_path, dst)
        for suffix in ("-wal", "-shm"):
            side = Path(str(db_path) + suffix)
            if side.is_file():
                try:
                    _copy_with_timeout(side, Path(str(dst) + suffix), timeout=1.5)
                except (OSError, TimeoutError):
                    pass
        conn = sqlite3.connect(str(dst), timeout=_SQLITE_TIMEOUT_SEC)
        try:
            cur = conn.execute(
                "SELECT host, value, lastAccessed FROM moz_cookies WHERE name = ?",
                (COOKIE_NAME,),
            )
            rows: list[tuple[str, str, int]] = []
            for host, value, last_access in cur.fetchall():
                rows.append((str(host or ""), str(value or ""), int(last_access or 0)))
            return rows
        finally:
            conn.close()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------- 解密 ----------

_MAC_KEYCHAIN = {
    "chrome": ("Chrome Safe Storage", "Chrome"),
    "chrome-beta": ("Chrome Safe Storage", "Chrome"),
    "chrome-canary": ("Chrome Safe Storage", "Chrome"),
    "chromium": ("Chromium Safe Storage", "Chromium"),
    "edge": ("Microsoft Edge Safe Storage", "Microsoft Edge"),
    "brave": ("Brave Safe Storage", "Brave"),
    "arc": ("Arc Safe Storage", "Arc"),
    "vivaldi": ("Vivaldi Safe Storage", "Vivaldi"),
}


def _browser_keys(browser: str, root: Path) -> list[bytes]:
    if IS_MAC:
        return _macos_chrome_keys(browser)
    key = _load_aes_key(root / "Local State")
    return [key] if key else []


def _macos_chrome_keys(browser: str) -> list[bytes]:
    """钥匙串密码 + peanuts 都试一遍；只接受能解出合法 Token 的密钥。"""
    import hashlib

    service, account = _MAC_KEYCHAIN.get(browser, ("Chrome Safe Storage", "Chrome"))
    passwords: list[str] = []
    secret = _keychain_password(service, account)
    if secret:
        passwords.append(secret)
        _SCAN.keychain_ok = True
    else:
        if not _SCAN.keychain_error:
            _SCAN.keychain_error = f"{browser} 钥匙串未授权或等待超时"
        app_log(f"keychain miss for {browser}: {_SCAN.keychain_error}")
    if "peanuts" not in passwords:
        passwords.append("peanuts")
    keys: list[bytes] = []
    seen: set[bytes] = set()
    for password in passwords:
        key = hashlib.pbkdf2_hmac("sha1", password.encode("utf-8"), b"saltysalt", 1003, dklen=16)
        if key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def _keychain_password(service: str, account: str) -> str | None:
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-w", "-s", service, "-a", account],
            capture_output=True,
            text=True,
            timeout=_KEYCHAIN_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        app_log(f"keychain prompt timed out after {_KEYCHAIN_TIMEOUT_SEC:.0f}s ({service})")
        return None
    except OSError as exc:
        app_log(f"keychain security command failed: {exc}")
        return None
    if result.returncode != 0:
        err = (result.stderr or "").strip().replace("\n", " ")[:180]
        app_log(f"keychain denied/failed rc={result.returncode} {err}")
        return None
    secret = (result.stdout or "").strip()
    return secret or None


def _decrypt_with_keys(encrypted: bytes, keys: list[bytes]) -> str:
    if not encrypted:
        _SCAN.decrypt_fail += 1
        return ""
    last_exc: Exception | None = None
    for key in keys:
        try:
            raw = _decrypt_chrome_value(encrypted, key, macos=IS_MAC)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if "v20" in str(exc):
                _SCAN.v20 += 1
                return ""
            continue
        if _is_plausible_session_token(raw):
            return raw
    _SCAN.decrypt_fail += 1
    if last_exc is not None:
        app_log(f"chrome cookie decrypt failed: {last_exc}")
    return ""


def _load_aes_key(local_state_path: Path) -> bytes | None:
    if not local_state_path.is_file():
        return None
    try:
        data = json.loads(local_state_path.read_text(encoding="utf-8"))
        enc_key_b64 = data.get("os_crypt", {}).get("encrypted_key")
        if not enc_key_b64:
            return None
        enc_key = base64.b64decode(enc_key_b64)
        if enc_key.startswith(b"DPAPI"):
            enc_key = enc_key[5:]
        return _dpapi_decrypt(enc_key)
    except Exception:
        return None


def _dpapi_decrypt(data: bytes) -> bytes:
    if not IS_WIN:
        raise OSError("DPAPI 仅在 Windows 可用")
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    in_buf = ctypes.create_string_buffer(data)
    blob_in = DATA_BLOB(len(data), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()

    if not crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    ):
        raise OSError("CryptUnprotectData failed")

    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _decode_cookie_bytes(plain: bytes) -> str:
    """严格 UTF-8。错误密钥的 CBC 会解出乱码，绝不能 errors=replace 再拿去当 Token。"""
    if not plain:
        raise ValueError("Cookie 解密结果为空")
    try:
        text = plain.decode("utf-8")
        if "\ufffd" not in text:
            return text
    except UnicodeDecodeError:
        text = ""
    if len(plain) > 32:
        try:
            tail = plain[32:].decode("utf-8")
            if "\ufffd" not in tail:
                return tail
        except UnicodeDecodeError:
            pass
    raise ValueError("Cookie 解密结果不是合法文本（密钥不对或加密格式已变）")


def _decrypt_chrome_value(encrypted: bytes, key: bytes, *, macos: bool = False) -> str:
    if not encrypted:
        return ""
    if macos:
        return _decrypt_chrome_macos(encrypted, key)
    # 极老版本可能是直接 DPAPI
    if encrypted.startswith(b"\x01\x00\x00\x00"):
        return _decode_cookie_bytes(_dpapi_decrypt(encrypted))

    prefix = encrypted[:3]
    if prefix in (b"v10", b"v11"):
        nonce = encrypted[3:15]
        ciphertext = encrypted[15:]
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        plain = AESGCM(key).decrypt(nonce, ciphertext, None)
        return _decode_cookie_bytes(plain)

    if prefix == b"v20":
        raise ValueError(
            "Cookie 使用 App-Bound 加密（v20），当前进程无法直接解密。"
            "可改用 Edge / Firefox，或暂时手动粘贴 Token。"
        )

    # 未知格式：尝试 DPAPI
    try:
        return _decode_cookie_bytes(_dpapi_decrypt(encrypted))
    except Exception as err:
        raise ValueError(f"无法解密 Cookie（前缀 {prefix!r}）") from err


def _decrypt_chrome_macos(encrypted: bytes, key: bytes) -> str:
    """macOS Chromium：v10/v11 先试 AES-GCM，再试 AES-128-CBC（IV 为 16 个空格）。"""
    if encrypted.startswith(b"v20"):
        raise ValueError(
            "Cookie 使用 App-Bound 加密（v20），当前进程无法直接解密。"
            "可改用 Safari / Firefox / Edge，或手动粘贴 Token。"
        )
    payload = encrypted[3:] if encrypted[:3] in (b"v10", b"v11") else encrypted
    if len(payload) < 16:
        raise ValueError("Cookie 密文过短")

    # 新版 Chrome：与其它平台相同的 AES-GCM（12 字节 nonce）
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        plain = AESGCM(key).decrypt(payload[:12], payload[12:], None)
        return _decode_cookie_bytes(plain)
    except Exception:
        pass

    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    iv = b" " * 16
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    plain = decryptor.update(payload) + decryptor.finalize()
    if not plain:
        raise ValueError("Cookie 解密结果为空")
    pad = plain[-1]
    if 1 <= pad <= 16 and plain.endswith(bytes([pad]) * pad):
        plain = plain[:-pad]
    return _decode_cookie_bytes(plain)


def _find_safari_candidates() -> list[CookieCandidate]:
    """读取 Safari binarycookies（可能需要完全磁盘访问权限）。"""
    found: list[CookieCandidate] = []
    candidates = [
        Path.home() / "Library" / "Cookies" / "Cookies.binarycookies",
        Path.home()
        / "Library"
        / "Containers"
        / "com.apple.Safari"
        / "Data"
        / "Library"
        / "Cookies"
        / "Cookies.binarycookies",
    ]
    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key in seen or not path.is_file():
            continue
        seen.add(key)
        try:
            rows = parse_safari_binarycookies(path)
        except Exception:
            continue
        for host, name, value, last_access in rows:
            if name != COOKIE_NAME:
                continue
            if not any(h in (host or "").lower() for h in COOKIE_HOST_HINTS):
                continue
            token = _safe_normalize(value)
            if not token:
                continue
            found.append(
                CookieCandidate(
                    browser="safari",
                    profile="Default",
                    token=token,
                    last_update=_firefox_to_unix_us(int(last_access or 0)),
                )
            )
    return found


def parse_safari_binarycookies(path: Path) -> list[tuple[str, str, str, int]]:
    """解析 Safari Cookies.binarycookies，返回 (host, name, value, last_access_us)。"""
    import struct

    data = path.read_bytes()
    if len(data) < 8 or data[:4] != b"cook":
        return []
    page_count = struct.unpack(">i", data[4:8])[0]
    if page_count <= 0 or page_count > 4096:
        return []
    header_end = 8 + 4 * page_count
    if len(data) < header_end:
        return []
    offsets = struct.unpack(f">{page_count}i", data[8:header_end])
    pages: list[bytes] = []
    cursor = header_end
    for size in offsets:
        if size <= 0 or cursor + size > len(data):
            break
        pages.append(data[cursor : cursor + size])
        cursor += size

    rows: list[tuple[str, str, str, int]] = []
    for page in pages:
        if len(page) < 16:
            continue
        try:
            n_cookies = struct.unpack("<i", page[4:8])[0]
        except struct.error:
            continue
        if n_cookies <= 0 or n_cookies > 4096:
            continue
        table_end = 8 + 4 * n_cookies
        if len(page) < table_end:
            continue
        cookie_offsets = struct.unpack(f"<{n_cookies}i", page[8:table_end])
        for off in cookie_offsets:
            rec = _parse_safari_cookie_record(page, off)
            if rec is not None:
                rows.append(rec)
    return rows


def _parse_safari_cookie_record(page: bytes, offset: int) -> tuple[str, str, str, int] | None:
    import struct

    if offset < 0 or offset + 56 > len(page):
        return None
    try:
        size = struct.unpack_from("<i", page, offset)[0]
        url_off = struct.unpack_from("<i", page, offset + 16)[0]
        name_off = struct.unpack_from("<i", page, offset + 20)[0]
        path_off = struct.unpack_from("<i", page, offset + 24)[0]
        value_off = struct.unpack_from("<i", page, offset + 28)[0]
        # 32: flags, 36: unused, 40: expires (double), 48: lastAccess (double) — Mac epoch
        last_access_mac = struct.unpack_from("<d", page, offset + 48)[0]
    except struct.error:
        return None
    if size <= 0 or offset + size > len(page):
        return None

    def _cstr(rel: int) -> str:
        start = offset + rel
        if start < offset or start >= offset + size:
            return ""
        end = page.find(b"\x00", start, offset + size)
        if end < 0:
            end = offset + size
        try:
            return page[start:end].decode("utf-8")
        except UnicodeDecodeError:
            return ""

    host = _cstr(url_off)
    name = _cstr(name_off)
    _ = path_off
    value = _cstr(value_off)
    if not name:
        return None
    # Mac absolute time（2001-01-01）→ Unix 微秒
    unix_us = int((float(last_access_mac) + 978307200.0) * 1_000_000)
    return host, name, value, unix_us


def _copy_with_timeout(src: Path, dst: Path, timeout: float = _COPY_TIMEOUT_SEC) -> None:
    """带超时的文件拷贝，避免浏览器锁文件时 shutil 一直阻塞。"""
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            shutil.copy2(src, dst)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise TimeoutError(f"复制 Cookie 数据库超时: {src}")
    if errors:
        raise errors[0]


def _read_cookie_rows(db_path: Path) -> list[tuple[str, str, str, bytes, int]]:
    """返回 (name, host_key, value, encrypted_value, last_update_utc)。"""
    tmp_dir = tempfile.mkdtemp(prefix="cursor_tray_cookies_")
    try:
        dst = Path(tmp_dir) / "Cookies"
        _copy_with_timeout(db_path, dst)
        # WAL 旁路文件尽量带上，提高拷贝一致性
        for suffix in ("-wal", "-shm"):
            side = Path(str(db_path) + suffix)
            if side.is_file():
                try:
                    _copy_with_timeout(side, Path(str(dst) + suffix), timeout=1.5)
                except (OSError, TimeoutError):
                    pass
        conn = sqlite3.connect(str(dst), timeout=_SQLITE_TIMEOUT_SEC)
        try:
            cur = conn.execute(
                "SELECT name, host_key, value, encrypted_value, last_update_utc "
                "FROM cookies WHERE name = ?",
                (COOKIE_NAME,),
            )
            rows: list[tuple[str, str, str, bytes, int]] = []
            for name, host, value, enc, last_update in cur.fetchall():
                if isinstance(enc, memoryview):
                    enc_b = enc.tobytes()
                elif isinstance(enc, bytes):
                    enc_b = enc
                else:
                    enc_b = bytes(enc or b"")
                rows.append(
                    (
                        str(name),
                        str(host or ""),
                        str(value or ""),
                        enc_b,
                        int(last_update or 0),
                    )
                )
            return rows
        finally:
            conn.close()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
