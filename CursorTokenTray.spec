# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — onedir，无控制台

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
        'pystray._win32',
        'PIL._tkinter_finder',
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'cryptography',
        'cryptography.hazmat.primitives.ciphers.aead',
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
    [],
    exclude_binaries=True,
    name='CursorTokenTray',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app_icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CursorTokenTray',
)
