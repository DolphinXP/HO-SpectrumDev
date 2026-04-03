# -*- mode: python ; coding: utf-8 -*-

block_cipher = None


a = Analysis(
    ['main.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('assets/*', 'assets'),
        ('src/ui/styles.qss', 'src/ui'),
        ('src/device/gxipy', 'gxipy'),
    ],
    hiddenimports=['gxipy'],
    hookspath=[],
    runtime_hooks=['runtime_hook_set_log_dir.py'],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data,
          cipher=block_cipher)

# Single-file build (onefile=True): bundle everything into one .exe
# exe = EXE(
#     pyz,
#     a.scripts,
#     a.binaries,
#     a.zipfiles,
#     a.datas,
#     [],
#     name='specdev-9h',
#     debug=False,
#     bootloader_ignore_signals=False,
#     strip=False,
#     upx=True,
#     console=False,
#     disable_windowed_traceback=False,
#     target_arch=None,
#     codesign_identity=None,
#     entitlements_file=None,
#     icon='assets/app.ico',
#     onefile=True
# )

# Folder-based build (onedir): output a directory with exe + dependencies
exe = EXE(
    pyz,
    a.scripts,
    [],
    name='specdev-9h',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='specdev-9h',
)