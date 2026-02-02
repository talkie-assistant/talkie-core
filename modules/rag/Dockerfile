# RAG module container: chunk, embed (Ollama), Chroma store, PDF.
# Hosts only RAG dependencies inside this image.
FROM python:3.11-slim

WORKDIR /app

# Shared code and config (required for python -m modules.rag.server)
COPY sdk ./sdk
COPY modules/__init__.py modules/discovery.py ./modules/
COPY modules/api ./modules/api
COPY modules/rag ./modules/rag
COPY config.yaml ./

# Install only this module's dependencies
RUN pip install --no-cache-dir -r modules/rag/requirements.txt

RUN mkdir -p data

CMD ["python", "-m", "modules.rag.server", "--host", "0.0.0.0", "--port", "8002"]
