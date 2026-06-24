@echo off
setlocal EnableDelayedExpansion
REM ============================================================================
REM  build.bat — Full build pipeline for DocSearch backend.exe
REM
REM  Run this from the repo root with your venv activated:
REM      build.bat
REM
REM  What it does:
REM    1. Sanity-checks the environment (Python, PyInstaller, venv)
REM    2. Downloads UPX (compressor) if not present
REM    3. Runs PyInstaller with backend.spec
REM    4. Copies runtime files (.env, uploads/, rag_storage/) into dist\backend\
REM    5. Prints final size report
REM ============================================================================

echo.
echo ============================================================
echo   DocSearch Backend — PyInstaller Build
echo ============================================================
echo.

REM ── 0. Must run from repo root ──────────────────────────────────────────────
if not exist "run.py" (
    echo [ERROR] run.py not found. Run this script from the repo root.
    exit /b 1
)
if not exist "backend\knowledge_rag.py" (
    echo [ERROR] backend\knowledge_rag.py not found. Wrong directory?
    exit /b 1
)

REM ── 1. Check Python ─────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found on PATH. Activate your venv first.
    exit /b 1
)
echo [OK] Python found:
python --version

REM ── 2. Check venv is active (look for fastapi in site-packages) ─────────────
python -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] FastAPI not importable. Make sure your venv is activated.
    echo         Run:  venv\Scripts\activate
    exit /b 1
)
echo [OK] venv appears active ^(fastapi importable^)

REM ── 3. Install / upgrade PyInstaller ────────────────────────────────────────
echo.
echo [STEP 1] Installing PyInstaller...
pip install "pyinstaller>=6.10" --quiet --upgrade
if errorlevel 1 (
    echo [ERROR] Failed to install PyInstaller.
    exit /b 1
)
echo [OK] PyInstaller ready

REM ── 4. Download UPX if not present ──────────────────────────────────────────
echo.
echo [STEP 2] Checking UPX...
if not exist "upx\upx.exe" (
    echo [INFO] UPX not found. Downloading UPX 4.2.4 for Windows x64...
    mkdir upx 2>nul
    REM Use PowerShell to download
    powershell -NoProfile -Command ^
        "Invoke-WebRequest -Uri 'https://github.com/upx/upx/releases/download/v4.2.4/upx-4.2.4-win64.zip' -OutFile 'upx\upx.zip' -UseBasicParsing"
    if errorlevel 1 (
        echo [WARN] UPX download failed. Build will continue WITHOUT compression.
        echo        Install UPX manually from https://upx.github.io/ into upx\upx.exe
        set UPX_DIR=
    ) else (
        powershell -NoProfile -Command ^
            "Expand-Archive -Path 'upx\upx.zip' -DestinationPath 'upx\tmp' -Force; Copy-Item 'upx\tmp\upx-4.2.4-win64\upx.exe' 'upx\upx.exe'; Remove-Item 'upx\tmp' -Recurse -Force; Remove-Item 'upx\upx.zip'"
        echo [OK] UPX downloaded to upx\upx.exe
        set UPX_DIR=--upx-dir upx
    )
) else (
    echo [OK] UPX found at upx\upx.exe
    set UPX_DIR=--upx-dir upx
)

REM ── 5. Clean previous build ──────────────────────────────────────────────────
echo.
echo [STEP 3] Cleaning previous build artifacts...
if exist "dist\backend" (
    rmdir /s /q "dist\backend"
    echo [OK] dist\backend removed
)
if exist "build\backend" (
    rmdir /s /q "build\backend"
    echo [OK] build\backend removed
)

REM ── 6. Run PyInstaller ───────────────────────────────────────────────────────
echo.
echo [STEP 4] Running PyInstaller...
echo          This will take 5-15 minutes for the first build.
echo          torch + docling + spacy = lots of files to collect.
echo.

pyinstaller backend.spec --noconfirm --clean > build_log.txt 2>&1
type build_log.txt | findstr /I "warn warning error"
if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller failed. Check the output above.
    echo         Common causes:
    echo           - Missing hidden import ^(add to backend.spec hiddenimports^)
    echo           - DLL not found ^(add to backend.spec binaries^)
    echo           - Import error in run.py or backend\knowledge_rag.py
    exit /b 1
)
echo.
echo [OK] PyInstaller finished

REM ── 7. Copy runtime files into dist\backend\ ─────────────────────────────────
echo.
echo [STEP 5] Copying runtime files...

REM .env (required — contains OLLAMA_HOST, EMBED_MODEL etc.)
if exist ".env" (
    copy /y ".env" "dist\backend\.env" >nul
    echo [OK] .env copied
) else (
    echo [WARN] .env not found at repo root. You must manually place it in dist\backend\
)

REM Create empty uploads and rag_storage dirs
if not exist "dist\backend\uploads" mkdir "dist\backend\uploads"
echo [OK] dist\backend\uploads\ created

if not exist "dist\backend\rag_storage" mkdir "dist\backend\rag_storage"

REM Optionally copy pre-seeded rag_storage (existing graph data)
if exist "rag_storage" (
    xcopy /e /y /q "rag_storage\*" "dist\backend\rag_storage\" >nul 2>&1
    echo [OK] rag_storage\ copied ^(pre-seeded graph data^)
)

REM ── 8. Write a launch script inside dist\backend\ ─────────────────────────────
echo.
echo [STEP 6] Writing start.bat inside dist\backend\...
(
echo @echo off
echo cd /d "%%~dp0"
echo echo Starting DocSearch Backend...
echo echo API will be available at http://localhost:8000
echo echo Swagger UI at http://localhost:8000/docs
echo echo Press Ctrl+C to stop.
echo echo.
echo backend.exe
echo pause
) > "dist\backend\start.bat"
echo [OK] dist\backend\start.bat written

REM ── 9. Size report ───────────────────────────────────────────────────────────
echo.
echo [STEP 7] Build complete. Final size:
for /f "tokens=3" %%a in ('dir /s "dist\backend" ^| findstr "File(s)"') do (
    echo          dist\backend\ = %%a bytes total
)
echo.
echo ============================================================
echo   BUILD SUCCESS
echo   Distributable folder: dist\backend\
echo   Run it:               dist\backend\start.bat
echo                      or dist\backend\backend.exe
echo ============================================================
echo.
echo BEFORE DISTRIBUTING — checklist:
echo   [1] dist\backend\.env         — edit OLLAMA_HOST if needed
echo   [2] dist\backend\rag_storage\ — pre-seeded graph (already copied if existed)
echo   [3] dist\backend\uploads\     — pre-loaded documents (copy manually if wanted)
echo   [4] Ollama must be installed separately on the target machine
echo       and the models must be pulled before first run.
echo.

endlocal