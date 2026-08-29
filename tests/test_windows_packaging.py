"""Windows 打包：spec 必须是 onefile（Linux CI 可跑）。"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _spec_call_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.add(func.id)
    return names


class WindowsSpecTests(unittest.TestCase):
    def test_spec_is_onefile(self) -> None:
        spec = ROOT / "CursorTokenTray.spec"
        self.assertTrue(spec.is_file())
        text = spec.read_text(encoding="utf-8")
        self.assertIn("onefile", text)
        names = _spec_call_names(spec)
        self.assertIn("EXE", names)
        self.assertNotIn("COLLECT", names)
        self.assertNotIn("exclude_binaries=True", text.replace(" ", ""))

    def test_windows_spec_packs_native_ui(self) -> None:
        spec = ROOT / "CursorTokenTray.spec"
        text = spec.read_text(encoding="utf-8")
        hidden = text.split("excludes")[0]
        self.assertIn("'win_tray'", hidden)
        self.assertIn("'win_flyout'", hidden)
        self.assertIn("'win_settings'", hidden)
        self.assertNotIn("'customtkinter'", hidden)
        self.assertNotIn("'ui_ctk'", hidden)
        self.assertNotIn("ctk_theme.json", text)


class DotnetPublishTests(unittest.TestCase):
    def test_self_contained_exe_is_compressed(self) -> None:
        csproj = (ROOT / "windows" / "CursorTokenTray" / "CursorTokenTray.csproj").read_text(encoding="utf-8")
        self.assertIn("<PublishSingleFile>true</PublishSingleFile>", csproj)
        self.assertIn("<SelfContained>true</SelfContained>", csproj)
        self.assertIn("<EnableCompressionInSingleFile>true</EnableCompressionInSingleFile>", csproj)
        self.assertIn("<InvariantGlobalization>true</InvariantGlobalization>", csproj)
        self.assertIn("<PublishTrimmed>false</PublishTrimmed>", csproj)
        self.assertIn("<ApplicationHighDpiMode>PerMonitorV2</ApplicationHighDpiMode>", csproj)
        self.assertIn(r"<ApplicationIcon>..\..\assets\app_icon.ico</ApplicationIcon>", csproj)
        self.assertNotIn("<ApplicationIcon></ApplicationIcon>", csproj)
        self.assertNotIn("_SuppressWinFormsTrimError", csproj)
        self.assertNotIn("<PublishTrimmed>true</PublishTrimmed>", csproj)
        workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
        self.assertNotIn("PublishTrimmed=true", workflow)
        self.assertNotIn("_SuppressWinFormsTrimError", workflow)

    def test_report_form_applies_dpi_layout(self) -> None:
        text = (ROOT / "windows" / "CursorTokenTray" / "ReportForm.cs").read_text(encoding="utf-8")
        self.assertIn("OnDpiChanged", text)
        self.assertIn("ApplyDpiLayout", text)
        self.assertIn("UiLayout.ScalePx", text)
        self.assertIn("UiLayout.FitWindow", text)
        self.assertIn("MinimumWidth", text)
        self.assertIn("UsageChartPanel", text)
        self.assertIn("_chart.ApplyDpi", text)
        chart = (ROOT / "windows" / "CursorTokenTray" / "UsageChartPanel.cs").read_text(encoding="utf-8")
        self.assertIn("按小时", chart)
        self.assertIn("BuildChart", chart)
        self.assertIn("HourlyChartWindowHours", (ROOT / "windows" / "CursorTokenCore" / "UsageEvents.cs").read_text(encoding="utf-8"))

    def test_windows_exe_icon_is_win32_compatible(self) -> None:
        ico = ROOT / "assets" / "app_icon.ico"
        self.assertTrue(ico.is_file())
        kinds = _ico_entry_kinds(ico)
        self.assertIn((16, "BMP"), kinds)
        self.assertIn((32, "BMP"), kinds)
        self.assertIn((48, "BMP"), kinds)
        self.assertIn((256, "PNG"), kinds)
        self.assertNotIn((16, "PNG"), kinds)
        generator = (ROOT / "assets" / "gen_app_icon.py").read_text(encoding="utf-8")
        self.assertIn("ICO_BMP_SIZES", generator)
        self.assertIn("_bmp_dib", generator)
        ui = (ROOT / "windows" / "CursorTokenTray" / "UiForms.cs").read_text(encoding="utf-8")
        report = (ROOT / "windows" / "CursorTokenTray" / "ReportForm.cs").read_text(encoding="utf-8")
        program = (ROOT / "windows" / "CursorTokenTray" / "Program.cs").read_text(encoding="utf-8")
        self.assertIn("AppWindow.CreateIcon", ui)
        self.assertIn("AppWindow.CreateIcon", report)
        self.assertIn("ExtractAssociatedIcon", program)


def _ico_entry_kinds(path: Path) -> list[tuple[int, str]]:
    raw = path.read_bytes()
    count = int.from_bytes(raw[4:6], "little")
    kinds: list[tuple[int, str]] = []
    png = b"\x89PNG\r\n\x1a\n"
    for i in range(count):
        base = 6 + i * 16
        width = raw[base]
        size = int.from_bytes(raw[base + 8 : base + 12], "little")
        offset = int.from_bytes(raw[base + 12 : base + 16], "little")
        blob = raw[offset : offset + size]
        kind = "PNG" if blob[:8] == png else "BMP"
        kinds.append((256 if width == 0 else width, kind))
    return kinds
