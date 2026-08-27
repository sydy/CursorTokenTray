"""Windows 托盘菜单：数据与系统弹出菜单。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from accounts import format_account_caption, list_accounts
from cursor_api import dashboard_menu_label


@dataclass(frozen=True)
class MenuEntry:
    key: str
    label: str
    separator: bool = False
    checked: bool = False
    enabled: bool = True


def build_tray_menu_items(
    cfg: dict[str, Any],
    *,
    membership: str = "",
    limit_type: str = "",
) -> list[MenuEntry]:
    """构造右键菜单项。纯数据，不碰 Win32。"""
    items = [
        MenuEntry("status", "显示状态"),
        MenuEntry("refresh", "立即刷新"),
        MenuEntry("web", dashboard_menu_label(membership=membership, limit_type=limit_type)),
        MenuEntry("sep1", "", separator=True),
    ]
    accounts = list_accounts(cfg)
    active_id = str(cfg.get("active_account_id") or "")
    if not accounts:
        items.append(MenuEntry("noacc", "暂无账号", enabled=False))
    else:
        for acc in accounts:
            aid = str(acc.get("id") or "")
            items.append(
                MenuEntry(
                    f"switch:{aid}",
                    format_account_caption(acc, is_active=aid == active_id),
                    checked=aid == active_id,
                )
            )
    items.extend(
        [
            MenuEntry("sep2", "", separator=True),
            MenuEntry("import", "导入 Token…"),
            MenuEntry("settings", "设置…"),
            MenuEntry("sep3", "", separator=True),
            MenuEntry("quit", "退出"),
        ]
    )
    return items


def popup_native_menu(owner_hwnd: int, items: list[MenuEntry]) -> str | None:
    """在光标处弹出系统菜单，返回选中的 key。必须在拥有托盘窗口的线程调用。"""
    import sys

    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    from win_api import (
        MF_CHECKED,
        MF_GRAYED,
        MF_SEPARATOR,
        MF_STRING,
        POINT,
        TPM_BOTTOMALIGN,
        TPM_RETURNCMD,
        TPM_RIGHTALIGN,
        TPM_RIGHTBUTTON,
        WM_NULL,
    )

    user32 = ctypes.windll.user32
    menu = user32.CreatePopupMenu()
    if not menu:
        return None
    id_to_key: dict[int, str] = {}
    cmd_id = 1
    try:
        for entry in items:
            if entry.separator:
                user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
                continue
            flags = MF_STRING
            if not entry.enabled:
                flags |= MF_GRAYED
            if entry.checked:
                flags |= MF_CHECKED
            user32.AppendMenuW(menu, flags, cmd_id, entry.label)
            id_to_key[cmd_id] = entry.key
            cmd_id += 1
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(wintypes.HWND(owner_hwnd))
        chosen = int(
            user32.TrackPopupMenuEx(
                menu,
                TPM_RIGHTALIGN | TPM_BOTTOMALIGN | TPM_RETURNCMD | TPM_RIGHTBUTTON,
                pt.x,
                pt.y,
                wintypes.HWND(owner_hwnd),
                None,
            )
        )
        user32.PostMessageW(wintypes.HWND(owner_hwnd), WM_NULL, 0, 0)
        return id_to_key.get(chosen)
    finally:
        user32.DestroyMenu(menu)
