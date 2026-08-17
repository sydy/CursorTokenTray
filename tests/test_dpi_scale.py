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
