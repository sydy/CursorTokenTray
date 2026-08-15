"""独立设置进程的启动参数（无 GUI 依赖，可在 Linux CI 测试）。"""

from __future__ import annotations

import sys
from pathlib import Path


def settings_command(
    *,
    focus_token: bool = False,
    start_import: bool = False,
    executable: str | None = None,
    script: str | None = None,
    frozen: bool | None = None,
) -> list[str]:
    """构造 `CursorTokenTray --settings` / `python main.py --settings` 命令行。"""
    exe = executable or sys.executable
    is_frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if is_frozen:
        cmd = [exe, "--settings"]
    else:
        main_py = script or str(Path(__file__).resolve().parent / "main.py")
        cmd = [exe, main_py, "--settings"]
    if focus_token:
        cmd.append("--focus-token")
    if start_import:
        cmd.append("--start-import")
    return cmd
