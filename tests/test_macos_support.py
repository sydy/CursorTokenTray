"""macOS 支持相关的纯逻辑测试（可在 Linux CI 运行）。"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class ConfigDirTests(unittest.TestCase):
    def test_app_config_dir_macos(self) -> None:
        from platform_util import app_config_dir

        original = sys.platform
        try:
            sys.platform = "darwin"
            import importlib
            import platform_util

            importlib.reload(platform_util)
            path = platform_util.app_config_dir()
            self.assertTrue(str(path).endswith("Library/Application Support/CursorTokenTray"))
        finally:
            sys.platform = original
            import importlib
            import platform_util

            importlib.reload(platform_util)

    def test_app_config_dir_current_platform(self) -> None:
        from platform_util import app_config_dir

        path = app_config_dir()
        self.assertEqual(path.name, "CursorTokenTray")


class LaunchAgentTests(unittest.TestCase):
    def test_plist_contains_label_and_args(self) -> None:
        from autostart import MAC_LAUNCH_LABEL, build_launch_agent_plist

        xml = build_launch_agent_plist(
            program_args=["/usr/bin/python3", "/tmp/main.py"],
            workdir="/tmp",
        )
        self.assertIn(MAC_LAUNCH_LABEL, xml)
        self.assertIn("/usr/bin/python3", xml)
        self.assertIn("/tmp/main.py", xml)
        self.assertIn("<key>RunAtLoad</key>", xml)
        self.assertIn("LimitLoadToSessionType", xml)
        self.assertIn("Aqua", xml)
        escaped = build_launch_agent_plist(
            program_args=["/tmp/a&b"],
            workdir="/tmp",
        )
        self.assertIn("a&amp;b", escaped)


class ChromeMacDecryptTests(unittest.TestCase):
    def test_aes_cbc_v10_peanuts(self) -> None:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.padding import PKCS7

        from browser_auth import _decrypt_chrome_macos

        password = b"peanuts"
        key = hashlib.pbkdf2_hmac("sha1", password, b"saltysalt", 1003, dklen=16)
        iv = b" " * 16
        padder = PKCS7(128).padder()
        data = padder.update(b"user_test_session_token") + padder.finalize()
        enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
        payload = enc.update(data) + enc.finalize()
        plain = _decrypt_chrome_macos(b"v10" + payload, key)
        self.assertEqual(plain, "user_test_session_token")

    def test_v20_rejected(self) -> None:
        from browser_auth import _decrypt_chrome_macos

        with self.assertRaises(ValueError):
            _decrypt_chrome_macos(b"v20" + b"\x00" * 32, b"\x00" * 16)

    def test_wrong_key_does_not_return_replacement_chars(self) -> None:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.padding import PKCS7

        from browser_auth import _decrypt_chrome_macos, _safe_normalize

        password = b"peanuts"
        key = hashlib.pbkdf2_hmac("sha1", password, b"saltysalt", 1003, dklen=16)
        iv = b" " * 16
        padder = PKCS7(128).padder()
        data = padder.update(b"user_01ABC%3A%3AeyJhbGciOi.aaa.bbb") + padder.finalize()
        enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
        payload = enc.update(data) + enc.finalize()
        wrong = hashlib.pbkdf2_hmac("sha1", b"wrong", b"saltysalt", 1003, dklen=16)
        try:
            plain = _decrypt_chrome_macos(b"v10" + payload, wrong)
        except ValueError:
            plain = ""
        self.assertNotEqual(plain, "user_01ABC%3A%3AeyJhbGciOi.aaa.bbb")
        self.assertNotIn("\ufffd", plain)
        self.assertIsNone(_safe_normalize("user_\ufffd\ufffdbroken"))
        self.assertIsNone(_safe_normalize("not-a-token"))

    def test_keychain_timeout_is_long_enough(self) -> None:
        from browser_auth import _KEYCHAIN_TIMEOUT_SEC

        self.assertGreaterEqual(_KEYCHAIN_TIMEOUT_SEC, 60)


class SafariCookieTests(unittest.TestCase):
    def test_parse_minimal_binarycookies(self) -> None:
        from browser_auth import parse_safari_binarycookies

        # 构造单页、单 cookie 的最小 binarycookies
        host = b".cursor.com\x00"
        name = b"WorkosCursorSessionToken\x00"
        path = b"/\x00"
        value = b"cookie-value-abc\x00"
        strings = host + name + path + value
        rec_header = 56
        rec = bytearray(rec_header + len(strings))
        struct.pack_into("<i", rec, 0, len(rec))
        struct.pack_into("<i", rec, 16, rec_header)  # url
        struct.pack_into("<i", rec, 20, rec_header + len(host))  # name
        struct.pack_into("<i", rec, 24, rec_header + len(host) + len(name))  # path
        struct.pack_into("<i", rec, 28, rec_header + len(host) + len(name) + len(path))  # value
        struct.pack_into("<d", rec, 40, 0.0)
        struct.pack_into("<d", rec, 48, 0.0)
        rec[rec_header:] = strings

        cookie_off = 12
        page = bytearray(cookie_off + len(rec))
        struct.pack_into("<i", page, 0, 0x00000100)
        struct.pack_into("<i", page, 4, 1)
        struct.pack_into("<i", page, 8, cookie_off)
        page[cookie_off:] = rec

        header = b"cook" + struct.pack(">i", 1) + struct.pack(">i", len(page))
        blob = header + bytes(page)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Cookies.binarycookies"
            path.write_bytes(blob)
            rows = parse_safari_binarycookies(path)
        self.assertEqual(len(rows), 1)
        host_s, name_s, value_s, _ts = rows[0]
        self.assertEqual(host_s, ".cursor.com")
        self.assertEqual(name_s, "WorkosCursorSessionToken")
        self.assertEqual(value_s, "cookie-value-abc")

    def test_parse_safari_sqlite(self) -> None:
        import sqlite3

        from browser_auth import parse_safari_sqlite_cookies

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Cookies.db"
            conn = sqlite3.connect(path)
            conn.execute(
                "CREATE TABLE cookies (name TEXT, value TEXT, host TEXT, last_access INTEGER)"
            )
            conn.execute(
                "INSERT INTO cookies VALUES (?,?,?,?)",
                ("WorkosCursorSessionToken", "user_01ABC%3A%3AeyJ.aa.bb", ".cursor.com", 123),
            )
            conn.commit()
            conn.close()
            rows = parse_safari_sqlite_cookies(path)
        self.assertEqual(len(rows), 1)
        host, name, value, ts = rows[0]
        self.assertEqual(host, ".cursor.com")
        self.assertEqual(name, "WorkosCursorSessionToken")
        self.assertEqual(value, "user_01ABC%3A%3AeyJ.aa.bb")
        self.assertEqual(ts, 123)


class FirefoxProfileTests(unittest.TestCase):
    def test_profiles_ini_and_install_default(self) -> None:
        from browser_auth import _iter_firefox_profiles

        with tempfile.TemporaryDirectory() as tmp:
            support = Path(tmp)
            prof = support / "Profiles" / "abcd.default-release"
            prof.mkdir(parents=True)
            (prof / "cookies.sqlite").write_bytes(b"")
            (support / "profiles.ini").write_text(
                "[InstallDEADBEEF]\n"
                "Default=Profiles/abcd.default-release\n"
                "\n"
                "[Profile0]\n"
                "Name=default-release\n"
                "IsRelative=1\n"
                "Path=Profiles/abcd.default-release\n",
                encoding="utf-8",
            )
            found = _iter_firefox_profiles(support)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].name, "abcd.default-release")

    def test_read_named_cookie_from_sqlite(self) -> None:
        from browser_auth import COOKIE_NAME, _read_firefox_cookie_rows, _safe_normalize

        token = "user_01FFTEST%3A%3AeyJhbGciOi.aaa.bbb"
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "cookies.sqlite"
            conn = sqlite3.connect(db)
            conn.execute(
                "CREATE TABLE moz_cookies (host TEXT, name TEXT, value TEXT, lastAccessed INTEGER)"
            )
            conn.execute(
                "INSERT INTO moz_cookies VALUES (?,?,?,?)",
                ("authenticator.cursor.sh", COOKIE_NAME, token, 1_700_000_000_000_000),
            )
            conn.commit()
            conn.close()
            rows = _read_firefox_cookie_rows(db)
        self.assertEqual(len(rows), 1)
        self.assertEqual(_safe_normalize(rows[0][1]), token)


class CursorAppTokenTests(unittest.TestCase):
    def _jwt(self, sub: str) -> str:
        header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
        payload = base64.urlsafe_b64encode(
            json.dumps({"sub": sub, "aud": "https://cursor.com", "type": "session"}).encode()
        ).decode().rstrip("=")
        return f"{header}.{payload}.sig"

    def test_state_vscdb_to_workos_cookie(self) -> None:
        from browser_auth import _safe_normalize, read_cursor_access_token

        jwt = self._jwt("github|user_01CURSORAPP")
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state.vscdb"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE ItemTable (key TEXT, value TEXT)")
            conn.execute(
                "INSERT INTO ItemTable VALUES (?, ?)",
                ("cursorAuth/accessToken", jwt),
            )
            conn.commit()
            conn.close()
            raw = read_cursor_access_token(db)
        self.assertEqual(raw, jwt)
        token = _safe_normalize(raw or "")
        self.assertIsNotNone(token)
        assert token is not None
        self.assertTrue(token.startswith("user_01CURSORAPP%3A%3A"))
        self.assertIn(jwt, token)

    def test_find_session_candidates_reads_cursor_app(self) -> None:
        import browser_auth

        jwt = self._jwt("github|user_01FINDME")
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state.vscdb"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE ItemTable (key TEXT, value TEXT)")
            conn.execute("INSERT INTO ItemTable VALUES (?, ?)", ("cursorAuth/accessToken", jwt))
            conn.commit()
            conn.close()
            old = browser_auth.cursor_state_db_paths
            browser_auth.cursor_state_db_paths = lambda: [db]
            try:
                found = browser_auth.find_session_candidates()
            finally:
                browser_auth.cursor_state_db_paths = old
        tokens = [c.token for c in found if c.browser == "cursor-app"]
        self.assertTrue(tokens)
        self.assertTrue(tokens[0].startswith("user_01FINDME%3A%3A"))


class BrowserPreferTests(unittest.TestCase):
    def test_mac_app_names_prefer_safari_firefox(self) -> None:
        from browser_auth import COOKIE_HOST_HINTS, _default_prefer_browsers, preferred_mac_app_names

        self.assertIn("cursor.sh", COOKIE_HOST_HINTS)
        self.assertTrue(any("cursor.sh" in h or "cursor.com" in h for h in COOKIE_HOST_HINTS))
        self.assertEqual(preferred_mac_app_names("safari")[0], "Safari")
        self.assertEqual(preferred_mac_app_names("firefox")[0], "Firefox")
        self.assertEqual(_default_prefer_browsers("safari")[0], "cursor-app")
        self.assertEqual(_default_prefer_browsers("safari")[1], "safari")
        self.assertEqual(_default_prefer_browsers("firefox")[0], "cursor-app")
        self.assertEqual(_default_prefer_browsers("firefox")[1], "firefox")

    def test_firefox_only_excludes_chrome(self) -> None:
        from browser_auth import only_browsers_for

        only = only_browsers_for("firefox")
        self.assertIsNotNone(only)
        assert only is not None
        self.assertIn("firefox", only)
        self.assertNotIn("chrome", only)
        self.assertNotIn("edge", only)
        self.assertIsNone(only_browsers_for(None))


class InstanceLockUnixTests(unittest.TestCase):
    def test_second_acquire_fails(self) -> None:
        if os.name == "nt":
            self.skipTest("unix lock")
        import instance_lock

        with tempfile.TemporaryDirectory() as tmp:
            instance_lock.LOCK_PATH = Path(tmp) / "instance.lock"
            instance_lock.PID_PATH = Path(tmp) / "instance.pid"
            instance_lock.CONFIG_DIR = Path(tmp)
            self.assertTrue(instance_lock._acquire_unix())
            # 同进程再 flock 同一文件会成功（POSIX 同进程不互斥），改用子文件描述符模拟
            import fcntl

            fp = instance_lock.LOCK_PATH.open("a+", encoding="utf-8")
            with self.assertRaises(BlockingIOError):
                fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fp.close()
            instance_lock._release_unix()


class LogPathTests(unittest.TestCase):
    def test_log_path_current_platform(self) -> None:
        from platform_util import log_path

        path = log_path()
        self.assertTrue(path.name in {"CursorTokenTray.log", "app.log"})


class WindowHelperTests(unittest.TestCase):
    def test_center_pos(self) -> None:
        from platform_util import window_center_pos

        x, y = window_center_pos(1440, 900, 760, 560)
        self.assertGreaterEqual(x, 40)
        self.assertGreaterEqual(y, 48)
        self.assertLess(x + 760, 1440)
        self.assertLess(y + 560, 900)


class MenuBarIconTests(unittest.TestCase):
    def test_macos_idle_icon_has_light_pixels(self) -> None:
        import icon_renderer

        original = sys.platform
        try:
            sys.platform = "darwin"
            img = icon_renderer.create_idle_icon(size=64)
            bright = 0
            for r, g, b, a in img.getdata():
                if a > 80 and (r + g + b) / 3 > 170:
                    bright += 1
            self.assertGreater(bright, 40, "macOS 菜单栏图标应有足够浅色像素")
        finally:
            sys.platform = original

    def test_menubar_icon_pixels_matches_retina(self) -> None:
        from icon_renderer import menubar_icon_pixels

        self.assertEqual(menubar_icon_pixels(22, 1), 44)
        self.assertEqual(menubar_icon_pixels(22, 2), 44)
        self.assertEqual(menubar_icon_pixels(22, 3), 66)
        from icon_renderer import menubar_icon_rep_sizes

        self.assertEqual(menubar_icon_rep_sizes(22), (44, 66))

    def test_macos_tray_icon_size_is_retina(self) -> None:
        import importlib

        import icon_renderer

        original = sys.platform
        try:
            sys.platform = "darwin"
            icon_renderer.tray_icon_size.cache_clear()
            importlib.reload(icon_renderer)
            self.assertGreaterEqual(icon_renderer.tray_icon_size(), 66)
        finally:
            sys.platform = original
            importlib.reload(icon_renderer)


class SettingsProcessTests(unittest.TestCase):
    def test_is_settings_process_argv_and_env(self) -> None:
        from settings_launch import is_settings_process, settings_flags

        self.assertFalse(is_settings_process(argv=[], env={}))
        self.assertTrue(is_settings_process(argv=["--settings"], env={}))
        self.assertTrue(is_settings_process(argv=[], env={"CURSORTOKEN_MODE": "settings"}))
        focus, start_import = settings_flags(argv=["--focus-token"], env={"CURSORTOKEN_START_IMPORT": "1"})
        self.assertTrue(focus)
        self.assertTrue(start_import)

    def test_settings_command_dev(self) -> None:
        from settings_launch import settings_command

        cmd = settings_command(
            focus_token=True,
            start_import=True,
            executable="/usr/bin/python3",
            script="/tmp/main.py",
            frozen=False,
        )
        self.assertEqual(cmd, ["/usr/bin/python3", "/tmp/main.py", "--settings", "--focus-token", "--start-import"])

    def test_settings_command_frozen(self) -> None:
        from settings_launch import settings_command

        exe = "/Applications/CursorTokenTray.app/Contents/MacOS/CursorTokenTray"
        cmd = settings_command(executable=exe, frozen=True)
        self.assertEqual(cmd, [exe, "--settings"])
        cmd2 = settings_command(executable=exe, frozen=True, focus_token=True)
        self.assertEqual(cmd2, [exe, "--settings", "--focus-token"])

    def test_main_settings_flag_still_rejects_linux(self) -> None:
        if sys.platform in ("win32", "darwin"):
            self.skipTest("only on linux CI")
        import main

        old = sys.argv
        try:
            sys.argv = ["main.py", "--settings"]
            self.assertEqual(main.main(), 1)
        finally:
            sys.argv = old


class ConfigLockTests(unittest.TestCase):
    def test_roundtrip_and_poll(self) -> None:
        import config

        old_dir = config.CONFIG_DIR
        old_path = config.CONFIG_PATH
        with tempfile.TemporaryDirectory() as tmp:
            config.CONFIG_DIR = Path(tmp)
            config.CONFIG_PATH = Path(tmp) / "config.json"
            try:
                config.save_config({**config.DEFAULT_CONFIG, "refresh_interval_minutes": 7})
                self.assertEqual(config.load_config()["refresh_interval_minutes"], 7)
                seen: list[int] = []
                state = {"i": 0}

                def running() -> bool:
                    state["i"] += 1
                    if state["i"] == 2:
                        config.save_config({**config.DEFAULT_CONFIG, "refresh_interval_minutes": 3})
                    return state["i"] < 5

                config.poll_config_changes(
                    running,
                    on_change=lambda cfg: seen.append(int(cfg["refresh_interval_minutes"])),
                    interval=0.01,
                )
                self.assertIn(3, seen)
            finally:
                config.CONFIG_DIR = old_dir
                config.CONFIG_PATH = old_path


class NativeSettingsGuardTests(unittest.TestCase):
    def test_macos_settings_module_has_no_tk(self) -> None:
        text = (ROOT / "macos_settings.py").read_text(encoding="utf-8")
        self.assertNotIn("tkinter", text)
        self.assertNotIn("customtkinter", text)
        self.assertNotIn("import tk", text)

    def test_show_settings_importable(self) -> None:
        import macos_settings

        self.assertTrue(callable(macos_settings.show_settings))
        self.assertTrue(callable(macos_settings.run_macos_settings))
        self.assertTrue(callable(macos_settings.close_settings))
        self.assertTrue(callable(macos_settings._on_main))
        seen: list[int] = []
        macos_settings._on_main(lambda: seen.append(1))
        self.assertEqual(seen, [1])

    def test_tray_opens_settings_in_process(self) -> None:
        text = (ROOT / "tray_app.py").read_text(encoding="utf-8")
        self.assertIn("from macos_settings import show_settings", text)
        self.assertNotIn("open_settings_async", text)

    def test_quit_closes_settings_on_main_thread(self) -> None:
        tray = (ROOT / "tray_app.py").read_text(encoding="utf-8")
        settings = (ROOT / "macos_settings.py").read_text(encoding="utf-8")
        self.assertIn("close_settings", tray)
        self.assertIn("abortModal", settings)
        self.assertIn("def close_settings", settings)
        self.assertIn("_quit_macos", tray)

    def test_settings_uses_main_thread_modal(self) -> None:
        text = (ROOT / "macos_settings.py").read_text(encoding="utf-8")
        self.assertIn("isMainThread", text)
        self.assertIn("performSelectorOnMainThread", text)
        self.assertIn("runModalForWindow_", text)
        self.assertNotIn("subprocess", text)
        self.assertNotIn("Popen", text)


class TokenNormalizeTests(unittest.TestCase):
    def test_replacement_char_is_decrypt_damage(self) -> None:
        from cursor_api import CursorApiError, normalize_workos_token

        with self.assertRaises(CursorApiError) as ctx:
            normalize_workos_token("user_01ABC%3A%3A\ufffd")
        self.assertIn("解密失败", str(ctx.exception))

    def test_session_token_variants_cover_common_shapes(self) -> None:
        from cursor_api import session_token_variants

        header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
        payload = base64.urlsafe_b64encode(
            json.dumps({"sub": "github|user_01VAR"}).encode()
        ).decode().rstrip("=")
        jwt = f"{header}.{payload}.sig"
        variants = session_token_variants(jwt)
        self.assertTrue(any(v.startswith("user_01VAR%3A%3A") for v in variants))
        self.assertTrue(any("::" in v for v in variants))
        self.assertLessEqual(len(variants), 4)

    def test_ssl_context_available(self) -> None:
        from cursor_api import _ssl_context

        ctx = _ssl_context()
        self.assertIsNotNone(ctx)


class StatusTextTests(unittest.TestCase):
    def test_waiting_and_error(self) -> None:
        from status_text import format_summary_text

        self.assertIn("等待刷新", format_summary_text(None, None, None))
        self.assertIn("过期", format_summary_text(None, "Token 过期", "12:00"))

    def test_build_status_lines_usage(self) -> None:
        from cursor_api import UsageSnapshot
        from status_text import build_status_lines

        snap = UsageSnapshot(
            used_percent=36.0,
            remaining_percent=64.0,
            auto_percent_used=10.0,
            api_percent_used=2.0,
            total_percent_used=12.0,
            membership_type="Pro",
            billing_cycle_start=None,
            billing_cycle_end="2026-09-01T00:00:00Z",
            days_remaining=17,
            days_elapsed=13.0,
            estimated_usable_days=20.0,
            raw={},
            total_tokens=12345,
        )
        rows = dict(build_status_lines(snap, None, "12:00"))
        self.assertIn("64.0%", rows["剩余"])
        self.assertEqual(rows["计划"], "Pro")
        self.assertIn("First-party", rows["明细"])
        self.assertIn("9月1日", rows["重置"])
        self.assertEqual(rows["更新"], "12:00")

    def test_build_status_lines_error(self) -> None:
        from status_text import build_status_lines

        self.assertEqual(build_status_lines(None, "Token 过期"), [("状态", "Token 过期")])
        self.assertEqual(build_status_lines(None, None), [("状态", "等待刷新…")])


class NativeMenubarGuardTests(unittest.TestCase):
    def test_macos_menubar_module_has_no_tk(self) -> None:
        text = (ROOT / "macos_menubar.py").read_text(encoding="utf-8")
        self.assertNotIn("tkinter", text)
        self.assertNotIn("customtkinter", text)
        self.assertNotIn("import tk", text)
        self.assertIn("imageWithSize_flipped_drawingHandler_", text)
        self.assertIn("menubar_icon_rep_sizes", text)
        self.assertIn("_update_icon", text)

    def test_menubar_api_importable(self) -> None:
        import macos_menubar

        self.assertTrue(callable(macos_menubar.install))
        self.assertTrue(callable(macos_menubar.show_status))
        self.assertTrue(callable(macos_menubar.update_status))
        self.assertTrue(callable(macos_menubar.close_status))
        self.assertTrue(callable(macos_menubar.apply_retina_icon))
        self.assertTrue(callable(macos_menubar.set_menubar_icon))
        self.assertFalse(macos_menubar.is_status_visible())

    def test_tray_uses_status_panel_not_alert(self) -> None:
        text = (ROOT / "tray_app.py").read_text(encoding="utf-8")
        self.assertIn("from macos_menubar import", text)
        self.assertIn("show_macos_status", text)
        self.assertIn("set_menubar_icon", text)
        self.assertIn("install_menubar", text)
        self.assertNotIn("show_native_status", text)
        self.assertIn("close_macos_status", text)
        self.assertIn("不要走 pystray 的 icon setter", text)


class MainGuardTests(unittest.TestCase):
    def test_main_rejects_linux(self) -> None:
        if sys.platform in ("win32", "darwin"):
            self.skipTest("only on linux CI")
        import main

        rc = main.main()
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
