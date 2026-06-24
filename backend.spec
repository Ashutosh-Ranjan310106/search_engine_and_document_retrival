# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# IMPORTANT: force PyInstaller to include backend modules
hidden_imports = (
    collect_submodules("backend")
    + collect_submodules("lightrag")
)

a = Analysis(
    ["run.py"],   # your entry point
    pathex=[os.getcwd()],  # CRITICAL FIX: ensures backend package is found
    binaries=[],
    datas=[],
    hiddenimports=hidden_imports + [
        "uvicorn",
        "fastapi",
        "starlette",
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
        "setuptools",
        "wheel",
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
    upx=True,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="backend"
)