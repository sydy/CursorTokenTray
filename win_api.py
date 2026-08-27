"""Windows 原生 API 封装。非 Windows 上导入安全，调用会失败。"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

IS_WIN = sys.platform == "win32"

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_TIMER = 0x0113
WM_PAINT = 0x000F
WM_ERASEBKGND = 0x0014
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_LBUTTONDOWN = 0x0201
WM_MOUSEMOVE = 0x0200
WM_CONTEXTMENU = 0x007B
WM_KEYDOWN = 0x0100
WM_KILLFOCUS = 0x0008
WM_SETFOCUS = 0x0007
WM_ACTIVATE = 0x0006
WM_SETFONT = 0x0030
WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
WM_USER = 0x0400
WM_APP = 0x8000
WM_NULL = 0x0000
WM_QUIT = 0x0012
WM_NOTIFY = 0x004E
WM_CTLCOLORSTATIC = 0x0138
WM_CTLCOLOREDIT = 0x0133
WM_CTLCOLORBTN = 0x0135
WM_CTLCOLORLISTBOX = 0x0134
WM_HSCROLL = 0x0114
WM_VSCROLL = 0x0115
WM_SIZE = 0x0005
WM_INITDIALOG = 0x0110

VK_ESCAPE = 0x1B
VK_RETURN = 0x0D

NIN_SELECT = WM_USER + 0
NIN_KEYSELECT = WM_USER + 1
NIN_BALLOONSHOW = WM_USER + 2
NIN_BALLOONHIDE = WM_USER + 3
NIN_BALLOONTIMEOUT = WM_USER + 4
NIN_BALLOONUSERCLICK = WM_USER + 5

NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIM_SETFOCUS = 3
NIM_SETVERSION = 4
NOTIFYICON_VERSION_4 = 4

NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_STATE = 0x00000008
NIF_INFO = 0x00000010
NIF_GUID = 0x00000020
NIF_REALTIME = 0x00000040
NIF_SHOWTIP = 0x00000080

NIIF_INFO = 0x00000001
NIIF_NOSOUND = 0x00000010

WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_POPUP = 0x80000000
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_CAPTION = 0x00C00000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_CLIPSIBLINGS = 0x04000000
WS_CLIPCHILDREN = 0x02000000
WS_TABSTOP = 0x00010000
WS_GROUP = 0x00020000
WS_BORDER = 0x00800000
WS_VSCROLL = 0x00200000
DS_SETFONT = 0x40

WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
WS_EX_APPWINDOW = 0x00040000
WS_EX_CLIENTEDGE = 0x00000200
WS_EX_COMPOSITED = 0x02000000

HWND_MESSAGE = wintypes.HWND(-3)
HWND_TOPMOST = wintypes.HWND(-1)

SW_HIDE = 0
SW_SHOW = 5
SW_SHOWNOACTIVATE = 4
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_HIDEWINDOW = 0x0080

TPM_RIGHTALIGN = 0x0008
TPM_BOTTOMALIGN = 0x0020
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080
TPM_RIGHTBUTTON = 0x0002

MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
MF_CHECKED = 0x00000008
MF_UNCHECKED = 0x00000000
MF_DISABLED = 0x00000002
MF_GRAYED = 0x00000001
MF_ENABLED = 0x00000000

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
LR_DEFAULTSIZE = 0x0040
IDI_APPLICATION = 32512

COLOR_WINDOW = 5
COLOR_WINDOWTEXT = 8
COLOR_BTNFACE = 15

IDC_ARROW = 32512
CW_USEDEFAULT = 0x80000000

BN_CLICKED = 0
LBN_SELCHANGE = 1
CBN_SELCHANGE = 1
EN_CHANGE = 0x0300

BM_GETCHECK = 0x00F0
BM_SETCHECK = 0x00F1
BST_UNCHECKED = 0
BST_CHECKED = 1

LB_ADDSTRING = 0x0180
LB_RESETCONTENT = 0x0184
LB_GETCURSEL = 0x0188
LB_SETCURSEL = 0x0186
LB_GETCOUNT = 0x018B
LB_GETTEXT = 0x018A
LB_GETTEXTLEN = 0x018A

CB_ADDSTRING = 0x0143
CB_SETCURSEL = 0x014E
CB_GETCURSEL = 0x0147
CB_RESETCONTENT = 0x014B

ES_AUTOHSCROLL = 0x0080
ES_PASSWORD = 0x0020
ES_MULTILINE = 0x0004
ES_WANTRETURN = 0x1000

SS_LEFT = 0x0000
SS_NOTIFY = 0x0100
BS_PUSHBUTTON = 0x00000000
BS_DEFPUSHBUTTON = 0x00000001
BS_AUTOCHECKBOX = 0x00000003
BS_GROUPBOX = 0x00000007
LBS_NOTIFY = 0x0001
LBS_NOINTEGRALHEIGHT = 0x0100
CBS_DROPDOWNLIST = 0x0003

WHITE_BRUSH = 0
BLACK_BRUSH = 4
DC_BRUSH = 18

SRCCOPY = 0x00CC0020
BI_RGB = 0
DIB_RGB_COLORS = 0
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
ULW_ALPHA = 0x00000002

SM_CXSMICON = 49
SM_CYSMICON = 50

GWL_STYLE = -16
GWL_EXSTYLE = -20
GWLP_USERDATA = -21
HWND_TOP = 0

MB_OK = 0x00000000
MB_YESNO = 0x00000004
MB_ICONERROR = 0x00000010
MB_ICONINFORMATION = 0x00000040
MB_ICONQUESTION = 0x00000020
IDYES = 6
IDOK = 1
IDCANCEL = 2

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

WM_TRAYICON = WM_APP + 1
WM_INVOKE = WM_APP + 2
WM_APPLY_ICON = WM_APP + 3
WM_APPLY_NOTIFY = WM_APP + 4
WM_FLYOUT_CLOSE = WM_APP + 5
WM_SETTINGS_RESULT = WM_APP + 6

LRESULT = ctypes.c_ssize_t
# WINFUNCTYPE 只在 Windows 上存在；Linux CI 用 CFUNCTYPE 占位，保证模块可导入。
_FUNCTYPE = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
WNDPROC = _FUNCTYPE(LRESULT, wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM)


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", ctypes.c_uint),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", ctypes.c_uint),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HANDLE),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HANDLE),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HANDLE),
    ]


class NOTIFYICONIDENTIFIER(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("guidItem", GUID),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HANDLE),
        ("hbmColor", wintypes.HANDLE),
    ]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", wintypes.BYTE),
        ("BlendFlags", wintypes.BYTE),
        ("SourceConstantAlpha", wintypes.BYTE),
        ("AlphaFormat", wintypes.BYTE),
    ]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hdc", wintypes.HDC),
        ("fErase", wintypes.BOOL),
        ("rcPaint", RECT),
        ("fRestore", wintypes.BOOL),
        ("fIncUpdate", wintypes.BOOL),
        ("rgbReserved", wintypes.BYTE * 32),
    ]


def _user32():
    return ctypes.windll.user32


def _shell32():
    return ctypes.windll.shell32


def _gdi32():
    return ctypes.windll.gdi32


def _kernel32():
    return ctypes.windll.kernel32


def get_module_handle() -> int:
    return int(_kernel32().GetModuleHandleW(None) or 0)


def load_cursor_arrow() -> int:
    return int(_user32().LoadCursorW(None, ctypes.c_wchar_p(IDC_ARROW)) or 0)


def def_window_proc(hwnd, msg, wparam, lparam) -> int:
    return int(_user32().DefWindowProcW(hwnd, msg, wparam, lparam))


def post_quit_message(code: int = 0) -> None:
    _user32().PostQuitMessage(int(code))


def post_message(hwnd, msg, wparam=0, lparam=0) -> None:
    _user32().PostMessageW(wintypes.HWND(hwnd), int(msg), wparam, lparam)


def message_box(title: str, text: str, flags: int = MB_OK | MB_ICONINFORMATION, parent: int = 0) -> int:
    return int(
        _user32().MessageBoxW(
            wintypes.HWND(parent or 0),
            str(text),
            str(title),
            int(flags),
        )
    )


def destroy_icon(handle: int) -> None:
    if handle:
        _user32().DestroyIcon(wintypes.HANDLE(handle))


def delete_object(handle: int) -> None:
    if handle:
        _gdi32().DeleteObject(wintypes.HANDLE(handle))
