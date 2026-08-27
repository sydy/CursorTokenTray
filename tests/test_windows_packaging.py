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
