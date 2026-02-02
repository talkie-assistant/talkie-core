# Speech module container: STT (Vosk/Whisper), TTS, speaker filter.
# Hosts only speech dependencies inside this image.
FROM python:3.11-slim

# System deps for audio (sounddevice, ffmpeg for whisper)
RUN apt-get update && apt-get install -y \
    build-essential \
    libasound2-dev \
    libportaudio2 \
    libportaudiocpp0 \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Shared code and config (required for python -m modules.speech.server)
COPY sdk ./sdk
COPY modules/__init__.py modules/discovery.py ./modules/
COPY modules/api ./modules/api
COPY modules/speech ./modules/speech
COPY config.yaml ./

# Install only this module's dependencies
RUN pip install --no-cache-dir -r modules/speech/requirements.txt

RUN mkdir -p data

CMD ["python", "-m", "modules.speech.server", "--host", "0.0.0.0", "--port", "8001"]
