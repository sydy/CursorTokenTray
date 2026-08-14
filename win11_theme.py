"""Win11 深色主题：色板、字体、圆角按钮与 Toggle（设置窗 / 右键菜单共用）。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

# 贴近 Win11 系统设置深色主题（Settings / Fluent）
BG = "#202020"
SURFACE = "#2B2B2B"
SURFACE_ALT = "#333333"
CTRL = "#454545"
CTRL_HOVER = "#555555"
HOVER = "#2D2D2D"
FG = "#FFFFFF"
FG_SEC = "#C5C5C5"
FG_TER = "#9A9A9A"
LINE = "#3F3F3F"
ACCENT = "#0067C0"
ACCENT_HOVER = "#1975C4"
ACCENT_LIGHT = "#60CDFF"
TOGGLE_ON = "#60CDFF"
STATUS = "#60CDFF"
DANGER = "#FF99A4"
DANGER_HOVER = "#FFB4BC"
MENU_BG = "#2B2B2B"
MENU_HOVER = "#3D3D3D"
MENU_SEP = "#424242"
MENU_PAD = 4
MENU_ITEM_RADIUS = 8
MENU_CORNER_RADIUS = 12
# 设置卡片圆角：与 Win11 浮层/右键菜单一致（约 12px）
CARD_RADIUS = 12
BTN_RADIUS = 8


_FONT_FAMILY: str | None = None


def font(size: int, bold: bool = False) -> tuple:
    global _FONT_FAMILY
    weight = "bold" if bold else "normal"
    if _FONT_FAMILY is None:
        try:
            import tkinter.font as tkfont

            families = set(tkfont.families())
            for family in ("Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI"):
                if family in families:
                    _FONT_FAMILY = family
                    break
        except Exception:
            pass
        if _FONT_FAMILY is None:
            _FONT_FAMILY = "Microsoft YaHei UI"
    return (_FONT_FAMILY, size, weight)


def scaled_size(base: int, scale: float = 1.0) -> int:
    return max(base, int(round(base * max(1.0, scale))))


def _canvas_round_rect(
    canvas: tk.Canvas,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    r: int,
    fill: str,
    *,
    tags: str | None = None,
) -> None:
    r = max(1, min(r, (x2 - x1) // 2, (y2 - y1) // 2))
    kw: dict = {"fill": fill, "outline": fill}
    if tags:
        kw["tags"] = tags
    canvas.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, **kw)
    canvas.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, **kw)
    canvas.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, **kw)
    canvas.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, **kw)
    canvas.create_rectangle(x1 + r, y1, x2 - r, y2, **kw)
    canvas.create_rectangle(x1, y1 + r, x2, y2 - r, **kw)


class Win11Card(tk.Frame):
    """圆角卡片：Canvas 绘制背景，避免 PIL/PhotoImage 触发 Configure 死循环。"""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        bg: str = SURFACE,
        radius: int = CARD_RADIUS,
        scale: float = 1.0,
    ) -> None:
        page_bg = parent.cget("bg") if hasattr(parent, "cget") else BG
        self._card_bg = bg
        self._page_bg = page_bg
        self._radius = scaled_size(radius, scale)
        self._last_paint: tuple[int, int] | None = None
        self._paint_job: str | None = None
        self._painting = False

        super().__init__(parent, bg=page_bg, highlightthickness=0, bd=0)

        self._bg = tk.Canvas(
            self,
            bg=page_bg,
            highlightthickness=0,
            bd=0,
        )
        self._bg.place(x=0, y=0, relwidth=1, relheight=1)

        self.content = tk.Frame(self, bg=bg, highlightthickness=0, bd=0)
        self.content.pack(
            fill=tk.BOTH,
            expand=True,
            padx=self._radius,
            pady=self._radius,
        )
        self.content.lift()

        self.bind("<Configure>", self._on_configure, add="+")

    def _on_configure(self, event=None) -> None:
        if event is not None and getattr(event, "widget", None) is not self:
            return
        # 尺寸几乎不变时跳过，避免开关/输入切换时无意义重绘
        if event is not None and self._last_paint is not None:
            lw, lh = self._last_paint
            if abs(int(event.width) - lw) <= 1 and abs(int(event.height) - lh) <= 1:
                return
        if self._paint_job is not None:
            try:
                self.after_cancel(self._paint_job)
            except tk.TclError:
                pass
        try:
            self._paint_job = self.after(16, self._paint_now)
        except tk.TclError:
            self._paint_job = None

    def _paint_now(self) -> None:
        self._paint_job = None
        w = max(int(self.winfo_width()), 1)
        h = max(int(self.winfo_height()), 1)
        self._paint_bg(w, h)

    def _paint_bg(self, w: int, h: int) -> None:
        if w < 8 or h < 8 or self._painting:
            return
        if self._last_paint == (w, h):
            return
        self._painting = True
        try:
            self._last_paint = (w, h)
            self._bg.delete("all")
            self._bg.configure(bg=self._page_bg)
            rad = min(self._radius, w // 2, h // 2)
            _canvas_round_rect(self._bg, 0, 0, w, h, rad, self._card_bg)
            self.content.lift()
        finally:
            self._painting = False

    def refresh_bg(self) -> None:
        self._last_paint = None
        try:
            self.update_idletasks()
        except tk.TclError:
            return
        w = max(int(self.winfo_width()), int(self.winfo_reqwidth()), 1)
        h = max(int(self.winfo_height()), int(self.winfo_reqheight()), 1)
        self._paint_bg(w, h)


class Win11RoundedButton(tk.Canvas):
    """圆角按钮（Canvas 绘制）。"""

    def __init__(
        self,
        parent: tk.Misc,
        text: str,
        command: Callable[[], None],
        *,
        variant: str = "default",
        state: str = tk.NORMAL,
        radius: int = BTN_RADIUS,
        font_size: int = 11,
        scale: float = 1.0,
        stretch: bool = False,
        height: int | None = None,
    ) -> None:
        self._text = text
        self._command = command
        self._variant = variant
        self._enabled = state == tk.NORMAL
        self._hover = False
        self._stretch = stretch
        self._font = font(font_size)
        self._pad_x = scaled_size(18, scale)
        self._pad_y = scaled_size(9, scale)
        self._draw_job: str | None = None
        self._last_size: tuple[int, int] | None = None

        palettes = {
            "accent": (ACCENT, ACCENT_HOVER, FG),
            "default": (SURFACE_ALT, CTRL_HOVER, FG),
            "subtle": (SURFACE, HOVER, FG_SEC),
        }
        self._bg, self._bg_hover, self._fg = palettes.get(variant, palettes["default"])
        if not self._enabled:
            self._bg, self._fg = SURFACE, "#666666"

        try:
            import tkinter.font as tkfont

            text_h = int(tkfont.Font(font=self._font).metrics("linespace"))
        except Exception:
            text_h = scaled_size(14, scale)
        h = int(height) if height is not None else (self._pad_y * 2 + text_h)
        # 圆角不超过高度一半，避免矮宽按钮看起来像“胶囊”
        self._radius = min(
            max(4, int(round(radius * max(1.0, min(scale, 1.25) * 0.5 + 0.5)))),
            max(4, h // 2 - 1),
        )
        w = self._measure_w(text) + self._pad_x * 2 if not stretch else 120

        bg_parent = parent.cget("bg") if hasattr(parent, "cget") else BG
        super().__init__(
            parent,
            width=w,
            height=h,
            bg=bg_parent,
            highlightthickness=0,
            bd=0,
            cursor="hand2" if self._enabled else "arrow",
        )
        # 固定高度，避免 grid/pack 把通栏按钮压扁、半宽按钮撑成胶囊
        self.pack_propagate(False)
        try:
            self.grid_propagate(False)
        except tk.TclError:
            pass
        self.bind("<Configure>", self._on_configure)
        self._bind_interactions(self._enabled)
        self._draw()

    def _measure_w(self, text: str) -> int:
        try:
            import tkinter.font as tkfont

            f = tkfont.Font(font=self._font)
            return int(f.measure(text))
        except Exception:
            return len(text) * 10

    def _on_configure(self, _e=None) -> None:
        if self._draw_job is not None:
            try:
                self.after_cancel(self._draw_job)
            except tk.TclError:
                pass
        try:
            self._draw_job = self.after_idle(self._draw)
        except tk.TclError:
            self._draw_job = None

    def _round_rect(self, x1: int, y1: int, x2: int, y2: int, r: int, fill: str) -> None:
        _canvas_round_rect(self, x1, y1, x2, y2, r, fill)

    def _draw(self) -> None:
        self._draw_job = None
        w = max(int(self.winfo_width()), int(self.winfo_reqwidth()))
        h = max(int(self.winfo_height()), int(self.winfo_reqheight()))
        if w <= 1 or h <= 1:
            w = int(self["width"])
            h = int(self["height"])
        size = (w, h)
        # 尺寸未变且非状态重绘时，允许强制刷新（set_state 会清 last_size）
        fill = self._bg_hover if self._hover and self._enabled else self._bg
        self.delete("all")
        self._round_rect(1, 1, w - 1, h - 1, self._radius, fill)
        self.create_text(
            w // 2,
            h // 2,
            text=self._text,
            fill=self._fg,
            font=self._font,
        )
        self._last_size = size

    def _on_enter(self, _e=None) -> None:
        self._hover = True
        self._draw()

    def _on_leave(self, _e=None) -> None:
        self._hover = False
        self._draw()

    def _on_click(self, _e=None) -> None:
        if self._enabled:
            self._command()

    def _bind_interactions(self, enabled: bool) -> None:
        self.unbind("<Enter>")
        self.unbind("<Leave>")
        self.unbind("<Button-1>")
        if enabled:
            self.bind("<Enter>", self._on_enter)
            self.bind("<Leave>", self._on_leave)
            self.bind("<Button-1>", self._on_click)

    def set_state(self, state: str) -> None:
        enabled = state == tk.NORMAL
        self._enabled = enabled
        palettes = {
            "accent": (ACCENT, ACCENT_HOVER, FG),
            "default": (SURFACE_ALT, CTRL_HOVER, FG),
            "subtle": (SURFACE, HOVER, FG_SEC),
        }
        self._bg, self._bg_hover, self._fg = palettes.get(self._variant, palettes["default"])
        if not enabled:
            self._bg, self._fg = SURFACE, "#666666"
            self._hover = False
        self.configure(cursor="hand2" if enabled else "arrow")
        self._bind_interactions(enabled)
        self._last_size = None
        self._draw()


class Win11Toggle(tk.Canvas):
    """Win11 Toggle 开关。只负责翻转变量；副作用请挂 var.trace，避免重复触发。"""

    def __init__(
        self,
        parent: tk.Misc,
        var: tk.BooleanVar,
        *,
        bg: str = SURFACE,
        on_toggle: Callable[[], None] | None = None,
        scale: float = 1.0,
    ) -> None:
        self._var = var
        self._on_toggle = on_toggle
        self._bg = bg
        w = scaled_size(46, scale)
        h = scaled_size(24, scale)
        super().__init__(
            parent,
            width=w,
            height=h,
            bg=bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.bind("<Button-1>", self._click)
        # 仅重绘，不再二次调用 on_toggle（由点击路径或外部 trace 负责副作用）
        var.trace_add("write", lambda *_: self._safe_draw())
        self._draw()

    def _safe_draw(self) -> None:
        try:
            if self.winfo_exists():
                self._draw()
        except tk.TclError:
            pass

    def _click(self, _e=None) -> None:
        # 只翻转变量一次；副作用请挂 var.trace，避免与行点击/回调重复执行
        self._var.set(not self._var.get())
        if self._on_toggle:
            try:
                self._on_toggle()
            except Exception:
                pass

    def _draw(self) -> None:
        self.delete("all")
        w = int(self.winfo_reqwidth())
        h = int(self.winfo_reqheight())
        on = bool(self._var.get())
        track = TOGGLE_ON if on else CTRL
        pad = 2
        r = h - pad * 2
        self.create_oval(pad, pad, pad + r, pad + r, fill=track, outline=track)
        self.create_oval(w - pad - r, pad, w - pad, pad + r, fill=track, outline=track)
        self.create_rectangle(pad + r / 2, pad, w - pad - r / 2, pad + r, fill=track, outline=track)
        # 旋钮略内缩，贴近 Win11 Toggle
        kn = r - 2
        tx = (w - pad - r) + 1 if on else pad + 1
        ty = pad + 1
        self.create_oval(tx, ty, tx + kn, ty + kn, fill=FG, outline=FG)


def setup_combobox(style: ttk.Style, root: tk.Misc) -> None:
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(
        "Win11.TCombobox",
        fieldbackground=SURFACE_ALT,
        background=SURFACE_ALT,
        foreground=FG,
        arrowcolor=FG_SEC,
        bordercolor=LINE,
        lightcolor=LINE,
        darkcolor=LINE,
        padding=(10, 8),
        font=font(11),
    )
    style.map(
        "Win11.TCombobox",
        fieldbackground=[("readonly", SURFACE_ALT), ("disabled", SURFACE)],
        foreground=[("readonly", FG)],
        background=[("readonly", SURFACE_ALT)],
    )
    root.option_add("*TCombobox*Listbox.background", SURFACE_ALT)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", FG)
    root.option_add("*TCombobox*Listbox.font", font(11))
