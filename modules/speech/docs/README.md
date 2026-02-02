# Speech module

Audio capture, speech-to-text (STT), text-to-speech (TTS), speaker filter, and voice calibration. Provides the core listening and speaking pipeline for Talkie.

## Features

- **Audio capture**: Microphone input (sounddevice or WebSocket in web UI), configurable sample rate and chunk duration.
- **STT**: Whisper (recommended for accuracy) or Vosk (faster, lower latency). Configurable model path and device.
- **TTS**: macOS built-in `say` or noop. Voice selection and speech rate.
- **Speaker filter**: Noop or voice-profile (accept only enrolled voice).
- **Calibration**: Voice enrollment, sensitivity, chunk duration, min transcription length.

## Config

Module config is merged from `config.yaml` in this directory with the main app config. Keys:

- **audio**: `device_id`, `sample_rate`, `chunk_duration_sec`, `sensitivity`, `auto_sensitivity` options.
- **stt**: `engine` (whisper | vosk), `whisper.model_path`, `whisper.device`, `vosk.model_path`.
- **tts**: `enabled`, `engine` (say | noop), `voice`, `speak_timeout_sec`, `wait_until_done_before_listen`.

Override any key in the root `config.yaml` or `config.user.yaml`.

## Quick reference (H key)

- **Main mode**: Press **H** or **h** to show general quick reference.
- **Calibration**: Use the Calibration panel for voice enrollment and sensitivity/chunk/min-length settings.
