"""
History view: list recent interactions, edit corrected response, save, toggle use for learning.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from persistence.history_repo import HistoryRepo

logger = logging.getLogger(__name__)


class HistoryView(QDialog):
    """
    Table of recent interactions (date, transcription, response, corrected, use for learning).
    User can edit the displayed response and save as correction; toggle use for learning.
    """

    def __init__(
        self,
        history_repo: HistoryRepo,
        history_list_limit: int = 100,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._repo = history_repo
        self._history_list_limit = history_list_limit
        self._current_id: int | None = None

        self.setWindowTitle("Talkie – History")
        self.setMinimumSize(860, 560)
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(24, 24, 24, 24)

        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ["Time", "You said", "Response", "Corrected", "Use for learning"]
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.verticalHeader().setDefaultSectionSize(52)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.cellChanged.connect(self._on_cell_changed)
        layout.addWidget(self._table)

        layout.addWidget(QLabel("Edit response (saved as correction):"))
        self._edit = QPlainTextEdit()
        self._edit.setMinimumHeight(100)
        self._edit.setMaximumHeight(160)
        layout.addWidget(self._edit)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(16)
        save_btn = QPushButton("Save correction")
        save_btn.setMinimumHeight(56)
        save_btn.clicked.connect(self._save_correction)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

        self._load_history()

    def _load_history(self) -> None:
        try:
            rows = self._repo.list_recent(limit=self._history_list_limit)
        except Exception as e:
            logger.exception("Failed to load history: %s", e)
            QMessageBox.warning(self, "Talkie", "Could not load history.")
            return
        self._table.blockSignals(True)
        self._table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            time_item = QTableWidgetItem(r["created_at"][:19] if r["created_at"] else "")
            time_item.setData(Qt.ItemDataRole.UserRole, r["id"])
            self._table.setItem(i, 0, time_item)
            self._table.setItem(i, 1, QTableWidgetItem(r["original_transcription"] or ""))
            self._table.setItem(i, 2, QTableWidgetItem(r["llm_response"] or ""))
            self._table.setItem(i, 3, QTableWidgetItem(r["corrected_response"] or ""))
            exclude = r.get("exclude_from_profile", 0)
            use_item = QTableWidgetItem()
            use_item.setCheckState(Qt.CheckState.Unchecked if exclude else Qt.CheckState.Checked)
            use_item.setData(Qt.ItemDataRole.UserRole, r["id"])
            self._table.setItem(i, 4, use_item)
        self._table.blockSignals(False)
        self._table.resizeColumnsToContents()

    def _on_selection_changed(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            self._current_id = None
            self._edit.setPlainText("")
            return
        id_item = self._table.item(row, 0)
        self._current_id = id_item.data(Qt.ItemDataRole.UserRole) if id_item else None
        response = self._table.item(row, 2)
        corrected = self._table.item(row, 3)
        text = (corrected and corrected.text()) or (response and response.text()) or ""
        self._edit.setPlainText(text)

    def _on_cell_changed(self, row: int, column: int) -> None:
        if column != 4:
            return
        item = self._table.item(row, 4)
        if not item:
            return
        interaction_id = item.data(Qt.ItemDataRole.UserRole)
        if interaction_id is None:
            return
        exclude = item.checkState() == Qt.CheckState.Unchecked
        try:
            self._repo.update_exclude_from_profile(interaction_id, exclude)
        except Exception as e:
            logger.exception("Failed to update exclude_from_profile: %s", e)
            QMessageBox.warning(self, "Talkie", "Could not update.")
            self._load_history()

    def _save_correction(self) -> None:
        if self._current_id is None:
            return
        text = self._edit.toPlainText().strip()
        if not text:
            return
        try:
            self._repo.update_correction(self._current_id, text)
        except Exception as e:
            logger.exception("Failed to save correction: %s", e)
            QMessageBox.warning(self, "Talkie", "Could not save.")
            return
        self._load_history()
        row = self._table.currentRow()
        if row >= 0 and row < self._table.rowCount():
            corr_item = self._table.item(row, 3)
            if corr_item:
                corr_item.setText(text)
