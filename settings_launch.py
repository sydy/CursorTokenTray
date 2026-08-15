"""独立设置进程的启动参数（无 GUI 依赖，可在 Linux CI 测试）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

MODE_ENV = "CURSORTOKEN_MODE"
FOCUS_ENV = "CURSORTOKEN_FOCUS_TOKEN"
IMPORT_ENV = "CURSORTOKEN_START_IMPORT"


def is_settings_process(argv: list[str] | None = None, env: dict[str, str] | None = None) -> bool:
    """打包后的 .app 有时吃掉 argv，因此同时认环境变量。"""
    args = sys.argv[1:] if argv is None else argv
    environ = os.environ if env is None else env
    return "--settings" in args or environ.get(MODE_ENV) == "settings"


def settings_flags(argv: list[str] | None = None, env: dict[str, str] | None = None) -> tuple[bool, bool]:
    args = sys.argv[1:] if argv is None else argv
    environ = os.environ if env is None else env
    focus = "--focus-token" in args or environ.get(FOCUS_ENV) == "1"
    start_import = "--start-import" in args or environ.get(IMPORT_ENV) == "1"
    return focus, start_import


def settings_env(*, focus_token: bool = False, start_import: bool = False) -> dict[str, str]:
    env = os.environ.copy()
    env[MODE_ENV] = "settings"
    if focus_token:
        env[FOCUS_ENV] = "1"
    else:
        env.pop(FOCUS_ENV, None)
    if start_import:
        env[IMPORT_ENV] = "1"
    else:
        env.pop(IMPORT_ENV, None)
    return env


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
