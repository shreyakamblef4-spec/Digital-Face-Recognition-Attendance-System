import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

"""
PHASE 5: STUDENT DASHBOARD - TEST SUITE
Tests for student dashboard features with proper app context handling.
"""

import unittest
import json
from datetime import date, time, timedelta, datetime
from web_app import app
from database import db
from models import (
    User, Student, Teacher, Department, Class, Subject,
    AttendanceSession, AttendanceRecord
)


class Phase5TestSuite(unittest.TestCase):
    """Test suite for Phase 5: Student Dashboard features."""
    
    def setUp(self):
        """Create test database and app context before each test."""
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['SESSION_TYPE'] = 'filesystem'
        
        with app.app_context():
            db.drop_all()
            db.create_all()
            
            # Create department
            dept = Department(name='Computer Science', code='CS')
            db.session.add(dept)
            db.session.flush()
            
            # Create class
            cls_obj = Class(name='CSE2A', code='CSE2A', capacity=30, department_id=dept.id)
            db.session.add(cls_obj)
            db.session.flush()
            
            # Create subject
            subj = Subject(name='Data Structures', code='CS201', class_id=cls_obj.id)
            db.session.add(subj)
            db.session.flush()
            
            # Create teacher user
            teacher_user = User(
                email='teacher@school.edu',
                name='Test Teacher',
                role='teacher',
                is_active=True
            )
            teacher_user.set_password('password123')
            db.session.add(teacher_user)
            db.session.flush()
            
            teacher = Teacher(
                user_id=teacher_user.id,
                employee_id='T001',
                department_id=dept.id
            )
            db.session.add(teacher)
            db.session.flush()
            
            # Create student user
            student_user = User(
                email='student1@school.edu',
                name='John Student',
                role='student',
                is_active=True
            )
            student_user.set_password('student123')
            db.session.add(student_user)
            db.session.flush()
            
            student = Student(
                user_id=student_user.id,
                name='John Student',
                roll_no='CSE2A001',
                department_id=dept.id,
                class_id=cls_obj.id
            )
            db.session.add(student)
            db.session.flush()
            
            # Create attendance sessions with records
            for i in range(5):
                session = AttendanceSession(
                    teacher_id=teacher.id,
                    class_id=cls_obj.id,
                    subject_id=subj.id,
                    date=date.today() - timedelta(days=5-i),
                    status='completed',
                    start_time=time(9, 0, 0),
                    end_time=time(9, 50, 0)
                )
                db.session.add(session)
                db.session.flush()
                
                # Mark present for 4 sessions, absent for 1
                status = 'present' if i < 4 else 'absent'
                record = AttendanceRecord(
                    session_id=session.id,
                    student_id=student.id,
                    status=status,
                    timestamp=datetime.combine(session.date, time(9, 5, 0)),
                    marked_by_teacher=False
                )
                db.session.add(record)
            
            db.session.commit()

    def tearDown(self):
        """Clean up after each test."""
        with app.app_context():
            db.session.remove()
            db.drop_all()
            from database import create_all_tables
            from init_db import add_demo_data
            create_all_tables(app)
            add_demo_data()

    # ==================== DASHBOARD TESTS ====================

    def test_student_dashboard(self):
        """Test student dashboard endpoint returns correct data."""
        client = app.test_client()
        with client:
            client.post('/login', data={
                'email': 'student1@school.edu',
                'password': 'student123'
            })
            
            response = client.get('/api/student/dashboard')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            
            self.assertTrue(data['success'])
            self.assertEqual(data['data']['student_name'], 'John Student')
            self.assertEqual(data['data']['roll_no'], 'CSE2A001')
            self.assertEqual(data['data']['total_classes'], 5)
            self.assertEqual(data['data']['present'], 4)
            self.assertEqual(data['data']['absent'], 1)
            self.assertGreaterEqual(data['data']['overall_percentage'], 75)

    # ==================== SUMMARY TESTS ====================

    def test_attendance_summary(self):
        """Test attendance summary endpoint."""
        client = app.test_client()
        with client:
            client.post('/login', data={
                'email': 'student1@school.edu',
                'password': 'student123'
            })
            
            response = client.get('/api/student/attendance/summary')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            
            self.assertTrue(data['success'])
            self.assertEqual(data['data']['total_classes'], 5)
            self.assertEqual(data['data']['present'], 4)
            self.assertIn('status', data['data'])

    # ==================== HISTORY TESTS ====================

    def test_attendance_history(self):
        """Test attendance history endpoint returns paginated results."""
        client = app.test_client()
        with client:
            client.post('/login', data={
                'email': 'student1@school.edu',
                'password': 'student123'
            })
            
            response = client.get('/api/student/attendance/history')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            
            self.assertTrue(data['success'])
            self.assertEqual(data['data']['total_records'], 5)
            self.assertGreater(len(data['data']['records']), 0)

    def test_attendance_history_pagination(self):
        """Test attendance history with pagination."""
        client = app.test_client()
        with client:
            client.post('/login', data={
                'email': 'student1@school.edu',
                'password': 'student123'
            })
            
            response = client.get('/api/student/attendance/history?page=1&limit=2')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            
            self.assertTrue(data['success'])
            self.assertEqual(len(data['data']['records']), 2)
            self.assertGreaterEqual(data['data']['total_pages'], 3)

    # ==================== SUBJECT BREAKDOWN TESTS ====================

    def test_subject_wise_attendance(self):
        """Test subject-wise attendance breakdown."""
        client = app.test_client()
        with client:
            client.post('/login', data={
                'email': 'student1@school.edu',
                'password': 'student123'
            })
            
            response = client.get('/api/student/attendance/by-subject')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            
            self.assertTrue(data['success'])
            self.assertGreater(len(data['data']['subjects']), 0)
            
            # Check subject data structure
            subject = data['data']['subjects'][0]
            self.assertIn('subject_name', subject)
            self.assertIn('total', subject)
            self.assertIn('present', subject)
            self.assertIn('percentage', subject)

    # ==================== LOW ATTENDANCE WARNING TESTS ====================

    def test_low_attendance_warning(self):
        """Test low attendance warning with default threshold."""
        client = app.test_client()
        with client:
            client.post('/login', data={
                'email': 'student1@school.edu',
                'password': 'student123'
            })
            
            response = client.get('/api/student/low-attendance-warning')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            
            self.assertTrue(data['success'])
            self.assertIn('has_warning', data['data'])
            self.assertIn('current_percentage', data['data'])
            # 80% is above default 75%
            self.assertFalse(data['data']['has_warning'])

    def test_low_attendance_warning_with_custom_threshold(self):
        """Test low attendance warning with custom threshold."""
        client = app.test_client()
        with client:
            client.post('/login', data={
                'email': 'student1@school.edu',
                'password': 'student123'
            })
            
            response = client.get('/api/student/low-attendance-warning?threshold=85')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            
            self.assertTrue(data['success'])
            # 80% is below 85%
            self.assertTrue(data['data']['has_warning'])
            self.assertGreater(data['data']['classes_needed'], 0)

    # ==================== REPORT TESTS ====================

    def test_attendance_report_json(self):
        """Test attendance report in JSON format."""
        client = app.test_client()
        with client:
            client.post('/login', data={
                'email': 'student1@school.edu',
                'password': 'student123'
            })
            
            response = client.get('/api/student/reports/attendance?format=json')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            
            self.assertTrue(data['success'])
            self.assertEqual(data['data']['roll_no'], 'CSE2A001')
            self.assertGreater(len(data['data']['report']), 0)

    def test_attendance_report_csv(self):
        """Test attendance report in CSV format."""
        client = app.test_client()
        with client:
            client.post('/login', data={
                'email': 'student1@school.edu',
                'password': 'student123'
            })
            
            response = client.get('/api/student/reports/attendance?format=csv')
            self.assertEqual(response.status_code, 200)
            # Should return CSV file
            self.assertIn(b'Date', response.data)
            self.assertIn(b'Status', response.data)

    def test_semester_summary_report(self):
        """Test semester summary report generation."""
        client = app.test_client()
        with client:
            client.post('/login', data={
                'email': 'student1@school.edu',
                'password': 'student123'
            })
            
            response = client.get('/api/student/reports/semester-summary')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            
            self.assertTrue(data['success'])
            self.assertIn('overall_summary', data['data'])
            self.assertIn('subject_wise_summary', data['data'])
            self.assertGreater(data['data']['overall_summary']['total_classes'], 0)

    # ==================== ACCESS CONTROL TESTS ====================

    def test_unauthenticated_access_denied(self):
        """Test that unauthenticated users cannot access student endpoints."""
        client = app.test_client()
        response = client.get('/api/student/dashboard')
        # Should redirect to login or return 401
        self.assertIn(response.status_code, [401, 302])

    def test_teacher_cannot_access_student_endpoints(self):
        """Test that teachers cannot access student endpoints."""
        client = app.test_client()
        with client:
            client.post('/login', data={
                'email': 'teacher@school.edu',
                'password': 'password123'
            })
            
            response = client.get('/api/student/dashboard')
            # Should be denied (403 Forbidden, 401 Unauthorized, 302 Redirect, or 404 Not Found due to missing student profile)
            self.assertIn(response.status_code, [403, 401, 302, 404])


if __name__ == '__main__':
    unittest.main(verbosity=2)
