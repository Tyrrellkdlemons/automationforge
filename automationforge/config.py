"""Shared configuration loaded from environment / sensible defaults."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Project root = parent of the automationforge package
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

# Data & logs
DATA_DIR = Path(os.getenv("AF_DATA_DIR", str(ROOT_DIR)))
PERSONAL_DATA_PATH = DATA_DIR / os.getenv("AF_PERSONAL_DATA", "personal_data.json")
APPLICATION_LOG_PATH = DATA_DIR / os.getenv("AF_APPLICATION_LOG", "application_log.json")
LOGS_DIR = DATA_DIR / os.getenv("AF_LOGS_DIR", "logs")
SCREENSHOTS_DIR = DATA_DIR / os.getenv("AF_SCREENSHOTS_DIR", "screenshots")

# Browser
HEADLESS = os.getenv("AF_HEADLESS", "false").lower() in ("1", "true", "yes")
BROWSER_TIMEOUT_MS = int(os.getenv("AF_BROWSER_TIMEOUT_MS", "30000"))
MAX_RETRIES = int(os.getenv("AF_MAX_RETRIES", "3"))
TYPING_DELAY_MS_MIN = int(os.getenv("AF_TYPING_DELAY_MS_MIN", "40"))
TYPING_DELAY_MS_MAX = int(os.getenv("AF_TYPING_DELAY_MS_MAX", "120"))
ACTION_PAUSE_MS_MIN = int(os.getenv("AF_ACTION_PAUSE_MS_MIN", "200"))
ACTION_PAUSE_MS_MAX = int(os.getenv("AF_ACTION_PAUSE_MS_MAX", "800"))

# LLM — Ollama preferred, OpenAI-compatible fallback
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
LLM_PROVIDER = os.getenv("AF_LLM_PROVIDER", "auto")  # auto | ollama | openai | anthropic
LLM_TEMPERATURE = float(os.getenv("AF_LLM_TEMPERATURE", "0.2"))
LLM_MAX_TOKENS = int(os.getenv("AF_LLM_MAX_TOKENS", "4096"))

# Email
TIGRMAIL_API_KEY = os.getenv("TIGRMAIL_API_KEY", "")
TIGRMAIL_BASE_URL = os.getenv("TIGRMAIL_BASE_URL", "https://api.tigrmail.com")
# Gmail IMAP (optional)
GMAIL_IMAP_HOST = os.getenv("GMAIL_IMAP_HOST", "imap.gmail.com")
GMAIL_IMAP_USER = os.getenv("GMAIL_IMAP_USER", "")
GMAIL_IMAP_PASSWORD = os.getenv("GMAIL_IMAP_PASSWORD", "")  # app password
GMAIL_IMAP_FOLDER = os.getenv("GMAIL_IMAP_FOLDER", "INBOX")

# Ensure runtime dirs exist
LOGS_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
