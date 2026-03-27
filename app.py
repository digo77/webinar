import json
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Config
from models import db


def migrate_db(app):
    with app.app_context():
        from sqlalchemy import text, inspect
        inspector = inspect(db.engine)

        # webinar_config novas colunas
        wc_cols = {c['name'] for c in inspector.get_columns('webinar_config')}
        wc_new = {
            'day_of_week': 'INTEGER DEFAULT 1',
            'start_hour': 'INTEGER DEFAULT 19',
            'start_minute': 'INTEGER DEFAULT 0',
            'client_name': 'TEXT',
            'webhook_token': 'TEXT',
            'test_date': 'TEXT',
            'slug': 'TEXT',
            'offer_image_url': 'TEXT',
            'offer_original_price': 'TEXT',
            'offer_price': 'TEXT',
            'chatbot_responses': 'TEXT',
            'register_mode': 'INTEGER DEFAULT 1',
            'register_headline': 'TEXT',
            'register_subtitle': 'TEXT',
            'register_bg_color': 'TEXT',
            'register_bg_image_url': 'TEXT',
            'register_presenter_photo_url': 'TEXT',
            'register_bullets': 'TEXT',
            'register_button_text': 'TEXT',
        }
        for col, typedef in wc_new.items():
            if col not in wc_cols:
                db.session.execute(text(f'ALTER TABLE webinar_config ADD COLUMN {col} {typedef}'))

        # registrants novas colunas
        r_cols = {c['name'] for c in inspector.get_columns('registrants')}
        if 'webinar_id' not in r_cols:
            db.session.execute(text('ALTER TABLE registrants ADD COLUMN webinar_id INTEGER'))

        db.session.commit()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    db.init_app(app)

    from routes.webhook import webhook_bp
    from routes.sala import sala_bp
    from routes.admin import admin_bp
    from routes.registrar import registrar_bp

    app.register_blueprint(webhook_bp)
    app.register_blueprint(sala_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(registrar_bp)

    # Filtro Jinja2 from_json
    app.jinja_env.filters['from_json'] = lambda s: json.loads(s) if s else []

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
