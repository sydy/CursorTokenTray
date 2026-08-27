"""Windows 原生设置窗口（系统控件，同一托盘消息循环）。"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from accounts import (
    display_label,
    existing_token_variants,
    format_account_caption,
    list_accounts,
    remove_account,
    rename_account,
    set_active_account,
    upsert_account,
)
from config import load_config, save_config
from cursor_api import CursorApiError, normalize_workos_token
from platform_util import app_log, window_center_pos
from settings_launch import settings_flags

SETTINGS_IDLE_CLOSE_SEC = 30 * 60

IDC_ACCOUNTS = 1001
IDC_SWITCH = 1002
IDC_RENAME = 1003
IDC_DELETE = 1004
IDC_TOKEN = 1005
IDC_ADD = 1006
IDC_IMPORT_ANY = 1007
IDC_IMPORT_FF = 1008
IDC_IMPORT_COOKIE = 1009
IDC_CANCEL_WAIT = 1010
IDC_STATUS = 1011
IDC_INTERVAL = 1012
IDC_THRESHOLDS = 1013
IDC_NOTIFY = 1014
IDC_EXHAUST = 1015
IDC_MODE = 1016
IDC_AUTOSTART = 1017
IDC_CANCEL = 1018
IDC_APPLY = 1019
IDC_SAVE = 1020
IDC_HINT = 1021

MODE_LABELS = ("圆环百分比", "纯数字", "仅色点")
MODE_VALUES = ("ring", "number", "dot")

_hwnd = 0
_proc = None
_font = 0
_account_ids: list[str] = []
_on_saved: Callable[[dict[str, Any]], None] | None = None
_cancel_import = False
_importing = False
_last_input = 0.0
_hint_clear_at = 0.0
_owns_loop = False
_prompt_proc = None


def persist_settings_values(
    *,
    token_text: str,
    interval_text: str,
    thresholds_text: str,
    notify_enabled: bool,
    exhaust_enabled: bool,
    display_mode: str,
    autostart_enabled: bool,
) -> tuple[str | None, dict[str, Any] | None]:
    """校验并写入配置。成功返回 (None, cfg)，失败返回 (错误, None)。"""
    token = ""
    raw_token = (token_text or "").strip()
    if raw_token:
        try:
            token = normalize_workos_token(raw_token)
        except CursorApiError as err:
            return str(err), None
    try:
        interval = int(str(interval_text).strip())
    except (TypeError, ValueError):
        return "刷新间隔必须是数字", None
    if interval < 1:
        return "刷新间隔至少为 1 分钟", None
    raw_thr = (thresholds_text or "").strip().replace("，", ",")
    parts = [p.strip() for p in raw_thr.split(",") if p.strip()]
    try:
        parsed = sorted({int(float(p)) for p in parts if 1 <= int(float(p)) <= 100}, reverse=True)
    except ValueError:
        return "告警阈值格式无效，请使用如 50,20,5", None
    if not parsed:
        return "请至少填写一个 1–100 的告警阈值", None
    mode = display_mode if display_mode in MODE_VALUES else "ring"
    new_cfg = load_config()
    old_thr = list(new_cfg.get("alert_thresholds") or [])
    if parsed != old_thr:
        new_cfg["alert_notified_levels"] = []
        new_cfg["low_quota_notified"] = False
        for acc in list_accounts(new_cfg):
            acc["alert_notified_levels"] = []
            acc["low_quota_notified"] = False
    if token:
        upsert_account(new_cfg, token, activate=True)
    new_cfg["refresh_interval_minutes"] = interval
    new_cfg["alert_thresholds"] = parsed
    new_cfg["low_quota_threshold"] = min(parsed)
    new_cfg["notify_enabled"] = bool(notify_enabled)
    new_cfg["notify_exhaustion_risk"] = bool(exhaust_enabled)
    new_cfg["tray_display_mode"] = mode
    new_cfg["autostart_enabled"] = bool(autostart_enabled)
    save_config(new_cfg)
    return None, new_cfg


def settings_visible() -> bool:
    return bool(_hwnd)


def close_settings() -> None:
    import sys

    global _hwnd, _cancel_import
    _cancel_import = True
    if sys.platform != "win32" or not _hwnd:
        _hwnd = 0
        return
    import ctypes

    ctypes.windll.user32.DestroyWindow(_hwnd)
    _hwnd = 0


def run_settings_main() -> int:
    """独立 `--settings`：自己跑消息循环。"""
    import sys

    from win_api import MSG

    global _owns_loop
    if sys.platform != "win32":
        return 1
    import ctypes

    _owns_loop = True
    focus, start_import = settings_flags()
    show_settings(focus_token=focus, start_import=start_import)
    if not _hwnd:
        return 1
    msg = MSG()
    user32 = ctypes.windll.user32
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        if user32.IsDialogMessageW(_hwnd, ctypes.byref(msg)):
            continue
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    return 0


def show_settings(
    *,
    on_saved: Callable[[dict[str, Any]], None] | None = None,
    focus_token: bool = False,
    start_import: bool = False,
) -> None:
    import sys
    import time as time_mod

    global _hwnd, _proc, _font, _on_saved, _cancel_import, _importing, _last_input
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    from app_icon import icon_file, set_app_user_model_id
    from dpi_util import enable_dpi_awareness, scaled_px, current_dpi_scale
    from win_api import (
        BS_AUTOCHECKBOX,
        BS_PUSHBUTTON,
        CBS_DROPDOWNLIST,
        CB_ADDSTRING,
        CB_GETCURSEL,
        CB_SETCURSEL,
        ES_AUTOHSCROLL,
        ES_PASSWORD,
        IDYES,
        LBS_NOTIFY,
        LBS_NOINTEGRALHEIGHT,
        LB_ADDSTRING,
        LB_GETCURSEL,
        LB_RESETCONTENT,
        MB_ICONERROR,
        MB_ICONINFORMATION,
        MB_ICONQUESTION,
        MB_OK,
        MB_YESNO,
        SS_LEFT,
        WM_CLOSE,
        WM_COMMAND,
        WM_DESTROY,
        WM_SETFONT,
        WM_TIMER,
        WNDCLASSW,
        WNDPROC,
        WS_BORDER,
        WS_CAPTION,
        WS_CHILD,
        WS_MINIMIZEBOX,
        WS_OVERLAPPEDWINDOW,
        WS_SYSMENU,
        WS_TABSTOP,
        WS_VISIBLE,
        WS_VSCROLL,
        def_window_proc,
        get_module_handle,
        load_cursor_arrow,
        message_box,
        post_quit_message,
    )
    from win11_style import apply_win11_window

    enable_dpi_awareness()
    set_app_user_model_id()
    _on_saved = on_saved
    _cancel_import = False
    _importing = False
    _last_input = time_mod.monotonic()

    if _hwnd:
        ctypes.windll.user32.ShowWindow(_hwnd, 5)
        ctypes.windll.user32.SetForegroundWindow(_hwnd)
        if start_import:
            _start_import(open_browser=True, prefer=None)
        return

    scale = current_dpi_scale()
    s = lambda n: scaled_px(n, scale)
    width, height = s(540), s(700)
    class_name = "CursorTokenSettings"

    def _ctl(parent, cls, text, style, x, y, w, h, cid=0):
        hwnd = ctypes.windll.user32.CreateWindowExW(
            0,
            cls,
            text,
            WS_CHILD | WS_VISIBLE | style,
            int(x),
            int(y),
            int(w),
            int(h),
            parent,
            cid,
            get_module_handle(),
            None,
        )
        if hwnd and _font:
            ctypes.windll.user32.SendMessageW(hwnd, WM_SETFONT, _font, 1)
        return hwnd

    def _text(hwnd_ctl) -> str:
        n = int(ctypes.windll.user32.GetWindowTextLengthW(hwnd_ctl) or 0)
        buf = ctypes.create_unicode_buffer(n + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd_ctl, buf, n + 1)
        return buf.value

    def _checked(hwnd_ctl) -> bool:
        return int(ctypes.windll.user32.SendMessageW(hwnd_ctl, 0x00F0, 0, 0)) == 1

    def _set_check(hwnd_ctl, on: bool) -> None:
        ctypes.windll.user32.SendMessageW(hwnd_ctl, 0x00F1, 1 if on else 0, 0)

    def _fill_accounts(list_hwnd) -> None:
        global _account_ids
        ctypes.windll.user32.SendMessageW(list_hwnd, LB_RESETCONTENT, 0, 0)
        cfg = load_config()
        _account_ids = []
        active = str(cfg.get("active_account_id") or "")
        for acc in list_accounts(cfg):
            aid = str(acc.get("id") or "")
            _account_ids.append(aid)
            caption = format_account_caption(acc, is_active=aid == active)
            ctypes.windll.user32.SendMessageW(list_hwnd, LB_ADDSTRING, 0, caption)

    def _selected_account_id(list_hwnd) -> str:
        idx = int(ctypes.windll.user32.SendMessageW(list_hwnd, LB_GETCURSEL, 0, 0))
        if idx < 0 or idx >= len(_account_ids):
            return ""
        return _account_ids[idx]

    def _apply(*, close: bool) -> None:
        mode_i = int(ctypes.windll.user32.SendMessageW(h_mode, CB_GETCURSEL, 0, 0))
        mode = MODE_VALUES[mode_i] if 0 <= mode_i < len(MODE_VALUES) else "ring"
        err, cfg = persist_settings_values(
            token_text=_text(h_token),
            interval_text=_text(h_interval),
            thresholds_text=_text(h_thr),
            notify_enabled=_checked(h_notify),
            exhaust_enabled=_checked(h_exhaust),
            display_mode=mode,
            autostart_enabled=_checked(h_auto),
        )
        if err:
            message_box("错误", err, MB_OK | MB_ICONERROR, hwnd)
            return
        ctypes.windll.user32.SetWindowTextW(h_token, "")
        _fill_accounts(h_list)
        if cfg is not None and _on_saved is not None:
            _on_saved(cfg)
        ctypes.windll.user32.SetWindowTextW(h_hint, "已应用" if not close else "")
        if close:
            close_settings()

    def _start_import(*, open_browser: bool, prefer: str | None) -> None:
        global _importing, _cancel_import
        if _importing:
            return
        _importing = True
        _cancel_import = False
        ctypes.windll.user32.SetWindowTextW(h_status, "正在导入…")

        def worker() -> None:
            from browser_auth import import_and_validate, start_browser_login_and_import

            def progress(_text: str) -> None:
                return

            try:
                cfg = load_config()
                skip = existing_token_variants(cfg)
                if open_browser:
                    result = start_browser_login_and_import(
                        prefer=prefer,
                        should_cancel=lambda: _cancel_import,
                        on_progress=progress,
                    )
                else:
                    result = import_and_validate(
                        skip_tokens=skip,
                        should_cancel=lambda: _cancel_import,
                        on_progress=progress,
                    )
            except Exception as exc:  # noqa: BLE001
                result = type("R", (), {"ok": False, "message": str(exc), "token": ""})()

            def done() -> None:
                global _importing
                _importing = False
                if getattr(result, "ok", False) and getattr(result, "token", ""):
                    cfg2 = load_config()
                    upsert_account(cfg2, result.token, activate=True)
                    save_config(cfg2)
                    _fill_accounts(h_list)
                    if _on_saved is not None:
                        _on_saved(cfg2)
                    ctypes.windll.user32.SetWindowTextW(h_status, result.message or "已导入")
                    message_box("导入", result.message or "已导入", MB_OK | MB_ICONINFORMATION, hwnd)
                else:
                    ctypes.windll.user32.SetWindowTextW(
                        h_status, getattr(result, "message", "") or "导入失败"
                    )

            _pending.append(done)
            ctypes.windll.user32.PostMessageW(hwnd, 0x8000 + 20, 0, 0)

        threading.Thread(target=worker, daemon=True, name="win-import").start()

    _pending: list[Callable[[], None]] = []

    def _wnd(hwnd_s, msg, wparam, lparam):
        global _last_input, _cancel_import, _hwnd, _owns_loop
        if msg in (0x0200, 0x0100, WM_COMMAND):
            _last_input = time_mod.monotonic()
        if msg == WM_COMMAND:
            cid = int(wparam) & 0xFFFF
            if cid == IDC_SWITCH:
                aid = _selected_account_id(h_list)
                if aid:
                    cfg = load_config()
                    if set_active_account(cfg, aid):
                        save_config(cfg)
                        _fill_accounts(h_list)
                        if _on_saved:
                            _on_saved(cfg)
            elif cid == IDC_RENAME:
                aid = _selected_account_id(h_list)
                if aid:
                    name = _prompt(hwnd_s, "重命名账号", "显示名称")
                    if name:
                        cfg = load_config()
                        rename_account(cfg, aid, name)
                        save_config(cfg)
                        _fill_accounts(h_list)
                        if _on_saved:
                            _on_saved(cfg)
            elif cid == IDC_DELETE:
                aid = _selected_account_id(h_list)
                if aid and message_box("删除账号", "确定删除这个账号？", MB_YESNO | MB_ICONQUESTION, hwnd_s) == IDYES:
                    cfg = load_config()
                    remove_account(cfg, aid)
                    save_config(cfg)
                    _fill_accounts(h_list)
                    if _on_saved:
                        _on_saved(cfg)
            elif cid == IDC_ADD:
                _apply(close=False)
            elif cid == IDC_IMPORT_ANY:
                _start_import(open_browser=True, prefer=None)
            elif cid == IDC_IMPORT_FF:
                _start_import(open_browser=True, prefer="firefox")
            elif cid == IDC_IMPORT_COOKIE:
                _start_import(open_browser=False, prefer=None)
            elif cid == IDC_CANCEL_WAIT:
                _cancel_import = True
            elif cid == IDC_APPLY:
                _apply(close=False)
            elif cid == IDC_SAVE:
                _apply(close=True)
            elif cid == IDC_CANCEL:
                _cancel_import = True
                close_settings()
            return 0
        if msg == 0x8000 + 20:
            while _pending:
                fn = _pending.pop(0)
                try:
                    fn()
                except Exception as exc:
                    app_log(f"settings done cb failed: {exc}")
            return 0
        if msg == WM_TIMER:
            if _importing:
                _last_input = time_mod.monotonic()
            elif time_mod.monotonic() - _last_input >= SETTINGS_IDLE_CLOSE_SEC:
                app_log("settings idle timeout, closing")
                close_settings()
            return 0
        if msg == WM_CLOSE:
            close_settings()
            return 0
        if msg == WM_DESTROY:
            _hwnd = 0
            ctypes.windll.user32.KillTimer(hwnd_s, 1)
            if _owns_loop:
                post_quit_message(0)
            return 0
        return def_window_proc(hwnd_s, msg, wparam, lparam)

    _proc = WNDPROC(_wnd)
    wc = WNDCLASSW()
    wc.lpfnWndProc = _proc
    wc.hInstance = get_module_handle()
    wc.hCursor = load_cursor_arrow()
    wc.lpszClassName = class_name
    wc.hbrBackground = ctypes.windll.user32.GetSysColorBrush(15)
    ctypes.windll.user32.RegisterClassW(ctypes.byref(wc))
    _font = int(ctypes.windll.gdi32.GetStockObject(17) or 0)  # DEFAULT_GUI_FONT

    sw = int(ctypes.windll.user32.GetSystemMetrics(0))
    sh = int(ctypes.windll.user32.GetSystemMetrics(1))
    px, py = window_center_pos(sw, sh, width, height)
    hwnd = int(
        ctypes.windll.user32.CreateWindowExW(
            0,
            class_name,
            "CursorToken 设置",
            WS_OVERLAPPEDWINDOW & ~0x00010000 | WS_VISIBLE,
            px,
            py,
            width,
            height,
            None,
            None,
            get_module_handle(),
            None,
        )
        or 0
    )
    if not hwnd:
        app_log("create settings window failed")
        return
    _hwnd = hwnd
    apply_win11_window(hwnd, mica=True)
    ctypes.windll.user32.SendMessageW(hwnd, WM_SETFONT, _font, 1)

    pad = s(16)
    y = pad
    _ctl(hwnd, "STATIC", "账号", SS_LEFT, pad, y, s(200), s(18))
    y += s(22)
    h_list = _ctl(
        hwnd,
        "LISTBOX",
        "",
        LBS_NOTIFY | LBS_NOINTEGRALHEIGHT | WS_BORDER | WS_VSCROLL | WS_TABSTOP,
        pad,
        y,
        s(500),
        s(110),
        IDC_ACCOUNTS,
    )
    y += s(118)
    h_switch = _ctl(hwnd, "BUTTON", "切换为当前", BS_PUSHBUTTON | WS_TABSTOP, pad, y, s(100), s(28), IDC_SWITCH)
    h_ren = _ctl(hwnd, "BUTTON", "重命名", BS_PUSHBUTTON | WS_TABSTOP, pad + s(108), y, s(80), s(28), IDC_RENAME)
    h_del = _ctl(hwnd, "BUTTON", "删除", BS_PUSHBUTTON | WS_TABSTOP, pad + s(196), y, s(80), s(28), IDC_DELETE)
    y += s(40)
    _ctl(hwnd, "STATIC", "粘贴 Token", SS_LEFT, pad, y, s(200), s(18))
    y += s(20)
    h_token = _ctl(
        hwnd,
        "EDIT",
        "",
        ES_AUTOHSCROLL | WS_BORDER | WS_TABSTOP | ES_PASSWORD,
        pad,
        y,
        s(360),
        s(24),
        IDC_TOKEN,
    )
    _ctl(hwnd, "BUTTON", "添加此 Token", BS_PUSHBUTTON | WS_TABSTOP, pad + s(368), y - 2, s(132), s(28), IDC_ADD)
    y += s(36)
    _ctl(hwnd, "BUTTON", "浏览器登录并导入", BS_PUSHBUTTON | WS_TABSTOP, pad, y, s(140), s(28), IDC_IMPORT_ANY)
    _ctl(hwnd, "BUTTON", "Firefox 登录导入", BS_PUSHBUTTON | WS_TABSTOP, pad + s(148), y, s(140), s(28), IDC_IMPORT_FF)
    _ctl(hwnd, "BUTTON", "仅导入 Cookie", BS_PUSHBUTTON | WS_TABSTOP, pad + s(296), y, s(120), s(28), IDC_IMPORT_COOKIE)
    y += s(32)
    _ctl(hwnd, "BUTTON", "取消等待", BS_PUSHBUTTON | WS_TABSTOP, pad, y, s(100), s(26), IDC_CANCEL_WAIT)
    y += s(30)
    h_status = _ctl(hwnd, "STATIC", "", SS_LEFT, pad, y, s(500), s(36), IDC_STATUS)
    y += s(44)
    _ctl(hwnd, "STATIC", "刷新间隔（分钟）", SS_LEFT, pad, y, s(160), s(18))
    h_interval = _ctl(hwnd, "EDIT", "", ES_AUTOHSCROLL | WS_BORDER | WS_TABSTOP, pad + s(170), y - 2, s(80), s(24), IDC_INTERVAL)
    y += s(30)
    _ctl(hwnd, "STATIC", "告警阈值", SS_LEFT, pad, y, s(160), s(18))
    h_thr = _ctl(hwnd, "EDIT", "", ES_AUTOHSCROLL | WS_BORDER | WS_TABSTOP, pad + s(170), y - 2, s(160), s(24), IDC_THRESHOLDS)
    y += s(32)
    h_notify = _ctl(hwnd, "BUTTON", "启用通知", BS_AUTOCHECKBOX | WS_TABSTOP, pad, y, s(160), s(22), IDC_NOTIFY)
    h_exhaust = _ctl(hwnd, "BUTTON", "耗尽风险通知", BS_AUTOCHECKBOX | WS_TABSTOP, pad + s(180), y, s(180), s(22), IDC_EXHAUST)
    y += s(32)
    _ctl(hwnd, "STATIC", "托盘显示", SS_LEFT, pad, y, s(160), s(18))
    h_mode = _ctl(
        hwnd,
        "COMBOBOX",
        "",
        CBS_DROPDOWNLIST | WS_TABSTOP | WS_VSCROLL,
        pad + s(170),
        y - 4,
        s(180),
        s(160),
        IDC_MODE,
    )
    for lab in MODE_LABELS:
        ctypes.windll.user32.SendMessageW(h_mode, CB_ADDSTRING, 0, lab)
    y += s(36)
    h_auto = _ctl(hwnd, "BUTTON", "开机自启", BS_AUTOCHECKBOX | WS_TABSTOP, pad, y, s(160), s(22), IDC_AUTOSTART)
    y += s(40)
    h_hint = _ctl(hwnd, "STATIC", "", SS_LEFT, pad, y, s(200), s(18), IDC_HINT)
    _ctl(hwnd, "BUTTON", "取消", BS_PUSHBUTTON | WS_TABSTOP, pad + s(200), y - 4, s(80), s(28), IDC_CANCEL)
    _ctl(hwnd, "BUTTON", "应用", BS_PUSHBUTTON | WS_TABSTOP, pad + s(288), y - 4, s(80), s(28), IDC_APPLY)
    _ctl(hwnd, "BUTTON", "保存", BS_PUSHBUTTON | WS_TABSTOP, pad + s(376), y - 4, s(80), s(28), IDC_SAVE)

    cfg = load_config()
    ctypes.windll.user32.SetWindowTextW(h_interval, str(int(cfg.get("refresh_interval_minutes", 10))))
    thr = cfg.get("alert_thresholds") or [50, 20, 5]
    ctypes.windll.user32.SetWindowTextW(h_thr, ",".join(str(int(x)) for x in thr))
    _set_check(h_notify, bool(cfg.get("notify_enabled", True)))
    _set_check(h_exhaust, bool(cfg.get("notify_exhaustion_risk", True)))
    _set_check(h_auto, bool(cfg.get("autostart_enabled", True)))
    mode = str(cfg.get("tray_display_mode") or "ring")
    ctypes.windll.user32.SendMessageW(h_mode, CB_SETCURSEL, MODE_VALUES.index(mode) if mode in MODE_VALUES else 0, 0)
    _fill_accounts(h_list)
    ctypes.windll.user32.SetTimer(hwnd, 1, 30_000, None)
    if focus_token:
        ctypes.windll.user32.SetFocus(h_token)
    ctypes.windll.user32.ShowWindow(hwnd, 5)
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    app_log("native settings shown")
    if start_import:
        _start_import(open_browser=True, prefer=None)


def _prompt(parent: int, title: str, label: str) -> str | None:
    """极简输入框。取消返回 None。"""
    import ctypes
    from ctypes import wintypes

    from win_api import (
        BS_PUSHBUTTON,
        ES_AUTOHSCROLL,
        IDOK,
        WM_CLOSE,
        WM_COMMAND,
        WM_DESTROY,
        WM_SETFONT,
        WNDCLASSW,
        WNDPROC,
        WS_BORDER,
        WS_CAPTION,
        WS_CHILD,
        WS_POPUP,
        WS_SYSMENU,
        WS_TABSTOP,
        WS_VISIBLE,
        def_window_proc,
        get_module_handle,
        load_cursor_arrow,
    )

    result: list[str | None] = [None]
    class_name = "CursorTokenPrompt"
    hwnd_p = 0
    global _prompt_proc

    def _wnd(hwnd, msg, wparam, lparam):
        if msg == WM_COMMAND and (int(wparam) & 0xFFFF) in (1, 2):
            if (int(wparam) & 0xFFFF) == 1:
                n = int(ctypes.windll.user32.GetWindowTextLengthW(edit) or 0)
                buf = ctypes.create_unicode_buffer(n + 1)
                ctypes.windll.user32.GetWindowTextW(edit, buf, n + 1)
                result[0] = buf.value.strip()
            ctypes.windll.user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_CLOSE:
            ctypes.windll.user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            ctypes.windll.user32.EnableWindow(parent, True)
            ctypes.windll.user32.SetForegroundWindow(parent)
            return 0
        return def_window_proc(hwnd, msg, wparam, lparam)

    _prompt_proc = WNDPROC(_wnd)
    proc = _prompt_proc
    wc = WNDCLASSW()
    wc.lpfnWndProc = proc
    wc.hInstance = get_module_handle()
    wc.hCursor = load_cursor_arrow()
    wc.lpszClassName = class_name
    ctypes.windll.user32.RegisterClassW(ctypes.byref(wc))
    hwnd_p = int(
        ctypes.windll.user32.CreateWindowExW(
            0,
            class_name,
            title,
            WS_CAPTION | WS_SYSMENU | WS_POPUP | WS_VISIBLE,
            200,
            200,
            360,
            140,
            parent,
            None,
            get_module_handle(),
            None,
        )
        or 0
    )
    font = int(ctypes.windll.gdi32.GetStockObject(17) or 0)
    ctypes.windll.user32.CreateWindowExW(0, "STATIC", label, WS_CHILD | WS_VISIBLE, 16, 16, 320, 18, hwnd_p, 0, get_module_handle(), None)
    edit = ctypes.windll.user32.CreateWindowExW(
        0, "EDIT", "", WS_CHILD | WS_VISIBLE | WS_BORDER | ES_AUTOHSCROLL | WS_TABSTOP, 16, 40, 320, 24, hwnd_p, 10, get_module_handle(), None
    )
    ctypes.windll.user32.CreateWindowExW(0, "BUTTON", "确定", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON | WS_TABSTOP, 160, 76, 80, 26, hwnd_p, 1, get_module_handle(), None)
    ctypes.windll.user32.CreateWindowExW(0, "BUTTON", "取消", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON | WS_TABSTOP, 248, 76, 80, 26, hwnd_p, 2, get_module_handle(), None)
    ctypes.windll.user32.EnableWindow(parent, False)
    msg = ctypes.wintypes.MSG() if hasattr(ctypes, "wintypes") else None
    from win_api import MSG

    msg = MSG()
    user32 = ctypes.windll.user32
    while user32.IsWindow(hwnd_p) and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
        if not user32.IsWindow(hwnd_p):
            break
    return result[0]
