import os
import sys

# 🔥 IMPORTANT: ensures "backend" package is always found
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from backend.knowledge_rag import app


def main():
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )


if __name__ == "__main__":
    main()