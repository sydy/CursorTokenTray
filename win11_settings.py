"""设置页组件：深色侧栏 / 卡片行（样式参考 Fluent，不做系统设置复刻）。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from win11_theme import (
    ACCENT_LIGHT,
    BG,
    FG,
    FG_TER,
    HOVER,
    LINE,
    SURFACE,
    SURFACE_ALT,
    _canvas_round_rect,
    font,
)

CARD_GAP = 5
NAV_ITEM_H = 36


def fluent_font(size: int = 11) -> tuple:
    try:
        import tkinter.font as tkfont

        families = set(tkfont.families())
        for name in ("Segoe Fluent Icons", "Segoe MDL2 Assets"):
            if name in families:
                return (name, size)
    except Exception:
        pass
    return font(size)


def fluent_icon(
    parent: tk.Misc,
    glyph: str,
    *,
    size: int = 14,
    box: int | None = None,
    fg: str = FG,
    bg: str = SURFACE,
) -> tk.Canvas:
    """按字形实际像素占位，避免固定小盒子裁切 Fluent 图标。"""
    try:
        import tkinter.font as tkfont

        f = tkfont.Font(font=fluent_font(size))
        need = max(int(f.measure(glyph)), int(f.metrics("linespace"))) + 4
    except Exception:
        need = size + 12
    box_px = max(int(box or 0), need, size + 8)
    c = tk.Canvas(parent, width=box_px, height=box_px, bg=bg, highlightthickness=0, bd=0)
    c.create_text(
        box_px / 2,
        box_px / 2,
        text=glyph,
        fill=fg,
        font=fluent_font(size),
        anchor="center",
    )
    return c


class SettingsNavItem(tk.Canvas):
    def __init__(
        self,
        parent: tk.Misc,
        text: str,
        glyph: str,
        command: Callable[[], None],
        *,
        selected: bool = False,
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        self._text = text
        self._glyph = glyph
        self._command = command
        self._selected = selected
        self._hover = False
        w = int(width) if width is not None else 180
        h = int(height) if height is not None else NAV_ITEM_H
        super().__init__(
            parent, width=w, height=h, bg=BG, highlightthickness=0, bd=0, cursor="hand2"
        )
        self.bind("<Enter>", lambda _e: self._hover_set(True))
        self.bind("<Leave>", lambda _e: self._hover_set(False))
        self.bind("<Button-1>", lambda _e: self._command())
        self._draw()

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._draw()

    def _hover_set(self, v: bool) -> None:
        self._hover = v
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        w, h = int(self["width"]), int(self["height"])
        fill = SURFACE if self._selected else (HOVER if self._hover else BG)
        if fill != BG:
            _canvas_round_rect(self, 0, 2, w - 2, h - 2, 6, fill)
        if self._selected:
            bh = max(14, h // 2)
            y0 = (h - bh) // 2
            self.create_rectangle(0, y0, 3, y0 + bh, fill=ACCENT_LIGHT, outline=ACCENT_LIGHT)
        # 给左侧选中条留空隙，图标与文字略分开
        ix = max(30, 12 + h // 3)
        self.create_text(ix, h // 2, text=self._glyph, fill=FG, font=fluent_font(11), anchor="center")
        self.create_text(ix + 24, h // 2, text=self._text, fill=FG, font=font(10), anchor="w")


class SettingsSectionLabel(tk.Frame):
    def __init__(self, parent: tk.Misc, text: str) -> None:
        super().__init__(parent, bg=BG)
        tk.Label(self, text=text, fg=FG_TER, bg=BG, font=font(9), anchor="w").pack(
            fill=tk.X, pady=(12, 6)
        )


class SettingsExpander(tk.Frame):
    """设置行：标题/说明在左，控件在右。"""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        title: str,
        description: str = "",
        glyph: str = "\ue713",
        clickable: bool = False,
        on_click: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent, bg=BG)
        self.columnconfigure(0, weight=1)

        card = tk.Frame(
            self,
            bg=SURFACE,
            highlightthickness=1,
            highlightbackground=LINE,
            highlightcolor=LINE,
            bd=0,
        )
        card.grid(row=0, column=0, sticky="ew", pady=(0, CARD_GAP))
        card.columnconfigure(1, weight=1)
        self.card = card
        self.content = card

        pad_x, pad_y = 14, 10
        rows = 2 if description else 1

        icon = fluent_icon(card, glyph, size=11, fg=FG, bg=SURFACE)
        icon.grid(row=0, column=0, rowspan=rows, sticky="n", padx=(pad_x, 10), pady=pad_y)
        self._icon = icon

        self._title = tk.Label(card, text=title, fg=FG, bg=SURFACE, font=font(11), anchor="w")
        self._title.grid(row=0, column=1, sticky="w", pady=(pad_y, 0 if description else pad_y))

        self._desc = None
        if description:
            self._desc = tk.Label(
                card,
                text=description,
                fg=FG_TER,
                bg=SURFACE,
                font=font(9),
                anchor="w",
                justify=tk.LEFT,
                wraplength=480,
            )
            self._desc.grid(row=1, column=1, sticky="ew", pady=(1, pad_y))

        self.control_host = tk.Frame(card, bg=SURFACE)
        self.control_host.grid(row=0, column=2, rowspan=rows, sticky="e", padx=(10, pad_x), pady=pad_y)

        self.body_host = tk.Frame(card, bg=SURFACE)
        self.body_host.columnconfigure(0, weight=1)
        self._pad_x, self._pad_y = pad_x, pad_y

        if clickable or on_click:
            for w in (self, card, self._title):
                w.configure(cursor="hand2")
                if on_click:
                    w.bind("<Button-1>", lambda _e, cb=on_click: cb())

    def show_body(self) -> None:
        self.body_host.grid(
            row=3, column=0, columnspan=3, sticky="ew", padx=self._pad_x, pady=(0, self._pad_y)
        )

    def hide_body(self) -> None:
        self.body_host.grid_forget()

    def set_wrap(self, wrap: int) -> None:
        if self._desc is not None:
            self._desc.configure(wraplength=max(160, wrap))


def make_settings_entry(
    parent: tk.Misc,
    var: tk.Variable,
    *,
    show: str | None = None,
    width: int | None = None,
    justify: str = "left",
) -> tk.Entry:
    border = tk.Frame(parent, bg=LINE, highlightthickness=0, bd=0)
    kw: dict = {
        "textvariable": var,
        "bg": SURFACE_ALT,
        "fg": FG,
        "insertbackground": FG,
        "relief": tk.FLAT,
        "highlightthickness": 0,
        "bd": 0,
        "font": font(10),
        "justify": justify,
    }
    if show is not None:
        kw["show"] = show
    if width is not None:
        kw["width"] = width
    entry = tk.Entry(border, **kw)
    entry.pack(fill=tk.BOTH, expand=True, padx=1, pady=1, ipady=6)
    entry._border_frame = border  # type: ignore[attr-defined]
    return entry


def make_settings_combobox(
    parent: tk.Misc,
    var: tk.StringVar,
    values: list[str],
    *,
    width: int = 12,
) -> ttk.Combobox:
    border = tk.Frame(parent, bg=LINE, highlightthickness=0, bd=0)
    box = ttk.Combobox(
        border,
        textvariable=var,
        values=values,
        state="readonly",
        width=width,
        style="Win11.TCombobox",
    )
    box.pack(fill=tk.BOTH, expand=True, padx=1, pady=1, ipady=4)
    box._border_frame = border  # type: ignore[attr-defined]
    return box


def pack_bordered(control: tk.Widget, host: tk.Misc) -> None:
    if hasattr(control, "_border_frame"):
        control._border_frame.pack(in_=host)  # type: ignore[attr-defined]
    else:
        control.pack(in_=host)


def apply_settings_chrome(win: tk.Misc) -> None:
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
