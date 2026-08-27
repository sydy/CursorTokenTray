"""Windows DPI 缩放：纯逻辑测试（Linux CI 可跑）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dpi_util  # noqa: E402
from platform_util import window_center_pos  # noqa: E402


class ScaledPxTests(unittest.TestCase):
    def test_100_percent_keeps_design_pixels(self) -> None:
        self.assertEqual(dpi_util.scaled_px(52, 1.0), 52)
        self.assertEqual(dpi_util.scaled_px(420, 1.0), 420)

    def test_common_windows_factors(self) -> None:
        self.assertEqual(dpi_util.scaled_px(52, 1.25), 65)
        self.assertEqual(dpi_util.scaled_px(52, 1.5), 78)
        self.assertEqual(dpi_util.scaled_px(52, 2.0), 104)
        self.assertEqual(dpi_util.scaled_px(420, 1.5), 630)

    def test_never_shrinks_below_base(self) -> None:
        self.assertEqual(dpi_util.scaled_px(52, 0.5), 52)

    def test_insane_scale_is_clamped(self) -> None:
        self.assertEqual(dpi_util.scaled_px(52, 120.0), dpi_util.scaled_px(52, 3.0))
        self.assertEqual(dpi_util.scaled_px(420, 1e6), dpi_util.scaled_px(420, dpi_util.MAX_UI_SCALE))


class ClampScaleTests(unittest.TestCase):
    def test_clamp_rejects_garbage_and_nan(self) -> None:
        self.assertEqual(dpi_util.clamp_ui_scale(1.5), 1.5)
        self.assertEqual(dpi_util.clamp_ui_scale(0.1), 1.0)
        self.assertEqual(dpi_util.clamp_ui_scale(120.0), 3.0)
        self.assertEqual(dpi_util.clamp_ui_scale(float("nan")), 1.0)

    def test_clamp_dpi_rejects_pointer_sized_garbage(self) -> None:
        self.assertEqual(dpi_util.clamp_dpi(96), 96)
        self.assertEqual(dpi_util.clamp_dpi(144), 144)
        self.assertEqual(dpi_util.clamp_dpi(288), 288)
        self.assertEqual(dpi_util.clamp_dpi(0), 96)
        self.assertEqual(dpi_util.clamp_dpi(11520), 96)
        self.assertEqual(dpi_util.clamp_dpi(-4), 96)

    def test_tk_scaling_stays_bounded(self) -> None:
        self.assertAlmostEqual(dpi_util.tk_scaling_value(100.0), dpi_util.MAX_UI_SCALE * 96 / 72)

    def test_cap_ctk_maxsize_overrides_million_pixel_default(self) -> None:
        class _Win:
            _max_width = 1_000_000
            _max_height = 1_000_000
            sized: tuple[int, int] | None = None

            def maxsize(self, w: int, h: int) -> None:
                self.sized = (w, h)

        win = _Win()
        dpi_util.cap_ctk_maxsize(win)
        self.assertEqual(win._max_width, dpi_util.CTK_MAX_DESIGN_W)
        self.assertEqual(win._max_height, dpi_util.CTK_MAX_DESIGN_H)
        self.assertEqual(win.sized, (dpi_util.CTK_MAX_DESIGN_W, dpi_util.CTK_MAX_DESIGN_H))


class TkScalingTests(unittest.TestCase):
    def test_tk_scaling_is_dpi_over_72(self) -> None:
        self.assertAlmostEqual(dpi_util.tk_scaling_value(1.0), 96 / 72)
        self.assertAlmostEqual(dpi_util.tk_scaling_value(1.25), 120 / 72)
        self.assertAlmostEqual(dpi_util.tk_scaling_value(1.5), 144 / 72)
        self.assertAlmostEqual(dpi_util.tk_scaling_value(2.0), 192 / 72)


class GeometryTests(unittest.TestCase):
    def test_parse_positive_and_negative(self) -> None:
        self.assertEqual(dpi_util.parse_geometry_xy("630x900+120+800"), (120, 800))
        self.assertEqual(dpi_util.parse_geometry_xy("200x100-8-12"), (-8, -12))
        self.assertEqual(dpi_util.parse_geometry_xy("200x100+10-20"), (10, -20))
        self.assertIsNone(dpi_util.parse_geometry_xy("630x900"))

    def test_physical_geometry_string(self) -> None:
        self.assertEqual(dpi_util.physical_geometry_string(630, 900, 40, 80), "630x900+40+80")
        self.assertEqual(dpi_util.physical_geometry_string(200, 100), "200x100")

    def test_reqwidth_must_not_be_scaled_again(self) -> None:
        """CTk.geometry 会再乘 window_scaling；飞出层 reqwidth 已是物理像素。"""
        scale = 1.5
        req = dpi_util.scaled_px(420, scale)
        doubled = int(round(req * scale))
        self.assertEqual(req, 630)
        self.assertEqual(doubled, 945)
        self.assertNotEqual(req, doubled)


class SettingsCenterTests(unittest.TestCase):
    def test_center_uses_physical_size_at_150(self) -> None:
        phys_w, phys_h = dpi_util.physical_window_size(760, 560, 1.5)
        self.assertEqual((phys_w, phys_h), (1140, 840))
        x, y = window_center_pos(1920, 1080, phys_w, phys_h)
        unscaled = window_center_pos(1920, 1080, 760, 560)
        self.assertNotEqual((x, y), unscaled)
        self.assertGreater(x, 0)
        self.assertGreater(y, 0)


class HiddenHostGuardTests(unittest.TestCase):
    def test_popup_host_is_tk_not_ctk(self) -> None:
        text = (ROOT / "popup_ui.py").read_text(encoding="utf-8")
        self.assertIn("root = tk.Tk()", text)
        self.assertIn("harden_hidden_tk_root", text)
        self.assertIn("cap_ctk_maxsize", text)
        self.assertNotIn("root = ctk.CTk()", text)
        self.assertIn("self._status_win = None", text)
        # 空闲托盘不建 Tk 线程
        self.assertNotIn("self._start_ui_thread()", text.split("def bind_tray_icon")[0])

    def test_settings_caps_ctk_maxsize(self) -> None:
        text = (ROOT / "settings_ui.py").read_text(encoding="utf-8")
        self.assertIn("cap_ctk_maxsize(root)", text)
        self.assertGreaterEqual(text.count("cap_ctk_maxsize(root)"), 2)


class IconBudgetTests(unittest.TestCase):
    def test_progress_icon_rejects_huge_size(self) -> None:
        from icon_renderer import create_progress_icon

        img = create_progress_icon(80, size=99_999)
        self.assertLessEqual(max(img.size), 512)

    def test_windows_default_tray_icon_stays_small(self) -> None:
        from icon_renderer import create_progress_icon, tray_icon_size

        if sys.platform == "darwin":
            self.skipTest("macOS uses retina menubar size")
        if sys.platform == "win32":
            self.assertLessEqual(tray_icon_size(), 64)
            self.assertLessEqual(max(create_progress_icon(80).size), 64)
        else:
            self.assertLessEqual(tray_icon_size(), 64)

    def test_same_percent_reuses_cached_icon(self) -> None:
        from icon_renderer import _cached_icon, create_progress_icon

        before = _cached_icon.cache_info()
        a = create_progress_icon(87.3, size=64, mode="ring")
        b = create_progress_icon(87.4, size=64, mode="ring")
        after = _cached_icon.cache_info()
        self.assertIs(a, b)
        self.assertGreaterEqual(after.hits, before.hits + 1)

    def test_clear_icon_caches_drops_lru(self) -> None:
        from icon_renderer import _cached_icon, clear_icon_caches, create_progress_icon

        create_progress_icon(80, size=64, mode="ring")
        self.assertGreater(_cached_icon.cache_info().currsize, 0)
        clear_icon_caches()
        self.assertEqual(_cached_icon.cache_info().currsize, 0)


class IdleMemoryTests(unittest.TestCase):
    def test_tray_app_never_imports_windows_ui(self) -> None:
        text = (ROOT / "tray_app.py").read_text(encoding="utf-8")
        self.assertNotIn("from popup_ui import", text)
        self.assertNotIn("from settings_ui import", text)
        self.assertNotIn("def _ensure_windows_ui", text)
        self.assertIn("open_settings_async", text)
        self.assertIn("open_status_async", text)
        self.assertIn("run_menu_and_pick", text)

    def test_popup_process_entrypoints_exist(self) -> None:
        text = (ROOT / "popup_ui.py").read_text(encoding="utf-8")
        self.assertIn("def run_status_main", text)
        self.assertIn("def run_menu_main", text)
        self.assertIn("def _drop_tk_root_if_idle", text)

    def test_settings_ui_does_not_keep_tray_tk(self) -> None:
        text = (ROOT / "settings_ui.py").read_text(encoding="utf-8")
        self.assertNotIn("schedule_idle_release", text)

    def test_windows_spec_keeps_child_ui_modules(self) -> None:
        text = (ROOT / "CursorTokenTray.spec").read_text(encoding="utf-8")
        for name in ("popup_ui", "popup_launch", "usage_snapshot", "settings_ui", "customtkinter"):
            self.assertIn(f"'{name}'", text)

    def test_usage_snapshot_roundtrip(self) -> None:
        import tempfile
        from pathlib import Path

        import usage_snapshot
        from cursor_api import ModelTokenUsage, UsageSnapshot

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
            raw={"skip": True},
            total_tokens=1234,
            model_usages=(ModelTokenUsage("auto", 10, 0.1, 2, 4.0),),
        )
        old_path = usage_snapshot.SNAPSHOT_PATH
        with tempfile.TemporaryDirectory() as tmp:
            usage_snapshot.SNAPSHOT_PATH = Path(tmp) / "last_status.json"
            try:
                usage_snapshot.write_status_snapshot(
                    usage=snap, error_message=None, updated_at="12:00:00"
                )
                got, err, updated = usage_snapshot.read_status_snapshot()
            finally:
                usage_snapshot.SNAPSHOT_PATH = old_path
        self.assertIsNotNone(got)
        assert got is not None
        self.assertEqual(got.remaining_percent, 80.0)
        self.assertEqual(got.total_tokens, 1234)
        self.assertEqual(got.model_usages[0].name, "auto")
        self.assertIsNone(err)
        self.assertEqual(updated, "12:00:00")

    def test_pr_builds_skip_artifact_upload(self) -> None:
        text = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
        self.assertGreaterEqual(text.count("github.event_name != 'pull_request'"), 2)


class LinuxDefaultsTests(unittest.TestCase):
    def test_non_windows_scale_is_one(self) -> None:
        if sys.platform == "win32":
            self.skipTest("windows uses real DPI")
        if sys.platform == "darwin":
            self.skipTest("macOS uses backingScaleFactor")
        self.assertEqual(dpi_util.current_dpi_scale(), 1.0)
        self.assertEqual(dpi_util.enable_dpi_awareness(), 1.0)
        self.assertEqual(dpi_util.apply_ctk_scaling(1.5), 1.0)


if __name__ == "__main__":
    unittest.main()
