from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Registrant(db.Model):
    __tablename__ = 'registrants'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text)
    email = db.Column(db.Text)  # nullable — mantido para compatibilidade Hotmart
    phone_country_code = db.Column(db.Text, default='+55')
    phone_number = db.Column(db.Text)
    phone = db.Column(db.Text)  # campo legado
    hotmart_transaction = db.Column(db.Text, unique=True)
    token = db.Column(db.Text, unique=True)
    webinar_id = db.Column(db.Integer, db.ForeignKey('webinar_config.id'))
    webinar_date = db.Column(db.DateTime)
    attended = db.Column(db.Boolean, default=False)
    watch_time_seconds = db.Column(db.Integer, default=0)
    clicked_cta = db.Column(db.Boolean, default=False)
    utm_source = db.Column(db.Text)
    utm_medium = db.Column(db.Text)
    utm_campaign = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    webinar = db.relationship('WebinarConfig', backref='registrants')


class WebinarConfig(db.Model):
    __tablename__ = 'webinar_config'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text)
    client_name = db.Column(db.Text)
    webhook_token = db.Column(db.Text, unique=True)
    vturb_video_id = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    day_of_week = db.Column(db.Integer, default=1)
    start_hour = db.Column(db.Integer, default=19)
    start_minute = db.Column(db.Integer, default=0)
    attendee_count_base = db.Column(db.Integer, default=47)
    upsell_url = db.Column(db.Text)
    upsell_cta_text = db.Column(db.Text)
    test_date = db.Column(db.Text)
    slug = db.Column(db.Text, unique=True)
    # Oferta
    offer_image_url = db.Column(db.Text)
    offer_original_price = db.Column(db.Text)
    offer_price = db.Column(db.Text)
    pitch_second = db.Column(db.Integer, default=0)
    # Chatbot
    chatbot_responses = db.Column(db.Text)  # JSON: [{"keyword":"oi","response":"Olá!"}]
    # Página de registro configurável
    register_mode = db.Column(db.Integer, default=1)  # 1, 2 ou 3
    register_headline = db.Column(db.Text)
    register_subtitle = db.Column(db.Text)
    register_bg_color = db.Column(db.Text)
    register_bg_image_url = db.Column(db.Text)
    register_presenter_photo_url = db.Column(db.Text)
    register_bullets = db.Column(db.Text)  # JSON array de strings
    register_button_text = db.Column(db.Text)


class TimelineEvent(db.Model):
    __tablename__ = 'timeline_events'
    id = db.Column(db.Integer, primary_key=True)
    webinar_id = db.Column(db.Integer, db.ForeignKey('webinar_config.id'))
    trigger_second = db.Column(db.Integer)
    event_type = db.Column(db.Text)  # 'chat' | 'cta_popup' | 'poll' | 'purchase_notification' | 'end_broadcast'
    payload = db.Column(db.Text)  # JSON string
    webinar = db.relationship('WebinarConfig', backref='events')


class SupportMessage(db.Model):
    __tablename__ = 'support_messages'
    id = db.Column(db.Integer, primary_key=True)
    registrant_id = db.Column(db.Integer, db.ForeignKey('registrants.id'))
    webinar_id = db.Column(db.Integer)
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    answered = db.Column(db.Boolean, default=False)
    registrant = db.relationship('Registrant', backref='support_messages')


class LivePresence(db.Model):
    __tablename__ = 'live_presence'
    id = db.Column(db.Integer, primary_key=True)
    registrant_id = db.Column(db.Integer, db.ForeignKey('registrants.id'), unique=True)
    webinar_id = db.Column(db.Integer, index=True)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    user_agent = db.Column(db.Text)
    registrant = db.relationship('Registrant', backref='presence')


class UserChatMessage(db.Model):
    __tablename__ = 'user_chat_messages'
    id = db.Column(db.Integer, primary_key=True)
    registrant_id = db.Column(db.Integer, db.ForeignKey('registrants.id'), index=True)
    webinar_id = db.Column(db.Integer, index=True)
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    admin_reply = db.Column(db.Text)
    replied_at = db.Column(db.DateTime)
    status = db.Column(db.Text, default='pending')  # pending | approved | rejected | simulated
    video_timestamp = db.Column(db.Integer, nullable=True)
    is_pinned = db.Column(db.Boolean, default=False)
    registrant = db.relationship('Registrant', backref='user_chat')
