# backend.spec  — PyInstaller spec for DocSearch backend
# Run from inside your activated venv:
#   pyinstaller backend.spec
#
# Output: dist\backend\backend.exe  (one-folder build)
# Copy the entire dist\backend\ folder to the target machine.

import sys
import os
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

# ── Helper: collect everything from a package ─────────────────────────────────
def collect_pkg(name):
    d, b, h = collect_all(name)
    return d, b, h

# ── Collect all packages that have data files / dynamic imports ───────────────

# lightrag
lr_d, lr_b, lr_h = collect_pkg('lightrag')

# docling (ships lots of config/model data)
dl_d, dl_b, dl_h = collect_pkg('docling')
dlc_d, dlc_b, dlc_h = collect_pkg('docling_core')
dlm_d, dlm_b, dlm_h = collect_pkg('docling_ibm_models')
dlp_d, dlp_b, dlp_h = collect_pkg('docling_parse')

# spacy + model
sp_d, sp_b, sp_h = collect_pkg('spacy')
sp_model_d = collect_data_files('en_core_web_sm')

# gliner
gl_d, gl_b, gl_h = collect_pkg('gliner')

# sentence_transformers
st_d, st_b, st_h = collect_pkg('sentence_transformers')

# transformers / tokenizers / huggingface_hub
tr_d, tr_b, tr_h = collect_pkg('transformers')
hf_d, hf_b, hf_h = collect_pkg('huggingface_hub')
tk_d, tk_b, tk_h = collect_pkg('tokenizers')

# torch  (large but required by gliner, sentence-transformers, docling)
to_d, to_b, to_h = collect_pkg('torch')
tv_d, tv_b, tv_h = collect_pkg('torchvision')

# onnxruntime (docling uses it for table detection)
on_d, on_b, on_h = collect_pkg('onnxruntime')

# fastapi / uvicorn / starlette
fa_d, fa_b, fa_h = collect_pkg('fastapi')
uv_d, uv_b, uv_h = collect_pkg('uvicorn')
st2_d, st2_b, st2_h = collect_pkg('starlette')

# misc data-bearing packages
misc_d = (
    collect_data_files('tiktoken') +
    collect_data_files('nano_vectordb') +
    collect_data_files('networkx') +
    collect_data_files('sklearn') +
    collect_data_files('scipy') +
    collect_data_files('PIL') +
    collect_data_files('cv2') +
    collect_data_files('pdfminer') +
    collect_data_files('pypdfium2') +
    collect_data_files('rapidocr') +
    collect_data_files('easyocr') +
    []
)

all_datas = (
    lr_d + dl_d + dlc_d + dlm_d + dlp_d +
    sp_d + sp_model_d + gl_d + st_d +
    tr_d + hf_d + tk_d +
    to_d + tv_d + on_d +
    fa_d + uv_d + st2_d +
    misc_d +
    # Include the backend source package itself
    [('backend', 'backend')]
)

all_binaries = (
    lr_b + dl_b + dlc_b + dlm_b + dlp_b +
    sp_b + gl_b + st_b +
    tr_b + hf_b + tk_b +
    to_b + tv_b + on_b +
    fa_b + uv_b + st2_b
)

