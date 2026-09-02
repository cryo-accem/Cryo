import os
import threading
from flask_mail import Mail, Message
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

mail = Mail()


def init_mail(app):
    """Configure and attach Flask-Mail to the app."""
    username = os.environ.get("MAIL_USERNAME", "").strip()
    password = os.environ.get("MAIL_PASSWORD", "").strip()
    sender = os.environ.get("MAIL_DEFAULT_SENDER", "").strip() or username

    app.config["MAIL_SERVER"]        = "smtp.gmail.com"
    app.config["MAIL_PORT"]          = 587
    app.config["MAIL_USE_TLS"]       = True
    app.config["MAIL_USE_SSL"]       = False
    app.config["MAIL_USERNAME"]      = username
    app.config["MAIL_PASSWORD"]      = password
    app.config["MAIL_DEFAULT_SENDER"] = sender
    app.config["MAIL_TIMEOUT"]        = 10
    mail.init_app(app)

    missing = [
        name for name, value in (
            ("MAIL_USERNAME", username),
            ("MAIL_PASSWORD", password),
            ("MAIL_DEFAULT_SENDER", sender),
        ) if not value
    ]
    if missing:
        app.logger.warning(
            "Email is not configured; missing environment variable(s): %s",
            ", ".join(missing),
        )


def send_email(recipient: str, subject: str, body: str, cc=None, attachments=None):
    """Send email asynchronously so it never blocks a request."""
    from flask import current_app

    app = current_app._get_current_object()

    def _send():
        with app.app_context():
            try:
                if not app.config.get("MAIL_USERNAME") or not app.config.get("MAIL_PASSWORD"):
                    app.logger.error(
                        "Email to %s was not sent because SMTP credentials are not configured",
                        recipient,
                    )
                    return
                msg = Message(subject, recipients=[recipient], cc=cc or [])
                msg.body = body
                for attachment in attachments or []:
                    filename, content_type, data = attachment
                    msg.attach(filename, content_type, data)
                mail.send(msg)
            except Exception as exc:
                app.logger.error(f"Email to {recipient} failed: {exc}")

    threading.Thread(target=_send, daemon=True).start()
