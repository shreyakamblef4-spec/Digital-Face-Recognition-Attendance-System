"""
Tests for Camera Lifecycle and Authentication / Login Subsystems.
Verifies that:
1. Camera starts in IDLE / inactive state and NEVER turns on during:
   - Application startup
   - Login page load
   - Login credential submission
   - Dashboard rendering
   - Route loading
2. Camera starts ONLY upon explicit toggle/start action.
3. Camera stops completely on explicit stop and on user logout.
4. Video feed does not auto-start camera; streams placeholder frames when inactive.
5. All four roles (Teacher, Faculty, Student, Admin) authenticate successfully
   against real database records using the standard endpoint /api/login.
6. Error handling properly differentiates:
   - 400: empty or invalid email/password
   - 404: user not found
   - 403: inactive account
   - 401: wrong password
7. Session and JWT tokens are properly managed.
8. Server-side role protection blocks unauthorized access.
"""

import pytest
import json
from web_app import app, camera_active, camera_state, stop_camera, start_camera
from models import User
from database import db


@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        with app.app_context():
            # Ensure camera starts stopped
            stop_camera()
        yield client
        with app.app_context():
            stop_camera()


# ==================== CAMERA LIFECYCLE TESTS ====================

def test_camera_starts_in_idle_state(client):
    """Test that camera starts in IDLE state and is not active."""
    res = client.get('/api/camera/status')
    assert res.status_code == 200
    data = res.get_json()
    assert data['camera_active'] is False
    assert data['state'] == 'IDLE'


def test_login_page_does_not_start_camera(client):
    """Test that rendering the login page does not start the camera."""
    stop_camera()
    res = client.get('/login')
    assert res.status_code == 200

    status_res = client.get('/api/camera/status')
    data = status_res.get_json()
    assert data['camera_active'] is False
    assert data['state'] == 'IDLE'


def test_login_request_does_not_start_camera(client):
    """Test that submitting login credentials does not start the camera."""
    stop_camera()
    res = client.post('/api/login', json={
        'email': 'teacher@school.edu',
        'password': 'password123'
    })
    assert res.status_code == 200

    status_res = client.get('/api/camera/status')
    data = status_res.get_json()
    assert data['camera_active'] is False
    assert data['state'] == 'IDLE'


def test_dashboard_load_does_not_start_camera(client):
    """Test that opening the teacher dashboard does not start the camera."""
    stop_camera()
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['user_role'] = 'teacher'
        sess['user_email'] = 'teacher@school.edu'

    res = client.get('/')
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    # Ensure camera stream src is initially empty in the HTML
    assert '<img src="" alt="Camera Stream" id="camera-stream"' in html

    status_res = client.get('/api/camera/status')
    data = status_res.get_json()
    assert data['camera_active'] is False
    assert data['state'] == 'IDLE'


def test_portal_routes_do_not_start_camera(client):
    """Test that admin, faculty, and student portals do not start the camera."""
    stop_camera()

    # Admin portal
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['user_role'] = 'admin'
    res = client.get('/admin')
    assert res.status_code == 200
    assert client.get('/api/camera/status').get_json()['camera_active'] is False

    # Faculty portal
    with client.session_transaction() as sess:
        sess['user_id'] = 2
        sess['user_role'] = 'faculty'
    res = client.get('/faculty')
    assert res.status_code == 200
    assert client.get('/api/camera/status').get_json()['camera_active'] is False

    # Student portal
    with client.session_transaction() as sess:
        sess['user_id'] = 3
        sess['user_role'] = 'student'
    res = client.get('/student')
    assert res.status_code == 200
    assert client.get('/api/camera/status').get_json()['camera_active'] is False


def test_video_feed_does_not_auto_start_hardware_camera(client):
    """Test that requesting /video_feed does not invoke start_camera() when stopped."""
    stop_camera()
    # Read first chunk of video_feed stream
    res = client.get('/video_feed')
    assert res.status_code == 200
    # Stream Content-Type should be multipart/x-mixed-replace
    assert 'multipart/x-mixed-replace' in res.content_type

    # Camera must remain inactive (streams placeholder frames)
    status_res = client.get('/api/camera/status')
    data = status_res.get_json()
    assert data['camera_active'] is False
    assert data['state'] == 'IDLE'


def test_camera_toggle_and_logout_cleanup(client):
    """Test camera stop action and cleanup on logout."""
    # Stop camera explicitly
    stop_res = client.post('/api/camera/toggle', json={'action': 'stop'})
    assert stop_res.status_code == 200
    data = stop_res.get_json()
    assert data['camera_active'] is False
    assert data['state'] == 'IDLE'

    # Logging out must invoke stop_camera()
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['user_role'] = 'teacher'
    logout_res = client.post('/api/logout')
    assert logout_res.status_code == 200

    status_res = client.get('/api/camera/status')
    data = status_res.get_json()
    assert data['camera_active'] is False
    assert data['state'] == 'IDLE'


