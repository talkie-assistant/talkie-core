"""
Calibration dialog: guided questions and voice recording to set sensitivity, pauses, and TTS voice.
Includes optional "record yourself" step: user says a phrase, we analyze level (and optionally STT/LLM) to suggest settings.
Persists to SettingsRepo and applies sensitivity immediately; restart required for chunk duration and min_transcription_length.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from app.pipeline import Pipeline
    from persistence.settings_repo import SettingsRepo

logger = logging.getLogger(__name__)

CALIBRATION_RECORD_SEC = 10
CALIBRATION_PHRASE = "I want some water."

CALIBRATION_VERSION = 1
# Keys removed by "Clear calibration" (tts_voice is left so Settings choice is preserved)
CALIBRATION_KEYS_TO_DELETE = [
    "calibration_sensitivity",
    "calibration_chunk_duration_sec",
    "calibration_min_transcription_length",
    "calibration_version",
    "calibration_at",
]

# Volume options: (label, sensitivity value)
VOLUME_CHOICES = [
    ("Loud", 1.0),
    ("Normal", 1.5),
    ("Quiet", 2.5),
    ("Very quiet", 3.5),
]

# Pause options: (label, chunk_duration_sec)
PAUSE_CHOICES = [
    ("No", 5.5),
    ("A little", 7.0),
    ("Yes, I pause often", 9.0),
]

SENSITIVITY_MIN = 0.5
SENSITIVITY_MAX = 10.0
CHUNK_DURATION_MIN = 4.0
CHUNK_DURATION_MAX = 15.0
MIN_TRANSCRIPTION_LENGTH_SKIP = 3
MIN_TRANSCRIPTION_LENGTH_NOSKIP = 0
VOICE_PREVIEW_PHRASE = "Talkie is ready."


def _run_voice_calibration(
    config: dict,
    record_sec: int,
    expected_phrase: str,
    on_progress: Callable[[int], None],
    on_done: Callable[[dict], None],
) -> None:
    """Run in a background thread: record, then analyze; call on_done(result) with suggested settings."""
    try:
        from app.pipeline import _make_stt
        from calibration.analyzer import analyze_recording
        from calibration.recorder import record_seconds
        from llm.client import OllamaClient

        audio_cfg = config.get("audio", {})
        sample_rate = int(audio_cfg.get("sample_rate", 16000))
        device_id = audio_cfg.get("device_id")

        def progress_cb(sec_left: int) -> None:
            on_progress(sec_left)

        audio_bytes, rms_list = record_seconds(
            duration_sec=float(record_sec),
            sample_rate=sample_rate,
            device_id=device_id,
            on_progress=progress_cb,
        )
        on_progress(-1)  # "Analyzing..."
        stt_engine = _make_stt(config)
        ollama_cfg = config.get("ollama", {})
        llm_client = OllamaClient(
            base_url=ollama_cfg.get("base_url", "http://localhost:11434"),
            model_name=ollama_cfg.get("model_name", "mistral"),
        )
        result = analyze_recording(
            audio_bytes,
            sample_rate,
            rms_list,
            expected_phrase=expected_phrase,
            stt_engine=stt_engine,
            llm_client=llm_client,
        )
        on_done(result)
    except Exception as e:
        logger.exception("Voice calibration failed: %s", e)
        on_done({"sensitivity": 2.5, "chunk_duration_sec": 7.0, "min_transcription_length": 3, "error": str(e)})


class CalibrationDialog(QDialog):
    """Modal dialog: calibration questions and optional voice recording; then persist and apply sensitivity."""

    recording_progress = pyqtSignal(int)   # seconds left, or -1 for analyzing
    analysis_done = pyqtSignal(dict)

    def __init__(
        self,
        settings_repo: SettingsRepo,
        pipeline: Pipeline,
        config: dict,
        on_sensitivity_applied: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._repo = settings_repo
        self._pipeline = pipeline
        self._config = config
        self._on_sensitivity_applied = on_sensitivity_applied or (lambda: None)

        self.setWindowTitle("Talkie – Calibrate voice settings")
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(24, 24, 24, 24)

        voice_cal_group = QGroupBox("Calibrate with your voice")
        voice_cal_layout = QVBoxLayout(voice_cal_group)
        voice_cal_layout.addWidget(
            QLabel("Say the phrase below in your normal voice, then click Record. We'll analyze your volume and speech to suggest settings.")
        )
        voice_cal_layout.addWidget(QLabel(f'"{CALIBRATION_PHRASE}"'))
        self._record_btn = QPushButton("Record")
        self._record_btn.setToolTip(f"Record for {CALIBRATION_RECORD_SEC} seconds; then we analyze and suggest settings.")
        self._record_btn.clicked.connect(self._on_record_clicked)
        voice_cal_layout.addWidget(self._record_btn)
        self._record_status = QLabel("")
        self._record_status.setStyleSheet("color: #888;")
        voice_cal_layout.addWidget(self._record_status)
        layout.addWidget(voice_cal_group)

        layout.addWidget(QLabel("How would you describe your typical speaking volume?"))
        self._volume_combo = QComboBox()
        for label, _ in VOLUME_CHOICES:
            self._volume_combo.addItem(label)
        layout.addWidget(self._volume_combo)

        layout.addWidget(QLabel("Do you need extra time between words?"))
        self._pause_combo = QComboBox()
        for label, _ in PAUSE_CHOICES:
            self._pause_combo.addItem(label)
        layout.addWidget(self._pause_combo)

        voice_row = QHBoxLayout()
        voice_row.addWidget(QLabel("TTS voice (macOS):"))
        self._voice_combo = QComboBox()
        from tts.say_engine import get_available_voices
        voices = get_available_voices()
        if voices:
            self._voice_combo.addItems(voices)
        else:
            self._voice_combo.addItem("Daniel")
        voice_row.addWidget(self._voice_combo, stretch=1)
        self._preview_btn = QPushButton("Play voice sample")
        self._preview_btn.setToolTip("Listen to the selected voice")
        self._preview_btn.clicked.connect(self._on_preview_voice)
        voice_row.addWidget(self._preview_btn)
        layout.addLayout(voice_row)

        self._skip_short_cb = QCheckBox("Skip very short transcriptions?")
        self._skip_short_cb.setToolTip("Yes = ignore phrases shorter than a few characters to reduce noise (recommended).")
        layout.addWidget(self._skip_short_cb)

        self._last_calibrated_label = QLabel("")
        self._last_calibrated_label.setStyleSheet("color: #888; font-size: 0.9em;")
        layout.addWidget(self._last_calibrated_label)

        self._load_current()

        clear_btn = QPushButton("Use config defaults")
        clear_btn.setToolTip("Clear calibration and revert to config.yaml values (restart to apply pause length).")
        clear_btn.clicked.connect(self._on_clear_calibration)
        layout.addWidget(clear_btn)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.recording_progress.connect(self._on_recording_progress)
        self.analysis_done.connect(self._on_analysis_done)

    def _load_current(self) -> None:
        """Pre-fill from saved calibration or config defaults."""
        try:
            sens_s = self._repo.get("calibration_sensitivity")
            if sens_s is not None and sens_s.strip():
                try:
                    sens = float(sens_s)
                    best = 0
                    best_diff = abs(VOLUME_CHOICES[0][1] - sens)
                    for i, (_, val) in enumerate(VOLUME_CHOICES):
                        d = abs(val - sens)
                        if d < best_diff:
                            best_diff, best = d, i
                    self._volume_combo.setCurrentIndex(best)
                except (TypeError, ValueError):
                    pass
            else:
                cfg_sens = float(self._config.get("audio", {}).get("sensitivity", 2.5))
                best = 0
                best_diff = abs(VOLUME_CHOICES[0][1] - cfg_sens)
                for i, (_, val) in enumerate(VOLUME_CHOICES):
                    d = abs(val - cfg_sens)
                    if d < best_diff:
                        best_diff, best = d, i
                self._volume_combo.setCurrentIndex(best)

            chunk_s = self._repo.get("calibration_chunk_duration_sec")
            if chunk_s is not None and chunk_s.strip():
                try:
                    chunk = float(chunk_s)
                    best = 0
                    best_diff = abs(PAUSE_CHOICES[0][1] - chunk)
                    for i, (_, val) in enumerate(PAUSE_CHOICES):
                        d = abs(val - chunk)
                        if d < best_diff:
                            best_diff, best = d, i
                    self._pause_combo.setCurrentIndex(best)
                except (TypeError, ValueError):
                    pass
            else:
                cfg_chunk = float(self._config.get("audio", {}).get("chunk_duration_sec", 7.0))
                best = 0
                best_diff = abs(PAUSE_CHOICES[0][1] - cfg_chunk)
                for i, (_, val) in enumerate(PAUSE_CHOICES):
                    d = abs(val - cfg_chunk)
                    if d < best_diff:
                        best_diff, best = d, i
                self._pause_combo.setCurrentIndex(best)

            voice = self._repo.get("tts_voice") or self._config.get("tts", {}).get("voice", "Daniel")
            idx = self._voice_combo.findText(voice)
            if idx >= 0:
                self._voice_combo.setCurrentIndex(idx)
            elif self._voice_combo.count():
                self._voice_combo.setCurrentIndex(0)

            min_len_s = self._repo.get("calibration_min_transcription_length")
            if min_len_s is not None and min_len_s.strip():
                try:
                    n = int(min_len_s)
                    self._skip_short_cb.setChecked(n >= MIN_TRANSCRIPTION_LENGTH_SKIP)
                except (TypeError, ValueError):
                    pass
            else:
                cfg_min = self._config.get("llm", {}).get("min_transcription_length", 3)
                self._skip_short_cb.setChecked(int(cfg_min) >= MIN_TRANSCRIPTION_LENGTH_SKIP if cfg_min is not None else True)

            at_s = self._repo.get("calibration_at")
            if at_s and at_s.strip():
                try:
                    # Show short date for "Last calibrated: ..."
                    dt = datetime.fromisoformat(at_s.replace("Z", "+00:00"))
                    self._last_calibrated_label.setText("Last calibrated: " + dt.strftime("%Y-%m-%d %H:%M"))
                except (TypeError, ValueError):
                    self._last_calibrated_label.setText("")
            else:
                self._last_calibrated_label.setText("")
        except Exception as e:
            logger.debug("Load current calibration: %s", e)

    def _on_record_clicked(self) -> None:
        """Start voice calibration in a background thread."""
        self._record_btn.setEnabled(False)
        self._record_status.setText("Recording...")
        config = self._config
        record_sec = CALIBRATION_RECORD_SEC
        phrase = CALIBRATION_PHRASE

        def on_progress(sec_left: int) -> None:
            self.recording_progress.emit(sec_left)

        def on_done(result: dict) -> None:
            self.analysis_done.emit(result)

        thread = threading.Thread(
            target=_run_voice_calibration,
            args=(config, record_sec, phrase, on_progress, on_done),
            daemon=True,
        )
        thread.start()

    def _on_recording_progress(self, seconds_left: int) -> None:
        """Update status: Recording... N s or Analyzing..."""
        if seconds_left < 0:
            self._record_status.setText("Analyzing...")
            return
        self._record_status.setText(f"Recording... {seconds_left} s")

    def _on_analysis_done(self, result: dict) -> None:
        """Apply suggested settings to the form and re-enable Record."""
        self._record_btn.setEnabled(True)
        err = result.get("error")
        if err:
            self._record_status.setText("Recording failed. Use the options below.")
            QMessageBox.warning(
                self,
                "Talkie",
                f"Voice analysis failed: {err}. You can still set options manually below.",
            )
            return
        sens = result.get("sensitivity", 2.5)
        chunk = result.get("chunk_duration_sec", 7.0)
        min_len = result.get("min_transcription_length", 3)
        sens = max(SENSITIVITY_MIN, min(SENSITIVITY_MAX, sens))
        chunk = max(CHUNK_DURATION_MIN, min(CHUNK_DURATION_MAX, chunk))
        transcript = result.get("transcript", "")
        # Map to volume combo
        best_vol = 0
        best_diff = abs(VOLUME_CHOICES[0][1] - sens)
        for i, (_, val) in enumerate(VOLUME_CHOICES):
            d = abs(val - sens)
            if d < best_diff:
                best_diff, best_vol = d, i
        self._volume_combo.setCurrentIndex(best_vol)
        best_pause = 0
        best_diff = abs(PAUSE_CHOICES[0][1] - chunk)
        for i, (_, val) in enumerate(PAUSE_CHOICES):
            d = abs(val - chunk)
            if d < best_diff:
                best_diff, best_pause = d, i
        self._pause_combo.setCurrentIndex(best_pause)
        self._skip_short_cb.setChecked(min_len >= MIN_TRANSCRIPTION_LENGTH_SKIP)
        status = "Suggested settings updated from your recording."
        if transcript:
            status += f' Heard: "{transcript[:60]}{"..." if len(transcript) > 60 else ""}"'
        self._record_status.setText(status)

    def _on_preview_voice(self) -> None:
        """Play a short phrase with the currently selected voice."""
        voice = self._voice_combo.currentText() if self._voice_combo.count() else "Daniel"
        try:
            from tts.say_engine import SayEngine
            engine = SayEngine(voice=voice)
            engine.speak(VOICE_PREVIEW_PHRASE)
        except Exception as e:
            logger.debug("Voice preview failed: %s", e)
            QMessageBox.warning(self, "Talkie", "Could not play voice sample.")

    def _on_clear_calibration(self) -> None:
        """Clear calibration keys and reapply config defaults in UI; optionally sync sensitivity live."""
        try:
            self._repo.delete_many(CALIBRATION_KEYS_TO_DELETE)
        except Exception as e:
            logger.exception("Failed to clear calibration: %s", e)
            QMessageBox.warning(self, "Talkie", "Could not clear calibration.")
            return
        cfg_audio = self._config.get("audio", {})
        cfg_sens = float(cfg_audio.get("sensitivity", 2.5))
        cfg_sens = max(SENSITIVITY_MIN, min(SENSITIVITY_MAX, cfg_sens))
        self._pipeline.set_sensitivity(cfg_sens)
        self._on_sensitivity_applied()
        self._load_current()
        QMessageBox.information(
            self,
            "Talkie",
            "Calibration cleared. Sensitivity updated from config. Restart Talkie to apply config defaults for pause length and other settings.",
        )

    def _save_and_accept(self) -> None:
        vol_idx = self._volume_combo.currentIndex()
        pause_idx = self._pause_combo.currentIndex()
        sens = VOLUME_CHOICES[vol_idx][1] if 0 <= vol_idx < len(VOLUME_CHOICES) else 2.5
        chunk = PAUSE_CHOICES[pause_idx][1] if 0 <= pause_idx < len(PAUSE_CHOICES) else 7.0
        sens = max(SENSITIVITY_MIN, min(SENSITIVITY_MAX, sens))
        chunk = max(CHUNK_DURATION_MIN, min(CHUNK_DURATION_MAX, chunk))
        voice = self._voice_combo.currentText() if self._voice_combo.count() else "Daniel"
        min_len = MIN_TRANSCRIPTION_LENGTH_SKIP if self._skip_short_cb.isChecked() else MIN_TRANSCRIPTION_LENGTH_NOSKIP

        pairs = [
            ("calibration_sensitivity", str(sens)),
            ("calibration_chunk_duration_sec", str(chunk)),
            ("calibration_min_transcription_length", str(min_len)),
            ("calibration_version", str(CALIBRATION_VERSION)),
            ("calibration_at", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")),
            ("tts_voice", voice),
        ]
        try:
            self._repo.set_many(pairs)
        except Exception as e:
            logger.exception("Failed to save calibration: %s", e)
            QMessageBox.warning(
                self,
                "Talkie",
                "Could not save calibration.",
            )
            return

        self._pipeline.set_sensitivity(sens)
        self._on_sensitivity_applied()
        self.accept()
        QMessageBox.information(
            self,
            "Talkie",
            "Sensitivity and voice are updated. To apply pause length (and minimum phrase length), restart Talkie.",
        )