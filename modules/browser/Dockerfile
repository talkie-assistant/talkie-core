# Browser module container: fetch, parse, search (DuckDuckGo), markdown.
# Hosts only browser dependencies inside this image.
FROM python:3.11-slim

WORKDIR /app

# Shared code and config (required for python -m modules.browser.server)
COPY sdk ./sdk
COPY modules/__init__.py modules/discovery.py ./modules/
COPY modules/api ./modules/api
COPY modules/browser ./modules/browser
COPY config.yaml ./

# Install only this module's dependencies
RUN pip install --no-cache-dir -r modules/browser/requirements.txt

RUN mkdir -p data

CMD ["python", "-m", "modules.browser.server", "--host", "0.0.0.0", "--port", "8003"]
