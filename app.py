import os
import sys
import time
import urllib.parse
import webbrowser
from typing import List, Dict, Any, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QPoint
from PyQt6.QtGui import QIcon, QPixmap, QImage, QGuiApplication, QMouseEvent
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QGridLayout, QPushButton, QLabel, QTextEdit, QPlainTextEdit, 
    QFrame, QProgressBar, QSizePolicy, QDialog, QMessageBox
)

import keyboard

# Modular imports
from utils import (
    setup_high_dpi, initialize_directories, OLLAMA_MODEL, 
    OLLAMA_HOST, HOTKEY_SEQUENCE, HotkeySignalBridge, DARK_STYLESHEET
)
from history import DatabaseManager
from ocr_engine import OcrEngine
from translator import Translator
from ai_worker import AiWorker
from overlay import OverlayController
from tray import ScreenLensTray

# Initialize DPI configurations before any GUI action
setup_high_dpi()

# ---------------------------------------------------------
# Threaded Workers for UI Fluidity
# ---------------------------------------------------------

class OcrWorker(QThread):
    """Worker thread to run CPU/GPU EasyOCR processing in the background."""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, ocr_engine: OcrEngine, image_path: str) -> None:
        super().__init__()
        self.ocr_engine = ocr_engine
        self.image_path = image_path

    def run(self) -> None:
        try:
            results = self.ocr_engine.extract_text(self.image_path)
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class SinhalaOcrWorker(QThread):
    """Worker thread to run AI-based Sinhala OCR using Ollama in the background."""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, ocr_engine: OcrEngine, image_path: str) -> None:
        super().__init__()
        self.ocr_engine = ocr_engine
        self.image_path = image_path

    def run(self) -> None:
        try:
            result = self.ocr_engine.extract_sinhala_text_via_ai(self.image_path)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class StatusWorker(QThread):
    """Background worker to check Ollama host state and verify if the gemma model is pulled."""
    status_checked = pyqtSignal(bool, str)

    def run(self) -> None:
        import ollama
        try:
            client = ollama.Client(host=OLLAMA_HOST)
            models_data = client.list()
            models_list = models_data.get("models", [])
            models = [m.get("model", m.get("name", "")) for m in models_list]
            
            # Match strict or loose model signature
            has_model = False
            for m in models:
                if OLLAMA_MODEL in m or m in OLLAMA_MODEL:
                    has_model = True
                    break
            
            if has_model:
                self.status_checked.emit(True, "Ollama Online")
            else:
                self.status_checked.emit(True, f"Ollama Online (Model '{OLLAMA_MODEL}' not pulled)")
        except Exception:
            self.status_checked.emit(False, "Ollama Offline")

# ---------------------------------------------------------
# Main Floating Assistant Window
# ---------------------------------------------------------

