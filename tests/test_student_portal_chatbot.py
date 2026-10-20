"""
Tests for Student Portal Chatbot Integration on /student/attendance and /student.
Verifies that student sessions (via student_id in session) have access to the chatbot,
HTML templates contain the chatbot components, and AI context resolves student attendance.
"""
import pytest
from unittest.mock import patch
from app import app
from models import db, Student, AttendanceRecord
from ai.config import AIConfig
from ai.context_builder import build_database_context
from tests.test_ai_chatbot import MockAdapter

def test_student_portal_chatbot_html_included():
    client = app.test_client()

    with app.app_context():
        student = Student.query.first()
        assert student is not None, "At least one student should exist"

    # Set student session as established by student portal login
    with client.session_transaction() as sess:
        sess['student_id'] = student.id
        sess['student_roll_no'] = student.roll_no
        sess['student_name'] = student.name
        sess['user_role'] = 'student'

    # Check /student/attendance contains chatbot
    res = client.get('/student/attendance')
    assert res.status_code == 200
    html = res.data.decode('utf-8')
    assert "chatbot.css" in html
    assert "attendai-chatbot-root" in html or "chatbot-launcher-btn" in html
    assert "chatbot.js" in html

    # Check /api/chat/config returns role student
    cfg_res = client.get('/api/chat/config')
    assert cfg_res.status_code == 200
    cfg_data = cfg_res.get_json()
    assert cfg_data['success'] is True
    assert cfg_data['role'] == 'student'
    assert cfg_data['user_name'] == student.name

def test_student_portal_chatbot_context_and_messaging():
    client = app.test_client()

    with app.app_context():
        student = Student.query.first()
        assert student is not None

        user_info = {
            'user_id': student.id,
            'student_id': student.id,
            'role': 'student',
            'name': student.name,
            'email': student.email
        }
        ctx = build_database_context(user_info, "What is my attendance?")
        assert "STUDENT" in ctx
        assert student.name in ctx
        assert str(student.roll_no) in ctx

    with client.session_transaction() as sess:
        sess['student_id'] = student.id
        sess['student_roll_no'] = student.roll_no
        sess['student_name'] = student.name
        sess['user_role'] = 'student'

    mock_adapter = MockAdapter("test_key", "test_model")
    with patch("ai.chatbot_service.get_ai_adapter", return_value=mock_adapter), \
         patch.object(AIConfig, "is_configured", return_value=True):
        res = client.post("/api/chat", json={
            "message": "What is my attendance percentage?",
            "conversation_id": "conv_student_test"
        })
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert "[AI Response to:" in data["message"]
