"""CustomTkinter 内容层：主题初始化 + 设置卡片。外壳（圆角/标题栏）仍走系统层。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import customtkinter as ctk

from win11_theme import (
    ACCENT,
    ACCENT_LIGHT,
    BG,
    FG,
    FG_SEC,
    FG_TER,
    HOVER,
    LINE,
    SURFACE,
    SURFACE_ALT,
)

THEME_PATH = Path(__file__).resolve().parent / "assets" / "ctk_theme.json"

_initialized = False


def init_ctk() -> None:
    """进程内只初始化一次。Windows 关闭 CTk 自带 DPI，沿用项目 dpi_util。"""
    global _initialized
    if _initialized:
        return
    import sys

    if sys.platform == "win32":
        from dpi_util import apply_ctk_scaling, current_dpi_scale

        # 只关掉 CTk 自己调 SetProcessDpiAwareness；缩放仍要写回 widget/window_scaling，
        # 否则 DPI 感知进程里飞出层/设置窗会按 1x 物理像素画，高分屏又小又乱。
        ctk.deactivate_automatic_dpi_awareness()
        apply_ctk_scaling(current_dpi_scale())
    ctk.set_appearance_mode("dark")
    if THEME_PATH.is_file():
        ctk.set_default_color_theme(str(THEME_PATH))
    else:
        ctk.set_default_color_theme("dark-blue")
    _initialized = True


def apply_native_window_chrome(win) -> None:
    """Windows：暗色标题栏 + 圆角。其它系统忽略。"""
    try:
        import sys

        if not sys.platform.startswith("win"):
            return
    except Exception:
        return
    try:
        import pywinstyles

        pywinstyles.change_header_color(win, BG)
        try:
            pywinstyles.change_border_color(win, BG)
        except Exception:
            pass
    except Exception:
        pass
    try:
        from win11_style import apply_win11_window, toplevel_hwnd

        win.update_idletasks()
        apply_win11_window(toplevel_hwnd(win), mica=False)
    except Exception:
        pass


def fluent_icon_font(size: int = 16) -> ctk.CTkFont:
    import sys

    if sys.platform == "darwin":
        return ctk.CTkFont(family="PingFang SC", size=size)
    family = "Segoe Fluent Icons"
    try:
        import tkinter.font as tkfont

        if family not in set(tkfont.families()):
            family = "Segoe MDL2 Assets"
            if family not in set(tkfont.families()):
                family = ctk.ThemeManager.theme["CTkFont"]["Windows"]["family"]
    except Exception:
        family = "Microsoft YaHei UI"
    return ctk.CTkFont(family=family, size=size)


class CTkNavItem(ctk.CTkFrame):
    def __init__(
        self,
        master,
        text: str,
        glyph: str,
        command: Callable[[], None],
        *,
        selected: bool = False,
    ) -> None:
        super().__init__(master, height=40, corner_radius=8, fg_color="transparent", cursor="hand2")
        self._command = command
        self._selected = selected
        self._hover = False
        self.grid_columnconfigure(1, weight=1)

        self._icon = ctk.CTkLabel(self, text=glyph, width=28, font=fluent_icon_font(15), text_color=FG)
        self._icon.grid(row=0, column=0, padx=(10, 4), pady=8)
        self._label = ctk.CTkLabel(self, text=text, anchor="w", text_color=FG)
        self._label.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=8)
        self._bar = ctk.CTkFrame(self, width=3, height=18, fg_color=ACCENT_LIGHT, corner_radius=1)

        for w in (self, self._icon, self._label):
            w.bind("<Enter>", lambda _e: self._hover_set(True))
            w.bind("<Leave>", lambda _e: self._hover_set(False))
            w.bind("<Button-1>", lambda _e: self._command())
        self._paint()

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._paint()

    def _hover_set(self, hover: bool) -> None:
        self._hover = hover
        self._paint()

    def _paint(self) -> None:
        fill = SURFACE if self._selected else (HOVER if self._hover else "transparent")
        self.configure(fg_color=fill)
        if self._selected:
            self._bar.place(x=4, rely=0.5, anchor="w")
        else:
            self._bar.place_forget()


class CTkSettingsRow(ctk.CTkFrame):
    """标题/说明在左，控件在右；可选展开正文。"""

    def __init__(
        self,
        master,
        *,
        title: str,
        description: str = "",
        glyph: str = "",
        on_click: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(
            master,
            fg_color=SURFACE,
            corner_radius=10,
            border_width=1,
            border_color=LINE,
        )
        self.grid_columnconfigure(1, weight=1)
        rows = 2 if description else 1

        if glyph:
            icon = ctk.CTkLabel(
                self, text=glyph, width=28, font=fluent_icon_font(14), text_color=FG
            )
            icon.grid(row=0, column=0, rowspan=rows, padx=(12, 8), pady=10, sticky="n")
        else:
            icon = None

        self._title = ctk.CTkLabel(self, text=title, anchor="w", text_color=FG)
        self._title.grid(
            row=0,
            column=1,
            sticky="ew",
            pady=(10, 0 if description else 10),
        )
        self._desc = None
        if description:
            self._desc = ctk.CTkLabel(
                self,
                text=description,
                anchor="w",
                justify="left",
                text_color=FG_TER,
                font=ctk.CTkFont(size=12),
            )
            self._desc.grid(row=1, column=1, sticky="ew", pady=(2, 10))

        self.control_host = ctk.CTkFrame(self, fg_color="transparent")
        self.control_host.grid(row=0, column=2, rowspan=rows, padx=(8, 12), pady=10, sticky="e")

        self.body_host = ctk.CTkFrame(self, fg_color="transparent")
        self.body_host.grid_columnconfigure(0, weight=1)

        if on_click:
            targets = [self, self._title]
            if icon is not None:
                targets.append(icon)
            if self._desc is not None:
                targets.append(self._desc)
            for w in targets:
                w.configure(cursor="hand2")
                w.bind("<Button-1>", lambda _e, cb=on_click: cb())

    def show_body(self) -> None:
        self.body_host.grid(row=3, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 12))


def make_switch(parent, variable) -> ctk.CTkSwitch:
    return ctk.CTkSwitch(parent, text="", variable=variable, width=44, height=22)


def make_ghost_button(parent, text: str, command, *, width: int = 0) -> ctk.CTkButton:
    kw = {
        "text": text,
        "command": command,
        "fg_color": SURFACE_ALT,
        "hover_color": "#3A3A3A",
        "text_color": FG,
        "height": 32,
        "corner_radius": 6,
    }
    if width:
        kw["width"] = width
    return ctk.CTkButton(parent, **kw)


__all__ = [
    "ACCENT",
    "ACCENT_LIGHT",
    "BG",
    "CTkNavItem",
    "CTkSettingsRow",
    "FG",
    "FG_SEC",
    "FG_TER",
    "LINE",
    "SURFACE",
    "SURFACE_ALT",
    "apply_native_window_chrome",
    "fluent_icon_font",
    "init_ctk",
    "make_ghost_button",
    "make_switch",
]
