# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — onefile，无控制台
#
# Windows 设置窗挂在托盘同一进程，资源走 sys._MEIPASS，不需要 onedir。
# 单文件启动时解到临时目录，关掉进程后由 bootloader 清理。

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
        ('assets/ctk_theme.json', 'assets'),
    ],
    hiddenimports=[
        'pystray._win32',
        'PIL._tkinter_finder',
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'cryptography',
        'cryptography.hazmat.primitives.ciphers.aead',
        'certifi',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
