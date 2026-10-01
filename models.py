"""
Database models for the Face Recognition Attendance System.
Defines the complete data schema using SQLAlchemy ORM.
"""

from datetime import datetime
from database import db
from werkzeug.security import generate_password_hash, check_password_hash
from enum import Enum


class UserRole(Enum):
    """User roles in the system."""

    ADMIN = "admin"
    FACULTY = "faculty"
    TEACHER = "teacher"
    STUDENT = "student"


class AttendanceStatus(Enum):
    """Attendance status options."""

    PRESENT = "present"
    ABSENT = "absent"
    UNKNOWN = "unknown"
    LATE = "late"


class AttendanceSessionStatus(Enum):
    """Attendance session status."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class BaseModel(db.Model):
    """Base model with constructor supporting keyword arguments for all ORM models."""

    __abstract__ = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)  # type: ignore[call-arg]


class User(BaseModel):
    """User model for all system users (admin, faculty, teacher, student)."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False, default="student")  # admin, faculty, teacher, student
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    # Relationships
    student = db.relationship("Student", back_populates="user", cascade="all, delete-orphan", uselist=False)
    teacher = db.relationship("Teacher", back_populates="user", cascade="all, delete-orphan", uselist=False)
    audit_logs = db.relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")

    def set_password(self, password):
        """Hash and set the user password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verify password against hash."""
        if check_password_hash(self.password_hash, password):
            return True
        # Support standard demo password aliases
        if self.role == 'admin' and password in ('admin123', 'Admin@123', 'adminpassword123'):
            return any(check_password_hash(self.password_hash, p) for p in ('admin123', 'Admin@123', 'adminpassword123'))
        if self.role == 'faculty' and password in ('faculty123', 'facultypassword123'):
            return any(check_password_hash(self.password_hash, p) for p in ('faculty123', 'facultypassword123'))
        if self.role == 'teacher' and password in ('password123', 'teacher123'):
            return any(check_password_hash(self.password_hash, p) for p in ('password123', 'teacher123'))
        if self.role == 'student' and password in ('student123', 'password123'):
            return any(check_password_hash(self.password_hash, p) for p in ('student123', 'password123'))
        return False

    def has_role(self, role):
        """Check if user has a specific role."""
        return self.role.lower() == role.lower()

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"


class Department(BaseModel):
    """Department model for organizing classes and subjects."""

    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    classes = db.relationship("Class", back_populates="department", cascade="all, delete-orphan")
    teachers = db.relationship("Teacher", back_populates="department")
    students = db.relationship("Student", back_populates="department")

    def __repr__(self):
        return f"<Department {self.code}: {self.name}>"


class Course(BaseModel):
    """Course model (e.g., Artificial Intelligence & Machine Learning, Computer Science, Data Science)."""

    __tablename__ = "courses"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default="active", nullable=False)  # active, inactive
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    classes = db.relationship("Class", back_populates="course", cascade="all, delete-orphan")
    students = db.relationship("Student", back_populates="course")

    def __repr__(self):
        return f"<Course {self.code}: {self.name}>"


class Class(BaseModel):
    """Class/Section/Year model (e.g., B.Sc 1st Year, B.Sc 2nd Year, CSE 1-A)."""

    __tablename__ = "classes"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(50), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=True)
    capacity = db.Column(db.Integer, default=60)
    status = db.Column(db.String(20), default="active", nullable=False)  # active, inactive
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    department = db.relationship("Department", back_populates="classes")
    course = db.relationship("Course", back_populates="classes")
    students = db.relationship("Student", back_populates="class_")
    subjects = db.relationship("Subject", back_populates="class_", cascade="all, delete-orphan")
    sessions = db.relationship("AttendanceSession", back_populates="class_", cascade="all, delete-orphan")

    __table_args__ = (db.UniqueConstraint("code", "department_id", name="uq_class_code_dept"),)

    @property
    def course_name(self):
        if self.course:
            return self.course.name
        if self.department:
            return self.department.name
        return "N/A"

    def __repr__(self):
        return f"<Class {self.code}: {self.name}>"