class AssistantWindow(QMainWindow):
    """
    Windows 11 custom-styled floating always-on-top AI assistant.
    Features drag-to-move custom header, history loaders, streaming chat, and action controllers.
    """
    
    def __init__(self) -> None:
        super().__init__()
        
        # 1. Initialize Backend Engines
        initialize_directories()
        self.db = DatabaseManager()
        self.ocr = OcrEngine()
        self.translator = Translator()
        
        # Session state details
        self.session_id = f"sess_{int(time.time())}"
        self.active_screenshot_path: Optional[str] = None
        self.active_screenshot_id: Optional[int] = None
        self.extracted_ocr_data: Dict[str, Any] = {"text": "", "code_snippets": [], "urls": [], "emails": []}
        
        # Dragging variables for borderless window movement
        self.drag_position = QPoint()
        
        # 2. Window Configurations
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        
        # Sizing and screen position placement (Floating at bottom-right corner)
        self.resize(450, 720)
        self.setMinimumSize(400, 600)
        self._position_bottom_right()
        
        # 3. Setup Layout and Widgets
        self._setup_ui()
        
        # Apply premium dark themes
        self.setStyleSheet(DARK_STYLESHEET)
        
        # 4. Setup Overlay Screenshot Controller
        self.overlay_controller = OverlayController(self._handle_screenshot_callback)
        
        # 5. Connect Global Keyboard Hotkeys via a Safe Qt Bridge
        self.hotkey_bridge = HotkeySignalBridge()
        self.hotkey_bridge.hotkey_triggered.connect(self.trigger_screenshot_mode)
        
        try:
            keyboard.add_hotkey(HOTKEY_SEQUENCE, self.hotkey_bridge.hotkey_triggered.emit)
        except Exception as e:
            self.append_system_log(f"Warning: Global hotkey registration failed ({e}). Use System Tray to capture.")
            
        # 6. Initialize System Tray Integration
        self.tray = ScreenLensTray(
            parent=self,
            on_screenshot_trigger=self.trigger_screenshot_mode,
            on_toggle_window=self.toggle_visibility,
            on_clear_history=self._clear_all_logs,
            on_exit_app=self.close_app_fully
        )
        self.tray.show()
        
        # 7. Check Ollama Status
        self.check_ollama_status()
        self.append_system_log("ScreenLens AI Ready. Press **Ctrl+Shift+S** to drag-select and capture any region.")

    def _position_bottom_right(self) -> None:
        """Positions the floating window above the taskbar in the bottom-right sector of the primary screen."""
        primary_screen = QGuiApplication.primaryScreen()
        if primary_screen:
            screen_geom = primary_screen.availableGeometry()
            # Constrain window dimensions to available screen size
            max_w = max(350, screen_geom.width() - 40)
            max_h = max(500, screen_geom.height() - 40)
            target_w = min(self.width(), max_w)
            target_h = min(self.height(), max_h)
            if target_w != self.width() or target_h != self.height():
                self.resize(target_w, target_h)
                
            x = max(screen_geom.left() + 10, screen_geom.right() - self.width() - 20)
            y = max(screen_geom.top() + 10, screen_geom.bottom() - self.height() - 20)
            self.move(x, y)

    def _setup_ui(self) -> None:
        """Builds and nests the layout hierarchy."""
        self.setMouseTracking(True)
        # Top-level central widget
        central_widget = QWidget(self)
        central_widget.setObjectName("AssistantWindow")
        central_widget.setMouseTracking(True)
        self.setCentralWidget(central_widget)
        
        # Root layout
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(10)
        
        # Outer Framed Canvas Container to enable custom CSS borders and shadows
        self.container_frame = QFrame(central_widget)
        self.container_frame.setObjectName("ContentCard")
        self.container_frame.setMouseTracking(True)
        root_layout.addWidget(self.container_frame)
        
        # Main layout inside the styled frame
        main_layout = QVBoxLayout(self.container_frame)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)
        
        # ---------------------------------------------------------
        # Header / Title Bar Row
        # ---------------------------------------------------------
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        
        # Custom Status indicator dot
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(10, 10)
        self.status_dot.setStyleSheet("background-color: #f1c40f; border-radius: 5px;") # Yellow for testing/checking
        header_layout.addWidget(self.status_dot)
        
        # Title Label
        title_label = QLabel("ScreenLens AI")
        title_label.setObjectName("TitleLabel")
        header_layout.addWidget(title_label)
        
        # Ollama connection string label
        self.status_text = QLabel("Checking Ollama...")
        self.status_text.setStyleSheet("color: #9fa6b2; font-size: 11px;")
        header_layout.addWidget(self.status_text)
        
        header_layout.addStretch()
        
        # Minimize and Close buttons
        min_btn = QPushButton("—")
        min_btn.setObjectName("MinButton")
        min_btn.setFixedSize(26, 26)
        min_btn.clicked.connect(self.showMinimized)
        header_layout.addWidget(min_btn)
        
        close_btn = QPushButton("✕")
        close_btn.setObjectName("CloseButton")
        close_btn.setFixedSize(26, 26)
        close_btn.clicked.connect(self.hide) # Hide hides to tray instead of quitting
        header_layout.addWidget(close_btn)
        
        main_layout.addLayout(header_layout)
        
        # ---------------------------------------------------------
        # Screenshot Preview Card
        # ---------------------------------------------------------
        self.preview_frame = QFrame()
        self.preview_frame.setObjectName("PreviewContainer")
        self.preview_frame.setFixedHeight(120)
        self.preview_frame.setVisible(False) # Hidden initially
        
        preview_layout = QHBoxLayout(self.preview_frame)
        preview_layout.setContentsMargins(8, 8, 8, 8)
        
        # Image preview canvas
        self.preview_image_lbl = QLabel()
        self.preview_image_lbl.setFixedSize(140, 104)
        self.preview_image_lbl.setScaledContents(True)
        self.preview_image_lbl.setStyleSheet("border-radius: 6px; background-color: #101216; border: 1px solid #2d313c;")
        preview_layout.addWidget(self.preview_image_lbl)
        
        # Text details
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)
        self.preview_path_lbl = QLabel("No active screen clip.")
        self.preview_path_lbl.setWordWrap(True)
        self.preview_path_lbl.setStyleSheet("font-size: 11px; color: #9fa6b2;")
        info_layout.addWidget(self.preview_path_lbl)
        
        info_layout.addStretch()
        
        # Trash button
        remove_preview_btn = QPushButton("Clear Screenshot")
        remove_preview_btn.setStyleSheet("""
            QPushButton { 
                background-color: #ea4335; border: none; padding: 4px 8px; font-size: 11px; 
            }
            QPushButton:hover { background-color: #ff6659; }
        """)
        remove_preview_btn.clicked.connect(self.clear_screenshot_preview)
        info_layout.addWidget(remove_preview_btn)
        
        preview_layout.addLayout(info_layout)
        main_layout.addWidget(self.preview_frame)
        
        # ---------------------------------------------------------
        # Dynamic Processing Progress Bar
        # ---------------------------------------------------------
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setRange(0, 0) # Infinite streaming wave animation
        self.progress_bar.setStyleSheet("""
            QProgressBar { background-color: #1a1d24; border: none; border-radius: 2px; }
            QProgressBar::chunk { background-color: #3388ff; border-radius: 2px; }
        """)
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)
        
        # ---------------------------------------------------------
        # AI & OCR Streaming Response Window
        # ---------------------------------------------------------
        self.response_view = QTextEdit()
        self.response_view.setReadOnly(True)
        self.response_view.setPlaceholderText("Capture a region to start or ask a question directly...")
        main_layout.addWidget(self.response_view)
        
        # ---------------------------------------------------------
        # Quick Control Panel Dashboard Actions
        # ---------------------------------------------------------
        # ---------------------------------------------------------
        # Quick Control Panel Dashboard Actions (2x3 Grid Layout)
        # ---------------------------------------------------------
        controls_layout = QGridLayout()
        controls_layout.setSpacing(8)
        
        # Configure button widgets with expanding size policy
        self.ocr_btn = QPushButton("OCR")
        self.ocr_btn.setToolTip("Extract all text from the current captured region")
        self.ocr_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.ocr_btn.setMinimumHeight(35)
        self.ocr_btn.clicked.connect(self.run_ocr_on_screenshot)
        controls_layout.addWidget(self.ocr_btn, 0, 0) # Row 0, Col 0
        
        self.sinhala_ocr_btn = QPushButton("Sinhala OCR")
        self.sinhala_ocr_btn.setToolTip("Use Ollama AI Vision to extract Sinhala text")
        self.sinhala_ocr_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.sinhala_ocr_btn.setMinimumHeight(35)
        self.sinhala_ocr_btn.clicked.connect(self.run_sinhala_ocr_on_screenshot)
        controls_layout.addWidget(self.sinhala_ocr_btn, 0, 1) # Row 0, Col 1
        
        self.translate_btn = QPushButton("Translate")
        self.translate_btn.setToolTip("Translate extracted text English ↔ Sinhala")
        self.translate_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.translate_btn.setMinimumHeight(35)
        self.translate_btn.clicked.connect(self.run_translation)
        controls_layout.addWidget(self.translate_btn, 0, 2) # Row 0, Col 2
        
        self.search_btn = QPushButton("Search Web")
        self.search_btn.setToolTip("Search Google with response content or OCR text")
        self.search_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.search_btn.setMinimumHeight(35)
        self.search_btn.clicked.connect(self.search_web_with_query)
        controls_layout.addWidget(self.search_btn, 1, 0) # Row 1, Col 0
        
        self.copy_res_btn = QPushButton("Copy AI")
        self.copy_res_btn.setToolTip("Copy the full AI text response to your clipboard")
        self.copy_res_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.copy_res_btn.setMinimumHeight(35)
        self.copy_res_btn.clicked.connect(self.copy_ai_response)
        controls_layout.addWidget(self.copy_res_btn, 1, 1) # Row 1, Col 1
        
        self.copy_ocr_btn = QPushButton("Copy OCR")
        self.copy_ocr_btn.setToolTip("Copy all extracted OCR raw text")
        self.copy_ocr_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.copy_ocr_btn.setMinimumHeight(35)
        self.copy_ocr_btn.clicked.connect(self.copy_ocr_text)
        controls_layout.addWidget(self.copy_ocr_btn, 1, 2) # Row 1, Col 2
        
        main_layout.addLayout(controls_layout)
        
        # Configure initial buttons access based on screenshot state
        self._toggle_action_buttons_state(False)
        
        # ---------------------------------------------------------
        # Prompt Editor & Send Command Row
        # ---------------------------------------------------------
        prompt_layout = QHBoxLayout()
        prompt_layout.setSpacing(8)
        
        self.prompt_input = QPlainTextEdit()
        self.prompt_input.setPlaceholderText("Ask a question about the image or text...")
        self.prompt_input.setFixedHeight(50)
        self.prompt_input.installEventFilter(self) # Catch Enter keys
        prompt_layout.addWidget(self.prompt_input)
        
        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("PrimaryButton")
        self.send_btn.setFixedSize(70, 50)
        self.send_btn.clicked.connect(self.send_ai_query)
        prompt_layout.addWidget(self.send_btn)
        
        main_layout.addLayout(prompt_layout)

    # ---------------------------------------------------------
    # Window Actions & Movement Handling
    # ---------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Captures mouse clicks to drag (move) or resize the frameless window from borders/corners."""
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.pos()
            
            # 1. Resize Bottom-Right corner (15px threshold)
            if pos.x() >= self.width() - 15 and pos.y() >= self.height() - 15:
                self.drag_mode = "resize-bottom-right"
                event.accept()
            # 2. Resize Bottom-Left corner (15px threshold)
            elif pos.x() <= 15 and pos.y() >= self.height() - 15:
                self.drag_mode = "resize-bottom-left"
                event.accept()
            # 3. Resize Left border (8px threshold)
            elif pos.x() <= 8:
                self.drag_mode = "resize-left"
                event.accept()
            # 4. Resize Right border (8px threshold)
            elif pos.x() >= self.width() - 8:
                self.drag_mode = "resize-right"
                event.accept()
            # 5. Resize Bottom border (8px threshold)
            elif pos.y() >= self.height() - 8:
                self.drag_mode = "resize-bottom"
                event.accept()
            # 6. Drag Move (top title bar)
            elif pos.y() <= 45:
                self.drag_mode = "move"
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
            else:
                self.drag_mode = None

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handles cursor shape hover indicators and drags/resizes borders actively (Left, Right, Bottom)."""
        pos = event.pos()
        
        # A. If no buttons are pressed, update the cursor shape dynamically to show resize handles
        if not event.buttons():
            if pos.x() >= self.width() - 15 and pos.y() >= self.height() - 15:
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif pos.x() <= 15 and pos.y() >= self.height() - 15:
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            elif pos.x() <= 8:
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif pos.x() >= self.width() - 8:
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif pos.y() >= self.height() - 8:
                self.setCursor(Qt.CursorShape.SizeVerCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        # B. Left button drag actions
        if event.buttons() == Qt.MouseButton.LeftButton and hasattr(self, 'drag_mode'):
            screen = QGuiApplication.screenAt(event.globalPosition().toPoint()) or QGuiApplication.primaryScreen()
            sg = screen.availableGeometry() if screen else None
            
            if self.drag_mode == "move" and not self.drag_position.isNull():
                new_pos = event.globalPosition().toPoint() - self.drag_position
                if sg:
                    clamped_x = max(sg.left(), min(sg.right() - self.width(), new_pos.x()))
                    clamped_y = max(sg.top(), min(sg.bottom() - self.height(), new_pos.y()))
                    self.move(clamped_x, clamped_y)
                else:
                    self.move(new_pos)
                event.accept()
            elif self.drag_mode == "resize-bottom-right":
                max_w = (sg.right() - self.x()) if sg else 2500
                max_h = (sg.bottom() - self.y()) if sg else 2500
                w = max(350, min(max_w, pos.x()))
                h = max(500, min(max_h, pos.y()))
                self.resize(w, h)
                event.accept()
            elif self.drag_mode == "resize-bottom-left":
                max_h = (sg.bottom() - self.y()) if sg else 2500
                h = max(500, min(max_h, pos.y()))
                proposed_x = self.x() + pos.x()
                min_x = sg.left() if sg else 0
                new_x = max(min_x, proposed_x)
                new_width = (self.x() + self.width()) - new_x
                if new_width >= 350:
                    self.setGeometry(new_x, self.y(), new_width, h)
                else:
                    self.resize(self.width(), h)
                event.accept()
            elif self.drag_mode == "resize-left":
                proposed_x = self.x() + pos.x()
                min_x = sg.left() if sg else 0
                new_x = max(min_x, proposed_x)
                new_width = (self.x() + self.width()) - new_x
                if new_width >= 350:
                    self.setGeometry(new_x, self.y(), new_width, self.height())
                event.accept()
            elif self.drag_mode == "resize-right":
                max_w = (sg.right() - self.x()) if sg else 2500
                w = max(350, min(max_w, pos.x()))
                self.resize(w, self.height())
                event.accept()
            elif self.drag_mode == "resize-bottom":
                max_h = (sg.bottom() - self.y()) if sg else 2500
                h = max(500, min(max_h, pos.y()))
                self.resize(self.width(), h)
                event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Resets drag and resize states on mouse release."""
        self.drag_mode = None
        self.drag_position = QPoint()
        self.setCursor(Qt.CursorShape.ArrowCursor)
        
    def eventFilter(self, obj: Any, event: Any) -> bool:
        """Listens for enter key triggers on prompt input to submit prompts automatically."""
        if obj is self.prompt_input and event.type() == event.type().KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                # Standard Enter runs query, Shift+Enter moves carriage down
                if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self.send_ai_query()
                    return True
        return super().eventFilter(obj, event)

    def toggle_visibility(self) -> None:
        """Toggles show / hide visibility of the floating assistant panel."""
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()
            self._position_bottom_right()

    def close_app_fully(self) -> None:
        """Gracefully releases background listeners and exits app application execution."""
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        self.tray.hide()
        QApplication.quit()

    def append_system_log(self, text: str) -> None:
        """Prints a system notice/formatting cleanly inside the QTextEdit window."""
        self.response_view.append(f"\n*System: {text}*\n")
        # Scroll cursor down
        scrollbar = self.response_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    # ---------------------------------------------------------
    # Core Feature Orchestration
    # ---------------------------------------------------------
    def trigger_screenshot_mode(self) -> None:
        """Triggers fullscreen overlays across screens in order to grab selection coordinates."""
        self.hide() # Temporarily hide window so it doesn't block capture selection
        time.sleep(0.18) # Tiny delay to allow window close animation frames
        self.overlay_controller.trigger_overlay()

    def _handle_screenshot_callback(self, image_path: str) -> None:
        """Executed on overlay crop drag release. Save path received."""
        self.show()
        self.raise_()
        self.activateWindow()
        self._position_bottom_right()
        
        # Load screenshot preview
        self.active_screenshot_path = image_path
        
        # Save screenshot into database history immediately
        self.active_screenshot_id = self.db.save_screenshot(image_path)
        
        pixmap = QPixmap(image_path)
        scaled_pixmap = pixmap.scaled(
            self.preview_image_lbl.size(), 
            Qt.AspectRatioMode.KeepAspectRatioByExpanding, 
            Qt.TransformationMode.SmoothTransformation
        )
        self.preview_image_lbl.setPixmap(scaled_pixmap)
        
        file_name = os.path.basename(image_path)
        self.preview_path_lbl.setText(f"Active Clip: **{file_name}**")
        self.preview_frame.setVisible(True)
        
        # Enable relevant dashboard control actions
        self._toggle_action_buttons_state(True)
        
        self.tray.show_alert("Capture Success", "Screenshot grabbed. Processing with Ollama AI...")
        
        # Auto-initiate streaming AI interpretation prompt
        self.response_view.clear()
        self.send_ai_query(prompt_override="Analyze the captured screenshot and summarize its contents.")

    def clear_screenshot_preview(self) -> None:
        """Removes the active screenshot attachment."""
        self.active_screenshot_path = None
        self.active_screenshot_id = None
        self.preview_frame.setVisible(False)
        self.preview_image_lbl.clear()
        self.extracted_ocr_data = {"text": "", "code_snippets": [], "urls": [], "emails": []}
        self._toggle_action_buttons_state(False)
        self.append_system_log("Active screenshot attachment cleared.")

    def _toggle_action_buttons_state(self, enabled: bool) -> None:
        """Enables/disables specific dashboard quick actions depending on active screenshot attachment."""
        self.ocr_btn.setEnabled(enabled)
        self.sinhala_ocr_btn.setEnabled(enabled)
        # Translation remains available if we have extracted OCR text
        has_ocr = bool(self.extracted_ocr_data.get("text", "").strip())
        self.translate_btn.setEnabled(enabled or has_ocr)

    # ---------------------------------------------------------
    # Threaded Process Invocations
    # ---------------------------------------------------------
    def check_ollama_status(self) -> None:
        """Runs background check to ensure Ollama service and chosen model are accessible."""
        self.status_worker = StatusWorker()
        self.status_worker.status_checked.connect(self._handle_status_update)
        self.status_worker.start()

    def _handle_status_update(self, is_online: bool, status_msg: str) -> None:
        """Applies status dots and text updates from worker checked status."""
        self.status_text.setText(status_msg)
        if is_online:
            if "not pulled" in status_msg:
                self.status_dot.setStyleSheet("background-color: #e67e22; border-radius: 5px;") # Orange warning
                self.append_system_log(f"Warning: {status_msg}")
            else:
                self.status_dot.setStyleSheet("background-color: #2ecc71; border-radius: 5px;") # Green healthy
        else:
            self.status_dot.setStyleSheet("background-color: #e74c3c; border-radius: 5px;") # Red offline
            self.append_system_log("Error: Ollama is offline. Ensure Ollama service is running locally.")

    def run_ocr_on_screenshot(self) -> None:
        """Runs the background OcrWorker to parse the image text."""
        if not self.active_screenshot_path:
            return
            
        self.ocr_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.append_system_log("Initializing OCR Engine (Extracting Sinhala & English text)...")
        
        self.ocr_worker = OcrWorker(self.ocr, self.active_screenshot_path)
        self.ocr_worker.finished.connect(self._handle_ocr_completion)
        self.ocr_worker.error.connect(self._handle_ocr_error)
        self.ocr_worker.start()

    def _handle_ocr_completion(self, results: dict) -> None:
        """Triggers upon background OCR worker execution completion."""
        self.ocr_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        self.extracted_ocr_data = results
        raw_text = results.get("text", "").strip()
        
        # Save OCR results to active screenshot database record
        if self.active_screenshot_id:
            self.db.update_screenshot_ocr(self.active_screenshot_id, raw_text)
            
        self.response_view.clear()
        
        if not raw_text:
            self.response_view.setPlainText("OCR Completed: No text was detected in the captured region.")
            self.translate_btn.setEnabled(False)
            return
            
        # Display OCR formatted structure beautifully using PyQt setMarkdown support
        md_report = "# Extracted Text:\n"
        md_report += f"```\n{raw_text}\n```\n\n"
        
        # Display extracted specialized sub-segments
        code_blocks = results.get("code_snippets", [])
        if code_blocks:
            md_report += "## Detected Code Snippets:\n"
            for cb in code_blocks:
                md_report += f"```python\n{cb}\n```\n\n"
                
        urls = results.get("urls", [])
        if urls:
            md_report += "## Detected Links:\n"
            for url in urls:
                md_report += f"- [{url}]({url})\n"
            md_report += "\n"
            
        emails = results.get("emails", [])
        if emails:
            md_report += "## Detected Emails:\n"
            for em in emails:
                md_report += f"- {em}\n"
            md_report += "\n"
            
        self.response_view.setMarkdown(md_report)
        self.translate_btn.setEnabled(True)
        
        # Auto save OCR as assistant event in chat log
        self.db.save_chat_message(
            session_id=self.session_id,
            role="assistant",
            message=f"[OCR Raw Output]\n{raw_text}",
            screenshot_id=self.active_screenshot_id
        )

    def _handle_ocr_error(self, err_msg: str) -> None:
        """Handles background OCR pipeline exceptions safely."""
        self.ocr_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.append_system_log(f"OCR Operation failed: {err_msg}")

    def run_sinhala_ocr_on_screenshot(self) -> None:
        """Runs the background SinhalaOcrWorker to transcribe Sinhala text via Ollama Vision."""
        if not self.active_screenshot_path:
            return
            
        self.sinhala_ocr_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.append_system_log("Initializing AI Sinhala OCR (Reading image with Ollama Vision)...")
        
        self.sinhala_ocr_worker = SinhalaOcrWorker(self.ocr, self.active_screenshot_path)
        self.sinhala_ocr_worker.finished.connect(self._handle_sinhala_ocr_completion)
        self.sinhala_ocr_worker.error.connect(self._handle_sinhala_ocr_error)
        self.sinhala_ocr_worker.start()

    def _handle_sinhala_ocr_completion(self, result: str) -> None:
        """Triggers upon background AI Sinhala OCR worker completion."""
        self.sinhala_ocr_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        # Populate extracted OCR data so that standard Translate and Search actions are supported
        self.extracted_ocr_data = {
            "text": result,
            "code_snippets": [],
            "urls": [],
            "emails": []
        }
        
        # Save OCR results to active screenshot database record
        if self.active_screenshot_id:
            self.db.update_screenshot_ocr(self.active_screenshot_id, result)
            
        self.response_view.clear()
        
        if not result or result == "No Sinhala text detected.":
            self.response_view.setPlainText("AI OCR: No Sinhala text was detected in the captured region.")
            self.translate_btn.setEnabled(False)
            return
            
        # Display OCR formatted structure
        md_report = "# Extracted Sinhala Text (AI Vision):\n"
        md_report += f"{result}\n"
        
        self.response_view.setMarkdown(md_report)
        self.translate_btn.setEnabled(True)
        
        # Auto save OCR as assistant event in chat log
        self.db.save_chat_message(
            session_id=self.session_id,
            role="assistant",
            message=f"[AI Sinhala OCR Output]\n{result}",
            screenshot_id=self.active_screenshot_id
        )

    def _handle_sinhala_ocr_error(self, err_msg: str) -> None:
        """Handles background AI Sinhala OCR worker errors."""
        self.sinhala_ocr_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.append_system_log(f"AI Sinhala OCR Operation failed: {err_msg}")

    def run_translation(self) -> None:
        """Translates the extracted OCR text English <-> Sinhala and displays in response area."""
        target_text = self.extracted_ocr_data.get("text", "").strip()
        if not target_text:
            # Fallback to translate response view content
            target_text = self.response_view.toPlainText().strip()
            
        if not target_text:
            self.append_system_log("Nothing to translate. Capture screen or wait for text.")
            return
            
        self.progress_bar.setVisible(True)
        self.translate_btn.setEnabled(False)
        self.append_system_log("Running AI Script Translator...")
        
        # Since translation might query Ollama or perform request operations, we run it in a QThread
        class TransWorker(QThread):
            finished = pyqtSignal(str)
            def __init__(self, translator: Translator, text: str) -> None:
                super().__init__()
                self.translator = translator
                self.text = text
            def run(self) -> None:
                res = self.translator.translate(self.text)
                self.finished.emit(res)
                
        self.trans_worker = TransWorker(self.translator, target_text)
        self.trans_worker.finished.connect(self._handle_translation_completion)
        self.trans_worker.start()

    def _handle_translation_completion(self, translated_result: str) -> None:
        self.progress_bar.setVisible(False)
        self.translate_btn.setEnabled(True)
        
        self.response_view.clear()
        self.response_view.setMarkdown(f"# Translated Text:\n{translated_result}")
        
        # Persist translation in DB
        self.db.save_chat_message(
            session_id=self.session_id,
            role="assistant",
            message=f"[Translation Output]\n{translated_result}",
            screenshot_id=self.active_screenshot_id
        )

    def send_ai_query(self, prompt_override: Optional[str] = None) -> None:
        """Prepares history and starts streaming background worker for AI inference."""
        prompt = prompt_override or self.prompt_input.toPlainText().strip()
        if not prompt:
            return
            
        self.prompt_input.clear()
        self.send_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        
        # Log user query in response log
        if not prompt_override:
            self.response_view.append(f"\n### You:\n{prompt}\n")
            
        # 1. Fetch chat message histories
        chat_logs = self.db.get_chat_history(self.session_id)
        
        # 2. Persist user chat message entry
        self.db.save_chat_message(
            session_id=self.session_id,
            role="user",
            message=prompt,
            screenshot_id=self.active_screenshot_id
        )
        
        # Write response block placeholder
        if not prompt_override:
            self.response_view.append("### ScreenLens AI:\n")
        else:
            self.response_view.setPlainText("### ScreenLens AI:\n")
            
        self.current_response_index = len(self.response_view.toPlainText())
        self.accumulated_ai_response = ""
        
        # 3. Spawn background AiWorker
        # We only pass screenshot path if it's the very first request or auto-analysis request
        img_path = self.active_screenshot_path if (prompt_override or len(chat_logs) == 0) else None
        
        self.ai_worker = AiWorker(
            prompt=prompt,
            history=chat_logs,
            image_path=img_path
        )
        self.ai_worker.chunk_received.connect(self._handle_ai_chunk)
        self.ai_worker.finished.connect(self._handle_ai_finished)
        self.ai_worker.error.connect(self._handle_ai_error)
        self.ai_worker.start()

    def _handle_ai_chunk(self, chunk: str) -> None:
        """Appends tokens directly to response editor to simulate streaming text."""
        self.accumulated_ai_response += chunk
        self.response_view.insertPlainText(chunk)
        
        # Auto scroll to bottom
        scrollbar = self.response_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _handle_ai_finished(self, full_response: str) -> None:
        """Completes streaming thread transaction, updates text as Markdown, saves in history."""
        self.send_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        # Save complete assistant response
        self.db.save_chat_message(
            session_id=self.session_id,
            role="assistant",
            message=full_response,
            screenshot_id=self.active_screenshot_id
        )
        
        # Format the whole text block safely as Markdown (headers, code highlights, bold text)
        # We fetch full text accumulated, format and reset
        full_text = self.response_view.toPlainText()
        # QMarkdown updates are done on full logs or just render markdown
        # To avoid breaking ongoing streaming visual formats, let's keep simple QMarkdown rendering
        self.response_view.setMarkdown(full_text)

    def _handle_ai_error(self, error_msg: str) -> None:
        """Safely stops progress indicators and logs the error details in the conversation window."""
        self.send_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.append_system_log(f"{error_msg}")

    # ---------------------------------------------------------
    # Dashboard Control Operations
    # ---------------------------------------------------------
    def copy_ai_response(self) -> None:
        """Copies the contents of the AI response text box to clipboard."""
        response_text = self.response_view.toPlainText().strip()
        if response_text:
            QApplication.clipboard().setText(response_text)
            self.append_system_log("AI response copied to clipboard.")

    def copy_ocr_text(self) -> None:
        """Copies only the extracted OCR raw text to clipboard."""
        ocr_text = self.extracted_ocr_data.get("text", "").strip()
        if ocr_text:
            QApplication.clipboard().setText(ocr_text)
            self.append_system_log("Raw OCR recognized text copied to clipboard.")
        else:
            self.append_system_log("No OCR text available to copy. Run OCR on screenshot first.")

    def search_web_with_query(self) -> None:
        """Searches google in default web browser using OCR text or response query."""
        query = self.extracted_ocr_data.get("text", "").strip()
        if not query:
            # Fallback to selected prompt or response text
            query = self.response_view.toPlainText().strip()
            # Trim query for search efficiency if too large
            if len(query) > 250:
                query = query[:250] + "..."
                
        if query:
            webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(query)}")
            self.append_system_log(f"Opened web search browser for: '{query}'")
        else:
            self.append_system_log("Nothing to search. Capture text or run OCR first.")

    def _clear_all_logs(self) -> None:
        """Clears SQLite chat messages and screenshot tables completely."""
        confirm = QMessageBox.question(
            self,
            "Clear History",
            "Are you sure you want to permanently clear all stored screenshots and conversation histories?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.db.clear_history()
            self.clear_screenshot_preview()
            self.response_view.clear()
            self.session_id = f"sess_{int(time.time())}"
            self.append_system_log("All history cleared. Session reset.")


# ---------------------------------------------------------
# Application Entry Point
# ---------------------------------------------------------
def main() -> None:
    app = QApplication(sys.argv)
    
    # Configure high-end application traits
    app.setQuitOnLastWindowClosed(False)
    
    window = AssistantWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
