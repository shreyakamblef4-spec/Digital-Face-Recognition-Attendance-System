import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

"""
Automated RBAC Matrix Test Pass
Verifies server-side role-based access control across Admin, Faculty, Teacher, Student.
"""

import sys
import uuid
from web_app import app
from models import User, SystemSetting, AuditLog, Department, Class, Subject, Student, Teacher
from database import db

def run_tests():
    client = app.test_client()
    
    with app.app_context():
        db.create_all()
        # Create test users if missing
        roles = ['admin', 'faculty', 'teacher', 'student']
        users = {}
        for r in roles:
            email = f"test_{r}@school.edu"
            u = User.query.filter_by(email=email).first()
            if not u:
                u = User(email=email, name=f"Test {r.capitalize()}", role=r, is_active=True)
                u.set_password("password123")
                db.session.add(u)
            users[r] = u
        db.session.commit()

    results = []

    def login_as(role):
        client.get('/api/logout')
        res = client.post('/api/login', json={"email": f"test_{role}@school.edu", "password": "password123"})
        assert res.status_code == 200, f"Failed to login as {role}"

    print("\n--- Running RBAC Matrix Tests ---")

    unique_email = f"new_user_{uuid.uuid4().hex[:6]}@school.edu"

    # 1. Admin endpoints protection
    admin_endpoints = [
        ('/api/admin/dashboard', 'GET', {}),
        ('/api/admin/users', 'GET', {}),
        ('/api/admin/users', 'POST', {"name": "Valid Test User", "email": unique_email, "password": "password123", "role": "student"}),
        ('/api/admin/settings', 'GET', {}),
        ('/api/admin/audit-logs', 'GET', {}),
    ]


    for ep, method, payload in admin_endpoints:
        # Admin should pass
        login_as('admin')
        res = client.open(ep, method=method, json=payload)
        passed_admin = res.status_code in (200, 201)
        if not passed_admin:
            print(f"DEBUG FAIL {method} {ep}: status={res.status_code}, data={res.get_json()}")
        results.append(('admin', f"{method} {ep}", passed_admin, f"Got {res.status_code}"))

        # Non-admins should fail with 403
        for non_admin in ['faculty', 'teacher', 'student']:
            login_as(non_admin)
            res = client.open(ep, method=method, json=payload)
            passed = res.status_code == 403
            results.append((non_admin, f"{method} {ep}", passed, f"Expected 403, got {res.status_code}"))



    # 2. Student write endpoints block
    write_endpoints = [
        ('/api/admin/users', 'POST'),
        ('/api/admin/departments', 'POST'),
        ('/api/admin/classes', 'POST'),
        ('/api/teacher/attendance-sessions', 'POST'),
        ('/api/attendance/mark-manual', 'POST'),
        ('/api/admin/settings', 'PUT'),
    ]

    login_as('student')
    for ep, method in write_endpoints:
        res = client.open(ep, method=method, json={})
        passed = res.status_code == 403
        results.append(('student_write_block', f"{method} {ep}", passed, f"Expected 403, got {res.status_code}"))

    # 3. Student read-only endpoints access
    student_endpoints = [
        ('/api/student/dashboard', 'GET'),
        ('/api/student/attendance/summary', 'GET'),
        ('/api/student/notifications', 'GET'),
        ('/api/student/reports/semester-summary', 'GET'),
    ]

    login_as('student')
    for ep, method in student_endpoints:
        res = client.open(ep, method=method)
        passed = res.status_code in (200, 404) # 404 if profile missing but auth passed
        results.append(('student_read_access', ep, passed, f"Got {res.status_code}"))

    # Print summary
    failed = 0
    for role, ep, passed, note in results:
        status = "PASS" if passed else "FAIL"
        if not passed: failed += 1
        print(f"[{status}] Role: {role:18} | Endpoint: {ep:35} | {note}")

    print(f"\nTotal Tests: {len(results)}, Failed: {failed}")
    return failed == 0

if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
