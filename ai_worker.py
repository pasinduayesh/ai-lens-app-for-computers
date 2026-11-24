import os
from typing import List, Dict, Any, Optional
from PyQt6.QtCore import QThread, pyqtSignal
import ollama
from utils import OLLAMA_MODEL, OLLAMA_HOST

class AiWorker(QThread):
    """
    Thread-safe worker executing streaming Ollama SDK queries in the background.
    Emits custom signals for UI reactivity without causing locking/freezing.
    """
    chunk_received = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self, 
        prompt: str, 
        history: List[Dict[str, Any]], 
        image_path: Optional[str] = None
    ) -> None:
        super().__init__()
        self.prompt = prompt
        self.history = history
        self.image_path = image_path

    def run(self) -> None:
        """Runs the streaming chat interface using the Ollama Client in the worker thread."""
        try:
            client = ollama.Client(host=OLLAMA_HOST)
            
            # Format and prepare messages array to send
            messages: List[Dict[str, Any]] = []
            
            # Load historical chat conversation log
            for msg in self.history:
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("message", msg.get("content", ""))
                })
            
            # Form the active prompt message
            active_message: Dict[str, Any] = {
                "role": "user",
                "content": self.prompt
            }
            
            # If a screenshot is available, attach the file path to the images parameter
            if self.image_path and os.path.exists(self.image_path):
                active_message["images"] = [self.image_path]
                
            messages.append(active_message)

            # Check if model exists, if not we try to query or fail gracefully
            # client.chat will automatically download/pull or raise an error if not found.
            # We call chat with stream=True
            stream = client.chat(
                model=OLLAMA_MODEL,
                messages=messages,
                stream=True
            )
            
            full_response = ""
            for chunk in stream:
                if self.isInterruptionRequested():
                    break
                
                # Extract character token chunk from chat payload
                chunk_text = chunk.get("message", {}).get("content", "")
                if chunk_text:
                    full_response += chunk_text
                    self.chunk_received.emit(chunk_text)
            
            if not self.isInterruptionRequested():
                self.finished.emit(full_response)
                
        except Exception as e:
            # Emit error detail back to main thread
            error_msg = str(e)
            if "connection" in error_msg.lower() or "11434" in error_msg:
                self.error.emit(
                    f"Unable to connect to Ollama local host service on {OLLAMA_HOST}. "
                    "Please ensure Ollama is running and accessible."
                )
            elif "not found" in error_msg.lower():
                self.error.emit(
                    f"Model '{OLLAMA_MODEL}' was not found. "
                    f"Please run 'ollama pull {OLLAMA_MODEL}' in your terminal."
                )
            else:
                self.error.emit(f"AI Processing Error: {error_msg}")
