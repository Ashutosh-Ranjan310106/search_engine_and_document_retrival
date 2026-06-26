import os
import sys
import time
import signal
import subprocess

# ─────────────────────────────────────────────
#  Terminal helpers  (stdlib only, no extras)
# ─────────────────────────────────────────────
WIDTH = 60

def _clr(code: str, text: str) -> str:
    """Wrap text in ANSI colour (works on Win 10+ console & most terminals)."""
    return f"\033[{code}m{text}\033[0m"

def cyan(t):   return _clr("96", t)
def green(t):  return _clr("92", t)
def yellow(t): return _clr("93", t)
def red(t):    return _clr("91", t)
def bold(t):   return _clr("1",  t)
def dim(t):    return _clr("2",  t)

def box(lines, colour=cyan):
    """Print a single-line-border box around the given lines."""
    inner = WIDTH - 2
    top    = "┌" + "─" * inner + "┐"
    bottom = "└" + "─" * inner + "┘"
    print(colour(top))
    for line in lines:
        # strip ANSI for width calculation
        import re
        plain = re.sub(r"\033\[[0-9;]*m", "", line)
        pad = inner - len(plain)
        print(colour("│") + line + " " * max(pad, 0) + colour("│"))
    print(colour(bottom))

def banner():
    """Splash header shown once at startup."""
    os.system("cls" if os.name == "nt" else "clear")
    lines = [
        "",
        bold(cyan("  DocSearch  Launcher")),
        dim("  Powered by Ollama + FastAPI + Electron"),
        "",
    ]
    box(lines)
    print()

def status(label: str, state: str, ok: bool = True):
    """Print a coloured status line."""
    icon  = green("✔") if ok else red("✖")
    col   = green if ok else red
    print(f"  {icon}  {bold(label):<20} {col(state)}")

def spinner_wait(seconds: int, label: str = "Waiting"):
    """Animate a spinner for `seconds` seconds."""
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    end = time.time() + seconds
    i = 0
    while time.time() < end:
        remaining = max(0, int(end - time.time()))
        frame = cyan(frames[i % len(frames)])
        sys.stdout.write(f"\r  {frame}  {label} … {dim(str(remaining) + 's')} ")
        sys.stdout.flush()
        time.sleep(0.1)
        i += 1
    sys.stdout.write("\r" + " " * (WIDTH) + "\r")  # clear line
    sys.stdout.flush()

def section(title: str):
    """Print a subtle section divider."""
    print()
    print(f"  {dim('─' * 4)}  {yellow(title)}  {dim('─' * (WIDTH - len(title) - 10))}")

def shutdown_header():
    print()
    box([
        "",
        bold(yellow("  Shutting down services …")),
        "",
    ], colour=yellow)
    print()

# ─────────────────────────────────────────────
#  Enable ANSI on Windows
# ─────────────────────────────────────────────
if os.name == "nt":
    import ctypes
    kernel32 = ctypes.windll.kernel32        # type: ignore[attr-defined]
    kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

# ─────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────
BASE = os.path.abspath("Ollama")
env  = os.environ.copy()
env["OLLAMA_MODELS"] = os.path.join(BASE, "models")

processes: list[tuple[subprocess.Popen, str]] = []

# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────
def stop_process(proc: subprocess.Popen, name: str):
    if proc and proc.poll() is None:
        print(f"  {yellow('⏹')}  Stopping {bold(name)} …")
        try:
            proc.terminate()
            proc.wait(timeout=5)
            status(name, "stopped")
        except subprocess.TimeoutExpired:
            print(f"  {red('!')}  Force-killing {bold(name)} …")
            proc.kill()
            status(name, "killed", ok=False)

# ─────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────
banner()

try:
    # ── Ollama ───────────────────────────────
    section("Starting Ollama")
    ollama = subprocess.Popen(
        [os.path.join(BASE, "ollama.exe"), "serve"],
        env=env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    processes.append((ollama, "Ollama"))
    status("Ollama", "process launched")
    spinner_wait(5, "Waiting for Ollama to initialise")
    status("Ollama", "ready", ok=ollama.poll() is None)

    # ── FastAPI backend ───────────────────────
    section("Starting Backend")
    backend = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "backend.knowledge_rag:app",
            "--host", "127.0.0.1",
            "--port", "8000",
        ],
        env=env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    processes.append((backend, "Backend"))
    status("Backend", "process launched")
    spinner_wait(1, "Waiting for FastAPI")
    status("Backend", "ready  →  http://127.0.0.1:8000", ok=backend.poll() is None)

    # ── Frontend ──────────────────────────────
    section("Starting Frontend")
    frontend = subprocess.Popen(
        [r"frontend\dist\win-unpacked\DocSearch.exe"]
    )
    status("DocSearch UI", "launched")

    # ── All up ────────────────────────────────
    print()
    box([
        "",
        green("  ✔  All services are running"),
        dim("     Close the DocSearch window to exit"),
        "",
    ], colour=green)
    print()

    frontend.wait()
    print()
    status("Frontend", "closed — beginning shutdown")

except KeyboardInterrupt:
    print()
    print(f"  {yellow('⚡')}  Keyboard interrupt received.")

finally:
    shutdown_header()
    for proc, name in reversed(processes):
        stop_process(proc, name)
    print()
    box([
        "",
        bold("  All services stopped.  Goodbye!"),
        "",
    ], colour=dim)
    print()