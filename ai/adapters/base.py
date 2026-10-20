"""
Base AI Provider Adapter and unified error hierarchies.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any


class AIProviderError(Exception):
    """Base exception for AI provider errors."""
    def __init__(self, message: str, status_code: int = None, details: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class AIAuthError(AIProviderError):
    """Raised when authentication with AI provider fails (invalid/revoked API key)."""
    pass


class AIRateLimitError(AIProviderError):
    """Raised when provider returns rate limit or quota exceeded."""
    pass


class AITimeoutError(AIProviderError):
    """Raised when request to provider times out."""
    pass


class BaseAIAdapter(ABC):
    """Abstract interface for AI provider adapters."""

    def __init__(self, api_key: str, model: str, base_url: str = "", timeout_seconds: int = 30):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    @abstractmethod
    def generate_response(
        self,
        system_instruction: str,
        messages: List[Dict[str, str]],
        context_data: str = ""
    ) -> str:
        """
        Generate an AI response given system instruction, conversation history, and live context.

        Args:
            system_instruction: System prompt detailing persona, rules, role guidelines.
            messages: List of dicts with 'role' ('user' or 'assistant') and 'content'.
            context_data: Serialized real-time database context data.

        Returns:
            The string response from the AI provider.

        Raises:
            AIAuthError, AIRateLimitError, AITimeoutError, AIProviderError
        """
        raise NotImplementedError
