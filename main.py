import os
import datetime
from flask import Flask

from database import init_db
from extensions import init_mail

from blueprints.public    import public_bp
from blueprints.imaging   import imaging_bp
from blueprints.freezing  import freezing_bp
from blueprints.screening import screening_bp
from blueprints.register  import register_bp
from blueprints.admin     import admin_bp


def create_app() -> Flask:
    app = Flask(__name__)

    app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")
    app.config["PERMANENT_SESSION_LIFETIME"] = datetime.timedelta(minutes=30)

    init_mail(app)

    app.register_blueprint(public_bp)
    app.register_blueprint(imaging_bp)
    app.register_blueprint(freezing_bp)
    app.register_blueprint(screening_bp)
    app.register_blueprint(register_bp)
    app.register_blueprint(admin_bp)

    with app.app_context():
        init_db()

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
