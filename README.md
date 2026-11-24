# 🔍 ScreenLens AI

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows%2011%20%7C%2010-0078D4?logo=windows&logoColor=white" alt="Platform" />
  <img src="https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/GUI-PyQt6-41CD52?logo=qt&logoColor=white" alt="PyQt6" />
  <img src="https://img.shields.io/badge/OCR-EasyOCR-orange" alt="EasyOCR" />
  <img src="https://img.shields.io/badge/AI%20Model-Gemma%204%20(Ollama)-FF6F00" alt="Ollama" />
  <img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License" />
</p>

**ScreenLens AI** is a next-generation desktop screen intelligence assistant for Windows 11. Inspired by Google Lens and Circle to Search, it enables users to seamlessly freeze, circle, or crop any part of their screen to instantly copy text, extract Sinhala text using AI vision, translate, search the web, and stream follow-up conversational answers with local LLMs.

---

## ✨ Key Features

- 🎯 **Circle to Search & Dynamic Cropping:**
  - Freeform lasso drawing that snaps to a bounding box or precise corner bracket resizing.
  - Floating glassmorphic contextual menu pill directly over your selection (*Ask AI*, *Copy Text*, *Translate*).
- 🖥️ **Pixel-Perfect High-DPI Support:**
  - Per-Monitor DPI Aware V2 support with native hardware frame-buffer capture. Zero zoom or edge-overflow glitches on 125%, 150%, or 200% display scaling.
- ⚡ **Global Hotkey Activation:**
  - Activate instantly from anywhere using `Ctrl + Shift + S`.
- 📄 **Instant Offline OCR:**
  - Local EasyOCR engine for English text, code snippet formatting, emails, and URLs.
- 🌐 **Sinhala Text Extraction & Translation:**
  - Powered by Ollama Vision AI for high-accuracy Sinhala Unicode text recognition and contextual translations.
- 🧠 **Interactive AI Streaming Assistant:**
  - Always-on-top draggable assistant window with real-time response streaming and persistent SQLite chat history.
- 📦 **1-Click Standalone Windows Setup Installer:**
  - Pre-compiled standalone setup package (`ScreenLens_AI_Setup.exe`) with desktop shortcuts, system specs verification, and clean Windows Uninstaller registration.

---

## 📁 Project Architecture & Components

The codebase consists of modular OOP Python scripts:

* **`app.py`**: The main orchestrator and floating frameless always-on-top assistant window. Handles boundary clamping, resizing, and threaded background workers.
* **`overlay.py`**: Full-screen Circle-to-Search selection overlay with multi-monitor support, native Qt hardware frame-buffer capture, and contextual pill menu.
* **`ai_worker.py`**: Thread-safe worker inheriting from `QThread` streaming responses using Ollama client with multimodal image attachments.
* **`ocr_engine.py`**: EasyOCR wrapper with regex parsers for code, URLs, and emails, plus Ollama-based **AI Sinhala OCR**.
* **`translator.py`**: English ↔ Sinhala translator with automatic script detection and keyless fallback.
* **`history.py`**: Persistent SQLite database manager for chat history and screenshot metadata.
* **`tray.py`**: System tray icon with quick capture, hide/show, history reset, and exit options.
* **`utils.py`**: High-DPI configurations, operational constants, and custom dark stylesheets.

---

## 🚀 Getting Started

### Option 1: Standalone Installer (Recommended for End-Users)
1. Run `ScreenLens_AI_Setup.exe` from the `ScreenLens_AI_Installer/` folder or download it from Releases.
2. Follow the setup wizard to install into your programs folder.
3. Press `Ctrl + Shift + S` from any screen to begin capturing!

*(Optional for AI Vision)*: Run `setup_ollama_ai.bat` to install Ollama and pull the Gemma model:
```bash
ollama run gemma4:31b-cloud
```

---

### Option 2: Running from Source (For Developers)

#### Prerequisites
- Windows 10 or 11 (64-bit)
- Python 3.10+ (Tested up to Python 3.14)

#### Installation
```bash
# 1. Clone the repository
git clone https://github.com/pasinduayesh/ai-lens-app-for-computers.git
cd ai-lens-app-for-computers

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch the application
python app.py
```

---

## ⌨️ Shortcuts & Controls

- **`Ctrl + Shift + S`** : Activate Circle-to-Search Screen Capture
- **`Esc`** : Cancel Screen Capture
- **`Enter`** : Validate selection and route directly to AI Assistant
- **`Left Click + Drag`** : Freeform circle / box selection
- **`Drag Handles`** : Resize active selection box

---

## 📄 License
This project is licensed under the MIT License - see the LICENSE file for details.
