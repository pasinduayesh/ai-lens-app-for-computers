from typing import Any, Callable
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QBrush
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu

def create_dynamic_icon() -> QIcon:
    """
    Dynamically draws a beautiful, premium, high-contrast camera lens icon
    using QPainter. This ensures the app always has a sleek dark-theme system tray
    icon without needing to package external graphic asset files.
    """
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    # 1. Draw glowing accent outer ring (Vibrant Deep Blue)
    pen = QPen(QColor(51, 136, 255), 5)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(6, 6, 52, 52)
    
    # 2. Draw inner shutter/lens core (Deep slate fill with cyan accent circle)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor(26, 29, 36)))
    painter.drawEllipse(14, 14, 36, 36)
    
    # 3. Cyan central aperture lens glint (Glow highlight)
    painter.setBrush(QBrush(QColor(0, 212, 255)))
    painter.drawEllipse(24, 24, 16, 16)
    
    # 4. Subtle glint highlights (White reflection)
    painter.setBrush(QBrush(QColor(255, 255, 255, 200)))
    painter.drawEllipse(26, 22, 5, 5)
    
    painter.end()
    return QIcon(pixmap)


class ScreenLensTray(QSystemTrayIcon):
    """
    Sleek, modern system tray integration.
    Enables left-click double-toggle and right-click menu commands.
    """
    
    def __init__(
        self, 
        parent: Any, 
        on_screenshot_trigger: Callable[[], None],
        on_toggle_window: Callable[[], None],
        on_clear_history: Callable[[], None],
        on_exit_app: Callable[[], None]
    ) -> None:
        # Load the dynamic canvas-drawn icon
        self.dynamic_icon = create_dynamic_icon()
        super().__init__(self.dynamic_icon, parent)
        
        self.on_screenshot_trigger = on_screenshot_trigger
        self.on_toggle_window = on_toggle_window
        self.on_clear_history = on_clear_history
        self.on_exit_app = on_exit_app
        
        self.setToolTip("ScreenLens AI")
        self._setup_context_menu()
        self.activated.connect(self._handle_activation)

    def _setup_context_menu(self) -> None:
        """Sets up the custom modern right-click context menu styled with standard system visuals."""
        menu = QMenu()
        
        # Apply clean dark styling to system tray context menu matching dark mode
        menu.setStyleSheet("""
            QMenu {
                background-color: #1a1d24;
                color: #f1f3f7;
                border: 1px solid #2d313c;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #3388ff;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background-color: #2d313c;
                margin: 4px 0px;
            }
        """)
        
        # Add Actions
        screenshot_action = menu.addAction("Take Screenshot (Ctrl+Shift+S)")
        screenshot_action.triggered.connect(self.on_screenshot_trigger)
        
        toggle_action = menu.addAction("Show/Hide Assistant")
        toggle_action.triggered.connect(self.on_toggle_window)
        
        clear_action = menu.addAction("Clear Chat & Image History")
        clear_action.triggered.connect(self.on_clear_history)
        
        menu.addSeparator()
        
        exit_action = menu.addAction("Exit ScreenLens AI")
        exit_action.triggered.connect(self.on_exit_app)
        
        self.setContextMenu(menu)

    def _handle_activation(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Handles user interaction with the system tray icon (left-click/double-click logic)."""
        # Toggle window visibility on simple single left click or double click
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.on_toggle_window()

    def show_alert(self, title: str, message: str, is_info: bool = True) -> None:
        """Helper to fire standard native system notification balloons."""
        icon_type = QSystemTrayIcon.MessageIcon.Information if is_info else QSystemTrayIcon.MessageIcon.Warning
        self.showMessage(title, message, icon_type, 3000)
