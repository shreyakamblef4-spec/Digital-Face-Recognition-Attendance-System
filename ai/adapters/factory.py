"""
AI Adapter Factory for AttendAI.
Instantiates the appropriate provider adapter according to configuration.
"""

from .base import BaseAIAdapter
from .gemini_adapter import GeminiAdapter
from .openai_adapter import OpenAIAdapter
from ..config import AIConfig


def get_ai_adapter(config: AIConfig) -> BaseAIAdapter:
    """
    Factory function returning the configured AI provider adapter.

    Supported providers:
    - 'gemini': Google Gemini native REST API
    - 'openai', 'groq', 'openai_compatible': OpenAI-compatible REST endpoint
    """
    provider = (config.provider or "gemini").lower().strip()

    if provider == "gemini":
        return GeminiAdapter(
            api_key=config.api_key,
            model=config.model or "gemini-1.5-flash",
            base_url=config.base_url,
            timeout_seconds=config.timeout_seconds,
        )
    elif provider in ("openai", "groq", "openai_compatible"):
        # Auto-configure Groq default base URL if provider is groq and no URL specified
        base_url = config.base_url
        if provider == "groq" and not base_url:
            base_url = "https://api.groq.com/openai/v1"
            if not config.model:
                config.model = "llama-3.3-70b-versatile"

        return OpenAIAdapter(
            api_key=config.api_key,
            model=config.model or "gpt-4o-mini",
            base_url=base_url,
            timeout_seconds=config.timeout_seconds,
        )
    else:
        # Default fallback to Gemini adapter
        return GeminiAdapter(
            api_key=config.api_key,
            model=config.model or "gemini-1.5-flash",
            base_url=config.base_url,
            timeout_seconds=config.timeout_seconds,
        )
