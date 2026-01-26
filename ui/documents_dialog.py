"""
Documents dialog: upload files and vectorize them for RAG (retrieval-augmented generation).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from rag import RAGService

logger = logging.getLogger(__name__)


class VectorizeWorker(QThread):
    """Run RAG ingest in background; emit progress (current, total) and done(success, message)."""
    progress = pyqtSignal(int, int)
    done = pyqtSignal(bool, str)

    def __init__(self, rag_service: RAGService, paths: list[Path]) -> None:
        super().__init__()
        self._rag = rag_service
        self._paths = list(paths)

    def run(self) -> None:
        try:
            for i, path in enumerate(self._paths):
                self.progress.emit(i + 1, len(self._paths))
                self._rag.ingest([path])
            self.done.emit(True, f"Vectorized {len(self._paths)} file(s).")
        except ValueError as e:
            self.done.emit(False, str(e))
        except Exception as e:
            logger.exception("Vectorize failed: %s", e)
            self.done.emit(False, str(e))


class DocumentsDialog(QDialog):
    """
    Upload documents (PDF, TXT) and trigger vectorization for RAG.
    Shows indexed documents list with Remove from index and Clear all.
    """

    def __init__(self, rag_service: RAGService | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rag = rag_service
        self._file_paths: list[Path] = []
        self._vectorize_worker: VectorizeWorker | None = None

        self.setWindowTitle("Talkie – Documents")
        self.setMinimumSize(560, 520)
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(24, 24, 24, 24)

        layout.addWidget(
            QLabel(
                "Add documents to be chunked and vectorized for RAG. "
                "When you speak, relevant passages from these documents can be included in the LLM context."
            )
        )

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add files...")
        add_btn.setObjectName("cornerButton")
        add_btn.clicked.connect(self._on_add_files)
        btn_row.addWidget(add_btn)
        remove_btn = QPushButton("Remove selected")
        remove_btn.setObjectName("cornerButton")
        remove_btn.clicked.connect(self._on_remove_selected)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addWidget(QLabel("Documents to vectorize:"))
        self._list = QListWidget()
        self._list.setMinimumHeight(120)
        layout.addWidget(self._list)

        self._vectorize_btn = QPushButton("Vectorize")
        self._vectorize_btn.setToolTip("Chunk and embed documents, store in vector DB for RAG")
        self._vectorize_btn.setObjectName("toggleButton")
        self._vectorize_btn.clicked.connect(self._on_vectorize)
        layout.addWidget(self._vectorize_btn)

        self._progress_label = QLabel("")
        self._progress_label.setVisible(False)
        layout.addWidget(self._progress_label)
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        layout.addWidget(QLabel("Indexed documents:"))
        self._indexed_list = QListWidget()
        self._indexed_list.setMinimumHeight(100)
        layout.addWidget(self._indexed_list)

        index_btn_row = QHBoxLayout()
        remove_index_btn = QPushButton("Remove from index")
        remove_index_btn.setObjectName("cornerButton")
        remove_index_btn.clicked.connect(self._on_remove_from_index)
        index_btn_row.addWidget(remove_index_btn)
        clear_all_btn = QPushButton("Clear all")
        clear_all_btn.setObjectName("cornerButton")
        clear_all_btn.clicked.connect(self._on_clear_index)
        index_btn_row.addStretch()
        layout.addLayout(index_btn_row)

        self._status_label = QLabel("Add files, then click Vectorize to index them for RAG.")
        layout.addWidget(self._status_label)

        self._refresh_indexed_list()
        if not self._rag:
            self._vectorize_btn.setEnabled(False)
            self._status_label.setText("RAG service not available.")
            for w in (remove_index_btn, clear_all_btn):
                w.setEnabled(False)

    def _refresh_indexed_list(self) -> None:
        self._indexed_list.clear()
        if self._rag:
            for source in self._rag.list_indexed_sources():
                self._indexed_list.addItem(QListWidgetItem(source))

    def _on_add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select documents",
            "",
            "Text files (*.txt);;PDF files (*.pdf);;All files (*)",
        )
        for p in paths:
            path = Path(p)
            if path not in self._file_paths:
                self._file_paths.append(path)
                self._list.addItem(QListWidgetItem(path.name))

    def _on_remove_selected(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        self._list.takeItem(row)
        if 0 <= row < len(self._file_paths):
            self._file_paths.pop(row)

    def _on_vectorize(self) -> None:
        if not self._rag or not self._file_paths:
            QMessageBox.information(
                self,
                "Documents",
                "Add at least one file before vectorizing.",
            )
            return
        self._vectorize_btn.setEnabled(False)
        self._progress_label.setVisible(True)
        self._progress_label.setText("Vectorizing…")
        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, len(self._file_paths))
        self._progress_bar.setValue(0)
        self._vectorize_worker = VectorizeWorker(self._rag, self._file_paths)
        self._vectorize_worker.progress.connect(self._on_vectorize_progress)
        self._vectorize_worker.done.connect(self._on_vectorize_done)
        self._vectorize_worker.start()

    def _on_vectorize_progress(self, current: int, total: int) -> None:
        self._progress_label.setText(f"Vectorizing… ({current} of {total} files)")
        self._progress_bar.setValue(current)

    def _on_vectorize_done(self, success: bool, message: str) -> None:
        self._vectorize_worker = None
        self._vectorize_btn.setEnabled(True)
        self._progress_bar.setVisible(False)
        self._progress_label.setVisible(False)
        if success:
            self._status_label.setText(message)
            self._refresh_indexed_list()
        else:
            QMessageBox.warning(
                self,
                "Documents",
                message,
            )
            self._status_label.setText("Vectorization failed.")

    def _on_remove_from_index(self) -> None:
        if not self._rag:
            return
        row = self._indexed_list.currentRow()
        if row < 0:
            QMessageBox.information(self, "Documents", "Select an indexed document to remove.")
            return
        item = self._indexed_list.item(row)
        source = item.text() if item else ""
        if not source:
            return
        try:
            self._rag.remove_from_index(source)
            self._refresh_indexed_list()
            self._status_label.setText(f"Removed {source} from index.")
        except Exception as e:
            QMessageBox.warning(self, "Documents", f"Failed to remove: {e}")

    def _on_clear_index(self) -> None:
        if not self._rag:
            return
        reply = QMessageBox.question(
            self,
            "Documents",
            "Clear all indexed documents? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self._rag.clear_index()
            self._refresh_indexed_list()
            self._status_label.setText("Index cleared.")
        except Exception as e:
            QMessageBox.warning(self, "Documents", f"Failed to clear: {e}")
