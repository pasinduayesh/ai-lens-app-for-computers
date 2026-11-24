import os
import time
from typing import List, Dict, Any, Optional, Callable
from PyQt6.QtCore import Qt, QRect, QRectF, QPoint, QSize, pyqtSignal, QObject, QThread
from PyQt6.QtGui import QPainter, QPainterPath, QColor, QPen, QBrush, QPixmap, QImage, QGuiApplication, QScreen
from PyQt6.QtWidgets import QWidget, QFrame, QPushButton, QHBoxLayout, QLabel, QVBoxLayout, QGraphicsDropShadowEffect

import mss
from PIL import Image

from utils import SCREENSHOTS_DIR, initialize_directories
from ocr_engine import OcrEngine
from translator import Translator

# ---------------------------------------------------------
# Background Worker Threads for Overlay Contextual Actions
# ---------------------------------------------------------

class OverlayOcrWorker(QThread):
    """Background worker to run OCR on the active cropped selection inside the overlay itself."""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, image_path: str) -> None:
        super().__init__()
        self.image_path = image_path
        self.ocr_engine = OcrEngine()

    def run(self) -> None:
        try:
            results = self.ocr_engine.extract_text(self.image_path)
            raw_text = results.get("text", "").strip()
            self.finished.emit(raw_text)
        except Exception as e:
            self.error.emit(str(e))


class OverlayTranslateWorker(QThread):
    """Background worker to translate the cropped OCR text within the overlay."""
    finished = pyqtSignal(str)

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text
        self.translator = Translator()

    def run(self) -> None:
        try:
            res = self.translator.translate(self.text)
            self.finished.emit(res)
        except Exception as e:
            self.finished.emit(f"Translation Error: {str(e)}")

# ---------------------------------------------------------
# Dynamic Floating Pill Menu Bar (Google Lens Style)
# ---------------------------------------------------------

class FloatingMenuBar(QFrame):
    """Pill-shaped glassmorphic menu that floats directly over the active crop box."""
    
    def __init__(self, parent: QWidget, on_ask: Callable[[], None], on_copy: Callable[[], None], on_translate: Callable[[], None], on_cancel: Callable[[], None]) -> None:
        super().__init__(parent)
        self.setObjectName("FloatingPill")
        
        self.on_ask = on_ask
        self.on_copy = on_copy
        self.on_translate = on_translate
        self.on_cancel = on_cancel
        
        # Sleek borderless container styling
        self.setStyleSheet("""
            QFrame#FloatingPill {
                background-color: rgba(16, 18, 22, 235);
                border: 1.5px solid rgba(51, 136, 255, 180);
                border-radius: 20px;
            }
            QPushButton {
                background-color: transparent;
                border: none;
                color: #f1f3f7;
                font-family: "Segoe UI", sans-serif;
                font-size: 11px;
                font-weight: 600;
                padding: 6px 14px;
                border-radius: 15px;
            }
            QPushButton:hover {
                background-color: rgba(51, 136, 255, 80);
            }
            QPushButton#AskBtn {
                background-color: #3388ff;
                color: #ffffff;
            }
            QPushButton#AskBtn:hover {
                background-color: #4d9cff;
            }
            QPushButton#CancelBtn:hover {
                background-color: rgba(234, 67, 53, 100);
                color: #ff6659;
            }
        """)
        
        # Add drop shadow for glass float effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)
        
        self._init_layout()

    def _init_layout(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)
        
        # 1. Ask AI (Primary)
        self.ask_btn = QPushButton("🧠 Ask AI")
        self.ask_btn.setObjectName("AskBtn")
        self.ask_btn.clicked.connect(self.on_ask)
        layout.addWidget(self.ask_btn)
        
        # 2. Copy Text
        self.copy_btn = QPushButton("📄 Copy Text")
        self.copy_btn.clicked.connect(self.on_copy)
        layout.addWidget(self.copy_btn)
        
        # 3. Translate
        self.translate_btn = QPushButton("🌐 Translate")
        self.translate_btn.clicked.connect(self.on_translate)
        layout.addWidget(self.translate_btn)
        
        # 4. Cancel
        self.cancel_btn = QPushButton("✕")
        self.cancel_btn.setObjectName("CancelBtn")
        self.cancel_btn.setFixedSize(30, 30)
        self.cancel_btn.clicked.connect(self.on_cancel)
        layout.addWidget(self.cancel_btn)
        
        self.adjustSize()

