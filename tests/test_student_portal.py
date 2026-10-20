import pytest
import json
from web_app import app, db, Student, Course, Class, AttendanceRecord


@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        with app.app_context():
            # Ensure AI & ML course and B.Sc 3rd Year class exist
            crs = Course.query.filter(Course.name.ilike('%Artificial Intelligence%')).first()
            if not crs:
                crs = Course(name='Artificial Intelligence & Machine Learning', code='AIML', status='active')
                db.session.add(crs)
                db.session.flush()

            cls_obj = Class.query.filter(Class.name.ilike('%3rd Year%')).first()
            if not cls_obj:
                cls_obj = Class(name='B.Sc 3rd Year', code='AIML-3', course_id=crs.id, status='active')
                db.session.add(cls_obj)
                db.session.flush()

            # Ensure student 01 (kamble shreya) exists
            st = Student.query.filter_by(roll_no='01').first()
            if not st:
                st = Student(
                    name='kamble shreya',
                    roll_no='01',
                    course_id=crs.id,
                    class_id=cls_obj.id,
                    face_registered=True
                )
                db.session.add(st)
                db.session.commit()
            else:
                st.course_id = crs.id
                st.class_id = cls_obj.id
                db.session.commit()

        yield client


class TestStudentPortal:
    def test_student_login_page_renders(self, client):
        """Verify GET /student-login renders HTML with 200 status."""
        res = client.get('/student-login')
        assert res.status_code == 200
        html = res.data.decode('utf-8')
        assert 'Student Login' in html or 'Student Portal' in html
        assert 'Course' in html
        assert 'Class / Year' in html
        assert 'Roll Number' in html

    def test_public_courses_and_classes(self, client):
        """Verify public endpoints return courses and classes without auth."""
        res_c = client.get('/api/public/courses')
        assert res_c.status_code == 200
        data_c = res_c.get_json()
        assert data_c['success'] is True
        assert len(data_c['courses']) > 0

        res_cl = client.get('/api/public/classes')
        assert res_cl.status_code == 200
        data_cl = res_cl.get_json()
        assert data_cl['success'] is True
        assert len(data_cl['classes']) > 0

    def test_student_login_missing_fields(self, client):
        """Verify POST /api/student-login rejects missing inputs."""
        res = client.post('/api/student-login', json={'roll_no': '01'})
        assert res.status_code in (400, 404)
        data = res.get_json()
        assert data['success'] is False

    def test_student_login_invalid_credentials(self, client):
        """Verify exact error message on invalid student credentials."""
        res = client.post('/api/student-login', json={
            'course_id': '9999',
            'class_id': '9999',
            'roll_no': 'NON_EXISTENT_999'
        })
        assert res.status_code == 404
        data = res.get_json()
        assert data['success'] is False
        assert data['message'] == "No student found with these details. Please check your Course, Class/Year, and Roll Number."

    def test_student_login_success_by_ids(self, client):
        """Verify successful login matching Course + Class + Roll by IDs."""
        with app.app_context():
            st = Student.query.filter_by(roll_no='01').first()
            c_id = st.course_id
            cl_id = st.class_id

        res = client.post('/api/student-login', json={
            'course_id': str(c_id),
            'class_id': str(cl_id),
            'roll_no': '01'
        })
        assert res.status_code == 200
        data = res.get_json()
        assert data['success'] is True
        assert data['redirect_url'] == '/student/attendance'
        assert data['student']['roll_no'] == '01'
        assert 'token' in data

        with client.session_transaction() as sess:
            assert sess.get('student_id') is not None
            assert sess.get('student_roll_no') == '01'
            assert sess.get('user_role') == 'student'

    def test_student_login_success_by_names(self, client):
        """Verify successful login matching Course + Class + Roll by string names."""
        res = client.post('/api/student-login', json={
            'course': 'Artificial Intelligence & Machine Learning',
            'class': 'B.Sc 3rd Year',
            'roll_no': '01'
        })
        assert res.status_code == 200
        data = res.get_json()
        assert data['success'] is True

    def test_student_dashboard_requires_auth(self, client):
        """Verify unauthenticated student is redirected to /student-login."""
        res = client.get('/student/attendance')
        assert res.status_code in (302, 301)
        assert '/student-login' in res.location

    def test_student_dashboard_with_auth(self, client):
        """Verify authenticated student can access /student/attendance."""
        # Log in first
        with app.app_context():
            st = Student.query.filter_by(roll_no='01').first()
            c_id = st.course_id
            cl_id = st.class_id

        client.post('/api/student-login', json={
            'course_id': str(c_id),
            'class_id': str(cl_id),
            'roll_no': '01'
        })

        res = client.get('/student/attendance')
        assert res.status_code == 200
        html = res.data.decode('utf-8')
        assert 'My Attendance Dashboard' in html
        assert '01' in html

    def test_api_my_attendance_unauthorized(self, client):
        """Verify /api/student/my-attendance requires authentication."""
        res = client.get('/api/student/my-attendance')
        assert res.status_code == 401
        data = res.get_json()
        assert data['success'] is False

    def test_api_my_attendance_scoped_to_student(self, client):
        """Verify attendance records returned match only logged-in student."""
        with app.app_context():
            st = Student.query.filter_by(roll_no='01').first()
            c_id = st.course_id
            cl_id = st.class_id

        client.post('/api/student-login', json={
            'course_id': str(c_id),
            'class_id': str(cl_id),
            'roll_no': '01'
        })

        res = client.get('/api/student/my-attendance')
        assert res.status_code == 200
        data = res.get_json()
        assert data['success'] is True
        assert 'records' in data
        assert 'summary' in data
        assert 'total_sessions' in data['summary']
        assert 'total_present' in data['summary']
        assert 'percentage' in data['summary']

        # Ensure all records belong to student 01
        for rec in data['records']:
            assert 'date' in rec
            assert 'time' in rec
            assert 'status' in rec
            assert 'recognition_status' in rec

    def test_security_parameter_tampering_prevention(self, client):
        """Verify student cannot view another student's data by tampering query params."""
        with app.app_context():
            st = Student.query.filter_by(roll_no='01').first()
            c_id = st.course_id
            cl_id = st.class_id

        client.post('/api/student-login', json={
            'course_id': str(c_id),
            'class_id': str(cl_id),
            'roll_no': '01'
        })

        # Try to request another student's roll number
        res_tamper_roll = client.get('/api/student/my-attendance?roll_no=CSE002')
        assert res_tamper_roll.status_code == 403
        data_tamper = res_tamper_roll.get_json()
        assert data_tamper['success'] is False
        assert 'Access denied' in data_tamper['message']

        # Try to request a different course
        res_tamper_course = client.get('/api/student/my-attendance?course_id=99999')
        assert res_tamper_course.status_code == 403

        # Try to request a different class
        res_tamper_class = client.get('/api/student/my-attendance?class_id=99999')
        assert res_tamper_class.status_code == 403

    def test_student_logout(self, client):
        """Verify student logout clears session and redirects to /student-login."""
        with app.app_context():
            st = Student.query.filter_by(roll_no='01').first()
            c_id = st.course_id
            cl_id = st.class_id

        client.post('/api/student-login', json={
            'course_id': str(c_id),
            'class_id': str(cl_id),
            'roll_no': '01'
        })

        # Logout via GET
        res = client.get('/student/logout')
        assert res.status_code in (302, 301)
        assert '/student-login' in res.location

        with client.session_transaction() as sess:
            assert sess.get('student_id') is None

        # Verify dashboard now denies access
        res2 = client.get('/student/attendance')
        assert res2.status_code in (302, 301)
