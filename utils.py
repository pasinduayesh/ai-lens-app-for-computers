import os
import sys
from typing import Final
from PyQt6.QtCore import QObject, pyqtSignal

# ---------------------------------------------------------
# High-DPI Support Configuration
# ---------------------------------------------------------
def setup_high_dpi() -> None:
    """Configures high-DPI scaling before QApplication is instantiated."""
    try:
        import ctypes
        # Ensure Windows 10/11 per-monitor DPI awareness (2 = PROCESS_PER_MONITOR_DPI_AWARE)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_SCALE_FACTOR_ROUNDING_POLICY"] = "PassThrough"

# ---------------------------------------------------------
# Directory Initialization & Path Configurations
# ---------------------------------------------------------
WORKSPACE_DIR: Final[str] = os.path.dirname(os.path.abspath(__file__))
SCREENSHOTS_DIR: Final[str] = os.path.join(WORKSPACE_DIR, "screenshots")
DATABASE_PATH: Final[str] = os.path.join(WORKSPACE_DIR, "screenlens.db")

def initialize_directories() -> None:
    """Ensures necessary operational directories exist."""
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

# ---------------------------------------------------------
# Application Constants
# ---------------------------------------------------------
OLLAMA_MODEL: Final[str] = "gemma4:31b-cloud"
OLLAMA_HOST: Final[str] = "http://localhost:11434"
HOTKEY_SEQUENCE: Final[str] = "ctrl+shift+s"

# ---------------------------------------------------------
# Global Thread-Safe Hotkey Bridge
# ---------------------------------------------------------
class HotkeySignalBridge(QObject):
    """QObject bridge to emit Qt signals from non-Qt threads (like keyboard library)."""
    hotkey_triggered = pyqtSignal()

# ---------------------------------------------------------
# Premium UI Stylesheet Configuration
# ---------------------------------------------------------
# HSL / Hex Custom Curated Palette
# Primary Accent:   hsl(215, 100%, 60%)  => #3388ff (Vibrant Deep Blue)
# Dark Main Background: hsl(220, 20%, 8%)    => #101216 (Sleek Dark Matte)
# Card Background:  hsl(220, 15%, 12%)   => #1a1d24 (Elevated Slate)
# Border & Divider: hsl(220, 10%, 20%)   => #2d313c (Subtle Charcoal Border)
# Primary Text:     hsl(210, 40%, 96%)   => #f1f3f7 (Crisp Off-White)
# Secondary Text:   hsl(215, 15%, 65%)   => #9fa6b2 (Muted Muted Blue)

DARK_STYLESHEET: Final[str] = """
QMainWindow, QWidget#AssistantWindow {
    background-color: #101216;
    color: #f1f3f7;
    font-family: "Segoe UI", "Inter", sans-serif;
    border-radius: 12px;
}

/* Scrollbars styling */
QScrollBar:vertical {
    border: none;
    background: #101216;
    width: 8px;
    margin: 0px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #2d313c;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #3388ff;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    border: none;
    background: #101216;
    height: 8px;
    margin: 0px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal {
    background: #2d313c;
    min-width: 20px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover {
    background: #3388ff;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* Custom Card Container */
QFrame#PreviewContainer, QFrame#ContentCard {
    background-color: #1a1d24;
    border: 1px solid #2d313c;
    border-radius: 10px;
}

/* Text Displays & Editors */
QTextEdit, QPlainTextEdit {
    background-color: #1a1d24;
    border: 1px solid #2d313c;
    border-radius: 8px;
    color: #f1f3f7;
    font-size: 13.5px;
    padding: 8px;
    selection-background-color: #3388ff;
    selection-color: #ffffff;
}
QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #3388ff;
}

/* Labels */
QLabel {
    color: #f1f3f7;
    font-size: 13px;
}
QLabel#TitleLabel {
    font-weight: bold;
    font-size: 15px;
    color: #ffffff;
}
QLabel#PreviewPlaceholder {
    color: #9fa6b2;
    font-style: italic;
}

/* Premium Buttons */
QPushButton {
    background-color: #1a1d24;
    border: 1px solid #2d313c;
    border-radius: 8px;
    color: #f1f3f7;
    padding: 8px 16px;
    font-size: 12.5px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #21252e;
    border: 1px solid #3388ff;
}
QPushButton:pressed {
    background-color: #101216;
}

QPushButton#PrimaryButton {
    background-color: #3388ff;
    border: 1px solid #3388ff;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#PrimaryButton:hover {
    background-color: #4d9cff;
    border: 1px solid #4d9cff;
}
QPushButton#PrimaryButton:pressed {
    background-color: #1a66cc;
}

QPushButton#CloseButton {
    background-color: transparent;
    border: none;
    border-radius: 4px;
    padding: 4px;
}
QPushButton#CloseButton:hover {
    background-color: #ea4335;
}

QPushButton#MinButton {
    background-color: transparent;
    border: none;
    border-radius: 4px;
    padding: 4px;
}
QPushButton#MinButton:hover {
    background-color: #2d313c;
}

/* Tool Buttons / Icon Buttons */
QToolButton {
    background-color: #1a1d24;
    border: 1px solid #2d313c;
    border-radius: 6px;
    padding: 6px;
}
QToolButton:hover {
    background-color: #2d313c;
    border: 1px solid #3388ff;
}
"""
