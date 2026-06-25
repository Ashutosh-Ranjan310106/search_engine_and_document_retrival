# -*- mode: python ; coding: utf-8 -*-

import os
import pkgutil
import importlib.util
from PyInstaller.utils.hooks import collect_submodules, collect_dynamic_libs

block_cipher = None

# --- Safe lightrag submodule discovery (no import, filesystem walk only) ---
def collect_submodules_safe(package_name, exclude_prefix=None):
    spec = importlib.util.find_spec(package_name)
    if spec is None or spec.submodule_search_locations is None:
        return [package_name]
    
    result = [package_name]
    for importer, modname, ispkg in pkgutil.walk_packages(
        path=spec.submodule_search_locations,
        prefix=package_name + ".",
        onerror=lambda x: None
    ):
        if exclude_prefix and any(modname.startswith(p) for p in exclude_prefix):
            continue
        result.append(modname)
    return result

lightrag_modules = collect_submodules_safe(
    "lightrag",
    exclude_prefix=["lightrag.api"]  # skip api — calls parse_args() at import time
)

# Manually list the lightrag.api modules your app needs at runtime
lightrag_api_manual = [
    "lightrag.api",
    "lightrag.api.config",
    "lightrag.api.auth",
    "lightrag.api.utils_api",
    "lightrag.api.routers",
    "lightrag.api.routers.ollama_api",
]

hiddenimports = (
    collect_submodules("backend")
    + lightrag_modules
    + lightrag_api_manual
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

binaries = collect_dynamic_libs("PyMuPDF")

a = Analysis(
    ["run.py"],
    pathex=[os.getcwd()],
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