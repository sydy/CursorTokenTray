"""Windows 开机自启。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_RUN_NAME = "CursorTokenTray"


def _startup_folder() -> Path:
    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _shortcut_path() -> Path:
    return _startup_folder() / f"{APP_RUN_NAME}.lnk"


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _pythonw_path() -> Path:
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    if pythonw.exists():
        return pythonw
    return exe


def _script_path() -> Path:
    return Path(__file__).resolve().parent / "main.py"


def _launch_target() -> tuple[Path, str, Path]:
    """返回 (TargetPath, Arguments, WorkingDirectory)。"""
    if _is_frozen():
        target = Path(sys.executable).resolve()
        workdir = target.parent
        return target, "", workdir
    target = _pythonw_path()
    script = _script_path()
    return target, f'"{script.as_posix()}"', script.parent


def is_autostart_enabled() -> bool:
    return _shortcut_path().exists()


def set_autostart(enabled: bool) -> None:
    if enabled:
        enable_autostart()
    else:
        disable_autostart()


def enable_autostart() -> None:
    startup = _startup_folder()
    startup.mkdir(parents=True, exist_ok=True)
    target, arguments, workdir = _launch_target()
    shortcut = _shortcut_path()

    def _ps_quote(value: str) -> str:
        # PowerShell 单引号字符串：' → ''
        return "'" + value.replace("'", "''") + "'"

    args_line = (
        f"$sc.Arguments = {_ps_quote(arguments)}" if arguments else "$sc.Arguments = ''"
    )

    ps = f"""
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut({_ps_quote(shortcut.as_posix())})
$sc.TargetPath = {_ps_quote(target.as_posix())}
{args_line}
$sc.WorkingDirectory = {_ps_quote(workdir.as_posix())}
$sc.WindowStyle = 7
$sc.Description = 'Cursor Token 剩余进度托盘'
$sc.Save()
"""
    import subprocess

    # -NoLogo/-NonInteractive 减轻冷启动；调用方应在后台线程执行
    subprocess.run(
        [
            "powershell",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps,
        ],
        check=True,
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def disable_autostart() -> None:
    path = _shortcut_path()
    if path.exists():
        path.unlink()
