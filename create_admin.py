from werkzeug.security import generate_password_hash
from app import app, db
from models import Manager as Professor

def create_admin():
    with app.app_context():
        # Check if admin already exists
        admin = Professor.query.filter_by(username='admin').first()
        if not admin:
            # Create new admin
            admin = Professor(
                username='admin',
                email='admin@est.ma',
                full_name='Administrateur',
                is_admin=True
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("Compte administrateur créé avec succès")
        else:
            # Update admin password and ensure admin flag is set
            admin.set_password('admin123')
            admin.is_admin = True
            db.session.commit()
            print("Mot de passe administrateur mis à jour avec succès")

if __name__ == '__main__':
    create_admin()
