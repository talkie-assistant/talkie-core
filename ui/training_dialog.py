"""
Training dialog: record sentences as context facts (e.g. "Star is my dog") for the LLM.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from app.pipeline import Pipeline
    from persistence.training_repo import TrainingRepo

logger = logging.getLogger(__name__)


class TrainingDialog(QDialog):
    """
    Lists training facts and lets the user record new ones via the pipeline.
    User must have "Start listening" active on the main window; then click Record, say a sentence, and it is saved.
    """

    fact_added = pyqtSignal()

    def __init__(
        self,
        training_repo: TrainingRepo,
        pipeline: Pipeline,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._training_repo = training_repo
        self._pipeline = pipeline
        self._recording = False

        self.setWindowTitle("Talkie – Train")
        self.setMinimumSize(560, 480)
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(24, 24, 24, 24)

        layout.addWidget(
            QLabel(
                "Record facts the LLM should remember (e.g. \"Star is my dog\", \"Susan is my wife\"). "
                "Start listening on the main window, then click Record and speak."
            )
        )

        self._record_btn = QPushButton("Record training sentence")
        self._record_btn.setObjectName("toggleButton")
        self._record_btn.setCheckable(True)
        self._record_btn.clicked.connect(self._on_record_clicked)
        layout.addWidget(self._record_btn)

        self._status_label = QLabel("Recording off. Click Record, then speak one sentence.")
        layout.addWidget(self._status_label)

        layout.addWidget(QLabel("Saved facts:"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(200)
        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(self._list_widget)
        layout.addWidget(scroll)

        self.fact_added.connect(self._refresh_list)
        self._refresh_list()

    def _on_training_transcription(self, text: str) -> None:
        """Called from pipeline thread when in training mode and user spoke."""
        try:
            self._training_repo.add(text)
            self.fact_added.emit()
        except Exception as e:
            logger.exception("Failed to add training fact: %s", e)
            self.fact_added.emit()

    def _on_record_clicked(self) -> None:
        checked = self._record_btn.isChecked()
        self._recording = checked
        if checked:
            self._pipeline.set_on_training_transcription(self._on_training_transcription)
            self._pipeline.set_training_mode(True)
            self._record_btn.setText("Stop recording")
            self._status_label.setText("Recording. Say a sentence to remember (e.g. \"Star is my dog\").")
        else:
            self._pipeline.set_training_mode(False)
            self._pipeline.set_on_training_transcription(None)
            self._record_btn.setText("Record training sentence")
            self._status_label.setText("Recording off. Click Record, then speak one sentence.")

    def _refresh_list(self) -> None:
        """Rebuild the list of facts (call on main thread)."""
        while self._list_layout.count():
            child = self._list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        try:
            rows = self._training_repo.list_all()
        except Exception as e:
            logger.exception("Failed to list training facts: %s", e)
            return
        for fact_id, text, _created_at in rows:
            row = QHBoxLayout()
            row.addWidget(QLabel(text or "(empty)"))
            del_btn = QPushButton("Delete")
            del_btn.clicked.connect(lambda _checked=False, fid=fact_id: self._delete_fact(fid))
            row.addWidget(del_btn)
            row.addStretch()
            row_widget = QWidget()
            row_widget.setLayout(row)
            self._list_layout.addWidget(row_widget)
        if not rows:
            self._list_layout.addWidget(QLabel("No facts yet. Record a sentence above."))

    def _delete_fact(self, fact_id: int) -> None:
        try:
            self._training_repo.delete(fact_id)
            self._refresh_list()
        except Exception as e:
            logger.exception("Failed to delete training fact: %s", e)
            QMessageBox.warning(self, "Talkie", "Could not delete.")

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_list()

    def closeEvent(self, event) -> None:
        if self._recording:
            self._pipeline.set_training_mode(False)
            self._pipeline.set_on_training_transcription(None)
            self._recording = False
        event.accept()
