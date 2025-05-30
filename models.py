from app import db, login_manager
from flask_login import UserMixin
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import uuid

@login_manager.user_loader
def load_user(id):
    return Manager.query.get(int(id))

class Manager(UserMixin, db.Model):
    __tablename__ = 'professor'  # Keep old table name for DB compatibility
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    full_name = db.Column(db.String(100))
    is_admin = db.Column(db.Boolean, default=False)
    departments = db.relationship('Department', secondary='professor_class', backref='managers')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Employee(db.Model):
    __tablename__ = 'student'  # Keep old table name for DB compatibility
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    student_id = db.Column(db.String(20), unique=True, nullable=False)  # Kept as student_id for DB compatibility
    department_id = db.Column('class_id', db.Integer, db.ForeignKey('class.id'))  # Keep old column name
    face_encoding = db.Column(db.PickleType)

class Department(db.Model):
    __tablename__ = 'class'  # Keep old table name for DB compatibility
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    employees = db.relationship('Employee', backref='department', lazy='dynamic', cascade="all, delete-orphan")
    schedules = db.relationship('DepartmentSchedule', backref='department', cascade="all, delete-orphan")
    attendances = db.relationship('Attendance', backref='department', cascade="all, delete-orphan")
    checkinouts = db.relationship('CheckInOut', backref='department', cascade="all, delete-orphan")

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column('student_id', db.Integer, db.ForeignKey('student.id'))  # Keep old column name
    department_id = db.Column('class_id', db.Integer, db.ForeignKey('class.id'))  # Keep old column name
    manager_id = db.Column('professor_id', db.Integer, db.ForeignKey('professor.id'))  # Keep old column name
    date = db.Column(db.DateTime, default=datetime.utcnow)
    present = db.Column(db.Boolean, default=False)
    method = db.Column(db.String(20))  # 'facial' or 'manual'
    schedule_id = db.Column(db.Integer, db.ForeignKey('class_schedule.id'), nullable=True)

class DepartmentSchedule(db.Model):
    __tablename__ = 'class_schedule'  # Keep old table name for DB compatibility
    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column('class_id', db.Integer, db.ForeignKey('class.id'), nullable=False)  # Keep old column name
    day_of_week = db.Column(db.Integer, nullable=False)  # 0-6, Lundi-Dimanche
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    room_number = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    active = db.Column(db.Boolean, default=True)

class InvitationCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('professor.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    is_used = db.Column(db.Boolean, default=False)
    used_by = db.Column(db.Integer, db.ForeignKey('professor.id'), nullable=True)
    used_at = db.Column(db.DateTime, nullable=True)

    @staticmethod
    def generate_code():
        return ''.join([str(uuid.uuid4().int)[:8]])
    
    @staticmethod
    def create_new(created_by, expires_in_days=30):
        code = InvitationCode(
            code=InvitationCode.generate_code(),
            created_by=created_by,
            expires_at=datetime.utcnow() + timedelta(days=expires_in_days)
        )
        db.session.add(code)
        db.session.commit()
        return code

class CheckInOut(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column('student_id', db.Integer, db.ForeignKey('student.id'), nullable=False)  # Keep old column name
    department_id = db.Column('class_id', db.Integer, db.ForeignKey('class.id'), nullable=False)  # Keep old column name
    schedule_id = db.Column(db.Integer, db.ForeignKey('class_schedule.id'), nullable=False)
    time = db.Column(db.DateTime, default=datetime.utcnow)
    type = db.Column(db.String(10), nullable=False)  # 'check-in' or 'check-out'
    method = db.Column(db.String(20), default='facial')  # 'facial' or 'manual'
    confidence = db.Column(db.Float, nullable=True)  # For facial recognition confidence
    
    # Relationships
    employee = db.relationship('Employee', backref=db.backref('checkinouts', lazy='dynamic'))
    schedule = db.relationship('DepartmentSchedule', backref=db.backref('checkinouts', lazy='dynamic'))

# Keep old table name for DB compatibility
professor_class = db.Table('professor_class',
    db.Column('professor_id', db.Integer, db.ForeignKey('professor.id')),
    db.Column('class_id', db.Integer, db.ForeignKey('class.id'))
)
