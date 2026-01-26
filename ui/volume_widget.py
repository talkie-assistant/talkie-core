"""
Volume / waveform strip: rolling buffer of levels, painted as bars.
Large waveform widget for main "audio in" display.
"""
from __future__ import annotations

import math
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QWidget

LEVEL_BUFFER_SIZE = 80
WAVEFORM_BUFFER_SIZE = 120


class VolumeWidget(QWidget):
    """
    Displays the last N volume levels as a horizontal bar strip (waveform style).
    set_level(level) appends a level (0.0--1.0); invalid values are clamped or skipped.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._levels: list[float] = []
        self.setMinimumHeight(32)
        self.setMaximumHeight(40)

    def set_level(self, level: float) -> None:
        """Append one level (clamped to 0--1); NaN/None treated as 0."""
        if level is None or (isinstance(level, float) and math.isnan(level)):
            level = 0.0
        level = max(0.0, min(1.0, float(level)))
        self._levels.append(level)
        if len(self._levels) > LEVEL_BUFFER_SIZE:
            self._levels.pop(0)
        self.update()

    def paintEvent(self, event: object) -> None:
        # High-contrast: dark background, light bars (match app styles)
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().color(self.backgroundRole()))
        if not self._levels:
            return
        w = self.width()
        h = self.height()
        n = len(self._levels)
        bar_w = max(1, (w - (n - 1)) // n) if n else 0
        for i, level in enumerate(self._levels):
            x = i * (bar_w + 1)
            if x >= w:
                break
            bar_h = max(1, int(level * (h - 2)))
            y = h - bar_h - 1
            painter.fillRect(x, y, bar_w, bar_h, self.palette().color(self.foregroundRole()))
        painter.end()


class AudioWaveformWidget(QWidget):
    """
    Large waveform-style view of incoming audio levels (rolling buffer).
    Same level source as VolumeWidget; use for main "audio in" display.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._levels: list[float] = []
        self.setMinimumHeight(64)
        self.setMaximumHeight(160)

    def set_level(self, level: float) -> None:
        """Append one level (clamped to 0--1); NaN/None treated as 0."""
        if level is None or (isinstance(level, float) and math.isnan(level)):
            level = 0.0
        level = max(0.0, min(1.0, float(level)))
        self._levels.append(level)
        if len(self._levels) > WAVEFORM_BUFFER_SIZE:
            self._levels.pop(0)
        self.update()

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().color(self.backgroundRole()))
        if not self._levels:
            return
        w = self.width()
        h = self.height()
        n = len(self._levels)
        bar_w = max(1, (w - (n - 1)) // n) if n else 0
        for i, level in enumerate(self._levels):
            x = i * (bar_w + 1)
            if x >= w:
                break
            bar_h = max(1, int(level * (h - 2)))
            y = h - bar_h - 1
            painter.fillRect(x, y, bar_w, bar_h, self.palette().color(self.foregroundRole()))
        painter.end()