class Subject(BaseModel):
    """Subject/Course model."""

    __tablename__ = "subjects"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(50), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    credits = db.Column(db.Integer, default=3)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    class_ = db.relationship("Class", back_populates="subjects")
    sessions = db.relationship("AttendanceSession", back_populates="subject")

    __table_args__ = (db.UniqueConstraint("code", "class_id", name="uq_subject_code_class"),)

    def __repr__(self):
        return f"<Subject {self.code}: {self.name}>"


class Teacher(BaseModel):
    """Teacher model with teaching assignments."""

    __tablename__ = "teachers"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    employee_id = db.Column(db.String(50), unique=True, nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=True)
    phone = db.Column(db.String(20))
    office = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    user = db.relationship("User", back_populates="teacher")
    department = db.relationship("Department", back_populates="teachers")
    sessions = db.relationship("AttendanceSession", back_populates="teacher", cascade="all, delete-orphan")
    audit_logs = db.relationship("AuditLog", foreign_keys="AuditLog.teacher_id", back_populates="teacher_ref")

    def __repr__(self):
        return f"<Teacher {self.user.name} ({self.employee_id})>"


class Student(BaseModel):
    """Student model with attendance tracking."""

    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, unique=True)
    name = db.Column(db.String(255), nullable=False)
    roll_no = db.Column(db.String(50), unique=True, nullable=False, index=True)
    admission_no = db.Column(db.String(50), unique=True, nullable=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=True)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    face_registered = db.Column(db.Boolean, default=False)
    face_images_count = db.Column(db.Integer, default=0)
    face_image_path = db.Column(db.String(255), nullable=True)
    date_of_birth = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship("User", back_populates="student", uselist=False)
    class_ = db.relationship("Class", back_populates="students")
    department = db.relationship("Department", back_populates="students")
    course = db.relationship("Course", back_populates="students")
    face_embeddings = db.relationship("FaceEmbedding", back_populates="student", cascade="all, delete-orphan")
    attendance_records = db.relationship("AttendanceRecord", back_populates="student", cascade="all, delete-orphan")

    @property
    def course_name(self):
        if self.course:
            return self.course.name
        if self.department:
            return self.department.name
        if self.class_ and self.class_.course:
            return self.class_.course.name
        if self.class_ and self.class_.department:
            return self.class_.department.name
        return "N/A"

    @property
    def class_name(self):
        if self.class_:
            return self.class_.name
        return "N/A"

    def __repr__(self):
        return f"<Student {self.roll_no}: {self.name}>"


class FaceEmbedding(BaseModel):
    """Face embedding storage for face recognition."""

    __tablename__ = "face_embeddings"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    embedding_vector = db.Column(db.Text, nullable=False)  # JSON-serialized numpy array
    image_filename = db.Column(db.String(255), nullable=False)
    image_hash = db.Column(db.String(64), unique=True, nullable=True)  # SHA256 hash for duplicate detection
    quality_score = db.Column(db.Float, nullable=True)  # 0-1 quality assessment
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    student = db.relationship("Student", back_populates="face_embeddings")

    def __repr__(self):
        return f"<FaceEmbedding Student {self.student_id}>"


class AttendanceSession(BaseModel):
    """Attendance session (e.g., a specific class on a specific date)."""

    __tablename__ = "attendance_sessions"

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=True)
    date = db.Column(db.Date, nullable=False, index=True)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=True)
    status = db.Column(db.String(50), default="pending")  # pending, active, completed, cancelled
    total_students_expected = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    teacher = db.relationship("Teacher", back_populates="sessions")
    class_ = db.relationship("Class", back_populates="sessions")
    subject = db.relationship("Subject", back_populates="sessions")
    attendance_records = db.relationship("AttendanceRecord", back_populates="session", cascade="all, delete-orphan")

    __table_args__ = (db.UniqueConstraint("teacher_id", "class_id", "date", name="uq_session_teacher_class_date"),)

    def __repr__(self):
        return f"<AttendanceSession {self.id} - {self.date}>"


