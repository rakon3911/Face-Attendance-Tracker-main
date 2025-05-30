from flask import render_template, redirect, url_for, request, jsonify, flash, make_response
from flask_login import login_user, logout_user, login_required, current_user
from flask_weasyprint import HTML, render_pdf
from app import app, db, csrf
from models import Manager, Employee, Department, Attendance, DepartmentSchedule, InvitationCode, CheckInOut
from face_recognition_utils import get_face_encoding, identify_employee, process_frame
import cv2
import numpy as np
from datetime import datetime, timedelta, time
import base64
import logging
from functools import wraps
import os

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Gestionnaires d'erreurs
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Veuillez remplir tous les champs', 'error')
            return render_template('login.html')
            
        manager = Manager.query.filter_by(username=username).first()
        if manager and manager.check_password(password):
            login_user(manager)
            return redirect(url_for('dashboard'))
        flash('Nom d\'utilisateur ou mot de passe incorrect', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    # Si l'utilisateur est déjà connecté, rediriger vers le dashboard
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        invitation_code = request.form.get('invitation_code')
        username = request.form.get('username')
        email = request.form.get('email')
        full_name = request.form.get('full_name')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validation des données
        if not all([invitation_code, username, email, full_name, password, confirm_password]):
            flash('Tous les champs sont requis', 'error')
            return render_template('register.html')
            
        if password != confirm_password:
            flash('Les mots de passe ne correspondent pas', 'error')
            return render_template('register.html')
        
        # Vérifier le code d'invitation
        code = InvitationCode.query.filter_by(code=invitation_code, is_used=False).first()
        if not code or code.expires_at < datetime.now():
            flash('Code d\'invitation invalide ou expiré', 'error')
            return render_template('register.html')
          # Vérifier si l'utilisateur existe déjà
        existing_user = Manager.query.filter(
            (Manager.username == username) | 
            (Manager.email == email)
        ).first()
        
        if existing_user:
            flash('Ce nom d\'utilisateur ou cet email est déjà utilisé', 'error')
            return render_template('register.html')
        
        try:            # Créer le nouvel utilisateur
            new_manager = Manager(
                username=username,
                email=email,
                full_name=full_name
            )
            new_manager.set_password(password)
            
            db.session.add(new_manager)
            
            # Marquer le code d'invitation comme utilisé
            code.is_used = True
            code.used_by = new_manager.id
            code.used_at = datetime.now()
            
            db.session.commit()
            
            flash('Votre compte a été créé avec succès! Vous pouvez maintenant vous connecter.', 'success')
            logger.info(f"New professor registered: {username}")
            return redirect(url_for('login'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error during registration: {e}")
            flash('Une erreur est survenue lors de l\'inscription', 'error')
    
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    classes = current_user.departments
    
    # Calculate employee counts for each class
    employee_counts = {}
    for class_ in classes:
        employee_counts[class_.id] = class_.employees.count()

    # Passer la date actuelle au template
    now = datetime.now()
    
    # Récupérer les statistiques de présence pour les 7 derniers jours
    attendance_stats = []
    labels = []
    
    # Pour chaque jour des 7 derniers jours
    for i in range(6, -1, -1):
        date = datetime.now() - timedelta(days=i)
        date_str = date.strftime('%d/%m')
        labels.append(date_str)
        
        # Compter les présences pour ce jour
        daily_attendance = db.session.query(
            db.func.count(Attendance.id)
        ).filter(
            db.func.date(Attendance.date) == date.date(),
            Attendance.present == True,
            Attendance.manager_id == current_user.id        ).scalar() or 0
        
        # Compter le nombre total d'employés dans les départements du manager
        total_students = db.session.query(
            db.func.count(Employee.id)
        ).join(Department).filter(
            Department.id.in_([c.id for c in classes])
        ).scalar() or 1  # Éviter division par zéro
        
        if total_students > 0:
            attendance_rate = (daily_attendance / total_students) * 100
        else:
            attendance_rate = 0
            
        attendance_stats.append(round(attendance_rate, 1))
        
    return render_template('dashboard.html', 
                          classes=classes, 
                          attendance_stats=attendance_stats,
                          attendance_labels=labels,
                          now=now,
                          employee_counts=employee_counts)

@app.route('/attendance/<int:class_id>')
@login_required
def attendance(class_id):
    class_ = Department.query.get_or_404(class_id)
    if class_ not in current_user.departments:
        flash('Unauthorized access')
        return redirect(url_for('dashboard'))
      # Récupérer toutes les séances pour cette classe
    schedules = DepartmentSchedule.query.filter_by(department_id=class_id, active=True).all()
    
    # Fetch the list of employees for this department
    employees = class_.employees.all()
    
    # Obtenir la date et l'heure actuelle
    now = datetime.now()
    current_time = now.time()
    current_day = now.weekday()
    
    # Trouver la séance actuelle s'il y en a une
    current_schedule = None
    for schedule in schedules:
        if schedule.day_of_week == current_day and schedule.start_time <= current_time <= schedule.end_time:
            current_schedule = schedule
            break
    
    return render_template('attendance.html', class_=class_, schedules=schedules, 
                          current_schedule=current_schedule, now=now, employees=employees)

@app.route('/process_attendance', methods=['POST'])
@login_required
def process_attendance():
    try:
        # Obtenir la date et l'heure actuelle au début
        now = datetime.now()

        class_id = request.form.get('class_id')
        schedule_id = request.form.get('schedule_id')
        image_data = request.form.get('image')

    # Validation de la séance
        if not schedule_id:
            return jsonify({'success': False, 'message': 'ID de séance manquant'})
        
        schedule = DepartmentSchedule.query.get_or_404(schedule_id)
        if schedule.department_id != int(class_id):
            return jsonify({'success': False, 'message': 'Séance invalide pour cette classe'})        # Convert base64 image to numpy array
        encoded_data = image_data.split(',')[1]
        nparr = np.frombuffer(base64.b64decode(encoded_data), np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        face_encoding = get_face_encoding(img)
        if face_encoding is not None:
            employee_id, employee_name, confidence = identify_employee(face_encoding, class_id)
            if employee_id:
                # Vérifier si une présence n'a pas déjà été enregistrée pour cette séance
                today = datetime.now().date()
                
                # Calculer la date de la séance (en cas de détection rétrospective)                now = datetime.now()
                days_diff = (schedule.day_of_week - now.weekday()) % 7
                session_date = (now + timedelta(days=days_diff)).date()
                
                existing_attendance = Attendance.query.filter(
                    Attendance.employee_id == employee_id,
                    Attendance.department_id == class_id,
                    Attendance.schedule_id == schedule_id,
                    db.func.date(Attendance.date) == session_date
                ).first()
                
                if not existing_attendance:
                    attendance = Attendance(
                        employee_id=employee_id,
                        department_id=class_id,
                        manager_id=current_user.id,
                        present=True,
                        method='facial',
                        schedule_id=schedule_id
                    )
                    db.session.add(attendance)
                    db.session.commit()

                    logger.info(f"Facial attendance recorded for employee {employee_name} with confidence {confidence}%")
                    return jsonify({
                        'success': True,
                        'employee_id': employee_id,
                        'employee_name': employee_name,
                        'confidence': confidence,
                        'message': f'Présence enregistrée pour {employee_name} pour la séance sélectionnée'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': f'Présence déjà enregistrée pour {employee_name} pour cette séance'
                    })

        logger.warning("Face recognition failed or no face detected")
        return jsonify({'success': False, 'message': 'Aucun visage détecté ou reconnaissance échouée'})
    except Exception as e:
        logger.error(f"Error processing attendance: {e}")
        return jsonify({'success': False, 'message': f'Erreur lors du traitement de la présence: {str(e)}'})

@app.route('/manage_classes')
@login_required
def manage_classes():
    # Ensure only managers can access this page
    if not current_user.is_admin:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('dashboard'))

    departments = Department.query.all()

    # Calculate employee counts for each department
    employee_counts = {}
    for class_ in departments:
        employees = class_.employees.all() # Fetch the list of employees
        employee_counts[class_.id] = len(employees) # Now get the length of the list

    return render_template('manage_classes.html', classes=departments, employee_counts=employee_counts)

@app.route('/manage_department')
@login_required
def manage_department():
    classes = current_user.departments
    return render_template('departments.html', classes=classes)

@app.route('/manual_attendance', methods=['POST'])
@login_required
def manual_attendance():
    try:
        student_id = request.form.get('student_id')
        class_id = request.form.get('class_id')
        schedule_id = request.form.get('schedule_id')
        present = request.form.get('present') == 'true'

        # Si un ID de séance est fourni, toujours utiliser mark_session_attendance
        if schedule_id:
            # Rediriger vers la fonction mark_session_attendance
            return mark_session_attendance()
        
        # Ce code ne devrait plus jamais être exécuté si tous les formulaires
        # incluent schedule_id, mais conservé pour la compatibilité descendante
        logger.warning("Creating attendance without schedule_id - deprecated usage")
        attendance = Attendance(
            student_id=student_id,
            class_id=class_id,
            professor_id=current_user.id,
            present=present,
            method='manual'
        )
        db.session.add(attendance)
        db.session.commit()
        logger.info(f"Manual attendance recorded for student {student_id}")
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error recording manual attendance: {e}")
        return jsonify({'success': False, 'message': f'Error recording attendance: {str(e)}'})


@app.route('/create_class', methods=['POST'])
@login_required
def create_class():
    try:
        class_name = request.form.get('class_name')        
        if not class_name:
            flash('Le nom du département est requis', 'error')
            return redirect(url_for('manage_classes'))
        new_class = Department(name=class_name)
        db.session.add(new_class)
        db.session.commit()
        # Associate the new department with the current user
        current_user.departments.append(new_class)
        db.session.commit()
        flash(f'Le département "{class_name}" a été créé avec succès', 'success')
        logger.info(f"New department created: {class_name} by manager {current_user.id}")
        # Redirect to the employees page for the new department
        return redirect(url_for('manage_employes_class', class_id=new_class.id))
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating class: {e}")
        flash('Erreur lors de la création du département', 'error')
        return redirect(url_for('manage_classes'))

@app.route('/edit_class/<int:class_id>', methods=['POST'])
@login_required
def edit_class(class_id):
    try:
        # Get department with validation
        class_ = Department.query.get_or_404(class_id)
        if class_ not in current_user.departments:
            flash('Unauthorized access', 'error')
            return redirect(url_for('manage_classes'))
            
        # Get and validate new department name
        class_name = request.form.get('class_name', '').strip()
        if not class_name:
            flash('Department name is required', 'error')
            return redirect(url_for('manage_classes'))
            
        # Check for duplicate department name
        existing_dept = Department.query.filter(
            Department.name == class_name,
            Department.id != class_id
        ).first()
        if existing_dept:
            flash(f'A department with the name "{class_name}" already exists', 'error')
            return redirect(url_for('manage_classes'))
            
        # Update department name
        old_name = class_.name
        class_.name = class_name
        
        # Commit changes
        db.session.commit()
        
        flash(f'Department "{old_name}" has been renamed to "{class_name}" successfully', 'success')
        logger.info(f"Department {class_id} renamed from '{old_name}' to '{class_name}' by manager {current_user.id}")
        
        # Redirect to the employees page for the edited department
        return redirect(url_for('manage_employes_class', class_id=class_id))
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error editing department: {e}")
        flash('Error modifying department', 'error')
        return redirect(url_for('manage_classes'))

@app.route('/delete_class/<int:class_id>', methods=['POST'])
@login_required
def delete_class(class_id):
    try:
        # Get department with validation
        class_ = Department.query.get_or_404(class_id)
        if class_ not in current_user.departments:
            flash('Unauthorized access', 'error')
            return redirect(url_for('manage_classes'))
            
        class_name = class_.name
        
        # Begin deletion in proper order to maintain referential integrity
        try:
            # 1. Delete all check-in/out records for all employees in this department
            CheckInOut.query.filter_by(department_id=class_id).delete()
            
            # 2. Delete all attendance records for this department
            Attendance.query.filter_by(department_id=class_id).delete()
            
            # 3. Delete all schedules for this department
            DepartmentSchedule.query.filter_by(department_id=class_id).delete()
            
            # 4. Remove face encodings and delete employees
            employees = Employee.query.filter_by(department_id=class_id).all()
            for employee in employees:
                # Clear face encoding first
                if employee.face_encoding is not None:
                    employee.face_encoding = None
                    db.session.flush()
                db.session.delete(employee)
            
            # 5. Remove the department from manager associations
            current_user.departments.remove(class_)
            
            # 6. Finally delete the department itself
            db.session.delete(class_)
            
            # Commit all changes in one transaction
            db.session.commit()
            
            flash(f'Department "{class_name}" and all associated data have been deleted successfully', 'success')
            logger.info(f"Department {class_id} '{class_name}' and all associated data deleted by manager {current_user.id}")
            
        except Exception as e:
            # If any error occurs during deletion, rollback and raise to outer exception handler
            db.session.rollback()
            raise Exception(f"Error during cascading delete: {str(e)}")
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting department: {e}")
        flash('Error deleting department and associated data', 'error')
        
    return redirect(url_for('manage_classes'))

@app.route('/manage_schedules/<int:class_id>')
@login_required
def manage_schedules(class_id):
    class_ = Department.query.get_or_404(class_id)
    if class_ not in current_user.departments:
        flash('Accès non autorisé', 'error')
        return redirect(url_for('dashboard'))
    
    schedules = DepartmentSchedule.query.filter_by(department_id=class_id).all()
    return render_template('manage_schedules.html', class_=class_, schedules=schedules)

@app.route('/add_schedule/<int:class_id>', methods=['POST'])
@login_required
def add_schedule(class_id):
    try:
        class_ = Department.query.get_or_404(class_id)
        if class_ not in current_user.departments:
            flash('Accès non autorisé', 'error')
            return redirect(url_for('dashboard'))
        
        day_of_week = int(request.form.get('day_of_week'))
        start_time_str = request.form.get('start_time')
        end_time_str = request.form.get('end_time')
        room_number = request.form.get('room_number')
        
        # Validation
        if not all([start_time_str, end_time_str]) or day_of_week not in range(7):
            flash('Données invalides. Veuillez vérifier les informations.', 'error')
            return redirect(url_for('manage_schedules', class_id=class_id))
        
        # Conversion des chaînes d'heure en objets time
        start_time = datetime.strptime(start_time_str, '%H:%M').time()
        end_time = datetime.strptime(end_time_str, '%H:%M').time()
        
        if start_time >= end_time:
            flash('L\'heure de début doit être antérieure à l\'heure de fin.', 'error')
            return redirect(url_for('manage_schedules', class_id=class_id))
          # Créer le nouvel horaire
        new_schedule = DepartmentSchedule(
            department_id=class_id,
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
            room_number=room_number
        )
        
        db.session.add(new_schedule)
        db.session.commit()
        
        flash('Horaire ajouté avec succès!', 'success')
        logger.info(f"New schedule added for class {class_id}")
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding schedule: {e}")
        flash('Erreur lors de l\'ajout de l\'horaire.', 'error')
    
    return redirect(url_for('manage_schedules', class_id=class_id))

@app.route('/delete_schedule/<int:schedule_id>/<int:class_id>', methods=['POST'])
@login_required
def delete_schedule(schedule_id, class_id):
    try:
        class_ = Department.query.get_or_404(class_id)
        if class_ not in current_user.departments:
            flash('Accès non autorisé', 'error')
            return redirect(url_for('dashboard'))
        
        schedule = DepartmentSchedule.query.get_or_404(schedule_id)
        if schedule.department_id != class_id:
            flash('Accès non autorisé', 'error')
            return redirect(url_for('dashboard'))
        
        db.session.delete(schedule)
        db.session.commit()
        
        flash('Horaire supprimé avec succès!', 'success')
        logger.info(f"Schedule {schedule_id} deleted from class {class_id}")
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting schedule: {e}")
        flash('Erreur lors de la suppression de l\'horaire.', 'error')
    
    return redirect(url_for('manage_schedules', class_id=class_id))

@app.route('/session_attendance/<int:schedule_id>')
@login_required
def session_attendance(schedule_id):
    try:
        schedule = DepartmentSchedule.query.get_or_404(schedule_id)
        class_ = Department.query.get_or_404(schedule.department_id)
        
        if class_ not in current_user.departments:
            flash('Accès non autorisé', 'error')
            return redirect(url_for('dashboard'))
        
        # Obtenir la date courante
        now = datetime.now()
        
        # Calculer la date du jour de la semaine pour l'horaire choisi
        days_diff = (schedule.day_of_week - now.weekday()) % 7
        session_date = (now + timedelta(days=days_diff)).date()
        
        # Convertir les heures en format lisible
        start_time = schedule.start_time.strftime('%H:%M')
        end_time = schedule.end_time.strftime('%H:%M')
        
        # Récupérer tous les étudiants de la classe
        employees = class_.employees.all()
        
        # Récupérer les statuts de présence pour cette session
        attendance_status = {}
        present_count = 0
        absent_count = 0
        
        for student in employees:
            # Vérifier si l'étudiant a déjà été marqué pour cette session
            attendance_record = Attendance.query.filter(
                Attendance.employee_id == student.id,
                Attendance.department_id == class_.id,
                db.func.date(Attendance.date) == session_date,
                Attendance.schedule_id == schedule_id
            ).first()
            
            if attendance_record:
                attendance_status[student.id] = attendance_record
                if attendance_record.present:
                    present_count += 1
                else:
                    absent_count += 1
        
        unmarked_count = len(employees) - present_count - absent_count
        
        return render_template('session_attendance.html', 
                             class_=class_,
                             schedule_id=schedule_id,
                             students=employees,
                             session_date=session_date.strftime('%d/%m/%Y'),
                             start_time=start_time,
                             end_time=end_time,
                             room_number=schedule.room_number,
                             attendance_status=attendance_status,
                             present_count=present_count,
                             absent_count=absent_count,
                             unmarked_count=unmarked_count)
    
    except Exception as e:
        logger.error(f"Error accessing session attendance: {e}")
        flash('Une erreur est survenue lors de l\'accès à la session.', 'error')
        return redirect(url_for('dashboard'))

@app.route('/mark_session_attendance', methods=['POST'])
@login_required
def mark_session_attendance():
    try:
        student_id = request.form.get('student_id')
        class_id = request.form.get('class_id')
        schedule_id = request.form.get('schedule_id')
        present = request.form.get('present') == 'true'
        
        # Validation
        schedule = DepartmentSchedule.query.get_or_404(schedule_id)
        class_ = Department.query.get_or_404(class_id)
        
        if class_ not in current_user.departments:
            return jsonify({'success': False, 'message': 'Accès non autorisé'})
        
        # Calculer la date de la session
        now = datetime.now()
        days_diff = (schedule.day_of_week - now.weekday()) % 7
        session_date = (now + timedelta(days=days_diff)).date()
        
        # Vérifier si un enregistrement existe déjà
        existing_record = Attendance.query.filter(
            Attendance.employee_id == student_id,
            Attendance.department_id == class_id,
            db.func.date(Attendance.date) == session_date,
            Attendance.schedule_id == schedule_id
        ).first()
        
        if existing_record:
            # Mettre à jour l'enregistrement existant
            existing_record.present = present
            existing_record.date = datetime.now()  # Mettre à jour l'horodatage
        else:
            # Créer un nouvel enregistrement
            attendance = Attendance(
                employee_id=student_id,
                department_id=class_id,
                manager_id=current_user.id,
                present=present,
                method='manual',
                schedule_id=schedule_id
            )
            db.session.add(attendance)
        
        db.session.commit()
        
        # Calculer les nouveaux compteurs
        students = Employee.query.filter_by(department_id=class_id).all()
        
        attendance_records = Attendance.query.filter(
            Attendance.department_id == class_id,
            db.func.date(Attendance.date) == session_date,
            Attendance.schedule_id == schedule_id
        ).all()
        
        present_count = sum(1 for a in attendance_records if a.present)
        absent_count = len(attendance_records) - present_count
        unmarked_count = len(students) - len(attendance_records)
        
        return jsonify({
            'success': True, 
            'present_count': present_count,
            'absent_count': absent_count,
            'unmarked_count': unmarked_count
        })
        
    except Exception as e:
        logger.error(f"Error marking session attendance: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/export_attendance_pdf/<int:class_id>')
@login_required
def export_attendance_pdf(class_id):
    try:
        from flask_weasyprint import HTML, CSS
        
        class_ = Department.query.get_or_404(class_id)
        if class_ not in current_user.departments:
            flash('Accès non autorisé')
            return redirect(url_for('dashboard'))

        # Récupérer tous les étudiants de la classe
        employees = class_.employees
        employee_count = employees.count()

        # Récupérer le nombre total de séances planifiées
        total_sessions = DepartmentSchedule.query.filter_by(department_id=class_id).count()

        # Calculer les statistiques de présence pour chaque étudiant
        attendance_stats = {}
        total_present = 0
        total_absent = 0
        perfect_attendance = 0
        low_attendance = 0

        for student in employees:
            attendances = Attendance.query.filter_by(
                employee_id=student.id,
                department_id=class_id
            ).order_by(Attendance.date.desc()).all()

            # Récupérer la date de dernière présence
            last_attendance = Attendance.query.filter_by(
                employee_id=student.id,
                department_id=class_id,
                present=True
            ).order_by(Attendance.date.desc()).first()
            
            last_date = last_attendance.date.strftime('%d/%m/%Y') if last_attendance else None

            present_count = sum(1 for a in attendances if a.present)
            absent_count = sum(1 for a in attendances if not a.present)
            total_count = present_count + absent_count
            
            if total_count == 0:
                attendance_rate = 0
            else:
                attendance_rate = (present_count / total_count) * 100
            
            # Compteurs pour les statistiques globales
            total_present += present_count
            total_absent += absent_count
            
            if total_count > 0 and attendance_rate == 100:
                perfect_attendance += 1
                
            if total_count > 0 and attendance_rate < 50:
                low_attendance += 1

            attendance_stats[student.id] = {
                'present': present_count,
                'absent': absent_count,
                'rate': attendance_rate,
                'last_date': last_date
            }

        # Calculer le taux de présence moyen
        total_attendances = total_present + total_absent
        avg_attendance_rate = (total_present / total_attendances * 100) if total_attendances > 0 else 0

        today = datetime.now()
        
        # Générer le HTML avec les données complètes
        html = render_template('attendance_report.html',
                              class_=class_,
                              students=employees,
                              attendance_stats=attendance_stats,
                              avg_attendance_rate=avg_attendance_rate,
                              total_sessions=total_sessions,
                              perfect_attendance=perfect_attendance,
                              low_attendance=low_attendance,
                              total_present=total_present,
                              total_absent=total_absent,
                              today=today,
                              base_url=request.host_url,
                              employee_count=employee_count)
        
        # Générer le PDF avec WeasyPrint
        pdf_content = HTML(string=html, base_url=request.base_url).write_pdf()
        
        # Créer la réponse HTTP avec le PDF
        response = make_response(pdf_content)
        filename = f"rapport_presence_{class_.name}_{today.strftime('%Y%m%d')}.pdf"
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        app.logger.info(f"PDF attendance report generated for class {class_id}")
        return response

    except Exception as e:
        # Journaliser l'erreur avec des détails complets
        import traceback
        tb = traceback.format_exc()
        app.logger.error(f"Error generating PDF report: {e}\n{tb}")
        
        flash(f'Erreur lors de la génération du rapport PDF: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/manage_employes')
@login_required
def manage_employes():
    # Redirect to the first department's employees page, or show a message if none
    departments = current_user.departments
    if not departments:
        flash('Aucun département trouvé.', 'error')
        return redirect(url_for('dashboard'))
    # Redirect to the first department's employees page
    return redirect(url_for('manage_employes_class', class_id=departments[0].id))

@app.route('/manage_employes/<int:class_id>')
@login_required
def manage_employes_class(class_id):
    class_ = Department.query.get_or_404(class_id)
    if class_ not in current_user.departments:
        flash('Unauthorized access', 'error')
        return redirect(url_for('dashboard'))

    # Calculate attendance statistics for each employee
    attendance_stats = {}
    for employee in class_.employees:
        attendances = Attendance.query.filter_by(
            employee_id=employee.id,
            department_id=class_id
        ).all()

        present_count = sum(1 for a in attendances if a.present)
        total_count = len(attendances) if attendances else 1  # Avoid division by zero

        attendance_stats[employee.id] = {
            'present': present_count,
            'absent': total_count - present_count,
            'rate': (present_count / total_count) * 100
        }    
    return render_template('employees.html', 
                         class_=class_,
                         attendance_stats=attendance_stats)

# Update all backend redirects to use manage_employes instead of manage_students
@app.route('/add_student/<int:class_id>', methods=['POST'])
@login_required
def add_student(class_id):
    try:
        class_ = Department.query.get_or_404(class_id)
        if class_ not in current_user.departments:
            flash('Unauthorized access', 'error')
            return redirect(url_for('dashboard'))

        # Get form data
        full_name = request.form.get('full_name')
        student_id = request.form.get('student_id')
        photo = request.files.get('photo')

        if not all([full_name, student_id, photo]):
            flash('All fields are required', 'error')
            return redirect(url_for('manage_employes_class', class_id=class_id))

        # Check if employee ID is unique
        if Employee.query.filter_by(student_id=student_id).first():
            flash('This employee ID already exists', 'error')
            return redirect(url_for('manage_employes_class', class_id=class_id))

        # Process photo for facial recognition
        image_array = np.frombuffer(photo.read(), np.uint8)
        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        face_encoding = get_face_encoding(image)

        if face_encoding is None:
            flash('No face detected in the photo', 'error')
            return redirect(url_for('manage_employes_class', class_id=class_id))

        # Create new employee
        new_student = Employee(
            full_name=full_name,
            student_id=student_id,
            department_id=class_id,
            face_encoding=face_encoding
        )

        db.session.add(new_student)
        db.session.commit()

        flash(f'Employee {full_name} added successfully', 'success')
        logger.info(f"New employee added: {full_name} to department {class_id}")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding employee: {e}")
        flash('Error adding employee', 'error')

    return redirect(url_for('manage_employes_class', class_id=class_id))

# Update student (employee) information
@app.route('/update_student/<int:student_id>/<int:class_id>', methods=['POST'])
@login_required
def update_student(student_id, class_id):
    try:
        # Get the student and class
        student = Employee.query.get_or_404(student_id)
        class_ = Department.query.get_or_404(class_id)
        
        # Verify permission
        if class_ not in current_user.departments:
            flash('Unauthorized access', 'error')
            return redirect(url_for('dashboard'))
            
        # Check if student belongs to this class
        if student.department_id != class_id:
            flash('Employee does not belong to this department', 'error')
            return redirect(url_for('manage_employes_class', class_id=class_id))
        
        # Get form data
        full_name = request.form.get('full_name')
        student_id_form = request.form.get('student_id')
        photo = request.files.get('photo')
        
        # Check if employee ID exists and is different from current
        if student_id_form != student.student_id:
            existing_student = Employee.query.filter_by(student_id=student_id_form).first()
            if existing_student and existing_student.id != student.id:
                flash('This employee ID already exists', 'error')
                return redirect(url_for('manage_employes_class', class_id=class_id))
        
        # Update basic info
        student.full_name = full_name
        student.student_id = student_id_form
        
        # Process new photo if provided
        if photo and photo.filename:
            image_array = np.frombuffer(photo.read(), np.uint8)
            image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            face_encoding = get_face_encoding(image)
            
            if face_encoding is None:
                flash('No face detected in the photo', 'error')
                return redirect(url_for('manage_employes_class', class_id=class_id))
                
            student.face_encoding = face_encoding
            
        # Save changes
        db.session.commit()
        flash(f'Employee {full_name} updated successfully', 'success')
        logger.info(f"Employee updated: {full_name} (ID: {student_id})")
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating employee: {e}")
        flash('Error updating employee information', 'error')
        
    return redirect(url_for('manage_employes_class', class_id=class_id))

# Delete student (employee)
@app.route('/delete_student/<int:student_id>/<int:class_id>', methods=['POST'])
@login_required
def delete_student(student_id, class_id):
    try:
        # Get the student and class with validation
        student = Employee.query.get_or_404(student_id)
        class_ = Department.query.get_or_404(class_id)
        
        # Verify permission
        if class_ not in current_user.departments:
            flash('Unauthorized access', 'error')
            return redirect(url_for('dashboard'))
            
        # Check if student belongs to this class
        if student.department_id != class_id:
            flash('Employee does not belong to this department', 'error')
            return redirect(url_for('manage_employes_class', class_id=class_id))
        
        # Get student information for logging
        student_name = student.full_name
        
        # Delete all associated records in a proper order to maintain referential integrity
        # 1. Delete check-in/out records
        CheckInOut.query.filter_by(employee_id=student_id).delete()
        
        # 2. Delete attendance records
        Attendance.query.filter_by(employee_id=student_id).delete()
        
        # 3. Delete face encoding data if it exists
        if student.face_encoding is not None:
            student.face_encoding = None
            db.session.flush()  # Ensure the encoding is cleared before deletion
        
        # 4. Delete the employee record
        db.session.delete(student)
        
        # Commit all changes in one transaction
        db.session.commit()
        
        flash(f'Employee {student_name} and all associated records have been deleted successfully', 'success')
        logger.info(f"Employee and all associated data deleted: {student_name} (ID: {student_id}) from department {class_id}")
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting employee and associated data: {e}")
        flash('Error deleting employee and associated records', 'error')
        
    return redirect(url_for('manage_employes_class', class_id=class_id))

# Add admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Accès non autorisé. Vous devez être administrateur.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Add the admin manager management route
@app.route('/admin/managers')
@login_required
def admin_managers():
    managers = Manager.query.all()
    return render_template('admin_managers.html', managers=managers)

# Redirect old /admin/professors to new /admin/managers for backward compatibility
@app.route('/admin/professors')
def redirect_admin_professors():
    return redirect(url_for('admin_managers'))

# Generate invitation code
@app.route('/admin/generate_invitation_code', methods=['POST'])
@login_required
@admin_required
def generate_invitation_code():
    try:
        expires_in = int(request.form.get('expires_in', 30))
        code = InvitationCode.create_new(created_by=current_user.id, expires_in_days=expires_in)
        flash(f'Code d\'invitation généré avec succès: {code.code}', 'success')
    except Exception as e:
        logger.error(f"Error generating invitation code: {e}")
        flash('Erreur lors de la génération du code d\'invitation', 'error')
    
    return redirect(url_for('admin_managers'))

# Delete invitation code
@app.route('/admin/delete_invitation_code/<int:code_id>', methods=['POST'])
@login_required
@admin_required
def delete_invitation_code(code_id):
    try:
        code = InvitationCode.query.get_or_404(code_id)
        db.session.delete(code)
        db.session.commit()
        flash('Code d\'invitation supprimé avec succès', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting invitation code: {e}")
        flash('Erreur lors de la suppression du code d\'invitation', 'error')
    
    return redirect(url_for('admin_managers'))

# Update manager information
@app.route('/admin/update_manager/<int:manager_id>', methods=['POST'])
@login_required
@admin_required
def update_manager(manager_id):
    try:
        manager = Manager.query.get_or_404(manager_id)
        
        manager.full_name = request.form.get('full_name', manager.full_name)
        manager.email = request.form.get('email', manager.email)
        
        # Only allow admin status change if current user is admin and not modifying themselves
        if current_user.is_admin and current_user.id != manager.id:
            manager.is_admin = 'is_admin' in request.form
        
        # Update password if provided
        new_password = request.form.get('new_password')
        if new_password:
            manager.set_password(new_password)
        
        db.session.commit()
        flash('Informations du professeur mises à jour avec succès', 'success')
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating manager: {e}")
        flash('Erreur lors de la mise à jour des informations du professeur', 'error')
    
    return redirect(url_for('admin_managers'))

# Delete manager
@app.route('/admin/delete_manager/<int:manager_id>', methods=['POST'])
@login_required
@admin_required
def delete_manager(manager_id):
    try:
        # Prevent deleting yourself or the main admin
        if manager_id == current_user.id:
            flash('Vous ne pouvez pas supprimer votre propre compte', 'error')
            return redirect(url_for('admin_managers'))
        
        manager = Manager.query.get_or_404(manager_id)
        
        # Get associated attendance records to reassign or delete
        attendances = Attendance.query.filter_by(manager_id=manager_id).all()
        
        # Option 1: Reassign attendance records to current admin
        for attendance in attendances:
            attendance.manager_id = current_user.id
        
        # Delete the manager
        db.session.delete(manager)
        db.session.commit()
        
        flash('Professeur supprimé avec succès', 'success')
        logger.info(f"Professor {manager_id} deleted by admin {current_user.id}")
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting manager: {e}")
        flash('Erreur lors de la suppression du professeur', 'error')
    
    return redirect(url_for('admin_managers'))

# Check-in/out main page (list departments)
@app.route('/check_inout/')
@login_required
def check_inout_departments():
    classes = current_user.departments

    # Calculate employee counts for each class
    employee_counts = {}
    for class_ in classes:
        employee_counts[class_.id] = class_.employees.count()

    return render_template('check_inout.html', classes=classes, class_id=None, employee_counts=employee_counts)

# Check-in/out for a specific department
@app.route('/check_inout/<int:class_id>')
@login_required
def check_inout(class_id):
    # Show schedules for the selected department
    class_ = Department.query.get_or_404(class_id)
    if class_ not in current_user.departments:
        flash('Unauthorized access', 'error')
        return redirect(url_for('dashboard'))
    
    # Get schedules
    schedules = DepartmentSchedule.query.filter_by(department_id=class_id, active=True).all()
    
    # Get check-in/out records for today
    today = datetime.now().date()
    
    # Get recent check-in records
    checkin_records = {}
    checkout_records = {}
    
    for schedule in schedules:
        # Check-in records
        checkins = db.session.query(CheckInOut).filter(
            CheckInOut.schedule_id == schedule.id,
            CheckInOut.type == 'check-in',
            db.func.date(CheckInOut.time) == today
        ).order_by(CheckInOut.time.desc()).all()
        
        # Check-out records
        checkouts = db.session.query(CheckInOut).filter(
            CheckInOut.schedule_id == schedule.id,
            CheckInOut.type == 'check-out',
            db.func.date(CheckInOut.time) == today
        ).order_by(CheckInOut.time.desc()).all()
        
        # Store records
        checkin_records[schedule.id] = checkins
        checkout_records[schedule.id] = checkouts
    
    # Day names for display
    days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    return render_template('check_inout.html', 
                          class_=class_, 
                          schedules=schedules, 
                          days_of_week=days_of_week,
                          checkin_records=checkin_records,
                          checkout_records=checkout_records,
                          class_id=class_id)

# Process check-in/out
@app.route('/process_check_inout', methods=['POST'])
@login_required
def process_check_inout():
    try:
        # Get request data
        data = request.get_json()
        schedule_id = int(data.get('schedule_id'))
        class_id = int(data.get('class_id'))
        check_type = data.get('type')  # 'check-in' or 'check-out'
        image_data = data.get('image')
        
        # Verify permissions
        class_ = Department.query.get_or_404(class_id)
        if class_ not in current_user.departments:
            return jsonify({'success': False, 'message': 'Unauthorized access'})
        
        # Verify schedule exists and belongs to class
        schedule = DepartmentSchedule.query.get_or_404(schedule_id)
        if schedule.department_id != class_id:
            return jsonify({'success': False, 'message': 'Invalid schedule for this department'})
        
        # Process the image for facial recognition
        encoded_data = image_data.split(',')[1]
        nparr = np.frombuffer(base64.b64decode(encoded_data), np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        face_encoding = get_face_encoding(img)
        if face_encoding is None:
            return jsonify({'success': False, 'message': 'No face detected in the image'})
        
        # Identify the employee
        employee_id, employee_name, confidence = identify_employee(face_encoding, class_id)
        if not employee_id:
            return jsonify({'success': False, 'message': 'Employee not recognized'})
        
        # Get the employee
        employee = Employee.query.get(employee_id)
        if not employee:
            return jsonify({'success': False, 'message': 'Employee not found in database'})
        
        # Create check-in/out record
        record = CheckInOut(
            employee_id=employee_id,
            department_id=class_id,
            schedule_id=schedule_id,
            type=check_type,
            method='facial',
            confidence=confidence,
            time=datetime.now()
        )
        
        db.session.add(record)
        db.session.commit()
        
        # Create regular attendance record too
        if check_type == 'check-in':
            # Check if attendance record already exists
            today = datetime.now().date()
            existing_attendance = Attendance.query.filter(
                Attendance.employee_id == employee_id,
                Attendance.department_id == class_id,
                Attendance.schedule_id == schedule_id,
                db.func.date(Attendance.date) == today
            ).first()
            
            if not existing_attendance:
                attendance = Attendance(
                    employee_id=employee_id,
                    department_id=class_id,
                    manager_id=current_user.id,
                    schedule_id=schedule_id,
                    present=True,
                    method='facial'
                )
                db.session.add(attendance)
                db.session.commit()
        
        # Format current time for display
        current_time = datetime.now().strftime('%H:%M:%S')
        
        # Return success response
        return jsonify({
            'success': True, 
            'employee_id': employee.student_id,
            'employee_name': employee.full_name, 
            'time': current_time,
            'message': f'Successfully processed {check_type} for {employee.full_name}'
        })
        
    except Exception as e:
        logger.error(f"Error processing check-in/out: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

# Check-in/out report
@app.route('/check_inout_report/<int:class_id>')
@login_required
def check_inout_report(class_id):
    try:
        class_ = Department.query.get_or_404(class_id)
        if class_ not in current_user.departments:
            flash('Unauthorized access', 'error')
            return redirect(url_for('dashboard'))
        
        # Get date range for report
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        
        if start_date_str and end_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        else:
            # Default to current week
            today = datetime.now().date()
            start_date = today - timedelta(days=today.weekday())
            end_date = start_date + timedelta(days=6)
        
        # Get check-in/out records for date range
        records = db.session.query(CheckInOut).filter(
            CheckInOut.department_id == class_id,
            db.func.date(CheckInOut.time) >= start_date,
            db.func.date(CheckInOut.time) <= end_date
        ).order_by(CheckInOut.time).all()
        
        # Group records by student, date and schedule
        record_dict = {}
        for record in records:
            record_date = record.time.date()
            
            if record.employee_id not in record_dict:
                record_dict[record.employee_id] = {
                    'employee': record.employee,
                    'dates': {}
                }
            
            if record_date not in record_dict[record.employee_id]['dates']:
                record_dict[record.employee_id]['dates'][record_date] = {}
            
            if record.schedule_id not in record_dict[record.employee_id]['dates'][record_date]:
                record_dict[record.employee_id]['dates'][record_date][record.schedule_id] = {
                    'schedule': record.schedule,
                    'check_in': None,
                    'check_out': None
                }
            
            if record.type == 'check-in':
                record_dict[record.employee_id]['dates'][record_date][record.schedule_id]['check_in'] = record
            elif record.type == 'check-out':
                record_dict[record.employee_id]['dates'][record_date][record.schedule_id]['check_out'] = record
        
        # Get all students in class
        students = Employee.query.filter_by(department_id=class_id).all()
        
        # Generate date range for display
        date_range = []
        current_date = start_date
        while current_date <= end_date:
            date_range.append(current_date)
            current_date += timedelta(days=1)
        
        return render_template('check_inout_report.html',
                             class_=class_,
                             students=students,
                             records=record_dict,
                             date_range=date_range,
                             start_date=start_date,
                             end_date=end_date)
        
    except Exception as e:
        logger.error(f"Error generating check-in/out report: {e}")
        flash('Error generating report', 'error')
        return redirect(url_for('dashboard'))

# Export check-in/out report as PDF
@app.route('/export_checkinout_report/<int:class_id>')
@login_required
def export_checkinout_report(class_id):
    try:
        class_ = Department.query.get_or_404(class_id)
        if class_ not in current_user.departments:
            flash('Unauthorized access', 'error')
            return redirect(url_for('dashboard'))
        
        # Get date range for report
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        
        if start_date_str and end_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        else:
            # Default to current week
            today = datetime.now().date()
            start_date = today - timedelta(days=today.weekday())
            end_date = start_date + timedelta(days=6)
        
        # Get check-in/out records for date range
        records = db.session.query(CheckInOut).filter(
            CheckInOut.department_id == class_id,
            db.func.date(CheckInOut.time) >= start_date,
            db.func.date(CheckInOut.time) <= end_date
        ).order_by(CheckInOut.time).all()
        
        # Group records by student, date and schedule
        record_dict = {}
        total_check_ins = 0
        total_check_outs = 0
        
        for record in records:
            record_date = record.time.date()
            
            if record.employee_id not in record_dict:
                record_dict[record.employee_id] = {
                    'employee': record.employee,
                    'dates': {}
                }
            
            if record_date not in record_dict[record.employee_id]['dates']:
                record_dict[record.employee_id]['dates'][record_date] = {}
            
            if record.schedule_id not in record_dict[record.employee_id]['dates'][record_date]:
                record_dict[record.employee_id]['dates'][record_date][record.schedule_id] = {
                    'schedule': record.schedule,
                    'check_in': None,
                    'check_out': None
                }
            
            if record.type == 'check-in':
                record_dict[record.employee_id]['dates'][record_date][record.schedule_id]['check_in'] = record
                total_check_ins += 1
            elif record.type == 'check-out':
                record_dict[record.employee_id]['dates'][record_date][record.schedule_id]['check_out'] = record
                total_check_outs += 1
        
        # Get all students in class
        students = Employee.query.filter_by(department_id=class_id).all()
        
        # Generate date range for display
        date_range = []
        current_date = start_date
        while current_date <= end_date:
            date_range.append(current_date)
            current_date += timedelta(days=1)
            
        # Calculate completeness rate
        # For each student and each schedule, they should have both check-in and check-out
        # Get all active schedules
        schedules = DepartmentSchedule.query.filter_by(department_id=class_id, active=True).all()
        
        # Calculate total possible records (students × days × schedules)
        total_possible_records = len(students) * len(date_range) * len(schedules) * 2  # Both check-in and check-out
        total_actual_records = total_check_ins + total_check_outs
        
        completeness_rate = "0%"
        if total_possible_records > 0:
            completeness_percentage = (total_actual_records / total_possible_records) * 100
            completeness_rate = f"{completeness_percentage:.1f}%"
        
        # Generate HTML with the data
        html = render_template('check_inout_report_pdf.html',
                             class_=class_,
                             students=students,
                             records=record_dict,
                             date_range=date_range,
                             start_date=start_date,
                             end_date=end_date,
                             today=datetime.now(),
                             base_url=request.host_url,
                             current_user=current_user,
                             total_check_ins=total_check_ins,
                             total_check_outs=total_check_outs,
                             completeness_rate=completeness_rate)
        
        # Generate PDF with WeasyPrint
        pdf_content = HTML(string=html, base_url=request.base_url).write_pdf()
        
        # Create response with PDF
        filename = f"Department_TimeTracking_Report_{class_.name}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.pdf"
        response = make_response(pdf_content)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        logger.info(f"PDF time tracking report generated for department {class_id}")
        return response
    
    except Exception as e:
        logger.error(f"Error generating PDF time tracking report: {e}")
        flash('Error generating PDF report', 'error')
        return redirect(url_for('check_inout_report', class_id=class_id))