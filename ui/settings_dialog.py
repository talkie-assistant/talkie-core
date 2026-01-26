"""
Settings dialog: user context (optional) for profile tailoring.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from persistence.settings_repo import SettingsRepo

logger = logging.getLogger(__name__)

USER_CONTEXT_PLACEHOLDER = (
    "e.g. PhD, ex-tenured professor at Brown. Often discusses teaching, research, "
    "and university life. Helps tailor vocabulary and topic."
)


class SettingsDialog(QDialog):
    """Modal dialog to edit and save user context (stored in SettingsRepo)."""

    def __init__(
        self,
        settings_repo: SettingsRepo,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._repo = settings_repo
        self.setWindowTitle("Talkie – Settings")
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(24, 24, 24, 24)

        layout.addWidget(QLabel("TTS voice (macOS):"))
        self._voice_combo = QComboBox()
        self._voice_combo.setMinimumHeight(52)
        self._voice_combo.setToolTip("Takes effect after you restart Talkie.")
        from tts.say_engine import get_available_voices
        voices = get_available_voices()
        if voices:
            self._voice_combo.addItems(voices)
        else:
            self._voice_combo.addItem("Daniel")
        layout.addWidget(self._voice_combo)

        layout.addWidget(
            QLabel("User context (optional) – describe who is using Talkie so replies match their style and topics:")
        )
        self._edit = QPlainTextEdit()
        self._edit.setPlaceholderText(USER_CONTEXT_PLACEHOLDER)
        self._edit.setMaximumHeight(160)
        layout.addWidget(self._edit)
        try:
            value = self._repo.get("user_context")
            if value:
                self._edit.setPlainText(value)
            voice = self._repo.get("tts_voice") or "Daniel"
            idx = self._voice_combo.findText(voice)
            if idx >= 0:
                self._voice_combo.setCurrentIndex(idx)
            elif self._voice_combo.count():
                self._voice_combo.setCurrentIndex(0)
        except Exception as e:
            logger.exception("Failed to load settings: %s", e)
            QMessageBox.warning(
                self,
                "Talkie",
                "Could not load settings.",
            )
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save_and_accept(self) -> None:
        try:
            self._repo.set("user_context", self._edit.toPlainText().strip())
            if self._voice_combo.count():
                self._repo.set("tts_voice", self._voice_combo.currentText())
            self.accept()
        except Exception as e:
            logger.exception("Failed to save user context: %s", e)
            QMessageBox.warning(
                self,
                "Talkie",
                "Could not save settings.",
            )
