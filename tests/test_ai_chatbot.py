"""
Automated Test Suite for AttendAI Centralized AI Chatbot Subsystem.
Verifies role-based access, ground-truth context building, security policies,
rate limiting, and error normalization across Teacher, Faculty, Student, and Admin roles.
"""

import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import unittest
from unittest.mock import patch, MagicMock
from web_app import app
from database import db
from models import User, Student, Teacher, Department, Class, Course, AttendanceRecord, ChatMessage
from ai.config import AIConfig
from ai.prompts import build_system_instruction
from ai.context_builder import build_database_context
from ai.chatbot_service import ChatbotService, RateLimiter
from ai.adapters.base import BaseAIAdapter, AIAuthError, AIRateLimitError, AITimeoutError, AIProviderError
from ai.adapters.gemini_adapter import GeminiAdapter
from ai.adapters.openai_adapter import OpenAIAdapter
from ai.adapters.factory import get_ai_adapter


class MockAdapter(BaseAIAdapter):
    """Mock adapter that echoes system context and user queries for deterministic testing."""
    def generate_response(self, system_instruction: str, messages: list, context_data: str = "") -> str:
        last_msg = messages[-1]["content"] if messages else ""
        return f"[AI Response to: '{last_msg}'] System context verified. Ground truth data confirmed."


