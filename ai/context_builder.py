"""
AttendAI Database Context Builder.
Retrieves real-time ground-truth data from SQLAlchemy models bounded by user role and permissions.
"""

from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional
import csv
from pathlib import Path


def build_database_context(user_info: Dict[str, Any], query_text: str = "") -> str:
    """
    Build real-time database context based on the authenticated user's role.
    Respects strict authorization rules.
    """
    from models import (
        User, Course, Class, Student, Teacher, Department,
        Subject, AttendanceRecord, AttendanceSession, SystemSetting
    )
    from database import db

    role = (user_info.get("role") or "student").lower().strip()
    user_id = user_info.get("user_id")
    user_name = user_info.get("name", "")
    today_str = datetime.now().strftime("%Y-%m-%d")

    context_lines = [
        f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Authenticated User ID: {user_id}",
        f"Authenticated Name: {user_name}",
        f"Authenticated Role: {role.upper()}",
    ]

    try:
        # ====================================================================
        # ADMIN ROLE CONTEXT: Full System Visibility
        # ====================================================================
        if role == "admin":
            total_users = User.query.count()
            admin_count = User.query.filter_by(role="admin").count()
            teacher_count = User.query.filter_by(role="teacher").count()
            faculty_count = User.query.filter_by(role="faculty").count()
            student_count = User.query.filter_by(role="student").count()

            courses = Course.query.all()
            classes = Class.query.all()
            departments = Department.query.all()
            students = Student.query.all()
            registered_faces = Student.query.filter_by(face_registered=True).count()

            # Today's attendance
            today_records = AttendanceRecord.query.filter(
                db.func.date(AttendanceRecord.timestamp) == today_str
            ).all()
            present_today = sum(1 for r in today_records if (r.status or "").lower() == "present")

            context_lines.append("\n[Admin Overview Data]")
            context_lines.append(f"- Total Users: {total_users} (Admins: {admin_count}, Teachers: {teacher_count}, Faculty: {faculty_count}, Students: {student_count})")
            context_lines.append(f"- Total Registered Students: {len(students)} (With Face Enrolled: {registered_faces})")
            context_lines.append(f"- Total Courses: {len(courses)}")
            for c in courses:
                context_lines.append(f"  * Course: {c.name} (Code: {c.code}, Status: {c.status})")
            context_lines.append(f"- Total Classes: {len(classes)}")
            for cls in classes:
                c_name = cls.course.name if cls.course else "General"
                context_lines.append(f"  * Class: {cls.name} (Code: {cls.code}, Course: {c_name}, Capacity: {cls.capacity})")
            context_lines.append(f"- Today's Total Attendance Records: {len(today_records)} (Present Today: {present_today})")

        # ====================================================================
        # TEACHER ROLE CONTEXT: Classes, Attendance & Roster
        # ====================================================================
        elif role == "teacher":
            courses = Course.query.filter_by(status="active").all()
            classes = Class.query.filter_by(status="active").all()
            total_students = Student.query.count()
            registered_faces = Student.query.filter_by(face_registered=True).count()

            # Today's attendance
            today_records = AttendanceRecord.query.filter(
                db.func.date(AttendanceRecord.timestamp) == today_str
            ).all()

            present_students = []
            for r in today_records:
                if (r.status or "").lower() == "present":
                    present_students.append(f"{r.student_name} ({r.student_roll_no}, {r.formatted_time})")

            present_count = len(present_students)
            absent_count = max(0, total_students - present_count)
            rate = int((present_count / total_students * 100)) if total_students > 0 else 0

            context_lines.append("\n[Teacher Classroom & Attendance Data]")
            context_lines.append(f"- Total Students in System: {total_students} (Faces Enrolled: {registered_faces})")
            context_lines.append(f"- Today's Date: {today_str}")
            context_lines.append(f"- Students Present Today: {present_count}")
            context_lines.append(f"- Students Absent Today: {absent_count}")
            context_lines.append(f"- Today's Attendance Rate: {rate}%")
            if present_students:
                context_lines.append(f"- Present Students Today Sample: {', '.join(present_students[:10])}")
            else:
                context_lines.append("- No students marked present yet today.")

            context_lines.append("- Available Classes:")
            for cls in classes[:10]:
                context_lines.append(f"  * {cls.name} (Code: {cls.code})")

        # ====================================================================
        # FACULTY ROLE CONTEXT: Department and Assigned Classes
        # ====================================================================
        elif role == "faculty":
            user = db.session.get(User, user_id) if user_id else None
            teacher_profile = getattr(user, "teacher", None) if user else None
            dept = teacher_profile.department if teacher_profile and teacher_profile.department else Department.query.first()

            context_lines.append("\n[Faculty Department Data]")
            if dept:
                dept_classes = Class.query.filter(Class.department_id == dept.id).all()
                dept_students_count = Student.query.filter(Student.department_id == dept.id).count()
                context_lines.append(f"- Department: {dept.name} (Code: {dept.code})")
                context_lines.append(f"- Department Student Count: {dept_students_count}")
                context_lines.append(f"- Department Classes ({len(dept_classes)}):")
                for cls in dept_classes:
                    context_lines.append(f"  * {cls.name} (Code: {cls.code})")
            else:
                # General faculty view if department not yet assigned
                classes = Class.query.all()
                context_lines.append("- Department: General Faculty")
                context_lines.append(f"- Available Classes ({len(classes)}):")
                for cls in classes[:5]:
                    context_lines.append(f"  * {cls.name} (Code: {cls.code})")

            # Today's department attendance
            today_records = AttendanceRecord.query.filter(
                db.func.date(AttendanceRecord.timestamp) == today_str
            ).all()
            context_lines.append(f"- Department Attendance Records Today: {len(today_records)}")

        # ====================================================================
        # STUDENT ROLE CONTEXT: STRICT SELF-SERVICE ONLY
        # ====================================================================
        elif role == "student":
            student = None
            if user_id:
                student = db.session.get(Student, user_id)
                if not student:
                    user = db.session.get(User, user_id)
                    student = user.student if user else None
                    if not student and user and user.email:
                        student = Student.query.filter_by(email=user.email).first()
            if not student and user_info and user_info.get('student_id'):
                student = db.session.get(Student, user_info.get('student_id'))
            if not student and user_info and user_info.get('email'):
                student = Student.query.filter_by(email=user_info.get('email')).first()

            # Check if query is suspiciously attempting to probe other students
            lower_q = query_text.lower()
            privacy_violation_triggers = [
                "other student", "another student", "friend's attendance",
                "someone else", "all students", "student list", "teacher password", "admin password"
            ]
            has_violation = any(trigger in lower_q for trigger in privacy_violation_triggers)

            context_lines.append("\n[Student Self Profile & Attendance Data]")
            if has_violation:
                context_lines.append("SECURITY POLICY ALERT: The student is asking about another person or restricted system data.")
                context_lines.append("INSTRUCTION: Refuse the request strictly. State: 'Under AttendAI privacy policy, you can only access your own attendance records and profile.'")

            if student:
                all_records = AttendanceRecord.query.filter(
                    db.or_(AttendanceRecord.student_id == student.id, AttendanceRecord.roll_no == student.roll_no)
                ).order_by(AttendanceRecord.timestamp.desc()).all()

                total_classes = len(all_records)
                present_count = sum(1 for r in all_records if (r.status or "").lower() == "present")
                absent_count = sum(1 for r in all_records if (r.status or "").lower() == "absent")
                late_count = sum(1 for r in all_records if (r.status or "").lower() == "late")
                pct = int((present_count / total_classes * 100)) if total_classes > 0 else 0

                context_lines.append(f"- Student Name: {student.name}")
                context_lines.append(f"- Roll Number: {student.roll_no}")
                context_lines.append(f"- Admission Number: {student.admission_no or 'N/A'}")
                context_lines.append(f"- Course: {student.course_name}")
                context_lines.append(f"- Class: {student.class_name}")
                context_lines.append(f"- Face Enrolled in Biometric System: {'Yes' if student.face_registered else 'No'}")
                context_lines.append(f"- Total Recorded Classes: {total_classes}")
                context_lines.append(f"- Present: {present_count}")
                context_lines.append(f"- Absent: {absent_count}")
                context_lines.append(f"- Late: {late_count}")
                context_lines.append(f"- Overall Attendance Percentage: {pct}%")
                if pct < 75 and total_classes > 0:
                    context_lines.append("- Low Attendance Alert: ATTENDANCE IS BELOW 75% REQUIREMENT.")

                if all_records:
                    context_lines.append("- Recent Attendance History (Last 5 sessions):")
                    for r in all_records[:5]:
                        context_lines.append(f"  * Date: {r.formatted_date}, Status: {r.status.capitalize()}, Time: {r.formatted_time}")
                else:
                    context_lines.append("- No past attendance records found for this student.")
            else:
                context_lines.append("- Note: Student profile not linked to this user account yet.")

    except Exception as e:
        context_lines.append(f"\n[Database Context Note: {e}]")

    return "\n".join(context_lines)
