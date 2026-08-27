"""Windows 原生 UI：纯逻辑测试（Linux CI 可跑）。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TrayMenuDataTests(unittest.TestCase):
    def test_empty_accounts(self) -> None:
        from win_menu import build_tray_menu_items

        items = build_tray_menu_items({})
        keys = [i.key for i in items]
        self.assertEqual(keys[0], "status")
        self.assertIn("refresh", keys)
        self.assertIn("noacc", keys)
        self.assertIn("import", keys)
        self.assertIn("settings", keys)
        self.assertIn("quit", keys)
        disabled = [i for i in items if i.key == "noacc"]
        self.assertTrue(disabled)
        self.assertFalse(disabled[0].enabled)

    def test_switch_and_checked_active(self) -> None:
        from win_menu import build_tray_menu_items

        items = build_tray_menu_items(
            {
                "accounts": [
                    {"id": "a1", "token": "t1", "name": "A", "last_remaining": 40},
                    {"id": "a2", "token": "t2", "name": "B", "last_remaining": 90},
                ],
                "active_account_id": "a2",
            }
        )
        by_key = {i.key: i for i in items if not i.separator}
        self.assertIn("switch:a1", by_key)
        self.assertIn("switch:a2", by_key)
        self.assertTrue(by_key["switch:a2"].checked)
        self.assertFalse(by_key["switch:a1"].checked)

    def test_enterprise_menu_label(self) -> None:
        from win_menu import build_tray_menu_items

        items = build_tray_menu_items({}, membership="enterprise", limit_type="team")
        web = next(i for i in items if i.key == "web")
        self.assertEqual(web.label, "打开用量")


class FlyoutComposeTests(unittest.TestCase):
    def test_compose_error_state(self) -> None:
        from win_flyout import compose_flyout_image

        img, hits = compose_flyout_image(
            usage=None,
            error_message="未配置 Token，请打开设置粘贴",
            updated_at=None,
            account_label="",
            scale=1.0,
        )
        self.assertGreaterEqual(img.size[0], 400)
        self.assertGreater(img.size[1], 100)
        self.assertEqual([h.key for h in hits], ["copy", "refresh", "web", "settings"])

    def test_compose_usage_and_history(self) -> None:
        from cursor_api import UsageSnapshot
        from win_flyout import compose_flyout_image

        snap = UsageSnapshot(
            used_percent=20.0,
            remaining_percent=80.0,
            auto_percent_used=10.0,
            api_percent_used=5.0,
            total_percent_used=15.0,
            membership_type="pro",
            billing_cycle_start=None,
            billing_cycle_end=None,
            days_remaining=12,
            days_elapsed=3.5,
            estimated_usable_days=20.0,
            raw={},
        )
        img, hits = compose_flyout_image(
            usage=snap,
            error_message=None,
            updated_at="12:00:00",
            account_label="工作号",
            history_values=[70.0, 75.0, 80.0],
            scale=1.25,
        )
        self.assertGreater(img.size[0], 400)
        self.assertEqual(len(hits), 4)


class PersistSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        import config

        self._old_dir = config.CONFIG_DIR
        self._old_path = config.CONFIG_PATH
        self._tmp = tempfile.TemporaryDirectory()
        config.CONFIG_DIR = Path(self._tmp.name)
        config.CONFIG_PATH = Path(self._tmp.name) / "config.json"
        config.save_config({**config.DEFAULT_CONFIG})

    def tearDown(self) -> None:
        import config

        config.CONFIG_DIR = self._old_dir
        config.CONFIG_PATH = self._old_path
        self._tmp.cleanup()

    def test_rejects_bad_interval(self) -> None:
        from win_settings import persist_settings_values

        err, cfg = persist_settings_values(
            token_text="",
            interval_text="abc",
            thresholds_text="50,20,5",
            notify_enabled=True,
            exhaust_enabled=True,
            display_mode="ring",
            autostart_enabled=True,
        )
        self.assertIsNotNone(err)
        self.assertIsNone(cfg)

    def test_rejects_empty_thresholds(self) -> None:
        from win_settings import persist_settings_values

        err, cfg = persist_settings_values(
            token_text="",
            interval_text="10",
            thresholds_text="",
            notify_enabled=True,
            exhaust_enabled=True,
            display_mode="ring",
            autostart_enabled=True,
        )
        self.assertIsNotNone(err)
        self.assertIsNone(cfg)

    def test_saves_valid_values(self) -> None:
        import config
        from win_settings import persist_settings_values

        err, cfg = persist_settings_values(
            token_text="",
            interval_text="7",
            thresholds_text="40,10",
            notify_enabled=False,
            exhaust_enabled=False,
            display_mode="number",
            autostart_enabled=False,
        )
        self.assertIsNone(err)
        assert cfg is not None
        self.assertEqual(cfg["refresh_interval_minutes"], 7)
        self.assertEqual(cfg["alert_thresholds"], [40, 10])
        self.assertEqual(cfg["tray_display_mode"], "number")
        self.assertFalse(cfg["notify_enabled"])
        self.assertFalse(cfg["autostart_enabled"])
        self.assertEqual(config.load_config()["refresh_interval_minutes"], 7)


class NativeSourceGuardTests(unittest.TestCase):
    def test_win_modules_are_import_safe_on_linux(self) -> None:
        import win_api
        import win_flyout
        import win_menu
        import win_settings
        import win_tray

        self.assertTrue(callable(win_menu.build_tray_menu_items))
        self.assertTrue(callable(win_flyout.compose_flyout_image))
        self.assertTrue(callable(win_settings.persist_settings_values))
        self.assertTrue(hasattr(win_tray, "NativeTray"))
        self.assertTrue(hasattr(win_api, "NOTIFYICONDATAW"))

    def test_win_settings_posts_import_result(self) -> None:
        text = (ROOT / "win_settings.py").read_text(encoding="utf-8")
        self.assertIn("PostMessageW", text)
        self.assertIn("_pending.append", text)
        self.assertIn("SETTINGS_IDLE_CLOSE_SEC", text)
        self.assertNotIn("tkinter", text)


if __name__ == "__main__":
    unittest.main()
