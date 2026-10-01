"""
Authentication and authorization module.
Provides decorators for role-based access control and authentication utilities.
"""

from flask import session, redirect, url_for, jsonify, request
from functools import wraps
from datetime import datetime
from models import User, AuditLog
from database import db


import os
import json
import base64
import hmac
import hashlib
from datetime import datetime, timedelta

try:
    import jwt
except ImportError:
    jwt = None

SECRET_KEY = os.environ.get('SECRET_KEY', 'attendai-super-secret-key-2026-production-secured')

def generate_token(user_id, role, name, email):
    """Generate a signed token for a user."""
    payload = {
        'user_id': user_id,
        'role': role,
        'name': name,
        'email': email,
        'exp': (datetime.utcnow() + timedelta(days=7)).timestamp(),
        'iat': datetime.utcnow().timestamp()
    }
    if jwt:
        return jwt.encode(payload, SECRET_KEY, algorithm='HS256')
    else:
        # Fallback signed JSON token
        payload_str = base64.b64encode(json.dumps(payload).encode()).decode()
        signature = hmac.new(SECRET_KEY.encode(), payload_str.encode(), hashlib.sha256).hexdigest()
        return f"{payload_str}.{signature}"

def decode_token(token):
    """Decode and validate a signed token."""
    if not token:
        return None
    try:
        if jwt and '.' in token and len(token.split('.')) == 3:
            return jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        elif '.' in token:
            payload_str, signature = token.rsplit('.', 1)
            expected_sig = hmac.new(SECRET_KEY.encode(), payload_str.encode(), hashlib.sha256).hexdigest()
            if hmac.compare_digest(signature, expected_sig):
                data = json.loads(base64.b64decode(payload_str.encode()).decode())
                if data.get('exp') and data['exp'] < datetime.utcnow().timestamp():
                    return None
                return data
    except Exception:
        return None
    return None


def get_authenticated_user():
    """Get authenticated user info from session or Bearer token header."""
    # 1. Check Authorization header
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:].strip()
        payload = decode_token(token)
        if payload:
            return payload

    # 2. Check Flask session
    if 'user_id' in session:
        return {
            'user_id': session.get('user_id'),
            'role': session.get('user_role'),
            'name': session.get('user_name'),
            'email': session.get('user_email')
        }
    if 'student_id' in session:
        return {
            'user_id': session.get('student_id'),
            'role': 'student',
            'name': session.get('student_name', 'Student'),
            'email': session.get('student_email', '')
        }
    return None

def login_required(f):
    """Decorator to require user login (session or JWT)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_info = get_authenticated_user()
        if not user_info:
            is_api = (request.path.startswith('/api/') or request.is_json or 
                      request.headers.get('Accept', '').find('application/json') != -1 or
                      request.headers.get('X-Requested-With') == 'XMLHttpRequest')
            if is_api:
                return jsonify({'success': False, 'message': 'Login required.'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*allowed_roles):
    """Decorator to require specific user roles server-side."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_info = get_authenticated_user()
            if not user_info:
                is_api = (request.path.startswith('/api/') or request.is_json or 
                          request.headers.get('Accept', '').find('application/json') != -1 or
                          request.headers.get('X-Requested-With') == 'XMLHttpRequest')
                if is_api:
                    return jsonify({'success': False, 'message': 'Login required.'}), 401
                return redirect(url_for('login_page'))

            user_role = (user_info.get('role') or '').lower()
            allowed_roles_lower = [r.lower() for r in allowed_roles]

            if user_role not in allowed_roles_lower:
                is_api = (request.path.startswith('/api/') or request.is_json or 
                          request.headers.get('Accept', '').find('application/json') != -1 or
                          request.headers.get('X-Requested-With') == 'XMLHttpRequest')
                if is_api:
                    return jsonify({
                        'success': False,
                        'message': f'Access denied. Required role(s): {", ".join(allowed_roles)}'
                    }), 403
                return jsonify({'success': False, 'message': f'Access denied. Required role(s): {", ".join(allowed_roles)}'}), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator

def admin_required(f):
    """Decorator to require admin role."""
    return role_required('admin')(f)

def teacher_required(f):
    """Decorator to require teacher, faculty, or admin role."""
    return role_required('teacher', 'faculty', 'admin')(f)

def faculty_required(f):
    """Decorator to require faculty or admin role."""
    return role_required('faculty', 'admin')(f)

def student_required(f):
    """Decorator to require student, teacher, faculty, or admin role (for read-only student views)."""
    return role_required('student', 'teacher', 'faculty', 'admin')(f)



def get_current_user():
    """
    Get the currently logged-in user from database.
    
    Returns:
        User object or None if not logged in
    """
    if 'user_id' not in session:
        return None
    
    try:
        user = User.query.get(session.get('user_id'))
        return user
    except Exception:
        return None


def log_audit_action(user_id, action, table_name=None, record_id=None, 
                     old_value=None, new_value=None, details=None):
    """
    Log an action to the audit trail.
    
    Args:
        user_id: ID of user performing action
        action: Name of action (e.g., 'attendance_marked', 'user_created')
        table_name: Name of table affected
        record_id: ID of affected record
        old_value: JSON string of old data
        new_value: JSON string of new data
        details: Additional details
    """
    try:
        # Get IP address from request if available
        ip_address = request.remote_addr if request else None
        
        audit_log = AuditLog(
            user_id=user_id,
            action=action,
            table_name=table_name,
            record_id=record_id,
            old_value=old_value,
            new_value=new_value,
            ip_address=ip_address,
            details=details,
            timestamp=datetime.utcnow()
        )
        db.session.add(audit_log)
        db.session.commit()
    except Exception as e:
        print(f"Error logging audit action: {e}")
        db.session.rollback()


def check_permission(user_id, action, resource_type, resource_id=None):
    """
    Check if a user has permission to perform an action on a resource.
    
    Args:
        user_id: ID of user
        action: Action type (e.g., 'view', 'edit', 'delete')
        resource_type: Type of resource (e.g., 'attendance', 'student')
        resource_id: Optional ID of specific resource
    
    Returns:
        Boolean indicating if user has permission
    """
    try:
        user = User.query.get(user_id)
        if not user:
            return False
        
        role = user.role.lower()
        
        # Admin can do anything
        if role == 'admin':
            return True
        
        # Define permissions per role
        permissions = {
            'admin': {
                'attendance': ['view', 'edit', 'delete', 'export'],
                'student': ['view', 'edit', 'delete'],
                'user': ['view', 'edit', 'delete', 'create'],
                'class': ['view', 'edit', 'delete', 'create'],
                'subject': ['view', 'edit', 'delete', 'create'],
            },
            'faculty': {
                'attendance': ['view', 'edit', 'export'],
                'student': ['view', 'edit'],
                'class': ['view', 'edit'],
                'subject': ['view'],
            },
            'teacher': {
                'attendance': ['view', 'edit', 'export'],
                'student': ['view'],
                'class': ['view'],
                'subject': ['view'],
            },
            'student': {
                'attendance': ['view'],
                'student': ['view'],  # Own profile only
            },
        }
        
        role_perms = permissions.get(role, {})
        resource_perms = role_perms.get(resource_type, [])
        
        return action in resource_perms
    
    except Exception:
        return False
