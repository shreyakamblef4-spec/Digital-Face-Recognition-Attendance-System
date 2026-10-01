import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

"""
Test Suite for Phase 4: Enhanced Teacher/Faculty Features
Tests for Teacher Dashboard, Faculty Dashboard, Attendance Sessions, and Reporting
"""

import json
from datetime import datetime, date, timedelta
from web_app import app
from database import db
from models import (
    User, Student, Teacher, Department, Class, Subject,
    AttendanceSession, AttendanceRecord, UserRole
)


class Phase4TestSuite:
    """Test suite for Phase 4 features."""

    @staticmethod
    def setup():
        """Set up test database and fixtures."""
        with app.app_context():
            # Drop all tables and recreate them
            db.drop_all()
            db.create_all()
            
            # Create test users
            admin_user = User(
                email='admin@school.edu',
                name='Admin User',
                role='admin'
            )
            admin_user.set_password('admin123')
            
            teacher_user = User(
                email='teacher@school.edu',
                name='Teacher Name',
                role='teacher'
            )
            teacher_user.set_password('password123')
            
            faculty_user = User(
                email='faculty@school.edu',
                name='Faculty Name',
                role='faculty'
            )
            faculty_user.set_password('password123')
            
            student_user = User(
                email='student1@school.edu',
                name='Student One',
                role='student'
            )
            student_user.set_password('student123')
            
            db.session.add_all([admin_user, teacher_user, faculty_user, student_user])
            db.session.commit()
            
            # Create department
            dept = Department(
                name='Computer Science',
                code='CS',
                description='Computer Science Department'
            )
            db.session.add(dept)
            db.session.commit()
            
            # Create class
            cls = Class(
                name='B.Tech CSE - Year 2',
                code='CSE2A',
                department_id=dept.id,
                capacity=60
            )
            db.session.add(cls)
            db.session.commit()
            
            # Create subject
            subject = Subject(
                name='Data Structures',
                code='CS201',
                class_id=cls.id,
                credits=4
            )
            db.session.add(subject)
            db.session.commit()
            
            # Create teacher record
            teacher = Teacher(
                user_id=teacher_user.id,
                employee_id='EMP001',
                department_id=dept.id,
                phone='9876543210',
                office='A-201'
            )
            db.session.add(teacher)
            db.session.commit()
            
            # Create faculty record
            faculty = Teacher(
                user_id=faculty_user.id,
                employee_id='EMP002',
                department_id=dept.id,
                phone='9876543211',
                office='A-202'
            )
            db.session.add(faculty)
            db.session.commit()
            
            # Create students
            for i in range(5):
                student = Student(
                    user_id=student_user.id if i == 0 else None,
                    name=f'Student {i+1}',
                    roll_no=f'CSE2A{i+1:03d}',
                    class_id=cls.id,
                    department_id=dept.id,
                    email=f'student{i+1}@school.edu'
                )
                db.session.add(student)
            
            db.session.commit()
            print("✓ Test database setup complete")

    @staticmethod
    def teardown():
        """Clean up test database."""
        with app.app_context():
            db.session.remove()
            db.drop_all()
            from database import create_all_tables
            from init_db import add_demo_data
            create_all_tables(app)
            add_demo_data()
            print("✓ Test database cleaned up and restored")

    @staticmethod
    def test_teacher_dashboard():
        """Test teacher dashboard endpoint."""
        print("\n=== Testing Teacher Dashboard ===")
        
        with app.test_client() as client:
            # Login as teacher
            response = client.post('/api/login', json={
                'email': 'teacher@school.edu',
                'password': 'password123'
            })
            assert response.status_code == 200
            
            # Get teacher dashboard
            response = client.get('/api/teacher/dashboard')
            assert response.status_code == 200
            
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
            assert data['data']['teacher_name'] == 'Teacher Name'
            assert 'assigned_classes' in data['data']
            assert 'class_avg_attendance' in data['data']
            
            print("✓ Teacher dashboard API works")

    @staticmethod
    def test_teacher_get_classes():
        """Test getting teacher's assigned classes."""
        print("\n=== Testing Teacher Classes ===")
        
        with app.test_client() as client:
            # Login as teacher
            client.post('/api/login', json={
                'email': 'teacher@school.edu',
                'password': 'password123'
            })
            
            # Get classes
            response = client.get('/api/teacher/classes')
            assert response.status_code == 200
            
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
            
            print(f"✓ Teacher has access to {len(data['data'])} classes")

    @staticmethod
    def test_create_attendance_session():
        """Test creating an attendance session."""
        print("\n=== Testing Attendance Session Creation ===")
        
        with app.test_client() as client:
            # Login as teacher
            client.post('/api/login', json={
                'email': 'teacher@school.edu',
                'password': 'password123'
            })
            
            # Get class ID
            with app.app_context():
                cls = Class.query.filter_by(code='CSE2A').first()
                subject = Subject.query.filter_by(code='CS201').first()
            
            # Create session
            session_data = {
                'class_id': cls.id,
                'subject_id': subject.id,
                'date': (date.today() + timedelta(days=1)).isoformat(),
                'start_time': '10:00:00',
                'end_time': '11:30:00',
                'notes': 'Test session'
            }
            
            response = client.post('/api/teacher/attendance-sessions',
                                 json=session_data,
                                 content_type='application/json')
            assert response.status_code == 201
            
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'session_id' in data['data']
            
            print(f"✓ Attendance session created (ID: {data['data']['session_id']})")
            return data['data']['session_id']

    @staticmethod
    def test_get_attendance_session():
        """Test getting session details."""
        print("\n=== Testing Get Session Details ===")
        
        with app.test_client() as client:
            # Login as teacher
            client.post('/api/login', json={
                'email': 'teacher@school.edu',
                'password': 'password123'
            })
            
            # Create a session first
            with app.app_context():
                cls = Class.query.filter_by(code='CSE2A').first()
                teacher = Teacher.query.filter_by(employee_id='EMP001').first()
                subject = Subject.query.filter_by(code='CS201').first()
                
                session = AttendanceSession(
                    teacher_id=teacher.id,
                    class_id=cls.id,
                    subject_id=subject.id,
                    date=date.today() + timedelta(days=2),
                    start_time=datetime.strptime('10:00:00', '%H:%M:%S').time(),
                    status='pending'
                )
                db.session.add(session)
                db.session.commit()
                session_id = session.id
            
            # Get session details
            response = client.get(f'/api/teacher/attendance-sessions/{session_id}')
            assert response.status_code == 200
            
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['data']['session_id'] == session_id
            
            print(f"✓ Session details retrieved successfully")

    @staticmethod
    def test_start_attendance_session():
        """Test starting an attendance session."""
        print("\n=== Testing Start Session ===")
        
        with app.test_client() as client:
            # Login as teacher
            client.post('/api/login', json={
                'email': 'teacher@school.edu',
                'password': 'password123'
            })
            
            # Create a session
            with app.app_context():
                cls = Class.query.filter_by(code='CSE2A').first()
                teacher = Teacher.query.filter_by(employee_id='EMP001').first()
                subject = Subject.query.filter_by(code='CS201').first()
                
                session = AttendanceSession(
                    teacher_id=teacher.id,
                    class_id=cls.id,
                    subject_id=subject.id,
                    date=date.today() + timedelta(days=3),
                    start_time=datetime.strptime('10:00:00', '%H:%M:%S').time(),
                    status='pending'
                )
                db.session.add(session)
                db.session.commit()
                session_id = session.id
            
            # Start session
            response = client.post(f'/api/teacher/attendance-sessions/{session_id}/start')
            assert response.status_code == 200
            
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['data']['status'] == 'active'
            
            print("✓ Attendance session started successfully")

    @staticmethod
    def test_manual_attendance_marking():
        """Test manually marking attendance."""
        print("\n=== Testing Manual Attendance Marking ===")
        
        with app.test_client() as client:
            # Login as teacher
            client.post('/api/login', json={
                'email': 'teacher@school.edu',
                'password': 'password123'
            })
            
            # Create and setup session
            with app.app_context():
                cls = Class.query.filter_by(code='CSE2A').first()
                teacher = Teacher.query.filter_by(employee_id='EMP001').first()
                student = Student.query.filter_by(roll_no='CSE2A001').first()
                subject = Subject.query.filter_by(code='CS201').first()
                
                session = AttendanceSession(
                    teacher_id=teacher.id,
                    class_id=cls.id,
                    subject_id=subject.id,
                    date=date.today() + timedelta(days=4),
                    start_time=datetime.strptime('10:00:00', '%H:%M:%S').time(),
                    status='active'
                )
                db.session.add(session)
                db.session.commit()
                session_id = session.id
                student_id = student.id
            
            # Mark attendance manually
            mark_data = {
                'session_id': session_id,
                'student_id': student_id,
                'status': 'present',
                'notes': 'Manual marking test'
            }
            
            response = client.post('/api/attendance/mark-manual',
                                 json=mark_data,
                                 content_type='application/json')
            assert response.status_code == 201
            
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['data']['status'] == 'present'
            
            print("✓ Manual attendance marking works")

    @staticmethod
    def test_correct_attendance():
        """Test correcting attendance."""
        print("\n=== Testing Attendance Correction ===")
        
        with app.test_client() as client:
            # Login as teacher
            client.post('/api/login', json={
                'email': 'teacher@school.edu',
                'password': 'password123'
            })
            
            # Create session and attendance record
            with app.app_context():
                cls = Class.query.filter_by(code='CSE2A').first()
                teacher = Teacher.query.filter_by(employee_id='EMP001').first()
                student = Student.query.filter_by(roll_no='CSE2A002').first()
                
                session = AttendanceSession(
                    teacher_id=teacher.id,
                    class_id=cls.id,
                    date=date.today() + timedelta(days=5),
                    start_time=datetime.strptime('10:00:00', '%H:%M:%S').time(),
                    status='active'
                )
                db.session.add(session)
                db.session.commit()
                
                record = AttendanceRecord(
                    session_id=session.id,
                    student_id=student.id,
                    timestamp=datetime.utcnow(),
                    status='absent'
                )
                db.session.add(record)
                db.session.commit()
                record_id = record.id
            
            # Correct attendance
            response = client.put(f'/api/attendance/{record_id}/correct',
                                json={'status': 'present', 'notes': 'Corrected to present'},
                                content_type='application/json')
            assert response.status_code == 200
            
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['data']['new_status'] == 'present'
            
            print("✓ Attendance correction works")

    @staticmethod
    def test_complete_session():
        """Test completing an attendance session."""
        print("\n=== Testing Session Completion ===")
        
        with app.test_client() as client:
            # Login as teacher
            client.post('/api/login', json={
                'email': 'teacher@school.edu',
                'password': 'password123'
            })
            
            # Create and start session
            with app.app_context():
                cls = Class.query.filter_by(code='CSE2A').first()
                teacher = Teacher.query.filter_by(employee_id='EMP001').first()
                subject = Subject.query.filter_by(code='CS201').first()
                
                session = AttendanceSession(
                    teacher_id=teacher.id,
                    class_id=cls.id,
                    subject_id=subject.id,
                    date=date.today() + timedelta(days=6),
                    start_time=datetime.strptime('10:00:00', '%H:%M:%S').time(),
                    status='active'
                )
                db.session.add(session)
                db.session.commit()
                session_id = session.id
            
            # Complete session
            response = client.post(f'/api/teacher/attendance-sessions/{session_id}/complete')
            assert response.status_code == 200
            
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['data']['status'] == 'completed'
            
            print("✓ Session completion works")

    @staticmethod
    def test_faculty_dashboard():
        """Test faculty dashboard."""
        print("\n=== Testing Faculty Dashboard ===")
        
        with app.test_client() as client:
            # Login as faculty
            response = client.post('/api/login', json={
                'email': 'faculty@school.edu',
                'password': 'password123'
            })
            assert response.status_code == 200
            
            # Get faculty dashboard
            response = client.get('/api/faculty/dashboard')
            assert response.status_code == 200
            
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
            assert data['data']['faculty_name'] == 'Faculty Name'
            assert 'total_students' in data['data']
            assert 'total_classes' in data['data']
            
            print("✓ Faculty dashboard API works")

    @staticmethod
    def test_attendance_trends():
        """Test attendance trends endpoint."""
        print("\n=== Testing Attendance Trends ===")
        
        with app.test_client() as client:
            # Login as faculty
            client.post('/api/login', json={
                'email': 'faculty@school.edu',
                'password': 'password123'
            })
            
            # Get trends
            response = client.get('/api/faculty/attendance-trends?days=30')
            assert response.status_code == 200
            
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
            
            print("✓ Attendance trends API works")

    @staticmethod
    def test_attendance_report():
        """Test attendance report generation."""
        print("\n=== Testing Attendance Report ===")
        
        with app.test_client() as client:
            # Login as teacher
            client.post('/api/login', json={
                'email': 'teacher@school.edu',
                'password': 'password123'
            })
            
            # Get report
            response = client.get('/api/teacher/reports/attendance?format=json')
            assert response.status_code == 200
            
            data = json.loads(response.data)
            assert data['success'] is True
            
            print("✓ Attendance report generation works")

    @staticmethod
    def test_class_summary_report():
        """Test class summary report."""
        print("\n=== Testing Class Summary Report ===")
        
        with app.test_client() as client:
            # Login as teacher
            client.post('/api/login', json={
                'email': 'teacher@school.edu',
                'password': 'password123'
            })
            
            # Get class ID
            with app.app_context():
                cls = Class.query.filter_by(code='CSE2A').first()
            
            # Get report
            response = client.get(f'/api/teacher/reports/class-summary?class_id={cls.id}')
            assert response.status_code == 200
            
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['data']['class_name'] == 'B.Tech CSE - Year 2'
            
            print("✓ Class summary report works")

    @staticmethod
    def test_department_report():
        """Test department summary report."""
        print("\n=== Testing Department Report ===")
        
        with app.test_client() as client:
            # Login as faculty
            client.post('/api/login', json={
                'email': 'faculty@school.edu',
                'password': 'password123'
            })
            
            # Get report
            response = client.get('/api/faculty/reports/department-summary')
            assert response.status_code == 200
            
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['data']['department'] == 'Computer Science'
            
            print("✓ Department summary report works")

    @staticmethod
    def test_low_attendance():
        """Test low attendance retrieval."""
        print("\n=== Testing Low Attendance ===")
        
        with app.test_client() as client:
            # Login as teacher
            client.post('/api/login', json={
                'email': 'teacher@school.edu',
                'password': 'password123'
            })
            
            # Get low attendance students
            response = client.get('/api/teacher/low-attendance?threshold=75')
            assert response.status_code == 200
            
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'students' in data['data']
            
            print("✓ Low attendance API works")

    @staticmethod
    def test_access_control():
        """Test role-based access control."""
        print("\n=== Testing Access Control ===")
        
        with app.test_client() as client:
            # Login as student
            client.post('/api/login', json={
                'email': 'student1@school.edu',
                'password': 'student123'
            })
            
            # Try accessing teacher endpoint (should fail)
            response = client.get('/api/teacher/dashboard')
            assert response.status_code == 403
            
            print("✓ Access control enforcement works")


def run_tests():
    """Run all Phase 4 tests."""
    print("\n" + "="*60)
    print("PHASE 4 TEST SUITE - Enhanced Teacher/Faculty Features")
    print("="*60)
    
    try:
        Phase4TestSuite.setup()
        
        # Run all test methods
        test_methods = [m for m in dir(Phase4TestSuite) if m.startswith('test_')]
        passed = 0
        failed = 0
        
        for method_name in test_methods:
            try:
                method = getattr(Phase4TestSuite, method_name)
                method()
                passed += 1
            except AssertionError as e:
                print(f"✗ {method_name} failed: {e}")
                failed += 1
            except Exception as e:
                print(f"✗ {method_name} error: {e}")
                failed += 1
        
        Phase4TestSuite.teardown()
        
        # Summary
        print("\n" + "="*60)
        print(f"PHASE 4 TEST RESULTS")
        print("="*60)
        print(f"✓ Passed: {passed}")
        print(f"✗ Failed: {failed}")
        print(f"Total: {passed + failed}")
        print("="*60)
        
        return failed == 0
    
    except Exception as e:
        print(f"\nFatal error in test suite: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = run_tests()
    exit(0 if success else 1)
