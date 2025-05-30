import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from sqlalchemy.orm import DeclarativeBase
from flask_babel import Babel
from flask_wtf.csrf import CSRFProtect

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()
babel = Babel()
csrf = CSRFProtect()

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev_secret_key")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///attendance.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["BABEL_DEFAULT_LOCALE"] = "fr"
app.config["LANGUAGES"] = ["fr", "ar"]
app.config["WTF_CSRF_SECRET_KEY"] = os.environ.get("SESSION_SECRET", "dev_secret_key")

db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = "login"
babel.init_app(app)
csrf.init_app(app)

with app.app_context():
    import models  # noqa: F401
    from routes import *  # Import all routes
    db.create_all()
    
if __name__ == "__main__":
    app.run(debug=True)