"""macOS 支持相关的纯逻辑测试（可在 Linux CI 运行）。"""

from __future__ import annotations

import hashlib
import os
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
        self.assertTrue(callable(macos_settings._on_main))
        seen: list[int] = []
        macos_settings._on_main(lambda: seen.append(1))
        self.assertEqual(seen, [1])

    def test_tray_opens_settings_in_process(self) -> None:
        text = (ROOT / "tray_app.py").read_text(encoding="utf-8")
        self.assertIn("from macos_settings import show_settings", text)
        self.assertNotIn("open_settings_async", text)

    def test_settings_uses_main_thread_modal(self) -> None:
        text = (ROOT / "macos_settings.py").read_text(encoding="utf-8")
        self.assertIn("isMainThread", text)
        self.assertIn("performSelectorOnMainThread", text)
        self.assertIn("runModalForWindow_", text)
        self.assertNotIn("subprocess", text)
        self.assertNotIn("Popen", text)


class StatusTextTests(unittest.TestCase):
    def test_waiting_and_error(self) -> None:
        from status_text import format_summary_text

        self.assertIn("等待刷新", format_summary_text(None, None, None))
        self.assertIn("过期", format_summary_text(None, "Token 过期", "12:00"))


class MainGuardTests(unittest.TestCase):
    def test_main_rejects_linux(self) -> None:
        if sys.platform in ("win32", "darwin"):
            self.skipTest("only on linux CI")
        import main

        rc = main.main()
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
