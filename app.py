from flask import Flask
from config import Config
from models import db


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Init database
    db.init_app(app)

    # Register blueprints
    from routes.webhook import webhook_bp
    from routes.sala import sala_bp
    from routes.admin import admin_bp

    app.register_blueprint(webhook_bp)
    app.register_blueprint(sala_bp)
    app.register_blueprint(admin_bp)

    # Create tables
    with app.app_context():
        db.create_all()

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