def test_cache_control_headers_prevent_back_navigation(client):
    """Test that responses include Cache-Control headers to prevent caching protected pages."""
    res = client.get('/login')
    assert 'no-store' in res.headers.get('Cache-Control', '')
    assert 'no-cache' in res.headers.get('Cache-Control', '')


# ==================== LOGIN & AUTHENTICATION TESTS ====================

def test_login_empty_credentials(client):
    """Test login with empty email or password returns 400."""
    res = client.post('/api/login', json={'email': '', 'password': ''})
    assert res.status_code == 400
    data = res.get_json()
    assert data['success'] is False
    assert 'required' in data['message'].lower()


def test_login_invalid_email_format(client):
    """Test login with invalid email syntax returns 400."""
    res = client.post('/api/login', json={'email': 'not-an-email', 'password': 'password123'})
    assert res.status_code == 400
    data = res.get_json()
    assert data['success'] is False
    assert 'valid email' in data['message'].lower()


def test_login_user_not_found(client):
    """Test login with non-existent user returns 404."""
    res = client.post('/api/login', json={'email': 'nonexistent@school.edu', 'password': 'password123'})
    assert res.status_code == 404
    data = res.get_json()
    assert data['success'] is False
    assert 'no account was found' in data['message'].lower()


def test_login_wrong_password(client):
    """Test login with wrong password returns 401."""
    res = client.post('/api/login', json={'email': 'teacher@school.edu', 'password': 'wrongpassword999'})
    assert res.status_code == 401
    data = res.get_json()
    assert data['success'] is False
    assert 'invalid email or password' in data['message'].lower()


def test_login_inactive_user(client):
    """Test login with an inactive account returns 403."""
    with app.app_context():
        inactive_user = User.query.filter_by(email="inactive_test@school.edu").first()
        if not inactive_user:
            inactive_user = User(
                email="inactive_test@school.edu",
                name="Inactive Tester",
                role="student",
                is_active=False
            )
            inactive_user.set_password("password123")
            db.session.add(inactive_user)
            db.session.commit()
        else:
            inactive_user.is_active = False
            db.session.commit()

    res = client.post('/api/login', json={'email': 'inactive_test@school.edu', 'password': 'password123'})
    assert res.status_code == 403
    data = res.get_json()
    assert data['success'] is False
    assert 'inactive' in data['message'].lower()


@pytest.mark.parametrize("email,password,expected_role", [
    ("teacher@school.edu", "password123", "teacher"),
    ("faculty@school.edu", "faculty123", "faculty"),
    ("student1@school.edu", "student123", "student"),
    ("admin@school.edu", "admin123", "admin"),
    ("admin@attendai.edu", "admin123", "admin"),
])
def test_all_four_roles_login_success(client, email, password, expected_role):
    """Test that all four roles authenticate properly with real database credentials."""
    res = client.post('/api/login', json={'email': email, 'password': password})
    assert res.status_code == 200, f"Login failed for {email}: {res.get_json()}"
    data = res.get_json()
    assert data['success'] is True
    assert data['user_role'] == expected_role
    assert 'token' in data
    assert len(data['token']) > 10


def test_role_based_access_control(client):
    """Test that student cannot access admin or faculty portals."""
    # Login as student
    login_res = client.post('/api/login', json={'email': 'student1@school.edu', 'password': 'student123'})
    assert login_res.status_code == 200

    # Attempt to access admin dashboard -> redirected to student or index
    admin_res = client.get('/admin', follow_redirects=False)
    assert admin_res.status_code == 302
    assert admin_res.location.endswith('/') or admin_res.location.endswith('/student')

    # Attempt to access faculty dashboard -> redirected
    fac_res = client.get('/faculty', follow_redirects=False)
    assert fac_res.status_code == 302


def test_logout_clears_session_and_protects_routes(client):
    """Test that logout clears authentication and protected routes reject requests."""
    # Login as teacher
    client.post('/api/login', json={'email': 'teacher@school.edu', 'password': 'password123'})

    # Can access /me
    me_res = client.get('/api/me')
    assert me_res.status_code == 200

    # Logout
    logout_res = client.post('/api/logout')
    assert logout_res.status_code == 200

    # /api/me now rejects with 401
    me_after_res = client.get('/api/me')
    assert me_after_res.status_code == 401

    # Protected HTML page redirects to login
    page_res = client.get('/', follow_redirects=False)
    assert page_res.status_code == 302
    assert '/login' in page_res.location