# ---------------------------------------------------------
# Core Custom Multi-Monitor Overlay Window
# ---------------------------------------------------------

class OverlaySignalEmitter(QObject):
    """Signals bridge for coordinate handlers."""
    screenshot_captured = pyqtSignal(str)
    capture_cancelled = pyqtSignal()


class OverlayWindow(QWidget):
    """
    Custom-painted borderless overlay window supporting Circle to Search drawing,
    dynamic bounding box fitting, resizable corner handles, and contextual actions.
    """
    
    def __init__(
        self, 
        screen: QScreen, 
        background_pixmap: QPixmap, 
        emitter: OverlaySignalEmitter
    ) -> None:
        super().__init__()
        self.screen = screen
        self.background_pixmap = background_pixmap
        self.emitter = emitter
        
        # Frameless always-on-top fullscreen
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        self.setGeometry(screen.geometry())
        self.setMouseTracking(True)
        
        # Selection and Freeform drawing variables
        self.selection_rect: Optional[QRect] = None
        self.drawn_points: List[QPoint] = []
        
        # Resizing and movement handles state
        self.active_handle: Optional[str] = None # 'top-left', 'top-right', 'bottom-left', 'bottom-right', 'move', 'new'
        self.drag_offset = QPoint()
        self.is_adjusting = False # Enters adjustment mode once first crop is confirmed
        self.corner_bracket_size = 18
        self.handle_detection_size = 24
        
        # Floating elements
        self.menu_bar: Optional[FloatingMenuBar] = None
        self.tooltip_bubble: Optional[QLabel] = None
        
        self.setCursor(Qt.CursorShape.CrossCursor)

    def paintEvent(self, event: Any) -> None:
        """Paints desktop capture, dimming overlay, freeform loops, selection box, and brackets."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 1. Paint frozen desktop screenshot background
        painter.drawPixmap(self.rect(), self.background_pixmap)
        
        dimming_color = QColor(0, 0, 0, 130) # Elegant dark overlay dim
        
        # Case A: User is currently drawing a free-form loop (Circle to Search)
        if self.active_handle == "new" and self.drawn_points:
            # Dim the background screen
            painter.fillRect(self.rect(), dimming_color)
            
            # Paint the glowing freeform trace stroke (white/cyan)
            pen = QPen(QColor(255, 255, 255, 220), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            
            # Draw the trace lines
            for i in range(len(self.drawn_points) - 1):
                painter.drawLine(self.drawn_points[i], self.drawn_points[i+1])
                
        # Case B: Crop selection box is active
        elif self.selection_rect and not self.selection_rect.isEmpty():
            rect = self.selection_rect.normalized()
            
            # 2. Draw surrounding dimmed area with seamless cutout hole
            dim_path = QPainterPath()
            dim_path.addRect(QRectF(self.rect()))
            dim_path.addRect(QRectF(rect))
            painter.fillPath(dim_path, dimming_color)
            
            # 3. Draw glowing blue thin border
            pen = QPen(QColor(51, 136, 255), 1.5, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)
            
            # 4. Draw Google Lens style thick white corner brackets
            painter.setPen(QPen(QColor(255, 255, 255), 4.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            
            # Top-Left Bracket
            painter.drawLine(rect.left(), rect.top() + self.corner_bracket_size, rect.left(), rect.top())
            painter.drawLine(rect.left(), rect.top(), rect.left() + self.corner_bracket_size, rect.top())
            
            # Top-Right Bracket
            painter.drawLine(rect.right(), rect.top() + self.corner_bracket_size, rect.right(), rect.top())
            painter.drawLine(rect.right(), rect.top(), rect.right() - self.corner_bracket_size, rect.top())
            
            # Bottom-Left Bracket
            painter.drawLine(rect.left(), rect.bottom() - self.corner_bracket_size, rect.left(), rect.bottom())
            painter.drawLine(rect.left(), rect.bottom(), rect.left() + self.corner_bracket_size, rect.bottom())
            
            # Bottom-Right Bracket
            painter.drawLine(rect.right(), rect.bottom() - self.corner_bracket_size, rect.right(), rect.bottom())
            painter.drawLine(rect.right(), rect.bottom(), rect.right() - self.corner_bracket_size, rect.bottom())
            
            # 5. Draw dimensions coordinate text
            res_text = f"{rect.width()} × {rect.height()} px"
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QGuiApplication.font())
            text_rect = QRect(rect.left() + 6, rect.top() - 25, 120, 20)
            if rect.top() < 30:
                text_rect = QRect(rect.left() + 6, rect.top() + 6, 120, 20)
            
            painter.fillRect(text_rect, QColor(16, 18, 22, 220))
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, res_text)
        else:
            # Full dim if idle
            painter.fillRect(self.rect(), dimming_color)

    # ---------------------------------------------------------
    # Input Interaction & Resizing Logic
    # ---------------------------------------------------------
    def mousePressEvent(self, event: Any) -> None:
        """Determines if clicking handle, panning, or starting a new Circle to Search loop."""
        # Using event.pos() for absolute 100% version compatibility (fixes position() AttributeError)
        pos = event.pos()
        
        # Hide active translation tooltips on click
        if self.tooltip_bubble:
            self.tooltip_bubble.deleteLater()
            self.tooltip_bubble = None

        if event.button() == Qt.MouseButton.LeftButton:
            if self.is_adjusting and self.selection_rect:
                rect = self.selection_rect.normalized()
                left, top, right, bottom = rect.left(), rect.top(), rect.right(), rect.bottom()
                
                # Check corners coordinates
                if (pos - QPoint(left, top)).manhattanLength() < self.handle_detection_size:
                    self.active_handle = "top-left"
                elif (pos - QPoint(right, top)).manhattanLength() < self.handle_detection_size:
                    self.active_handle = "top-right"
                elif (pos - QPoint(left, bottom)).manhattanLength() < self.handle_detection_size:
                    self.active_handle = "bottom-left"
                elif (pos - QPoint(right, bottom)).manhattanLength() < self.handle_detection_size:
                    self.active_handle = "bottom-right"
                elif rect.contains(pos):
                    # Pan selection area
                    self.active_handle = "move"
                    self.drag_offset = pos - rect.topLeft()
                else:
                    # Clicked outside: redraw a new free-form selection
                    self.active_handle = "new"
                    self.drawn_points = [pos]
                    self.selection_rect = None
                    self.is_adjusting = False
                    if self.menu_bar:
                        self.menu_bar.hide()
            else:
                # First ever click: start free-form drawing
                self.active_handle = "new"
                self.drawn_points = [pos]
                self.selection_rect = None
            
            self.update()

    def mouseMoveEvent(self, event: Any) -> None:
        """Tracks coordinates, adjusts custom resize cursor states, and draws free-form loop traces."""
        pos = event.pos()
        
        # Cursor styling updates depending on proximity to corner handles
        if self.is_adjusting and self.selection_rect and not event.buttons():
            rect = self.selection_rect.normalized()
            left, top, right, bottom = rect.left(), rect.top(), rect.right(), rect.bottom()
            
            if (pos - QPoint(left, top)).manhattanLength() < self.handle_detection_size:
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif (pos - QPoint(right, top)).manhattanLength() < self.handle_detection_size:
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            elif (pos - QPoint(left, bottom)).manhattanLength() < self.handle_detection_size:
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            elif (pos - QPoint(right, bottom)).manhattanLength() < self.handle_detection_size:
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif rect.contains(pos):
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.setCursor(Qt.CursorShape.CrossCursor)
        
        # Actively applying changes on drag
        if event.buttons() == Qt.MouseButton.LeftButton:
            if self.active_handle == "new":
                self.drawn_points.append(pos)
            elif self.selection_rect:
                rect = self.selection_rect
                if self.active_handle == "move":
                    new_top_left = pos - self.drag_offset
                    new_rect = QRect(new_top_left, rect.size())
                    if self.rect().contains(new_rect):
                        self.selection_rect = new_rect
                elif self.active_handle == "top-left":
                    self.selection_rect = QRect(pos, rect.bottomRight())
                elif self.active_handle == "top-right":
                    self.selection_rect = QRect(QPoint(rect.left(), pos.y()), QPoint(pos.x(), rect.bottom()))
                elif self.active_handle == "bottom-left":
                    self.selection_rect = QRect(QPoint(pos.x(), rect.top()), QPoint(rect.right(), pos.y()))
                elif self.active_handle == "bottom-right":
                    self.selection_rect = QRect(rect.topLeft(), pos)
            
            self.update()
            
            # Re-position menu bar on drag moves
            if self.menu_bar and self.menu_bar.isVisible():
                self._reposition_menu_bar()

    def mouseReleaseEvent(self, event: Any) -> None:
        """Stops active resizing and locks position, invoking the floating actions menu bar."""
        if event.button() == Qt.MouseButton.LeftButton:
            if self.active_handle == "new" and len(self.drawn_points) > 2:
                # Calculate the bounding box that fits the hand-drawn circle/loop
                xs = [p.x() for p in self.drawn_points]
                ys = [p.y() for p in self.drawn_points]
                
                xmin, xmax = min(xs), max(xs)
                ymin, ymax = min(ys), max(ys)
                
                width = xmax - xmin
                height = ymax - ymin
                
                # Check for minimum crop size
                if width > 10 and height > 10:
                    self.selection_rect = QRect(xmin, ymin, width, height)
                    self.is_adjusting = True
                    self._show_floating_menu_bar()
                else:
                    self.selection_rect = None
                    self.is_adjusting = False
                    if self.menu_bar:
                        self.menu_bar.hide()
                        
                self.drawn_points = []
            
            self.active_handle = None
            self.update()

    def keyPressEvent(self, event: Any) -> None:
        """Escape cancels selection, Enter validates crop and sends to AI."""
        if event.key() == Qt.Key.Key_Escape:
            self.emitter.capture_cancelled.emit()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.handle_action_ask()

    # ---------------------------------------------------------
    # Floating Pill & Tooltip Placements
    # ---------------------------------------------------------
    def _show_floating_menu_bar(self) -> None:
        """Creates or restores the floating pill control menu."""
        if not self.menu_bar:
            self.menu_bar = FloatingMenuBar(
                parent=self,
                on_ask=self.handle_action_ask,
                on_copy=self.handle_action_copy,
                on_translate=self.handle_action_translate,
                on_cancel=self.emitter.capture_cancelled.emit
            )
        
        self._reposition_menu_bar()
        self.menu_bar.show()
        self.menu_bar.raise_()

    def _reposition_menu_bar(self) -> None:
        """Aligns the menu pill directly above the selection, or underneath if pressed against screen edge."""
        if not self.selection_rect or not self.menu_bar:
            return
            
        rect = self.selection_rect
        menu_width = self.menu_bar.width()
        
        # Center horizontally relative to crop rectangle
        x = rect.left() + (rect.width() - menu_width) // 2
        # Bound limit horizontally
        x = max(10, min(self.width() - menu_width - 10, x))
        
        # Position 45px above rect. If too close to screen top, position 15px below rect bottom.
        y = rect.top() - 48
        if y < 10:
            y = rect.bottom() + 12
            
        self.menu_bar.move(x, y)

    def _save_active_crop(self) -> str:
        """Crops the background desktop capture coordinates and saves to disk."""
        if not self.selection_rect:
            return ""
            
        rect = self.selection_rect.normalized()
        dpr = self.screen.devicePixelRatio()
        
        # Physical coordinates for the crop to preserve full screen fidelity
        phys_rect = QRect(
            int(round(rect.x() * dpr)),
            int(round(rect.y() * dpr)),
            int(round(rect.width() * dpr)),
            int(round(rect.height() * dpr))
        )
        
        # Clamp to physical background bounds
        bg_bounds = QRect(0, 0, self.background_pixmap.width(), self.background_pixmap.height())
        phys_rect = phys_rect.intersected(bg_bounds)
        if phys_rect.isEmpty():
            return ""
            
        cropped = self.background_pixmap.copy(phys_rect)
        initialize_directories()
        
        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        save_path = os.path.normpath(os.path.join(SCREENSHOTS_DIR, f"cap_{timestamp_str}.png"))
        cropped.save(save_path, "PNG")
        return save_path

    # ---------------------------------------------------------
    # Floating Actions Routing (Copy, Translate, Ask AI)
    # ---------------------------------------------------------
    def handle_action_ask(self) -> None:
        """Saves cropped selection and routes coordinates to AI Assistant orchestrator."""
        save_path = self._save_active_crop()
        if save_path:
            self.emitter.screenshot_captured.emit(save_path)
            if self.menu_bar:
                self.menu_bar.hide()
            self.close()

    def handle_action_copy(self) -> None:
        """Performs localized background OCR on selection and copies text instantly."""
        save_path = self._save_active_crop()
        if not save_path or not self.menu_bar:
            return
            
        self.menu_bar.copy_btn.setText("OCR-ing...")
        self.menu_bar.copy_btn.setEnabled(False)
        
        # Start background threaded OCR to prevent freezing overlay dragging
        self.ocr_worker = OverlayOcrWorker(save_path)
        self.ocr_worker.finished.connect(lambda txt: self._handle_copy_success(txt, save_path))
        self.ocr_worker.error.connect(lambda err: self._handle_copy_error(err))
        self.ocr_worker.start()

    def _handle_copy_success(self, text: str, temp_path: str) -> None:
        """Copies text to clipboard and updates pill text."""
        self.menu_bar.copy_btn.setText("📄 Copy Text")
        self.menu_bar.copy_btn.setEnabled(True)
        
        # Clean temporary file
        try:
            os.remove(temp_path)
        except Exception:
            pass
            
        if text.strip():
            QGuiApplication.clipboard().setText(text)
            self._show_floating_status_badge("Text Copied!")
        else:
            self._show_floating_status_badge("No text found.")

    def _handle_copy_error(self, error: str) -> None:
        self.menu_bar.copy_btn.setText("📄 Copy Text")
        self.menu_bar.copy_btn.setEnabled(True)
        self._show_floating_status_badge("OCR Failed.")

    def handle_action_translate(self) -> None:
        """Performs background OCR, feeds text into Translator, and displays in bubble."""
        save_path = self._save_active_crop()
        if not save_path or not self.menu_bar:
            return
            
        self.menu_bar.translate_btn.setText("Translating...")
        self.menu_bar.translate_btn.setEnabled(False)
        
        # Extract text first
        self.trans_ocr_worker = OverlayOcrWorker(save_path)
        self.trans_ocr_worker.finished.connect(lambda txt: self._start_translation_phase(txt, save_path))
        self.trans_ocr_worker.error.connect(lambda err: self._handle_trans_error(err))
        self.trans_ocr_worker.start()

    def _start_translation_phase(self, text: str, temp_path: str) -> None:
        try:
            os.remove(temp_path)
        except Exception:
            pass
            
        if not text.strip():
            self.menu_bar.translate_btn.setText("🌐 Translate")
            self.menu_bar.translate_btn.setEnabled(True)
            self._show_floating_status_badge("No text to translate.")
            return
            
        # Run background translation
        self.trans_worker = OverlayTranslateWorker(text)
        self.trans_worker.finished.connect(self._handle_translation_success)
        self.trans_worker.start()

    def _handle_translation_success(self, translated_text: str) -> None:
        self.menu_bar.translate_btn.setText("🌐 Translate")
        self.menu_bar.translate_btn.setEnabled(True)
        
        # Display translation in a beautiful overlay glassmorphic tooltip bubble inside the crop
        self._show_translation_bubble(translated_text)

    def _handle_trans_error(self, err: str) -> None:
        self.menu_bar.translate_btn.setText("🌐 Translate")
        self.menu_bar.translate_btn.setEnabled(True)
        self._show_floating_status_badge("Translate Failed.")

    def _show_floating_status_badge(self, text: str) -> None:
        """Draws a floating visual status label that fades out quickly."""
        badge = QLabel(text, self)
        badge.setStyleSheet("""
            background-color: rgba(51, 136, 255, 230);
            color: white;
            font-family: "Segoe UI", sans-serif;
            font-size: 11px;
            font-weight: bold;
            padding: 6px 16px;
            border-radius: 12px;
        """)
        
        # Align center right above the menu pill
        menu_pos = self.menu_bar.pos()
        badge.move(menu_pos.x() + (self.menu_bar.width() - badge.width()) // 2, menu_pos.y() - 32)
        badge.show()
        badge.raise_()
        
        # Quick autodelete timer
        time_to_delete = 1200 # ms
        def fade():
            badge.deleteLater()
            
        import PyQt6.QtCore as QtCore
        QtCore.QTimer.singleShot(time_to_delete, fade)

    def _show_translation_bubble(self, translated_text: str) -> None:
        """Draws a floating rounded translation card inside the active selection rectangle."""
        if self.tooltip_bubble:
            self.tooltip_bubble.deleteLater()
            
        self.tooltip_bubble = QLabel(translated_text, self)
        self.tooltip_bubble.setWordWrap(True)
        self.tooltip_bubble.setStyleSheet("""
            background-color: rgba(26, 29, 36, 240);
            color: #f1f3f7;
            font-family: "Segoe UI", sans-serif;
            font-size: 12.5px;
            padding: 10px 14px;
            border-radius: 8px;
            border: 1px solid rgba(51, 136, 255, 120);
        """)
        
        # Size and position calculation (Center of selection rectangle)
        rect = self.selection_rect.normalized()
        self.tooltip_bubble.setFixedWidth(min(320, max(200, rect.width() - 20)))
        self.tooltip_bubble.adjustSize()
        
        x = rect.left() + (rect.width() - self.tooltip_bubble.width()) // 2
        y = rect.top() + (rect.height() - self.tooltip_bubble.height()) // 2
        
        # Keep inside crop rectangle bounds
        x = max(rect.left() + 5, min(rect.right() - self.tooltip_bubble.width() - 5, x))
        y = max(rect.top() + 5, min(rect.bottom() - self.tooltip_bubble.height() - 5, y))
        
        self.tooltip_bubble.move(x, y)
        self.tooltip_bubble.show()
        self.tooltip_bubble.raise_()


class OverlayController:
    """Manages spawning overlay selector windows across all connected display monitor devices."""
    
    def __init__(self, callback: Callable[[str], None]) -> None:
        self.callback = callback
        self.windows: List[OverlayWindow] = []
        self.emitter = OverlaySignalEmitter()
        self.emitter.screenshot_captured.connect(self.callback)
        self.emitter.capture_cancelled.connect(self.close_all)

    def trigger_overlay(self) -> None:
        """Takes desktop screenshots on all monitors using MSS and shows the crop overlays."""
        self.close_all()
        
        screens = QGuiApplication.screens()
        if not screens:
            return
            
        for screen in screens:
            dpr = screen.devicePixelRatio()
            geom = screen.geometry()
            
            # Primary: Native hardware compositor grab (100% pixel-perfect 1:1, zero zoom/cut-off error)
            try:
                pixmap = screen.grabWindow(0)
                pixmap.setDevicePixelRatio(dpr)
            except Exception:
                # Fallback to MSS
                sct_cls = getattr(mss, "MSS", mss.mss)
                with sct_cls() as sct:
                    monitor = {
                        "top": int(round(geom.y() * dpr)),
                        "left": int(round(geom.x() * dpr)),
                        "width": int(round(geom.width() * dpr)),
                        "height": int(round(geom.height() * dpr))
                    }
                    sct_img = sct.grab(monitor)
                    pil_img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                    bytes_img = pil_img.tobytes("raw", "RGBA")
                    q_img = QImage(bytes_img, pil_img.size[0], pil_img.size[1], QImage.Format.Format_RGBA8888)
                    q_img.setDevicePixelRatio(dpr)
                    pixmap = QPixmap.fromImage(q_img)
                    pixmap.setDevicePixelRatio(dpr)
            
            window = OverlayWindow(
                screen=screen,
                background_pixmap=pixmap,
                emitter=self.emitter
            )
            self.windows.append(window)
        
        for win in self.windows:
            win.setScreen(win.screen)
            win.setGeometry(win.screen.geometry())
            win.showFullScreen()
            win.activateWindow()
            win.raise_()

    def close_all(self) -> None:
        """Gracefully closes all open overlay selector windows and releases resources."""
        for win in self.windows:
            # Delete child overlays explicitly
            if win.menu_bar:
                win.menu_bar.deleteLater()
            if win.tooltip_bubble:
                win.tooltip_bubble.deleteLater()
            win.close()
        self.windows.clear()