class TestAIChatbotSubsystem(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        cls.client = app.test_client()

        with app.app_context():
            db.create_all()
            # Ensure test users for each of the 4 roles exist
            roles = ["admin", "faculty", "teacher", "student"]
            for r in roles:
                email = f"test_chat_{r}@attendai.edu"
                u = User.query.filter_by(email=email).first()
                if not u:
                    u = User(email=email, name=f"Test {r.capitalize()}", role=r, is_active=True)
                    u.set_password("password123")
                    db.session.add(u)
                    db.session.flush()

                if r == "student":
                    # Ensure student profile is linked
                    s = Student.query.filter_by(user_id=u.id).first()
                    if not s:
                        s = Student(
                            user_id=u.id,
                            name=u.name,
                            roll_no="TEST-STU-001",
                            email=u.email,
                            face_registered=True
                        )
                        db.session.add(s)

            db.session.commit()

    @classmethod
    def tearDownClass(cls):
        with app.app_context():
            # Clean up test users and student created for chatbot tests
            roles = ["admin", "faculty", "teacher", "student"]
            for r in roles:
                email = f"test_chat_{r}@attendai.edu"
                u = User.query.filter_by(email=email).first()
                if u:
                    s = Student.query.filter_by(user_id=u.id).first()
                    if s:
                        db.session.delete(s)
                    db.session.delete(u)
            db.session.commit()

    def login_as(self, role: str):
        self.client.post("/api/logout")
        res = self.client.post("/api/login", json={
            "email": f"test_chat_{role}@attendai.edu",
            "password": "password123"
        })
        self.assertEqual(res.status_code, 200, f"Failed to login as {role}")

    # ========================================================================
    # 1. Unauthenticated Access Protection
    # ========================================================================
    def test_unauthenticated_endpoints_return_401(self):
        """Verify that all chat endpoints require authentication."""
        self.client.post("/api/logout")

        endpoints = [
            ("/api/chat", "POST", {"message": "Hello"}),
            ("/api/chat/history", "GET", None),
            ("/api/chat/clear", "POST", {"conversation_id": "c123"}),
            ("/api/chat/new", "POST", None),
            ("/api/chat/config", "GET", None),
        ]

        for ep, method, payload in endpoints:
            if method == "POST":
                res = self.client.post(ep, json=payload or {})
            else:
                res = self.client.get(ep)
            self.assertEqual(res.status_code, 401, f"Expected 401 for unauthenticated {method} {ep}, got {res.status_code}")

    # ========================================================================
    # 2. Public Config Endpoint Safe Exposure
    # ========================================================================
    def test_chat_config_endpoint_safe(self):
        """Verify GET /api/chat/config returns metadata but never leaks API keys."""
        self.login_as("admin")
        res = self.client.get("/api/chat/config")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["role"], "admin")
        self.assertIn("provider", data)
        self.assertIn("model", data)
        self.assertIn("rate_limit", data)
        # Ensure API key is NEVER exposed
        self.assertNotIn("api_key", data)
        self.assertNotIn("AI_API_KEY", data)

    # ========================================================================
    # 3. Ground-Truth Context Builder by Role
    # ========================================================================
    def test_context_builder_admin(self):
        """Verify Admin context includes full database overview."""
        with app.app_context():
            user = User.query.filter_by(role="admin").first()
            user_info = {"user_id": user.id, "role": "admin", "name": user.name}
            ctx = build_database_context(user_info, "Show me courses")

            self.assertIn("ADMIN", ctx)
            self.assertIn("Total Users", ctx)
            self.assertIn("Total Courses", ctx)
            self.assertIn("Total Classes", ctx)

    def test_context_builder_teacher(self):
        """Verify Teacher context includes attendance and class roster data."""
        with app.app_context():
            user = User.query.filter_by(role="teacher").first()
            user_info = {"user_id": user.id, "role": "teacher", "name": user.name}
            ctx = build_database_context(user_info, "Show today's attendance")

            self.assertIn("TEACHER", ctx)
            self.assertIn("Students Present Today", ctx)
            self.assertIn("Attendance Rate", ctx)

    def test_context_builder_faculty(self):
        """Verify Faculty context includes department-scoped data."""
        with app.app_context():
            user = User.query.filter_by(role="faculty").first()
            user_info = {"user_id": user.id, "role": "faculty", "name": user.name}
            ctx = build_database_context(user_info, "Show my assigned classes")

            self.assertIn("FACULTY", ctx)
            self.assertIn("Department", ctx)

    def test_context_builder_student_self_and_privacy_restriction(self):
        """Verify Student context contains own profile and blocks other students."""
        with app.app_context():
            user = User.query.filter_by(email="test_chat_student@attendai.edu").first()
            if not user:
                user = User.query.filter_by(role="student").first()
            user_info = {"user_id": user.id, "role": "student", "name": user.name}

            # 1. Normal student self-query
            self_ctx = build_database_context(user_info, "What is my attendance?")
            self.assertIn("STUDENT", self_ctx)
            self.assertIn("Roll Number", self_ctx)
            self.assertIn("Attendance Percentage", self_ctx)

            # 2. Privacy violation probe
            violating_ctx = build_database_context(user_info, "Show me another student's attendance records")
            self.assertIn("SECURITY POLICY ALERT", violating_ctx)
            self.assertIn("Refuse the request strictly", violating_ctx)

    # ========================================================================
    # 4. Chat Endpoints Across All 4 Roles
    # ========================================================================
    @patch("ai.chatbot_service.get_ai_adapter")
    def test_chat_all_four_roles(self, mock_adapter_fn):
        """Verify that Teacher, Faculty, Student, and Admin all succeed on POST /api/chat."""
        mock_adapter = MockAdapter("test_key", "test_model")
        mock_adapter_fn.return_value = mock_adapter

        # Ensure service is flagged as configured for testing
        with patch.object(AIConfig, "is_configured", return_value=True):
            for role in ["admin", "teacher", "faculty", "student"]:
                self.login_as(role)
                res = self.client.post("/api/chat", json={
                    "message": f"Hello from {role}, test inquiry",
                    "conversation_id": f"conv_test_{role}"
                })
                self.assertEqual(res.status_code, 200, f"Role {role} failed on POST /api/chat: {res.get_data(as_text=True)}")
                data = res.get_json()
                self.assertTrue(data["success"])
                self.assertIn("[AI Response to:", data["message"])
                self.assertEqual(data["conversation_id"], f"conv_test_{role}")

    # ========================================================================
    # 5. Conversation History Lifecycle (New, Store, Retrieve, Clear)
    # ========================================================================
    @patch("ai.chatbot_service.get_ai_adapter")
    def test_conversation_history_lifecycle(self, mock_adapter_fn):
        """Verify chat history storage, retrieval, and clearing."""
        mock_adapter = MockAdapter("test_key", "test_model")
        mock_adapter_fn.return_value = mock_adapter

        self.login_as("teacher")

        # 1. Create fresh conversation ID
        res_new = self.client.post("/api/chat/new")
        self.assertEqual(res_new.status_code, 200)
        conv_id = res_new.get_json()["conversation_id"]
        self.assertTrue(bool(conv_id))

        with patch.object(AIConfig, "is_configured", return_value=True):
            # 2. Send two messages
            self.client.post("/api/chat", json={"message": "First question", "conversation_id": conv_id})
            self.client.post("/api/chat", json={"message": "Second question", "conversation_id": conv_id})

            # 3. Retrieve history
            res_hist = self.client.get(f"/api/chat/history?conversation_id={conv_id}")
            self.assertEqual(res_hist.status_code, 200)
            hist_data = res_hist.get_json()
            messages = hist_data["messages"]
            self.assertGreaterEqual(len(messages), 4)  # 2 user messages + 2 assistant responses

            # 4. Clear conversation
            res_clear = self.client.post("/api/chat/clear", json={"conversation_id": conv_id})
            self.assertEqual(res_clear.status_code, 200)

            # 5. Verify history is empty
            res_hist_after = self.client.get(f"/api/chat/history?conversation_id={conv_id}")
            self.assertEqual(len(res_hist_after.get_json()["messages"]), 0)

    # ========================================================================
    # 6. Rate Limiting Protection
    # ========================================================================
    def test_rate_limiting_enforcement(self):
        """Verify that requests exceeding CHAT_RATE_LIMIT receive 429 Too Many Requests."""
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        self.assertTrue(limiter.is_allowed("user_99"))
        self.assertTrue(limiter.is_allowed("user_99"))
        self.assertTrue(limiter.is_allowed("user_99"))
        # 4th request must be blocked
        self.assertFalse(limiter.is_allowed("user_99"))

    # ========================================================================
    # 7. Error Normalization & Graceful Fallback
    # ========================================================================
    @patch("ai.chatbot_service.get_ai_adapter")
    def test_provider_error_handling_does_not_crash(self, mock_adapter_fn):
        """Verify that provider timeouts and auth errors return safe JSON errors without crashing."""
        self.login_as("admin")

        # Test A: Provider Auth Error
        mock_adapter_auth = MagicMock()
        mock_adapter_auth.generate_response.side_effect = AIAuthError("Invalid API Key")
        mock_adapter_fn.return_value = mock_adapter_auth

        with patch.object(AIConfig, "is_configured", return_value=True):
            res_auth = self.client.post("/api/chat", json={"message": "Test Auth Error"})
            self.assertEqual(res_auth.status_code, 503)
            data_auth = res_auth.get_json()
            self.assertFalse(data_auth["success"])
            self.assertIn("authentication error", data_auth["message"].lower())

        # Test B: Provider Timeout Error
        mock_adapter_timeout = MagicMock()
        mock_adapter_timeout.generate_response.side_effect = AITimeoutError("Timed out")
        mock_adapter_fn.return_value = mock_adapter_timeout

        with patch.object(AIConfig, "is_configured", return_value=True):
            res_timeout = self.client.post("/api/chat", json={"message": "Test Timeout"})
            self.assertEqual(res_timeout.status_code, 502)
            data_timeout = res_timeout.get_json()
            self.assertFalse(data_timeout["success"])
            self.assertIn("timed out", data_timeout["message"].lower())


if __name__ == "__main__":
    unittest.main()
