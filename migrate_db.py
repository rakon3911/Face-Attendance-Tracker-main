from app import app, db
import logging
from sqlalchemy import text
from models import Manager as Professor, Employee as Student, Department as Class, Attendance, DepartmentSchedule as ClassSchedule, InvitationCode

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_is_admin_to_professor():
    try:
        logger.info("Starting migration: Adding is_admin column to Professor table")
        with app.app_context():
            with db.engine.connect() as conn:
                # Vérifier si la colonne existe déjà
                try:
                    conn.execute(text("SELECT is_admin FROM professor LIMIT 1"))
                    logger.info("Column is_admin already exists in Professor table")
                except Exception:
                    # Ajouter la colonne si elle n'existe pas
                    conn.execute(text("ALTER TABLE professor ADD COLUMN is_admin BOOLEAN DEFAULT 0"))
                    conn.commit()
                    logger.info("Added is_admin column to Professor table")
        logger.info("Professor migration completed successfully")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        print(f"Error during migration: {e}")

def create_invitation_code_table():
    try:
        logger.info("Starting migration: Creating InvitationCode table if it doesn't exist")
        with app.app_context():
            # Utilisez l'API SQLAlchemy pour créer la table si elle n'existe pas
            if not db.engine.dialect.has_table(db.engine.connect(), 'invitation_code'):
                InvitationCode.__table__.create(db.engine)
                logger.info("Created InvitationCode table")
            else:
                logger.info("InvitationCode table already exists")
        logger.info("InvitationCode migration completed successfully")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        print(f"Error during migration: {e}")

def add_schedule_id_to_attendance():
    try:
        logger.info("Starting migration: Adding schedule_id column to Attendance table")
        with app.app_context():
            with db.engine.connect() as conn:
                # Vérifier si la colonne existe déjà
                try:
                    conn.execute(text("SELECT schedule_id FROM attendance LIMIT 1"))
                    logger.info("Column schedule_id already exists in Attendance table")
                except Exception:
                    # Ajouter la colonne si elle n'existe pas
                    conn.execute(text("ALTER TABLE attendance ADD COLUMN schedule_id INTEGER"))
                    conn.execute(text("ALTER TABLE attendance ADD CONSTRAINT fk_schedule_id FOREIGN KEY (schedule_id) REFERENCES class_schedule (id)"))
                    conn.commit()
                    logger.info("Added schedule_id column to Attendance table")
        logger.info("Migration completed successfully")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        print(f"Error during migration: {e}")

def migrate_db():
    with app.app_context():
        db.create_all()
        print("Database tables created successfully!")

if __name__ == "__main__":
    # Exécuter les migrations dans l'ordre
    add_is_admin_to_professor()
    create_invitation_code_table()
    add_schedule_id_to_attendance()
    print("Migration completed. Please restart your application.")
    migrate_db()
