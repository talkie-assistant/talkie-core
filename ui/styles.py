"""
Accessible, high-contrast stylesheet for Talkie: easy to read, modern, motor-friendly.
- Large touch targets (min 48px, primary actions 56px+)
- Clear focus rings for keyboard users
- Generous spacing; WCAG AAA contrast
"""
from __future__ import annotations

# Minimum touch target (px); primary actions larger
TOUCH_TARGET_MIN = 48
BUTTON_MIN_HEIGHT = 56
TOGGLE_BUTTON_MIN_HEIGHT = 100
CORNER_BUTTON_MIN_HEIGHT = 64
CORNER_BUTTON_MIN_WIDTH = 120
SPACING_UNIT = 8


def get_high_contrast_stylesheet(font_size: int = 24) -> str:
    """
    Returns a Qt stylesheet for fullscreen, accessible UI: large text, large controls,
    high contrast, and visible focus for keyboard/switch users.
    """
    btn_font = max(font_size + 2, 26)
    toggle_font = max(font_size + 10, 34)
    corner_font = max(font_size, 22)
    label_font = max(font_size, 22)
    # Focus ring (visible for keyboard/switch users)
    focus_outline = "3px solid #4a9eff"
    return f"""
        QMainWindow, QDialog {{
            background-color: #0d0d0d;
        }}
        QWidget {{
            background-color: #0d0d0d;
            color: #e8e8e8;
            font-size: {label_font}px;
        }}
        /* All buttons: large, spaced, focus ring */
        QPushButton {{
            background-color: #2a2a2a;
            color: #fff;
            border: 2px solid #666;
            border-radius: 14px;
            padding: 18px 32px;
            font-size: {btn_font}px;
            min-height: {BUTTON_MIN_HEIGHT}px;
        }}
        QPushButton:hover {{
            background-color: #3a3a3a;
            border-color: #888;
        }}
        QPushButton:pressed {{
            background-color: #1a5a1a;
        }}
        QPushButton:focus {{
            outline: none;
            border: {focus_outline};
        }}
        /* Primary listen/stop action: extra large */
        QPushButton#toggleButton {{
            background-color: #0d5c0d;
            font-size: {toggle_font}px;
            min-height: {TOGGLE_BUTTON_MIN_HEIGHT}px;
            padding: 24px 56px;
            border-radius: 18px;
            border: 3px solid #2a8a2a;
        }}
        QPushButton#toggleButton:hover {{
            background-color: #0f6b0f;
        }}
        QPushButton#toggleButton:checked {{
            background-color: #8a2020;
            border-color: #b03030;
        }}
        QPushButton#toggleButton:checked:hover {{
            background-color: #9a2828;
        }}
        QPushButton#toggleButton:focus {{
            border: {focus_outline};
        }}
        /* Corner/secondary actions: still large, with spacing */
        QPushButton#cornerButton {{
            padding: 16px 24px;
            min-height: {CORNER_BUTTON_MIN_HEIGHT}px;
            min-width: {CORNER_BUTTON_MIN_WIDTH}px;
            font-size: {corner_font}px;
            border-radius: 14px;
        }}
        QPushButton#cornerButton:focus {{
            border: {focus_outline};
        }}
        QLabel {{
            color: #e8e8e8;
            font-size: {label_font}px;
        }}
        QLabel#statusLabel {{
            font-size: {label_font + 2}px;
            font-weight: bold;
        }}
        QTextEdit, QPlainTextEdit {{
            background-color: #1a1a1a;
            color: #fff;
            border: 2px solid #444;
            border-radius: 10px;
            font-size: {font_size}px;
            padding: 20px;
        }}
        QTextEdit#responseDisplay {{
            font-size: {max(font_size + 24, 48)}px;
            text-align: center;
            line-height: 1.4;
        }}
        QDoubleSpinBox {{
            background-color: #1a1a1a;
            color: #fff;
            border: 2px solid #444;
            border-radius: 10px;
            font-size: {max(font_size, 22)}px;
            padding: 14px 18px;
            min-height: {TOUCH_TARGET_MIN}px;
            min-width: 100px;
        }}
        QDoubleSpinBox:focus {{
            border: {focus_outline};
        }}
        QComboBox {{
            background-color: #1a1a1a;
            color: #fff;
            border: 2px solid #444;
            border-radius: 10px;
            font-size: {max(font_size, 22)}px;
            padding: 14px 18px;
            min-height: {TOUCH_TARGET_MIN}px;
        }}
        QComboBox:focus {{
            border: {focus_outline};
        }}
        QComboBox::drop-down {{
            width: 40px;
        }}
        QGroupBox {{
            font-size: {label_font}px;
            padding: 20px 16px 16px 16px;
            margin-top: 16px;
            border: 2px solid #444;
            border-radius: 12px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 16px;
            padding: 0 8px;
        }}
        QCheckBox {{
            font-size: {label_font}px;
            spacing: 14px;
            padding: 12px 0;
            min-height: {TOUCH_TARGET_MIN}px;
        }}
        QCheckBox::indicator {{
            width: 28px;
            height: 28px;
        }}
        QCheckBox:focus {{
            outline: none;
        }}
        QTableWidget {{
            background-color: #1a1a1a;
            color: #e8e8e8;
            gridline-color: #333;
            font-size: {max(font_size - 2, 20)}px;
        }}
        QTableWidget::item {{
            padding: 14px 10px;
            min-height: 48px;
        }}
        QHeaderView::section {{
            background-color: #2a2a2a;
            color: #fff;
            padding: 16px 12px;
            font-size: {label_font}px;
        }}
        QDialogButtonBox QPushButton {{
            min-width: 120px;
        }}
        QScrollBar:vertical {{
            background: #1a1a1a;
            width: 20px;
            border-radius: 10px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: #444;
            min-height: 48px;
            border-radius: 8px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: #555;
        }}
        QScrollBar:horizontal {{
            background: #1a1a1a;
            height: 20px;
            border-radius: 10px;
        }}
        QScrollBar::handle:horizontal {{
            background: #444;
            min-width: 48px;
            border-radius: 8px;
        }}
    """
