import re
import os
from typing import List, Dict, Any, Optional
import easyocr
import numpy as np
from PIL import Image

class OcrEngine:
    """Wrapper class for EasyOCR to perform text extraction, code snippet detection, and regex matching."""
    
    def __init__(self) -> None:
        self._reader: Optional[easyocr.Reader] = None

    def _get_reader(self) -> easyocr.Reader:
        """Lazily initializes the EasyOCR reader to optimize application startup time."""
        if self._reader is None:
            # We initialize EasyOCR with English ('en') support since Sinhala ('si') is not supported in EasyOCR.
            self._reader = easyocr.Reader(['en'], gpu=True)
        return self._reader

    def extract_text(self, image_path: str) -> Dict[str, Any]:
        """
        Runs OCR on the given image path and analyzes the text.
        Returns a dictionary containing:
          - 'text': Full raw extracted text.
          - 'code_snippets': List of detected code snippet blocks.
          - 'urls': List of unique URLs.
          - 'emails': List of unique email addresses.
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found at path: {image_path}")

        try:
            reader = self._get_reader()
            # EasyOCR can accept image paths directly
            results = reader.readtext(image_path)
            
            # Reconstruct full text from read boxes, sorting vertically and horizontally
            # results is a list of tuples: (bbox, text, confidence)
            sorted_results = sorted(results, key=lambda x: (x[0][0][1], x[0][0][0]))
            
            raw_lines: List[str] = [item[1] for item in sorted_results]
            full_text = "\n".join(raw_lines)
            
            # Extract emails and URLs
            emails = self.detect_emails(full_text)
            urls = self.detect_urls(full_text)
            
            # Detect potential code snippets
            code_snippets = self.detect_code_snippets(raw_lines)

            return {
                "text": full_text,
                "code_snippets": code_snippets,
                "urls": urls,
                "emails": emails
            }
        except Exception as e:
            # Return an empty dict structure with error text as text in case of issues
            return {
                "text": f"Error running OCR: {str(e)}",
                "code_snippets": [],
                "urls": [],
                "emails": []
            }

    def detect_emails(self, text: str) -> List[str]:
        """Detects unique email addresses using a robust regex pattern."""
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        found = re.findall(email_pattern, text)
        return sorted(list(set(found)))

    def detect_urls(self, text: str) -> List[str]:
        """Detects unique URLs (including standard domains, localhost, or IP hosts with ports)."""
        url_pattern = r'https?://(?:localhost|(?:\d{1,3}\.){3}\d{1,3}|[-a-zA-Z0-9@:%._\+~#=]+(?:\.[a-zA-Z0-9()]{1,6})?)(?::\d+)?(?:/[-a-zA-Z0-9()@:%_\+.~#?&//=]*)?'
        found = re.findall(url_pattern, text)
        return sorted(list(set(found)))

    def detect_code_snippets(self, lines: List[str]) -> List[str]:
        """
        Uses structural features and keywords to group code blocks together.
        Returns a list of extracted code block strings.
        """
        code_snippets: List[str] = []
        current_block: List[str] = []
        
        # Core structural signatures of programming languages
        code_keywords = {
            'def ', 'class ', 'import ', 'from ', 'print(', 'console.log', 
            'function ', 'let ', 'const ', 'var ', 'public ', 'private ', 
            'void ', 'using namespace', '#include', 'std::', 'elif ', 'else:', 
            'return ', 'sys.', 'os.', 'import React', '<html>', '</div>', 'SELECT ',
            'FROM ', 'WHERE ', 'INSERT INTO', 'struct ', 'fn '
        }
        
        code_chars = {'{', '}', ';', '=>', '::', '(', ')', '[', ']', '='}

        in_code_block = False
        consecutive_non_code_lines = 0

        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue

            # Heuristics to check if line looks like code
            has_keyword = any(kw in line_stripped for kw in code_keywords)
            char_count = sum(1 for c in line_stripped if c in code_chars)
            has_brackets = '{' in line_stripped or '}' in line_stripped or ';' in line_stripped
            
            # An indentation indicator (spaces in OCR might be detected as empty margins)
            # EasyOCR boxes could also be checked for structural align but line text check is easier
            is_code_line = has_keyword or (char_count >= 2 and has_brackets) or (len(line_stripped) > 4 and line_stripped.endswith(';'))

            if is_code_line:
                in_code_block = True
                consecutive_non_code_lines = 0
                current_block.append(line)
            elif in_code_block:
                # If we are in a code block, allow some plain lines (like comments or simple assignments)
                # But stop if we hit 2 consecutive lines that look strictly like normal text
                consecutive_non_code_lines += 1
                if consecutive_non_code_lines >= 2:
                    if len(current_block) >= 2:  # Save code blocks of at least 2 lines
                        code_snippets.append("\n".join(current_block))
                    current_block = []
                    in_code_block = False
                else:
                    current_block.append(line)

        if in_code_block and len(current_block) >= 1:
            code_snippets.append("\n".join(current_block))

        return code_snippets

    def extract_sinhala_text_via_ai(self, image_path: str) -> str:
        """Uses Ollama's multimodal vision model to transcribe Sinhala text directly from the image."""
        try:
            import ollama
            from utils import OLLAMA_MODEL, OLLAMA_HOST
            
            client = ollama.Client(host=OLLAMA_HOST)
            
            prompt = (
                "You are an expert Sinhala OCR system. Carefully inspect the provided image and transcribe all Sinhala text exactly as it is written. "
                "Do NOT translate the Sinhala text into English. Do NOT summarize or explain it. Do NOT write any English comments. "
                "Provide ONLY the raw Sinhala text transcribed. If no Sinhala text is detected, respond with 'No Sinhala text detected.'"
            )
            
            response = client.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [image_path]
                    }
                ]
            )
            return response.get("message", {}).get("content", "").strip()
        except Exception as e:
            return f"Sinhala AI-OCR Error: {str(e)}"
