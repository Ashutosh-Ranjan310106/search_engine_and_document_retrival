FROM python:3.13.3-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    git curl build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip setuptools wheel

COPY requirements__.txt .

# install torch FIRST (CPU version)

RUN pip show torch 2>/dev/null | grep -q "Name: torch" || \
    pip install torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir "docling>=2.92.0,<2.107.0" transformers==4.47.1
RUN pip uninstall fastapi-cli typer -y
# install rest
RUN pip install -r requirements__.txt

COPY backend ./backend
COPY run.py ./run.py
COPY app_runner.py ./app_runner.py

EXPOSE 8000

CMD ["uvicorn", "backend.knowledge_rag:app", "--host", "0.0.0.0", "--port", "8000"]