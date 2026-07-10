# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


ROOT = Path(SPECPATH).resolve().parents[0]
VERSION_NS = {}
exec((ROOT / "src" / "data_merge_tool" / "version.py").read_text(encoding="utf-8"), VERSION_NS)
VERSION = VERSION_NS["VERSION"]
ENTRY = ROOT / "数据合并工具.py"
RESOURCES = ROOT / "src" / "data_merge_tool" / "resources"


a = Analysis(
    [str(ENTRY)],
    pathex=[str(ROOT), str(ROOT / "src")],
    binaries=[],
    datas=[
        (str(path), "resources")
        for path in RESOURCES.iterdir()
        if path.suffix.lower() in {".qss", ".svg"}
    ],
    hiddenimports=[
        "xlrd",
        "openpyxl",
        "originpro",
        "OriginExt",
        "data_merge_tool.origin.worker",
        "data_merge_tool.origin.automation",
        "data_merge_tool.origin.field_handlers",
    ],
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
    name=f"数据合并工具v{VERSION}",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
)
