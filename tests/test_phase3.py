import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

#!/usr/bin/env python
"""
Phase 3 Testing: Admin Management & Dashboard
Tests admin CRUD operations, role-based access, and audit logging.
"""

from app import app
from database import db
from models import User, Department, Class, AuditLog
import json

def test_admin_management():
    """Test admin management system."""
    print("\n" + "="*60)
    print("PHASE 3 TEST: Admin Management & Dashboard")
    print("="*60)
    
    with app.app_context():
        print("\n✓ App loaded successfully")
        
        # Get test users
        admin = User.query.filter_by(role='admin').first()
        teacher = User.query.filter_by(role='teacher').first()
        
        assert admin is not None, "Admin user not found"
        assert teacher is not None, "Teacher user not found"
        
        print(f"\n1️⃣  Testing Admin Dashboard Access...")
        with app.test_client() as client:
            # Test unauthenticated access
            response = client.get('/api/admin/dashboard', headers={'Accept': 'application/json'})
            assert response.status_code == 401, f"Dashboard should require login, got {response.status_code}"
            print(f"   ✓ Unauthenticated access blocked (401)")
            
            # Test non-admin access
            with client.session_transaction() as sess:
                sess['user_id'] = teacher.id
                sess['user_email'] = teacher.email
                sess['user_role'] = teacher.role
            
            response = client.get('/api/admin/dashboard', headers={'Accept': 'application/json'})
            assert response.status_code == 403, "Dashboard should require admin role"
            print(f"   ✓ Non-admin access blocked (403)")
            
            # Test admin access
            with client.session_transaction() as sess:
                sess['user_id'] = admin.id
                sess['user_email'] = admin.email
                sess['user_role'] = admin.role
            
            response = client.get('/api/admin/dashboard')
            assert response.status_code == 200, f"Admin dashboard failed: {response.data}"
            data = json.loads(response.data)
            assert data['success'] == True, "Dashboard should return success"
            assert 'users' in data, "Dashboard should include user stats"
            assert 'structure' in data, "Dashboard should include structure stats"
            assert 'sessions' in data, "Dashboard should include session stats"
            print(f"   ✓ Admin access granted (200)")
            print(f"   ✓ Dashboard stats: {data['users']['total']} users, {data['structure']['departments']} departments")
        
        print(f"\n2️⃣  Testing Users Management...")
        with app.test_client() as client:
            # Set admin session
            with client.session_transaction() as sess:
                sess['user_id'] = admin.id
                sess['user_email'] = admin.email
                sess['user_role'] = admin.role
            
            # Test list users
            response = client.get('/api/admin/users')
            assert response.status_code == 200, "List users failed"
            data = json.loads(response.data)
            assert data['success'] == True, "Should return success"
            assert 'users' in data, "Should include users list"
            initial_user_count = len(data['users'])
            print(f"   ✓ List users: {initial_user_count} users found")
            
            # Test create user
            new_user_data = {
                "email": "newteacher@school.edu",
                "password": "password123",
                "name": "New Teacher",
                "role": "teacher"
            }
            response = client.post('/api/admin/users', 
                                  json=new_user_data,
                                  content_type='application/json')
            assert response.status_code == 201, f"Create user failed: {response.data}"
            data = json.loads(response.data)
            assert data['success'] == True, "Should return success"
            new_user_id = data['user_id']
            print(f"   ✓ User created: {new_user_data['email']} (ID: {new_user_id})")
            
            # Test get user
            response = client.get(f'/api/admin/users/{new_user_id}')
            assert response.status_code == 200, "Get user failed"
            data = json.loads(response.data)
            assert data['user']['email'] == new_user_data['email'], "Email should match"
            assert data['user']['role'] == 'teacher', "Role should be teacher"
            print(f"   ✓ Get user: {data['user']['email']} ({data['user']['role']})")
            
            # Test update user
            update_data = {
                "name": "Updated Teacher Name",
                "is_active": True
            }
            response = client.put(f'/api/admin/users/{new_user_id}',
                                 json=update_data,
                                 content_type='application/json')
            assert response.status_code == 200, "Update user failed"
            print(f"   ✓ User updated: {update_data['name']}")
            
            # Test delete user
            response = client.delete(f'/api/admin/users/{new_user_id}')
            assert response.status_code == 200, "Delete user failed"
            print(f"   ✓ User deleted: ID {new_user_id}")
            
            # Verify user is gone
            response = client.get(f'/api/admin/users/{new_user_id}')
            assert response.status_code == 404, "User should not exist after deletion"
            print(f"   ✓ Deletion verified (404)")
        
        print(f"\n3️⃣  Testing Departments Management...")
        with app.test_client() as client:
            # Set admin session
            with client.session_transaction() as sess:
                sess['user_id'] = admin.id
                sess['user_email'] = admin.email
                sess['user_role'] = admin.role
            
            # Test list departments
            response = client.get('/api/admin/departments')
            assert response.status_code == 200, "List departments failed"
            data = json.loads(response.data)
            initial_dept_count = len(data['departments'])
            print(f"   ✓ List departments: {initial_dept_count} departments found")
            
            # Test create department
            new_dept_data = {
                "name": "Mechanical Engineering",
                "code": "ME",
                "description": "Department of Mechanical Engineering"
            }
            response = client.post('/api/admin/departments',
                                  json=new_dept_data,
                                  content_type='application/json')
            assert response.status_code == 201, f"Create department failed: {response.data}"
            data = json.loads(response.data)
            new_dept_id = data['department_id']
            print(f"   ✓ Department created: {new_dept_data['name']} (ID: {new_dept_id})")
            
            # Test update department
            update_data = {
                "description": "Updated description for ME department"
            }
            response = client.put(f'/api/admin/departments/{new_dept_id}',
                                 json=update_data,
                                 content_type='application/json')
            assert response.status_code == 200, "Update department failed"
            print(f"   ✓ Department updated")
            
            # Test delete department (should succeed if no classes)
            response = client.delete(f'/api/admin/departments/{new_dept_id}')
            assert response.status_code == 200, "Delete department failed"
            print(f"   ✓ Department deleted")
        
        print(f"\n4️⃣  Testing Classes Management...")
        with app.test_client() as client:
            # Set admin session
            with client.session_transaction() as sess:
                sess['user_id'] = admin.id
                sess['user_email'] = admin.email
                sess['user_role'] = admin.role
            
            # Get a department
            dept = Department.query.first()
            assert dept is not None, "Need a department for class testing"
            
            # Test list classes
            response = client.get('/api/admin/classes')
            assert response.status_code == 200, "List classes failed"
            data = json.loads(response.data)
            initial_class_count = len(data['classes'])
            print(f"   ✓ List classes: {initial_class_count} classes found")
            
            # Test create class
            new_class_data = {
                "name": "ME-4A",
                "code": "ME-4A",
                "department_id": dept.id,
                "capacity": 40
            }
            response = client.post('/api/admin/classes',
                                  json=new_class_data,
                                  content_type='application/json')
            assert response.status_code == 201, f"Create class failed: {response.data}"
            data = json.loads(response.data)
            new_class_id = data['class_id']
            print(f"   ✓ Class created: {new_class_data['name']} (ID: {new_class_id})")
            
            # Test update class
            update_data = {
                "capacity": 50
            }
            response = client.put(f'/api/admin/classes/{new_class_id}',
                                 json=update_data,
                                 content_type='application/json')
            assert response.status_code == 200, "Update class failed"
            print(f"   ✓ Class updated (capacity: 50)")
            
            # Test delete class (should succeed if no students)
            response = client.delete(f'/api/admin/classes/{new_class_id}')
            assert response.status_code == 200, "Delete class failed"
            print(f"   ✓ Class deleted")
        
        print(f"\n5️⃣  Testing Audit Logging...")
        with app.app_context():
            # Count audit logs for admin actions
            logs = AuditLog.query.filter_by(user_id=admin.id).all()
            
            # Should have logs for: users viewed, user created, user updated, user deleted
            # Plus department/class operations
            assert len(logs) > 0, "Should have audit logs"
            
            login_logs = [l for l in logs if 'dashboard_viewed' in l.action or l.action == 'user_created']
            assert len(login_logs) > 0, "Should have admin action logs"
            
            print(f"   ✓ {len(logs)} audit log entries found for admin user")
            
            # Display sample logs
            for log in logs[-3:]:
                print(f"   • [{log.action}] {log.table_name}: {log.details}")
        
        print(f"\n6️⃣  Testing Access Control...")
        with app.test_client() as client:
            # Try to access admin endpoints as teacher
            with client.session_transaction() as sess:
                sess['user_id'] = teacher.id
                sess['user_email'] = teacher.email
                sess['user_role'] = teacher.role
            
            # All admin endpoints should return 403
            endpoints = [
                '/api/admin/dashboard',
                '/api/admin/users',
                '/api/admin/departments',
                '/api/admin/classes'
            ]
            
            for endpoint in endpoints:
                response = client.get(endpoint)
                assert response.status_code == 403, f"{endpoint} should be admin-only"
            
            print(f"   ✓ All {len(endpoints)} admin endpoints protected (403 for non-admin)")
        
        print("\n" + "="*60)
        print("✅ PHASE 3 ADMIN MANAGEMENT TESTS: ALL PASSED")
        print("="*60)
        print("\n📊 Summary:")
        print(f"   • Admin dashboard accessible and functional")
        print(f"   • Users CRUD operations working")
        print(f"   • Departments CRUD operations working")
        print(f"   • Classes CRUD operations working")
        print(f"   • Role-based access control enforced")
        print(f"   • Audit logging capturing all admin actions")
        print("\n✨ Phase 3 Admin Management: READY")


if __name__ == "__main__":
    try:
        test_admin_management()
        exit(0)
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
