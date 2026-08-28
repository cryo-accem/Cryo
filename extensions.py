import os
import threading
from flask_mail import Mail, Message

mail = Mail()


def init_mail(app):
    """Configure and attach Flask-Mail to the app."""
    app.config["MAIL_SERVER"]         = "smtp.gmail.com"
    app.config["MAIL_PORT"]           = 587
    app.config["MAIL_USE_TLS"]        = True
    app.config["MAIL_USE_SSL"]        = False
    app.config["MAIL_USERNAME"]       = os.environ.get("MAIL_USERNAME")
    app.config["MAIL_PASSWORD"]       = os.environ.get("MAIL_PASSWORD")
    app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_DEFAULT_SENDER")
    app.config["MAIL_TIMEOUT"]        = 10
    mail.init_app(app)


def send_email(recipient: str, subject: str, body: str, cc=None, attachments=None):
    """Send email asynchronously so it never blocks a request."""
    from flask import current_app

    app = current_app._get_current_object()

    def _send():
        with app.app_context():
            try:
                msg = Message(subject, recipients=[recipient], cc=cc or [])
                msg.body = body
                for attachment in attachments or []:
                    filename, content_type, data = attachment
                    msg.attach(filename, content_type, data)
                mail.send(msg)
            except Exception as exc:
                app.logger.error(f"Email to {recipient} failed: {exc}")

    threading.Thread(target=_send, daemon=True).start()
