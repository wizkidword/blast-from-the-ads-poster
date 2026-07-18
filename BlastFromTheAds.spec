# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys


PROJECT_ROOT = Path(SPECPATH).resolve()
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from app_metadata import PACKAGE_HIDDEN_IMPORTS


a = Analysis(
    [str(SCRIPTS_DIR / "social_batch_app.py")],
    pathex=[str(SCRIPTS_DIR)],
    binaries=[],
    datas=[],
    hiddenimports=list(PACKAGE_HIDDEN_IMPORTS),
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
    name="BlastFromTheAds",
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
