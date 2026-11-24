import sqlite3
import time
from typing import List, Dict, Any, Optional
from utils import DATABASE_PATH

class DatabaseManager:
    """Manages a single persistent SQLite connection for ScreenLens AI screenshots and chat history."""
    
    def __init__(self, db_path: str = DATABASE_PATH) -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._initialize_database()

    def _initialize_database(self) -> None:
        """Creates the screenshots and chats tables if they do not exist."""
        cursor = self.conn.cursor()
        
        # Create screenshots table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS screenshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                extracted_text TEXT DEFAULT '',
                timestamp REAL NOT NULL
            )
        """)
        
        # Create chats table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL, -- 'user' or 'assistant'
                message TEXT NOT NULL,
                timestamp REAL NOT NULL,
                screenshot_id INTEGER,
                FOREIGN KEY (screenshot_id) REFERENCES screenshots (id) ON DELETE SET NULL
            )
        """)
        self.conn.commit()

    def save_screenshot(self, file_path: str, extracted_text: str = "") -> int:
        """Saves a screenshot path and optional OCR text, returning the primary key ID."""
        timestamp = time.time()
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO screenshots (file_path, extracted_text, timestamp) VALUES (?, ?, ?)",
            (file_path, extracted_text, timestamp)
        )
        self.conn.commit()
        return cursor.lastrowid

    def update_screenshot_ocr(self, screenshot_id: int, extracted_text: str) -> None:
        """Updates the OCR text associated with a screenshot."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE screenshots SET extracted_text = ? WHERE id = ?",
            (extracted_text, screenshot_id)
        )
        self.conn.commit()

    def save_chat_message(self, session_id: str, role: str, message: str, screenshot_id: Optional[int] = None) -> int:
        """Saves a chat message under a session session_id, optionally referencing a screenshot."""
        timestamp = time.time()
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO chats (session_id, role, message, timestamp, screenshot_id) VALUES (?, ?, ?, ?, ?)",
            (session_id, role, message, timestamp, screenshot_id)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_chat_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieves chronological chat log messages for a given session ID."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT role, message, timestamp, screenshot_id FROM chats WHERE session_id = ? ORDER BY id ASC",
            (session_id,)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_screenshot_history(self) -> List[Dict[str, Any]]:
        """Retrieves screenshot records ordered from newest to oldest."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, file_path, extracted_text, timestamp FROM screenshots ORDER BY id DESC"
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def clear_history(self) -> None:
        """Truncates chats and screenshots tables, defragmenting database storage via vacuum."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM chats")
        cursor.execute("DELETE FROM screenshots")
        self.conn.commit()
        cursor.execute("VACUUM")
        self.conn.commit()

    def close(self) -> None:
        """Closes the persistent SQLite connection."""
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()

    def __del__(self) -> None:
        """Ensures the SQLite connection is closed on deletion."""
        try:
            self.close()
        except Exception:
            pass
