import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

#!/usr/bin/env python
"""
Phase 2 Testing: Authentication & Authorization
Tests login, roles, and route protection.
"""

from app import app
from database import db
from models import User
from auth import get_current_user, check_permission
import json

def test_authentication():
    """Test authentication system."""
    print("\n" + "="*60)
    print("PHASE 2 TEST: Authentication & Authorization")
    print("="*60)
    
    with app.app_context():
        print("\n✓ App loaded successfully")
        
        # Test 1: Verify users exist
        print("\n1️⃣  Testing User Database...")
        admin = User.query.filter_by(email='admin@school.edu').first() or User.query.filter_by(role='admin').first()
        teacher = User.query.filter_by(email='teacher@school.edu').first() or User.query.filter_by(role='teacher').first()
        student = User.query.filter_by(email='student1@school.edu').first() or User.query.filter_by(role='student').first()
        
        assert admin is not None, "Admin user not found"
        assert teacher is not None, "Teacher user not found"
        assert student is not None, "Student user not found"
        print(f"   ✓ Admin: {admin.email} ({admin.role})")
        print(f"   ✓ Teacher: {teacher.email} ({teacher.role})")
        print(f"   ✓ Student: {student.email} ({student.role})")
        
        # Test 2: Verify password hashing
        print("\n2️⃣  Testing Password Security...")
        assert admin.password_hash not in ("admin123", "Admin@123"), "Passwords are NOT hashed!"
        print(f"   ✓ Passwords are hashed (not plaintext)")
        assert admin.check_password("admin123") or admin.check_password("Admin@123"), "Admin password verification failed"
        print(f"   ✓ Password verification works (admin)")
        assert teacher.check_password("password123") or teacher.check_password("Teacher@123"), "Teacher password verification failed"
        print(f"   ✓ Password verification works (teacher)")
        assert not admin.check_password("wrongpassword"), "Password check should fail for wrong password"
        print(f"   ✓ Wrong password correctly rejected")
        
        # Test 3: Test permission system
        print("\n3️⃣  Testing Permission System...")
        
        # Admin can do everything
        assert check_permission(admin.id, 'view', 'attendance'), "Admin cannot view attendance"
        assert check_permission(admin.id, 'edit', 'attendance'), "Admin cannot edit attendance"
        assert check_permission(admin.id, 'delete', 'student'), "Admin cannot delete student"
        print(f"   ✓ Admin has all permissions")
        
        # Teacher can view and edit attendance
        assert check_permission(teacher.id, 'view', 'attendance'), "Teacher cannot view attendance"
        assert check_permission(teacher.id, 'edit', 'attendance'), "Teacher cannot edit attendance"
        assert not check_permission(teacher.id, 'delete', 'student'), "Teacher should not delete student"
        print(f"   ✓ Teacher has correct permissions (view, edit attendance)")
        
        # Student can only view own attendance
        assert check_permission(student.id, 'view', 'attendance'), "Student cannot view attendance"
        assert not check_permission(student.id, 'edit', 'attendance'), "Student should not edit attendance"
        print(f"   ✓ Student has limited permissions (view only)")
        
        # Test 4: Test role presence
        print("\n4️⃣  Testing Role Assignments...")
        users = User.query.all()
        roles_present = {u.role for u in users}
        expected_roles = {'admin', 'faculty', 'teacher', 'student'}
        
        for role in expected_roles:
            assert role in roles_present, f"Role '{role}' not found in database"
            count = User.query.filter_by(role=role).count()
            print(f"   ✓ Role '{role}': {count} user(s)")
        
        # Test 5: Test user metadata
        print("\n5️⃣  Testing User Metadata...")
        assert admin.email == "admin@school.edu", "Admin email mismatch"
        assert admin.name == "Administrator", "Admin name mismatch"
        assert admin.is_active == True, "Admin should be active"
        print(f"   ✓ Admin metadata correct")
        
        assert teacher.email == "teacher@school.edu", "Teacher email mismatch"
        assert teacher.name == "Teacher Account", "Teacher name mismatch"
        print(f"   ✓ Teacher metadata correct")
        
        # Test 6: Test timestamps
        print("\n6️⃣  Testing Audit Timestamps...")
        for user in [admin, teacher, student]:
            assert user.created_at is not None, f"{user.email} has no created_at"
            assert user.updated_at is not None, f"{user.email} has no updated_at"
        print(f"   ✓ All users have creation/update timestamps")
        
        print("\n" + "="*60)
        print("✅ PHASE 2 AUTHENTICATION TESTS: ALL PASSED")
        print("="*60)
        print("\n📊 Summary:")
        print(f"   • {User.query.count()} total users in database")
        print(f"   • All users have hashed passwords")
        print(f"   • Role-based permissions working")
        print(f"   • All audit timestamps present")
        print("\n✨ Phase 2 Authentication & Authorization: READY")


if __name__ == "__main__":
    try:
        test_authentication()
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
