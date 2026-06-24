@echo off
title DocSearch Backend — Build EXE
color 0B
setlocal

echo ============================================================
echo  DocSearch Backend — PyInstaller Build
echo  Run this from your project root with venv ACTIVATED.
echo  e.g.  venv\Scripts\activate  then  build_exe.bat
echo ============================================================
echo.

REM ── Sanity checks ────────────────────────────────────────────
python --version >nul 2>&1 || (echo [ERROR] Python not found. Activate your venv first. & pause & exit /b 1)
pyinstaller --version >nul 2>&1 || (
    echo [INSTALLING] PyInstaller not found. Installing...
    pip install pyinstaller
)

REM ── Confirm we're in the right folder ────────────────────────
if not exist "backend\knowledge_rag.py" (
    echo [ERROR] Run this script from the project root folder.
    echo         Expected to find:  backend\knowledge_rag.py
    pause & exit /b 1
)

REM ── Copy build files into project root ───────────────────────
echo [1/5] Copying build files...
copy /Y "%~dp0run.py" "run.py" >nul
copy /Y "%~dp0backend.spec" "backend.spec" >nul

REM ── Create custom hooks folder ───────────────────────────────
echo [2/5] Creating PyInstaller hooks...
mkdir hooks 2>nul

REM Hook for spacy en_core_web_sm model
(
echo from PyInstaller.utils.hooks import collect_data_files, collect_submodules
echo datas = collect_data_files^('en_core_web_sm'^)
echo hiddenimports = collect_submodules^('en_core_web_sm'^)
) > hooks\hook-en_core_web_sm.py

REM Hook for lightrag
(
echo from PyInstaller.utils.hooks import collect_all
echo datas, binaries, hiddenimports = collect_all^('lightrag'^)
) > hooks\hook-lightrag.py

REM Hook for gliner
(
echo from PyInstaller.utils.hooks import collect_all
echo datas, binaries, hiddenimports = collect_all^('gliner'^)
) > hooks\hook-gliner.py

REM Hook for tiktoken (needs regex data files)
(
echo from PyInstaller.utils.hooks import collect_data_files
echo datas = collect_data_files^('tiktoken'^)
echo hiddenimports = ['tiktoken_ext', 'tiktoken_ext.openai_public']
) > hooks\hook-tiktoken.py

REM Hook for docling
(
echo from PyInstaller.utils.hooks import collect_all
echo datas, binaries, hiddenimports = collect_all^('docling'^)
) > hooks\hook-docling.py

REM ── Clean previous build ─────────────────────────────────────
echo [3/5] Cleaning previous build...
if exist "build\backend" rmdir /s /q "build\backend"
if exist "dist\backend"  rmdir /s /q "dist\backend"

REM ── Run PyInstaller ──────────────────────────────────────────
echo [4/5] Running PyInstaller (this takes 5-15 minutes)...
echo.
pyinstaller backend.spec
echo.

REM ── Check result ─────────────────────────────────────────────
if not exist "dist\backend\backend.exe" (
    echo.
    echo [FAILED] backend.exe was not created.
    echo Check the output above for errors.
    echo Common fixes listed at bottom of this script.
    pause & exit /b 1
)

REM ── Copy .env template and uploads folder ────────────────────
echo [5/5] Copying runtime files into dist\backend\...
if exist "backend\.env"     copy /Y "backend\.env"     "dist\backend\.env"     >nul
if exist "backend\uploads"  xcopy "backend\uploads"    "dist\backend\uploads\" /E /I /Y /Q 2>nul
if exist "backend\rag_storage" xcopy "backend\rag_storage" "dist\backend\rag_storage\" /E /I /Y /Q 2>nul

REM Create empty uploads folder if it doesn't exist
mkdir "dist\backend\uploads" 2>nul

REM ── Print size ───────────────────────────────────────────────
echo.
echo ============================================================
echo  BUILD COMPLETE
echo  Output folder: dist\backend\
echo  Exe:           dist\backend\backend.exe
echo.
for /f "tokens=3" %%a in ('dir "dist\backend" /s /-c ^| find "File(s)"') do set SIZE=%%a
echo  Total size: ~%SIZE% bytes
echo.
echo  To run: dist\backend\backend.exe
echo  API will be at: http://localhost:8000
echo ============================================================
echo.

REM ── Common error fixes (printed for reference) ───────────────
echo  IF YOU SEE ERRORS:
echo  ------------------------------------------------------------------
echo  ModuleNotFoundError: spacy en_core_web_sm
echo    Fix: pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
echo.
echo  RecursionError during build
echo    Fix: Add "import sys; sys.setrecursionlimit(5000)" to top of run.py
echo.
echo  OSError: [WinError 126] torch DLL not found
echo    Fix: pip install torch==2.12.1 --index-url https://download.pytorch.org/whl/cu126
echo         then rebuild
echo.
echo  onnxruntime missing
echo    Fix: pip install onnxruntime
echo  ------------------------------------------------------------------
pause
