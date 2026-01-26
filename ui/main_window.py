"""
Main window: fullscreen, high-contrast, toggle button, status, response area, history.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QDoubleSpinBox,
    QTextEdit,
)

if TYPE_CHECKING:
    from app.pipeline import Pipeline
    from persistence.history_repo import HistoryRepo
    from persistence.settings_repo import SettingsRepo
    from persistence.training_repo import TrainingRepo

logger = logging.getLogger(__name__)

DEBUG_LOG_MAX_LINES = 500


class MainWindow(QMainWindow):
    """
    Fullscreen (or maximized) high-contrast layout:
    - One large toggle (Start/Stop listening)
    - Live status (Listening / Transcribing / Responding / Error)
    - Response area (large read-only text)
    - History button -> HistoryView
    - Debug log (D/d toggles), shows Ollama and pipeline messages
    """

    status_changed = pyqtSignal(str)
    response_ready = pyqtSignal(str, int)
    error_occurred = pyqtSignal(str)
    debug_message = pyqtSignal(str)
    volume_ready = pyqtSignal(float)
    sensitivity_adjusted = pyqtSignal(float)

    def __init__(
        self,
        config: dict,
        pipeline: Pipeline,
        history_repo: HistoryRepo,
        settings_repo: SettingsRepo | None = None,
        training_repo: TrainingRepo | None = None,
        rag_service: object = None,
        debug_log_path: Path | None = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._pipeline = pipeline
        self._history_repo = history_repo
        self._settings_repo = settings_repo
        self._training_repo = training_repo
        self._rag_service = rag_service
        self._listening = False
        self._debug_log_file = None
        self._debug_log_lock = threading.Lock()
        if debug_log_path is not None:
            try:
                self._debug_log_file = open(debug_log_path, "a", encoding="utf-8")
                logger.info("Debug log writing to %s", debug_log_path)
            except OSError as e:
                logger.warning("Could not open debug log file %s: %s", debug_log_path, e)

        ui_config = config.get("ui", {})

        self.setWindowTitle("Talkie")
        if ui_config.get("fullscreen", True):
            self.showFullScreen()
        else:
            self.showMaximized()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        speak_size = 56
        self._speak_light = QFrame()
        self._speak_light.setObjectName("speakLight")
        self._speak_light.setFixedSize(speak_size, speak_size)
        self._speak_light.setToolTip("Green = ready, speak now; red = wait (starting or processing)")
        status_row.addWidget(self._speak_light, alignment=Qt.AlignmentFlag.AlignCenter)
        self._status_label = QLabel("Stopped")
        self._status_label.setObjectName("statusLabel")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_row.addWidget(self._status_label, stretch=1)
        layout.addLayout(status_row)

        from ui.volume_widget import VolumeWidget, AudioWaveformWidget
        self._volume_widget = VolumeWidget(self)
        layout.addWidget(self._volume_widget)

        self._waveform = AudioWaveformWidget(self)
        layout.addWidget(self._waveform)

        response_label = QLabel("Response (speak again to abort and retry):")
        response_label.setObjectName("sensitivityLabel")
        layout.addWidget(response_label)
        self._response_edit = QTextEdit()
        self._response_edit.setObjectName("responseDisplay")
        self._response_edit.setReadOnly(True)
        self._response_edit.setPlaceholderText("Your sentence will appear here in large text after you speak.")
        self._response_edit.setMinimumHeight(80)
        self._response_edit.setMaximumHeight(16777215)
        response_font_size = int(ui_config.get("response_font_size", 48))
        from PyQt6.QtGui import QFont
        font = self._response_edit.font()
        font.setPointSize(response_font_size)
        self._response_edit.setFont(font)
        layout.addWidget(self._response_edit, stretch=1)

        sensitivity_row = QHBoxLayout()
        sensitivity_row.setSpacing(16)
        sensitivity_label = QLabel("Sensitivity (mic gain):")
        sensitivity_label.setObjectName("sensitivityLabel")
        self._sensitivity_spin = QDoubleSpinBox()
        self._sensitivity_spin.setRange(0.5, 10.0)
        self._sensitivity_spin.setSingleStep(0.1)
        self._sensitivity_spin.setDecimals(1)
        try:
            initial = self._pipeline.get_sensitivity()
        except Exception:
            initial = float(config.get("audio", {}).get("sensitivity", 2.5))
        self._sensitivity_spin.setValue(min(10.0, max(0.5, initial)))
        self._sensitivity_spin.setToolTip("Higher = more sensitive for quiet speech (1.0 = normal, 2–4 = boosted)")
        self._sensitivity_spin.valueChanged.connect(self._on_sensitivity_changed)
        sensitivity_row.addWidget(sensitivity_label)
        sensitivity_row.addWidget(self._sensitivity_spin)
        sensitivity_row.addStretch()
        layout.addLayout(sensitivity_row)

        toggle_row = QHBoxLayout()
        self._toggle_btn = QPushButton("Start listening")
        self._toggle_btn.setObjectName("toggleButton")
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.clicked.connect(self._on_toggle_clicked)
        toggle_row.addStretch()
        toggle_row.addWidget(self._toggle_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        self._ask_docs_btn = QPushButton("?")
        self._ask_docs_btn.setToolTip("Ask a question about your documents by voice")
        self._ask_docs_btn.setObjectName("cornerButton")
        self._ask_docs_btn.setCheckable(True)
        self._ask_docs_btn.setFixedSize(56, 56)
        self._ask_docs_btn.clicked.connect(self._on_ask_documents_clicked)
        toggle_row.addWidget(self._ask_docs_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        toggle_row.addStretch()
        layout.addLayout(toggle_row)

        # Large text buttons for motor accessibility: clear labels, generous spacing
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.setSpacing(16)
        hist_btn = QPushButton("History")
        hist_btn.setToolTip("View conversation history")
        hist_btn.setObjectName("cornerButton")
        hist_btn.clicked.connect(self._open_history)
        btn_row.addWidget(hist_btn)
        docs_btn = QPushButton("Documents")
        docs_btn.setToolTip("Upload and vectorize documents for RAG")
        docs_btn.setObjectName("cornerButton")
        docs_btn.clicked.connect(self._open_documents)
        btn_row.addWidget(docs_btn)
        if self._training_repo is not None:
            train_btn = QPushButton("Train")
            train_btn.setToolTip("Record facts for the LLM to remember")
            train_btn.setObjectName("cornerButton")
            train_btn.clicked.connect(self._open_training)
            btn_row.addWidget(train_btn)
        if self._settings_repo is not None:
            calibrate_btn = QPushButton("Calibrate")
            calibrate_btn.setToolTip("Calibrate voice and timing settings")
            calibrate_btn.setObjectName("cornerButton")
            calibrate_btn.clicked.connect(self._open_calibration)
            btn_row.addWidget(calibrate_btn)
        if self._settings_repo is not None:
            settings_btn = QPushButton("Settings")
            settings_btn.setToolTip("TTS voice and user context")
            settings_btn.setObjectName("cornerButton")
            settings_btn.clicked.connect(self._open_settings)
            btn_row.addWidget(settings_btn)
        layout.addLayout(btn_row)

        self._debug_frame = QFrame()
        self._debug_frame.setFrameShape(QFrame.Shape.StyledPanel)
        debug_layout = QVBoxLayout(self._debug_frame)
        debug_layout.addWidget(QLabel("Debug log (D to toggle)"))
        self._debug_log = QPlainTextEdit()
        self._debug_log.setReadOnly(True)
        self._debug_log.setMaximumBlockCount(DEBUG_LOG_MAX_LINES)
        self._debug_log.setMinimumHeight(100)
        self._debug_log.setMaximumHeight(280)
        debug_layout.addWidget(self._debug_log)
        self._debug_frame.setVisible(False)
        layout.addWidget(self._debug_frame)

        shortcut_d = QShortcut(QKeySequence(Qt.Key.Key_D), self)
        shortcut_d.activated.connect(self._toggle_debug)
        shortcut_q = QShortcut(QKeySequence(Qt.Key.Key_Q), self)
        shortcut_q.activated.connect(self.close)

        # Thread-safe: pipeline calls these from worker; we emit signals so slots run on main thread
        self.status_changed.connect(self._on_status)
        self.response_ready.connect(self._on_response)
        self.error_occurred.connect(self._on_error)
        self.debug_message.connect(self._on_debug_message)
        self.volume_ready.connect(self._on_volume)
        self.sensitivity_adjusted.connect(self._on_sensitivity_adjusted)

        self._on_status("Stopped")
        self._append_debug_direct("App ready. Click Start listening; wait until the light turns green, then speak. First result after one chunk (~4 sec). D = debug log, Q = quit.")
        QTimer.singleShot(400, self._speak_ready)

    def _speak_ready(self) -> None:
        """Speak a short ready message once the app is shown (TTS)."""
        self._pipeline.speak("Talkie is ready. Click Start listening, then wait for the green light before you speak.")

    def _write_debug_to_file(self, line: str) -> None:
        """Append one line to the persistent debug log file (if configured). Thread-safe."""
        if self._debug_log_file is None:
            return
        with self._debug_log_lock:
            try:
                self._debug_log_file.write(line + "\n")
                self._debug_log_file.flush()
            except OSError as e:
                logger.debug("Debug log write failed: %s", e)

    def _append_debug_direct(self, message: str) -> None:
        """Append a debug line from the main thread (no signal)."""
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{ts}] {message}"
        self._debug_log.appendPlainText(line)
        self._write_debug_to_file(line)

    def _toggle_debug(self) -> None:
        self._debug_frame.setVisible(not self._debug_frame.isVisible())

    def on_pipeline_status(self, status: str) -> None:
        """Called from pipeline (any thread); emit so UI updates on main thread."""
        self.status_changed.emit(status)

    def on_pipeline_response(self, text: str, interaction_id: int) -> None:
        """Called from pipeline (any thread)."""
        self.response_ready.emit(text, interaction_id)

    def on_pipeline_error(self, message: str) -> None:
        """Called from pipeline (any thread)."""
        self.error_occurred.emit(message)

    def append_debug(self, message: str) -> None:
        """Called from pipeline (any thread); emits so append runs on main thread."""
        self.debug_message.emit(message)

    def _on_debug_message(self, message: str) -> None:
        self._debug_log.appendPlainText(message)
        self._write_debug_to_file(message)

    def _on_status(self, status: str) -> None:
        self._status_label.setText(status)
        if status == "Listening...":
            self._speak_light.setStyleSheet(
                "QFrame#speakLight { background-color: #0a0; border-radius: 28px; border: 3px solid #0f0; }"
            )
        else:
            self._speak_light.setStyleSheet(
                "QFrame#speakLight { background-color: #a00; border-radius: 28px; border: 3px solid #f44; }"
            )
        # User started talking (abort): clear response so they see it disappear, then new response will show.
        if status == "Transcribing...":
            self._response_edit.clear()

    def _on_response(self, text: str, _interaction_id: int) -> None:
        self._response_edit.setPlainText(text)

    def _on_error(self, message: str) -> None:
        self._status_label.setText(message)
        QMessageBox.warning(self, "Talkie", message)

    def on_pipeline_volume(self, level: float) -> None:
        """Called from pipeline (any thread); emit so UI updates on main thread."""
        self.volume_ready.emit(level)

    def on_pipeline_sensitivity_adjusted(self, value: float) -> None:
        """Called from pipeline when auto-sensitivity raises gain (any thread). Update spinbox on main thread."""
        self.sensitivity_adjusted.emit(value)

    def _on_volume(self, level: float) -> None:
        self._volume_widget.set_level(level)
        self._waveform.set_level(level)

    def _refresh_audio_controls_from_pipeline(self) -> None:
        """Sync UI controls that reflect pipeline/config (e.g. sensitivity) from the pipeline."""
        try:
            sens = self._pipeline.get_sensitivity()
            self._sensitivity_spin.blockSignals(True)
            self._sensitivity_spin.setValue(min(10.0, max(0.5, sens)))
            self._sensitivity_spin.blockSignals(False)
        except Exception as e:
            logger.debug("Refresh audio controls from pipeline: %s", e)

    def _on_sensitivity_changed(self, value: float) -> None:
        self._pipeline.set_sensitivity(value)

    def _on_sensitivity_adjusted(self, _value: float) -> None:
        """Pipeline (e.g. auto-sensitivity) changed sensitivity; refresh UI from pipeline."""
        self._refresh_audio_controls_from_pipeline()

    def _open_settings(self) -> None:
        from ui.settings_dialog import SettingsDialog
        if self._settings_repo is None:
            return
        dialog = SettingsDialog(self._settings_repo, self)
        dialog.exec()

    def _open_calibration(self) -> None:
        if self._settings_repo is None:
            return
        from ui.calibration_dialog import CalibrationDialog

        def on_applied() -> None:
            self._refresh_audio_controls_from_pipeline()

        dialog = CalibrationDialog(
            self._settings_repo,
            self._pipeline,
            self._config,
            on_sensitivity_applied=on_applied,
            parent=self,
        )
        dialog.exec()

    def _on_toggle_clicked(self) -> None:
        checked = self._toggle_btn.isChecked()
        self._listening = checked
        if checked:
            self._toggle_btn.setText("Stop listening")
            self._append_debug_direct("Start listening clicked – pipeline starting...")
            self._pipeline.start()
            self._refresh_audio_controls_from_pipeline()
        else:
            self._toggle_btn.setText("Start listening")
            self._append_debug_direct("Stop listening clicked.")
            self._pipeline.stop()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Stop the pipeline and wait for the worker thread before exiting.
        Prevents SIGSEGV when the app exits while the audio thread is in sounddevice/CFFI.
        """
        if self._listening:
            self._toggle_btn.setChecked(False)
            self._listening = False
            self._toggle_btn.setText("Start listening")
            self._pipeline.stop()
        if self._debug_log_file is not None:
            with self._debug_log_lock:
                try:
                    self._debug_log_file.close()
                except OSError:
                    pass
            self._debug_log_file = None
        event.accept()

    def _open_history(self) -> None:
        from ui.history_view import HistoryView

        history_list_limit = int(
            self._config.get("profile", {}).get("history_list_limit", 100)
        )
        dialog = HistoryView(self._history_repo, history_list_limit=history_list_limit, parent=self)
        dialog.exec()

    def _open_documents(self) -> None:
        from ui.documents_dialog import DocumentsDialog

        dialog = DocumentsDialog(rag_service=self._rag_service, parent=self)
        dialog.exec()

    def _on_ask_documents_clicked(self) -> None:
        checked = self._ask_docs_btn.isChecked()
        self._pipeline.set_document_qa_mode(checked)
        if checked:
            self._status_label.setText("Ask documents: on. Speak your question.")
        else:
            self._status_label.setText("Stopped" if not self._listening else "Listening...")

    def _open_training(self) -> None:
        if self._training_repo is None:
            return
        from ui.training_dialog import TrainingDialog

        dialog = TrainingDialog(self._training_repo, self._pipeline, parent=self)
        dialog.exec()
