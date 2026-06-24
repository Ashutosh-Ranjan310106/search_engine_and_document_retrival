import subprocess
import re
import sys
import os
import time
from pathlib import Path

# -----------------------------
# Configuration
# -----------------------------
APP_COMMAND = [
    "fastapi",
    "run",
    r"backend\knowledge_rag.py"
]

REQ_FILE = "requirements.txt"
LOG_FILE = "dependency_log.txt"
MAX_RETRIES = 50

# -----------------------------
# Regex Patterns
# -----------------------------
MODULE_REGEX = re.compile(
    r"ModuleNotFoundError:\s+No module named ['\"]([^'\"]+)['\"]"
)

UNICODE_REGEX = re.compile(
    r"UnicodeEncodeError:.*can't encode character"
)

# Optional mappings
PACKAGE_MAP = {
    "cv2": "opencv-python",
    "PIL": "pillow",
    "yaml": "pyyaml",
    "sklearn": "scikit-learn",
    "bs4": "beautifulsoup4"
}

attempted_modules = set()
utf8_enabled = False


# -----------------------------
# Logging
# -----------------------------
def log(message):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    text = f"[{timestamp}] {message}"

    print(text)

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(text + "\n")


# -----------------------------
# Requirements Handling
# -----------------------------
def add_to_requirements(package):
    req = Path(REQ_FILE)

    if req.exists():
        existing = {
            line.strip().lower()
            for line in req.read_text(
                encoding="utf-8"
            ).splitlines()
            if line.strip()
        }
    else:
        existing = set()

    if package.lower() not in existing:
        with open(REQ_FILE, "a", encoding="utf-8") as f:
            f.write("\n"+package)

        log(f"Added '{package}' to requirements.txt")


# -----------------------------
# Install Packages
# -----------------------------
def install_requirements():
    log("Installing requirements...")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-r",
            REQ_FILE
        ]
    )

    return result.returncode == 0


# -----------------------------
# Main Loop
# -----------------------------
for retry in range(MAX_RETRIES):

    log(f"Starting application (attempt {retry + 1})")

    env = os.environ.copy()

    if utf8_enabled:
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

    process = subprocess.Popen(
        APP_COMMAND,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env
    )

    missing_module = None
    unicode_error = False

    for line in process.stdout:

        print(line, end="")

        match = MODULE_REGEX.search(line)
        if match:
            missing_module = match.group(1)
            break

        if UNICODE_REGEX.search(line):
            unicode_error = True
            break

    # -------------------------
    # Missing module
    # -------------------------
    if missing_module:

        package = PACKAGE_MAP.get(
            missing_module,
            missing_module
        )

        if package in attempted_modules:
            log(
                f"Already tried installing '{package}'."
            )
            process.kill()
            break

        attempted_modules.add(package)

        log(
            f"Missing module detected: {missing_module}"
        )

        log(
            f"Installing package: {package}"
        )

        add_to_requirements(package)

        process.kill()

        if not install_requirements():
            log("Package installation failed.")
            break

        time.sleep(2)
        continue

    # -------------------------
    # Unicode error
    # -------------------------
    if unicode_error:

        process.kill()

        if not utf8_enabled:
            utf8_enabled = True

            log(
                "UnicodeEncodeError detected."
            )

            log(
                "Enabling UTF-8 and retrying."
            )

            time.sleep(1)
            continue

        log(
            "Unicode error still exists."
        )

        log(
            "The application itself must be fixed."
        )

        break

    # -------------------------
    # Normal exit
    # -------------------------
    return_code = process.wait()

    if return_code == 0:
        log("Application exited normally.")
    else:
        log(
            f"Application exited with code {return_code}"
        )

    break

else:
    log(
        f"Maximum retries ({MAX_RETRIES}) reached."
    )