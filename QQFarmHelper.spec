# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

# 收集 customtkinter 的主题/字体等数据文件
ctk_datas = collect_data_files('customtkinter')

a = Analysis(
    ['main_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('templates', 'templates'), ('config_runtime.json', '.')] + ctk_datas,
    hiddenimports=['cv2', 'numpy', 'pywintypes', 'win32api', 'win32con', 'win32gui', 'PIL._tkinter_finder'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='QQFarmHelper',
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
)
