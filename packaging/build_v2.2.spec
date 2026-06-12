# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


ROOT = Path(SPECPATH).resolve().parents[0]
ENTRY = next(ROOT.glob("*_v2.2.2.py"))
ASSET = ROOT / "src" / "data_merge_tool" / "assets" / "ui_checkmark.svg"


a = Analysis(
    [str(ENTRY)],
    pathex=[str(ROOT), str(ROOT / "src")],
    binaries=[],
    datas=[(str(ASSET), "assets")],
    hiddenimports=["xlrd", "openpyxl", "matplotlib.backends.backend_qtagg", "originpro", "OriginExt"],
    hookspath=[],
    hooksconfig={"matplotlib": {"backends": ["QtAgg"]}},
    runtime_hooks=[],
    excludes=[
        "PyQt5",
        "PyQt6",
        "PySide2",
        "torch",
        "torchvision",
        "torchaudio",
        "transformers",
        "tensorflow",
        "keras",
        "timm",
        "cv2",
        "IPython",
        "jupyter",
        "notebook",
        "zmq",
        "tkinter",
        "scipy",
    ],
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
    name="数据合并工具v2.2.2",
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
