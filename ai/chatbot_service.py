"""
AttendAI Centralized Chatbot Service.
Coordinates rate limiting, role policies, ground-truth database context,
persistent conversation history, and adapter execution.
"""

import time
import uuid
import logging
from typing import Dict, Any, Optional, List
from collections import defaultdict

from .config import AIConfig
from .prompts import build_system_instruction
from .context_builder import build_database_context
from .adapters import (
    get_ai_adapter,
    AIProviderError,
    AIAuthError,
    AIRateLimitError,
    AITimeoutError,
)

logger = logging.getLogger("attendai.chatbot")


class RateLimiter:
    """Thread-safe sliding-window rate limiter per user."""

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)

    def is_allowed(self, user_key: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds
        # Clean older entries
        self.requests[user_key] = [t for t in self.requests[user_key] if t > window_start]

        if len(self.requests[user_key]) >= self.max_requests:
            return False

        self.requests[user_key].append(now)
        return True


class ChatbotService:
    """Centralized service managing all chatbot interactions."""

    def __init__(self):
        self.config = AIConfig.from_env()
        self.rate_limiter = RateLimiter(
            max_requests=self.config.rate_limit,
            window_seconds=60
        )

    def reload_config(self):
        """Reload configuration from environment."""
        self.config = AIConfig.from_env()
        self.rate_limiter = RateLimiter(
            max_requests=self.config.rate_limit,
            window_seconds=60
        )

    def handle_message(
        self,
        user_info: Dict[str, Any],
        message_text: str,
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Main processing method for an incoming chat message.

        Args:
            user_info: Dict containing 'user_id', 'role', 'name', 'email'.
            message_text: User message string.
            conversation_id: Optional existing conversation identifier.

        Returns:
            Dict: {'success': bool, 'message': str, 'conversation_id': str, 'error_type': Optional[str]}
        """
        user_id = user_info.get("user_id")
        user_role = (user_info.get("role") or "student").lower().strip()
        user_name = user_info.get("name", "User")

        if not conversation_id or not conversation_id.strip():
            conversation_id = uuid.uuid4().hex

        # 1. Rate Limiting Check
        rate_key = f"user_{user_id}" if user_id else "anonymous"
        if not self.rate_limiter.is_allowed(rate_key):
            return {
                "success": False,
                "message": "Rate limit exceeded. Please wait a moment before sending more messages.",
                "conversation_id": conversation_id,
                "error_type": "rate_limit"
            }

        # 2. Check if AI Provider is configured
        # Always reload in case .env changed
        self.config = AIConfig.from_env()
        if not self.config.is_configured():
            return {
                "success": False,
                "message": "AI chatbot is not configured. Please configure the AI API key in .env.",
                "conversation_id": conversation_id,
                "error_type": "not_configured"
            }

        from models import ChatMessage
        from database import db

        # 3. Retrieve recent conversation history from database
        history_records = []
        if user_id:
            try:
                history_records = ChatMessage.query.filter_by(
                    conversation_id=conversation_id,
                    user_id=user_id
                ).order_by(ChatMessage.timestamp.asc()).limit(12).all()
            except Exception as e:
                logger.warning("Could not load chat history: %s", e)

        messages_payload = []
        for rec in history_records:
            messages_payload.append({
                "role": "assistant" if rec.sender == "assistant" else "user",
                "content": rec.message
            })

        # Append current user message
        messages_payload.append({
            "role": "user",
            "content": message_text
        })

        # 4. Save User Message to Database
        if user_id:
            try:
                user_msg_entry = ChatMessage(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role=user_role,
                    sender="user",
                    message=message_text
                )
                db.session.add(user_msg_entry)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.warning("Could not save user message: %s", e)

        # 5. Build System Prompt & Live DB Context
        system_instruction = build_system_instruction(user_role, user_name)
        db_context = build_database_context(user_info, message_text)

        # 6. Execute via AI Provider Adapter
        ai_reply = ""
        try:
            adapter = get_ai_adapter(self.config)
            ai_reply = adapter.generate_response(
                system_instruction=system_instruction,
                messages=messages_payload,
                context_data=db_context
            )
        except AIAuthError as e:
            logger.error("AI Auth Error: %s", e)
            return {
                "success": False,
                "message": "AI service authentication error. Please verify the configured API key.",
                "conversation_id": conversation_id,
                "error_type": "auth_error"
            }
        except AIRateLimitError as e:
            logger.warning("AI Provider Rate Limit: %s", e)
            return {
                "success": False,
                "message": "AI service quota or rate limit exceeded. Please try again shortly.",
                "conversation_id": conversation_id,
                "error_type": "provider_rate_limit"
            }
        except AITimeoutError as e:
            logger.warning("AI Timeout: %s", e)
            return {
                "success": False,
                "message": "AI Assistant timed out while processing your request. Please try again.",
                "conversation_id": conversation_id,
                "error_type": "timeout"
            }
        except AIProviderError as e:
            logger.error("AI Provider Error: %s", e)
            return {
                "success": False,
                "message": "AI Assistant is temporarily unavailable. Please try again later.",
                "conversation_id": conversation_id,
                "error_type": "provider_error"
            }
        except Exception as e:
            logger.exception("Unexpected error in ChatbotService: %s", e)
            return {
                "success": False,
                "message": "AI Assistant encountered an unexpected error. Please try again.",
                "conversation_id": conversation_id,
                "error_type": "unexpected_error"
            }

        # 7. Save Assistant Message to Database
        if user_id and ai_reply:
            try:
                ai_msg_entry = ChatMessage(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role=user_role,
                    sender="assistant",
                    message=ai_reply
                )
                db.session.add(ai_msg_entry)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.warning("Could not save assistant message: %s", e)

        return {
            "success": True,
            "message": ai_reply,
            "conversation_id": conversation_id
        }

    def get_conversation_history(self, user_id: int, conversation_id: str) -> List[Dict[str, Any]]:
        """Fetch message history for a conversation."""
        from models import ChatMessage
        try:
            records = ChatMessage.query.filter_by(
                conversation_id=conversation_id,
                user_id=user_id
            ).order_by(ChatMessage.timestamp.asc()).all()
            return [r.to_dict() for r in records]
        except Exception as e:
            logger.warning("Failed to fetch conversation history: %s", e)
            return []

    def clear_conversation(self, user_id: int, conversation_id: str) -> bool:
        """Delete all messages for a specific conversation."""
        from models import ChatMessage
        from database import db
        try:
            ChatMessage.query.filter_by(
                conversation_id=conversation_id,
                user_id=user_id
            ).delete()
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            logger.warning("Failed to clear conversation: %s", e)
            return False


# Singleton instance
chatbot_service = ChatbotService()