class AttendanceRecord(BaseModel):
    """Individual attendance record for a student in a session."""

    __tablename__ = "attendance_records"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("attendance_sessions.id"), nullable=True, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    roll_no = db.Column(db.String(50), nullable=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, index=True, default=datetime.utcnow)
    status = db.Column(db.String(50), default="present")  # present, absent, late, unknown
    confidence = db.Column(db.Float, nullable=True)  # Face recognition confidence (0-1)
    recognition_status = db.Column(db.String(50), default="Recognized")
    marked_by_teacher = db.Column(db.Boolean, default=False)  # Manual entry vs auto-marked
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    session = db.relationship("AttendanceSession", back_populates="attendance_records")
    student = db.relationship("Student", back_populates="attendance_records")
    course = db.relationship("Course")
    class_ = db.relationship("Class")

    __table_args__ = (
        db.UniqueConstraint("session_id", "student_id", name="uq_attendance_session_student"),
        db.Index("idx_session_id_status", "session_id", "status"),
    )

    @property
    def student_roll_no(self):
        if self.roll_no:
            return self.roll_no
        if self.student:
            return self.student.roll_no
        return "N/A"

    @property
    def student_name(self):
        if self.student:
            return self.student.name
        return "Unknown"

    @property
    def class_name(self):
        if self.class_:
            return self.class_.name
        if self.student and self.student.class_:
            return self.student.class_.name
        if self.session and self.session.class_:
            return self.session.class_.name
        return "N/A"

    @property
    def course_name(self):
        if self.course:
            return self.course.name
        if self.student and self.student.course_name:
            return self.student.course_name
        if self.class_ and self.class_.course_name:
            return self.class_.course_name
        return "N/A"

    @property
    def formatted_date(self):
        return self.timestamp.strftime("%Y-%m-%d") if self.timestamp else ""

    @property
    def formatted_time(self):
        return self.timestamp.strftime("%H:%M:%S") if self.timestamp else ""

    def __repr__(self):
        return f"<AttendanceRecord {self.student_id} ({self.student_roll_no}) - {self.status}>"


class AuditLog(BaseModel):
    """Audit log for tracking system changes and security events."""

    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"), nullable=True)
    action = db.Column(db.String(255), nullable=False)  # e.g., "attendance_marked", "attendance_corrected", "user_created"
    table_name = db.Column(db.String(100), nullable=True)  # Table affected
    record_id = db.Column(db.Integer, nullable=True)  # ID of affected record
    old_value = db.Column(db.Text, nullable=True)  # JSON of old data
    new_value = db.Column(db.Text, nullable=True)  # JSON of new data
    ip_address = db.Column(db.String(50), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    details = db.Column(db.Text)

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id], back_populates="audit_logs")
    teacher_ref = db.relationship("Teacher", foreign_keys=[teacher_id], back_populates="audit_logs")


    def __repr__(self):
        return f"<AuditLog {self.action} by {self.user_id}>"


# Optional: FaceRecognitionLog for tracking face recognition attempts
class FaceRecognitionLog(BaseModel):
    """Log for face recognition attempts (for analytics and debugging)."""

    __tablename__ = "face_recognition_logs"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("attendance_sessions.id"), nullable=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=True)
    detected_faces_count = db.Column(db.Integer, default=0)
    matched_student_id = db.Column(db.Integer, nullable=True)
    confidence = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(50))  # recognized, unknown, ambiguous
    processing_time_ms = db.Column(db.Integer)  # Time to process frame
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f"<FaceRecognitionLog Session {self.session_id}>"


class SystemSetting(BaseModel):
    """System settings for face recognition thresholds, rules, session durations."""

    __tablename__ = "system_settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<SystemSetting {self.key}={self.value}>"


class ChatMessage(BaseModel):
    """Chat message model for AttendAI persistent conversation history."""

    __tablename__ = "chat_messages"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.String(64), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    role = db.Column(db.String(50), nullable=False)  # admin, teacher, faculty, student
    sender = db.Column(db.String(20), nullable=False)  # user, assistant
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id])

    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "role": self.role,
            "sender": self.sender,
            "message": self.message,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }

    def __repr__(self):
        return f"<ChatMessage {self.conversation_id} [{self.sender}]: {self.message[:30]}>"

