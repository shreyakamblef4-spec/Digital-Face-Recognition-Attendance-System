"""
AI Chatbot configuration management.
Centralized loading of AI provider settings, timeouts, and rate limits.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class AIConfig:
    """Configuration data object for the AI Chatbot subsystem."""
    provider: str
    api_key: str
    model: str
    base_url: str
    timeout_seconds: int
    rate_limit: int

    @classmethod
    def from_env(cls) -> "AIConfig":
        """Load AI configuration from environment variables or Flask config."""
        try:
            from dotenv import load_dotenv
            load_dotenv(override=False)
        except Exception:
            pass

        provider = os.getenv("AI_PROVIDER", "gemini").strip().lower()
        api_key = os.getenv("AI_API_KEY", "").strip()
        model = os.getenv("AI_MODEL", "").strip()

        # Provide sensible default model per provider if none set
        if not model or (provider == "gemini" and model in ("gemini-1.5-flash", "gemini-2.5-flash")):
            if provider == "gemini":
                model = "gemini-3.6-flash"
            elif provider in ("openai", "groq", "openai_compatible"):
                model = "gpt-4o-mini"
            else:
                model = "gemini-3.6-flash"

        base_url = os.getenv("AI_BASE_URL", "").strip()
        try:
            timeout_seconds = int(os.getenv("AI_TIMEOUT_SECONDS", "30"))
        except ValueError:
            timeout_seconds = 30

        try:
            rate_limit = int(os.getenv("CHAT_RATE_LIMIT", "30"))
        except ValueError:
            rate_limit = 30

        return cls(
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            rate_limit=rate_limit,
        )

    def is_configured(self) -> bool:
        """Check if an API key or local endpoint is configured."""
        # For local endpoints (e.g. Ollama), an empty API key might be allowed if base_url is specified
        if "localhost" in self.base_url or "127.0.0.1" in self.base_url:
            return True
        return bool(self.api_key)
