"""
AttendAI Artificial Intelligence Subsystem.
Exports chatbot_service, AIConfig, and provider adapters.
"""

from .config import AIConfig
from .chatbot_service import ChatbotService, chatbot_service
from .adapters import (
    BaseAIAdapter,
    GeminiAdapter,
    OpenAIAdapter,
    get_ai_adapter,
    AIProviderError,
    AIAuthError,
    AIRateLimitError,
    AITimeoutError,
)

__all__ = [
    "AIConfig",
    "ChatbotService",
    "chatbot_service",
    "BaseAIAdapter",
    "GeminiAdapter",
    "OpenAIAdapter",
    "get_ai_adapter",
    "AIProviderError",
    "AIAuthError",
    "AIRateLimitError",
    "AITimeoutError",
]
