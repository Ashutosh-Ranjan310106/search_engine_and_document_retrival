# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_dynamic_libs
block_cipher = None

# Collect backend + lightrag modules automatically
hiddenimports = (
    collect_submodules("backend")
    + collect_submodules("lightrag")
    + collect_submodules("uvicorn")
    + collect_submodules("fastapi")
    + collect_submodules("starlette")
)
hiddenimports += [
    "jaraco.text",
    "jaraco.functools",
    "jaraco.context",
    "more_itertools",
    "pkg_resources",
]
hiddenimports += collect_submodules("docling")
hiddenimports += collect_submodules("spacy")
hiddenimports += collect_submodules("transformers")
hiddenimports += collect_submodules("torch")
hiddenimports += collect_submodules("onnxruntime")
hiddenimports += ["pkg_resources.py2_warn"]
hiddenimports += collect_submodules("docling.models")
hiddenimports += collect_submodules("docling.pipeline")
hiddenimports += collect_submodules("docling_core")
hiddenimports += [
    "fitz",
]
binaries = collect_dynamic_libs("PyMuPDF")
a = Analysis(
    ["run.py"],
    pathex=[os.getcwd()],   # CRITICAL FIX
    binaries=binaries,
    datas=[],

    hiddenimports=hiddenimports + [
        "backend",
        "backend.knowledge_rag",
        "backend.dockling_document_extraction",
        "backend.entity_extractor",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "notebook",
        "pytest",
        "IPython",
        "fastapi_cli"
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="backend"
)