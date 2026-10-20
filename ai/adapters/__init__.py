"""
AI Provider Adapters for AttendAI Chatbot.
"""

from .base import BaseAIAdapter, AIProviderError, AIAuthError, AIRateLimitError, AITimeoutError
from .gemini_adapter import GeminiAdapter
from .openai_adapter import OpenAIAdapter
from .factory import get_ai_adapter

__all__ = [
    "BaseAIAdapter",
    "GeminiAdapter",
    "OpenAIAdapter",
    "get_ai_adapter",
    "AIProviderError",
    "AIAuthError",
    "AIRateLimitError",
    "AITimeoutError",
]