all_hiddenimports = (
    lr_h + dl_h + dlc_h + dlm_h + dlp_h +
    sp_h + gl_h + st_h +
    tr_h + hf_h + tk_h +
    to_h + tv_h + on_h +
    fa_h + uv_h + st2_h +

    # Packages that use lazy / string-based imports
    collect_submodules('lightrag') +
    collect_submodules('docling') +
    collect_submodules('spacy') +
    collect_submodules('thinc') +
    collect_submodules('gliner') +
    collect_submodules('sentence_transformers') +
    collect_submodules('transformers') +
    collect_submodules('torch') +
    collect_submodules('fastapi') +
    collect_submodules('uvicorn') +
    collect_submodules('starlette') +
    collect_submodules('pydantic') +
    collect_submodules('aiohttp') +
    collect_submodules('multidict') +
    collect_submodules('yarl') +

    # Explicit hidden imports for known dynamic loaders
    [
        # uvicorn internals
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.asyncio',
        'uvicorn.loops.uvloop',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.http.httptools_impl',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.websockets_impl',
        'uvicorn.protocols.websockets.wsproto_impl',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',

        # fastapi / starlette
        'fastapi.middleware.cors',
        'fastapi.responses',
        'starlette.middleware',
        'starlette.middleware.cors',

        # pydantic v2
        'pydantic.deprecated.class_validators',
        'pydantic.deprecated.config',
        'pydantic_core',

        # aiohttp / multidict
        'aiohttp',
        'multidict._multidict',
        'yarl._quoting',

        # spacy
        'en_core_web_sm',
        'spacy.lang.en',
        'spacy.pipeline',
        'spacy.pipeline.ner',
        'thinc.backends',
        'thinc.backends._custom_kernels',
        'cymem',
        'preshed',
        'blis',
        'murmurhash',
        'srsly',
        'wasabi',
        'catalogue',
        'confection',
        'weasel',

        # gliner uses huggingface
        'gliner.model',
        'safetensors',
        'safetensors.torch',

        # sentence_transformers CrossEncoder
        'sentence_transformers.cross_encoder',
        'sentence_transformers.cross_encoder.CrossEncoder',

        # tiktoken
        'tiktoken_ext',
        'tiktoken_ext.openai_public',

        # lightrag storage backends
        'lightrag.kg',
        'lightrag.kg.shared_storage',
        'lightrag.kg.neo4j_impl',
        'lightrag.storage',
        'nano_vectordb',

        # docling internals
        'docling.datamodel',
        'docling.backend',
        'docling.pipeline',
        'docling_parse',
        'docling_ibm_models',

        # stdlib modules sometimes missed
        'sqlite3',
        'asyncio',
        'mimetypes',
        'hashlib',
        'uuid',
        'logging.handlers',
        'email.mime.multipart',
        'email.mime.text',

        # misc
        'numpy',
        'numpy.core._multiarray_umath',
        'scipy.special._ufuncs',
        'sklearn',
        'sklearn.utils._cython_blas',
        'sklearn.neighbors._partition_nodes',
        'PIL',
        'PIL.Image',
        'fitz',        # PyMuPDF
        'pypdf',
        'pdfminer',
        'pdfminer.high_level',
        'pdfminer.layout',
        'beautifulsoup4',
        'bs4',
        'lxml',
        'lxml._elementpath',
        'lxml.etree',
        'networkx',
        'dotenv',
        'json_repair',
        'tenacity',
        'orjson',
        'rich',
        'colorlog',
        'regex',
        'xxhash',
        'zstandard',
        'packaging',
        'psutil',
    ]
)

# ── Entry point wrapper ───────────────────────────────────────────────────────
# PyInstaller needs a plain __main__ entry point.
# We generate a small run.py that starts uvicorn programmatically.
# (See build_exe.bat which writes run.py before calling pyinstaller)

a = Analysis(
    ['run.py'],            # entry point — see build_exe.bat
    pathex=['.'],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hiddenimports,
    hookspath=['.\\hooks'],   # custom hooks folder (created by build_exe.bat)
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Things confirmed NOT imported anywhere in the backend
        'aioboto3', 'asyncpg', 'autogen', 'chromadb',
        'faiss', 'pymilvus', 'pymongo', 'pgvector',
        'qdrant_client', 'ragas', 'langfuse', 'zhipuai',
        'llama_index', 'imgui_bundle', 'moderngl',
        'datasets', 'google.genai', 'google.api_core',
        'langchain_openai', 'langchain_experimental',
        # Heavy stdlib modules not used
        'tkinter', 'unittest', 'pdb', 'doctest',
        'xml.etree.ElementTree',   # use lxml instead
        'curses', 'readline',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,    # one-folder mode (smaller, faster, easier to debug)
    name='backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                 # compress binaries with UPX if available
    console=True,             # keep console so you can see logs / errors
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=['torch_*.dll', 'cublas*.dll', 'cudnn*.dll'],
    name='backend',
)
