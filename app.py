from flask import Flask
from config import Config
from models import db


def migrate_db(app):
    """Adiciona colunas novas sem perder dados existentes."""
    with app.app_context():
        from sqlalchemy import text, inspect
        inspector = inspect(db.engine)

        # Colunas para adicionar em webinar_config
        wc_cols = {c['name'] for c in inspector.get_columns('webinar_config')}
        wc_new = {
            'day_of_week': 'INTEGER DEFAULT 1',
            'start_hour': 'INTEGER DEFAULT 19',
            'start_minute': 'INTEGER DEFAULT 0',
            'client_name': 'TEXT',
            'webhook_token': 'TEXT',
            'test_date': 'TEXT',
            'slug': 'TEXT',
        }
        for col, typedef in wc_new.items():
            if col not in wc_cols:
                db.session.execute(text(f'ALTER TABLE webinar_config ADD COLUMN {col} {typedef}'))

        # Colunas para adicionar em registrants
        r_cols = {c['name'] for c in inspector.get_columns('registrants')}
        if 'webinar_id' not in r_cols:
            db.session.execute(text('ALTER TABLE registrants ADD COLUMN webinar_id INTEGER'))

        db.session.commit()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Init database
    db.init_app(app)

    # Register blueprints
    from routes.webhook import webhook_bp
    from routes.sala import sala_bp
    from routes.admin import admin_bp
    from routes.registrar import registrar_bp

    app.register_blueprint(webhook_bp)
    app.register_blueprint(sala_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(registrar_bp)

    # Create tables (novas) + migrate colunas existentes
    with app.app_context():
        db.create_all()

    try:
        migrate_db(app)
    except Exception as e:
        app.logger.info(f'Migration ok ou ja aplicada: {e}')

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
