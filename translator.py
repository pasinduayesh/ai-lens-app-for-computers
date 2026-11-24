import urllib.parse
import requests
from typing import Final
import ollama
from utils import OLLAMA_MODEL, OLLAMA_HOST

class Translator:
    """Manages translation between English and Sinhala using Ollama AI or a keyless web API fallback."""
    
    SINHALA_RANGE_START: Final[str] = '\u0d80'
    SINHALA_RANGE_END: Final[str] = '\u0dff'

    def detect_language(self, text: str) -> str:
        """
        Detects if the text is primarily 'si' (Sinhala) or 'en' (English).
        Scans for any characters in the Sinhala Unicode range.
        """
        for char in text:
            if self.SINHALA_RANGE_START <= char <= self.SINHALA_RANGE_END:
                return "si"
        return "en"

    def translate(self, text: str, source_lang: str = "auto", target_lang: str = "auto") -> str:
        """
        Translates text between English and Sinhala.
        Automatically detects direction if parameters are 'auto'.
        Attempts Ollama AI translation first, then falls back to a free web API if Ollama is unavailable.
        """
        text_stripped = text.strip()
        if not text_stripped:
            return ""

        # Auto-detect language if required
        if source_lang == "auto":
            detected = self.detect_language(text_stripped)
            source_lang = detected
            target_lang = "en" if detected == "si" else "si"

        # Try Ollama translation first
        try:
            ollama_client = ollama.Client(host=OLLAMA_HOST)
            
            source_full = "Sinhala" if source_lang == "si" else "English"
            target_full = "English" if target_lang == "si" else "Sinhala"
            
            prompt = (
                f"You are a professional translator. Translate the following text from {source_full} to {target_full}. "
                f"Provide ONLY the translation, without any explanations, preambles, or formatting headers.\n\n"
                f"Text to translate:\n{text_stripped}"
            )
            
            response = ollama_client.generate(
                model=OLLAMA_MODEL,
                prompt=prompt,
                options={"temperature": 0.1, "num_predict": 1024}
            )
            
            translated_text = response.get("response", "").strip()
            if translated_text:
                return translated_text
        except Exception:
            # Fallback to keyless web translation if local Ollama fails or is unreachable
            pass

        return self._web_translate_fallback(text_stripped, source_lang, target_lang)

    def _web_translate_fallback(self, text: str, sl: str, tl: str) -> str:
        """Queries Google Translate's keyless API as a robust fallback translation method."""
        try:
            url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={sl}&tl={tl}&dt=t&q={urllib.parse.quote(text)}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                # Reconstruct full translated string from chunks
                translated_chunks = [chunk[0] for chunk in data[0] if chunk[0]]
                return "".join(translated_chunks)
            else:
                return f"[Translation Error: Web API returned status {response.status_code}]"
        except Exception as e:
            return f"[Translation Error: {str(e)}]"
