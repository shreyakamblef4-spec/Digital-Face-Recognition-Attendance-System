"""
OpenAI and OpenAI-compatible Provider Adapter using httpx.
Supports OpenAI, Groq, OpenRouter, DeepSeek, Together, Ollama, and local endpoints.
"""

import logging
from typing import List, Dict
import httpx

from .base import BaseAIAdapter, AIProviderError, AIAuthError, AIRateLimitError, AITimeoutError

logger = logging.getLogger("attendai.ai.openai")


class OpenAIAdapter(BaseAIAdapter):
    """Adapter for OpenAI and OpenAI-compatible Chat Completion APIs."""

    DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", base_url: str = "", timeout_seconds: int = 30):
        super().__init__(api_key, model, base_url or self.DEFAULT_BASE_URL, timeout_seconds)

    def generate_response(
        self,
        system_instruction: str,
        messages: List[Dict[str, str]],
        context_data: str = ""
    ) -> str:
        # Check if local endpoint without auth is being used
        is_local = "localhost" in self.base_url or "127.0.0.1" in self.base_url
        if not self.api_key and not is_local:
            raise AIAuthError("AI API key is missing. Please set AI_API_KEY in .env.")

        base = self.base_url.rstrip("/")
        if not base.endswith("/v1") and not base.endswith("/chat/completions"):
            endpoint = f"{base}/v1/chat/completions"
        elif base.endswith("/v1"):
            endpoint = f"{base}/chat/completions"
        else:
            endpoint = base

        # Combine context data into system instruction
        full_system_instruction = system_instruction
        if context_data:
            full_system_instruction += f"\n\n--- REAL-TIME ATTENDAI SYSTEM & DATABASE CONTEXT ---\n{context_data}"

        formatted_messages = [
            {"role": "system", "content": full_system_instruction}
        ]

        for msg in messages:
            role = "assistant" if msg.get("role") in ("assistant", "model") else "user"
            content = msg.get("content", "").strip()
            if content:
                formatted_messages.append({"role": role, "content": content})

        payload = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": 0.3,
            "max_tokens": 2048,
        }

        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(endpoint, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            logger.error("AI API request timed out: %s", exc)
            raise AITimeoutError("AI API request timed out. Please try again.") from exc
        except httpx.RequestError as exc:
            logger.error("AI API connection error: %s", exc)
            raise AIProviderError(f"Network error communicating with AI API: {exc}") from exc

        if response.status_code == 200:
            try:
                data = response.json()
                choices = data.get("choices", [])
                if choices:
                    first_choice = choices[0]
                    message_obj = first_choice.get("message", {})
                    return message_obj.get("content", "").strip()
                return "No response text was generated."
            except Exception as e:
                logger.error("Failed to parse AI response: %s", e)
                raise AIProviderError(f"Failed to parse AI API response: {e}") from e

        # Handle HTTP error statuses
        status = response.status_code
        err_msg = ""
        try:
            err_json = response.json()
            err_obj = err_json.get("error", {})
            err_msg = err_obj.get("message", response.text) if isinstance(err_obj, dict) else str(err_obj)
        except Exception:
            err_msg = response.text

        logger.error("AI API returned HTTP %s: %s", status, err_msg)

        if status in (401, 403):
            raise AIAuthError(f"AI API authentication failed: {err_msg}", status_code=status, details=err_msg)
        elif status == 429:
            raise AIRateLimitError(f"AI API rate limit or quota exceeded: {err_msg}", status_code=status, details=err_msg)
        else:
            raise AIProviderError(f"AI API error (HTTP {status}): {err_msg}", status_code=status, details=err_msg)
