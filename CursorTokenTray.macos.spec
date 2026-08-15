# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — macOS .app，无 Dock 图标（LSUIElement）

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/app_icon.png', 'assets'),
        ('assets/app_icon_16.png', 'assets'),
        ('assets/app_icon_32.png', 'assets'),
        ('assets/app_icon_48.png', 'assets'),
        ('assets/app_icon_64.png', 'assets'),
        ('assets/app_icon.svg', 'assets'),
        ('assets/ctk_theme.json', 'assets'),
    ],
    hiddenimports=[
        'pystray._darwin',
        'PIL._tkinter_finder',
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'cryptography',
        'cryptography.hazmat.primitives.ciphers.aead',
        'AppKit',
        'Foundation',
        'Quartz',
        'PyObjCTools',
        'objc',
        'macos_settings',
        'settings_launch',
        'status_text',
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
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app_icon.png',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='CursorTokenTray',
)

app = BUNDLE(
    coll,
    name='CursorTokenTray.app',
    icon='assets/app_icon.png',
    bundle_identifier='com.harker.cursortokentray',
    info_plist={
        'CFBundleName': 'CursorTokenTray',
        'CFBundleDisplayName': 'Cursor Token 剩余进度',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1.0.0',
        'LSMinimumSystemVersion': '11.0',
        'LSUIElement': True,
        'NSHighResolutionCapable': True,
        'NSAppleEventsUsageDescription': '用于显示用量通知。',
    },
)
