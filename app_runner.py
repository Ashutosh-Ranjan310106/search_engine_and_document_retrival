import os
import subprocess

BASE = os.path.abspath("Ollama")

env = os.environ.copy()
env["OLLAMA_MODELS"] = os.path.join(BASE, "models")

subprocess.Popen(
    [os.path.join(BASE, "ollama.exe"), "serve"],
    env=env
)