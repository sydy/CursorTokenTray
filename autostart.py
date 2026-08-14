"""开机自启：Windows 用 Startup 快捷方式，macOS 用 LaunchAgent。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from platform_util import IS_MAC, IS_WIN

APP_RUN_NAME = "CursorTokenTray"
MAC_LAUNCH_LABEL = "com.harker.cursortokentray"


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _script_path() -> Path:
    return Path(__file__).resolve().parent / "main.py"


def is_autostart_enabled() -> bool:
    if IS_MAC:
        return _plist_path().is_file()
    return _shortcut_path().exists()


def set_autostart(enabled: bool) -> None:
    if enabled:
        enable_autostart()
    else:
        disable_autostart()


def enable_autostart() -> None:
    if IS_MAC:
        _enable_mac()
        return
    if IS_WIN:
        _enable_win()


def disable_autostart() -> None:
    if IS_MAC:
        _disable_mac()
        return
    if IS_WIN:
        _disable_win()


def _launch_target() -> tuple[Path, str, Path]:
    """返回 (TargetPath, Arguments, WorkingDirectory)。"""
    if _is_frozen():
        target = Path(sys.executable).resolve()
        workdir = target.parent
        return target, "", workdir
    target = _pythonw_path() if IS_WIN else Path(sys.executable).resolve()
    script = _script_path()
    return target, f'"{script.as_posix()}"', script.parent


def _pythonw_path() -> Path:
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    if pythonw.exists():
        return pythonw
    return exe


def _startup_folder() -> Path:
    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _shortcut_path() -> Path:
    return _startup_folder() / f"{APP_RUN_NAME}.lnk"


def _enable_win() -> None:
    startup = _startup_folder()
    startup.mkdir(parents=True, exist_ok=True)
    target, arguments, workdir = _launch_target()
    shortcut = _shortcut_path()

    def _ps_quote(value: str) -> str:
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


def _disable_win() -> None:
    path = _shortcut_path()
    if path.exists():
        path.unlink()


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{MAC_LAUNCH_LABEL}.plist"


def _mac_program_arguments() -> list[str]:
    if _is_frozen():
        exe = Path(sys.executable).resolve()
        # .app/Contents/MacOS/CursorTokenTray
        return [str(exe)]
    python = Path(sys.executable).resolve()
    return [str(python), str(_script_path())]


def build_launch_agent_plist(program_args: list[str] | None = None, workdir: str | None = None) -> str:
    args = program_args if program_args is not None else _mac_program_arguments()
    cwd = workdir if workdir is not None else str(_script_path().parent)
    arg_xml = "\n".join(f"        <string>{_xml_escape(a)}</string>" for a in args)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{MAC_LAUNCH_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
{arg_xml}
    </array>
    <key>WorkingDirectory</key>
    <string>{_xml_escape(cwd)}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>ProcessType</key>
    <string>Interactive</string>
</dict>
</plist>
"""


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _enable_mac() -> None:
    plist = _plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_text(build_launch_agent_plist(), encoding="utf-8")
    uid = os.getuid()
    domain = f"gui/{uid}/{MAC_LAUNCH_LABEL}"
    # 新版 launchctl；失败则回退 load -w。写好 plist 后下次登录仍会生效。
    bootout = subprocess.run(
        ["launchctl", "bootout", domain],
        capture_output=True,
        text=True,
    )
    _ = bootout
    bootstrap = subprocess.run(
        ["launchctl", "bootstrap", f"gui/{uid}", str(plist)],
        capture_output=True,
        text=True,
    )
    if bootstrap.returncode != 0:
        subprocess.run(
            ["launchctl", "load", "-w", str(plist)],
            capture_output=True,
            text=True,
        )


def _disable_mac() -> None:
    plist = _plist_path()
    uid = os.getuid()
    domain = f"gui/{uid}/{MAC_LAUNCH_LABEL}"
    subprocess.run(["launchctl", "bootout", domain], capture_output=True, text=True)
    subprocess.run(["launchctl", "unload", "-w", str(plist)], capture_output=True, text=True)
    try:
        if plist.is_file():
            plist.unlink()
    except OSError:
        pass
