# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — onefile，无控制台
#
# Windows UI 全部走本进程 Win32（托盘 / 系统菜单 / 分层飞出层 / 原生设置），
# 不再打包 Tk、CustomTkinter、pystray。

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/app_icon.ico', 'assets'),
        ('assets/app_icon.png', 'assets'),
        ('assets/app_icon_16.png', 'assets'),
        ('assets/app_icon_32.png', 'assets'),
        ('assets/app_icon_48.png', 'assets'),
        ('assets/app_icon_64.png', 'assets'),
        ('assets/app_icon.svg', 'assets'),
    ],
    hiddenimports=[
        'cryptography',
        'cryptography.hazmat.primitives.ciphers.aead',
        'certifi',
        'accounts',
        'usage_snapshot',
        'usage_history',
        'status_text',
        'settings_launch',
        'win_api',
        'win_tray',
        'win_menu',
        'win_flyout',
        'win_settings',
        'win11_style',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'customtkinter',
        'pywinstyles',
        'pystray',
        'popup_ui',
        'popup_launch',
        'settings_ui',
        'ui_ctk',
        'tray_hover',
        'win11_settings',
        'win11_theme',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='CursorTokenTray',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app_icon.ico',
)
