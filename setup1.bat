@echo off
title DocRAG - Prepare Pendrive (Run this on INTERNET machine)
color 0B
setlocal

echo ============================================================
echo  STEP 1 of 2: Prepare Pendrive (needs internet - run ONCE)
echo  Run this on your machine WITH internet.
echo  Then copy the pendrive to the offline target machine.
echo ============================================================
echo.

REM ── Set the pendrive drive letter ─────────────────────────────
set /p DRIVE="Enter your pendrive drive letter (e.g. E): "
set PENDRIVE=%DRIVE%:
set PKGDIR=%PENDRIVE%\docrag_offline

echo.
echo Will download everything to: %PKGDIR%
echo.
pause

REM ── Check tools ──────────────────────────────────────────────
python --version >nul 2>&1 || (echo [ERROR] Python not found & pause & exit /b 1)
git --version >nul 2>&1 || (echo [ERROR] Git not found & pause & exit /b 1)

REM ── Create folder structure ───────────────────────────────────
mkdir "%PKGDIR%\pip_wheels" 2>nul
mkdir "%PKGDIR%\ollama_models" 2>nul
mkdir "%PKGDIR%\repo" 2>nul
mkdir "%PKGDIR%\lightrag_repo" 2>nul
mkdir "%PKGDIR%\python_installer" 2>nul
mkdir "%PKGDIR%\ollama_installer" 2>nul
mkdir "%PKGDIR%\git_installer" 2>nul

echo.
echo [1/6] Cloning main repo...
git clone https://github.com/Ashutosh-Ranjan310106/search_engine_and_document_retrival.git "%PKGDIR%\repo"

echo.
echo [2/6] Cloning LightRAG repo...
git clone https://github.com/HKUDS/LightRAG.git "%PKGDIR%\lightrag_repo"

echo.
echo [3/6] Downloading pip wheels (ALL dependencies, no internet needed later)...
REM --- Core framework ---
pip download flask python-dotenv aiohttp aiofiles numpy pydantic fastapi uvicorn starlette ^
    -d "%PKGDIR%\pip_wheels" --platform win_amd64 --python-version 3.11 --only-binary=:all:

REM --- Ollama client ---
pip download ollama -d "%PKGDIR%\pip_wheels" --platform win_amd64 --python-version 3.11 --only-binary=:all:

REM --- Document parsing ---
pip download docling docling-core docling-ibm-models docling-parse pypdf pdfplumber python-docx python-pptx ^
    -d "%PKGDIR%\pip_wheels" --platform win_amd64 --python-version 3.11 --only-binary=:all:

REM --- ML / embeddings ---
pip download sentence-transformers torch torchvision numpy scipy ^
    -d "%PKGDIR%\pip_wheels" --platform win_amd64 --python-version 3.11 --only-binary=:all:

REM --- Graph / search ---
pip download networkx nano-vectordb tiktoken regex ^
    -d "%PKGDIR%\pip_wheels" --platform win_amd64 --python-version 3.11 --only-binary=:all:

REM --- Utility ---
pip download sqlalchemy requests httpx python-multipart orjson rich colorlog ^
    -d "%PKGDIR%\pip_wheels" --platform win_amd64 --python-version 3.11 --only-binary=:all:

REM --- LightRAG and its extras ---
cd "%PKGDIR%\lightrag_repo"
pip download -e ".[api]" -d "%PKGDIR%\pip_wheels" --platform win_amd64 --python-version 3.11 --only-binary=:all:
cd /d "%~dp0"

echo.
echo [4/6] Pulling Ollama AI models (this is the big download ~5 GB)...
echo    Starting Ollama...
start /B ollama serve >nul 2>&1
timeout /t 3 /nobreak >nul

ollama pull phi4-mini
ollama pull nomic-embed-text

echo.
echo [5/6] Copying Ollama model files to pendrive...
REM Ollama stores models in %USERPROFILE%\.ollama\models
xcopy "%USERPROFILE%\.ollama\models" "%PKGDIR%\ollama_models" /E /I /Y /Q

echo.
echo [6/6] Downloading installers (Python, Git, Ollama)...
echo    Downloading Python 3.11 installer...
powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile '%PKGDIR%\python_installer\python-3.11.9-amd64.exe'"

echo    Downloading Git installer...
powershell -Command "Invoke-WebRequest -Uri 'https://github.com/git-for-windows/git/releases/download/v2.45.2.windows.1/Git-2.45.2-64-bit.exe' -OutFile '%PKGDIR%\git_installer\Git-2.45.2-64-bit.exe'"

echo    Downloading Ollama installer...
powershell -Command "Invoke-WebRequest -Uri 'https://ollama.com/download/OllamaSetup.exe' -OutFile '%PKGDIR%\ollama_installer\OllamaSetup.exe'"

echo.
echo    Writing clean requirements.txt (only real imports)...
(
echo flask
echo python-dotenv
echo aiohttp
echo aiofiles
echo numpy
echo pydantic
echo fastapi
echo uvicorn
echo starlette
echo ollama
echo docling
echo docling-core
echo docling-ibm-models
echo docling-parse
echo pypdf
echo pdfplumber
echo python-docx
echo sentence-transformers
echo torch
echo torchvision
echo networkx
echo nano-vectordb
echo tiktoken
echo regex
echo sqlalchemy
echo requests
echo httpx
echo python-multipart
echo orjson
echo rich
echo colorlog
echo scipy
echo langchain-core
echo langchain-community
echo langchain-text-splitters
echo openai
echo PyMuPDF
echo pillow
echo lxml
echo beautifulsoup4
echo tqdm
echo packaging
echo python-dateutil
) > "%PKGDIR%\repo\requirements_clean.txt"

echo.
echo ============================================================
echo  DONE! Pendrive is ready at: %PKGDIR%
echo.
echo  Contents:
echo    repo\            - The DocRAG source code
echo    lightrag_repo\   - LightRAG source (to install editable)
echo    pip_wheels\      - All Python packages (no internet needed)
echo    ollama_models\   - AI models (qwen2.5, phi4-mini, nomic)
echo    python_installer\- Python 3.11 setup exe
echo    git_installer\   - Git setup exe
echo    ollama_installer\- Ollama setup exe
echo.
echo  Now safely eject the pendrive and run STEP2_install.bat
echo  on the offline host machine.
echo ============================================================
pause