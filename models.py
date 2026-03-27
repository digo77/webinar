from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Registrant(db.Model):
    __tablename__ = 'registrants'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text)
    email = db.Column(db.Text)
    phone = db.Column(db.Text)
    hotmart_transaction = db.Column(db.Text, unique=True)
    token = db.Column(db.Text, unique=True)
    webinar_id = db.Column(db.Integer, db.ForeignKey('webinar_config.id'))
    webinar_date = db.Column(db.DateTime)
    attended = db.Column(db.Boolean, default=False)
    watch_time_seconds = db.Column(db.Integer, default=0)
    clicked_cta = db.Column(db.Boolean, default=False)
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
    day_of_week = db.Column(db.Integer, default=1)      # 0=seg, 1=ter, ..., 6=dom
    start_hour = db.Column(db.Integer, default=19)
    start_minute = db.Column(db.Integer, default=0)
    attendee_count_base = db.Column(db.Integer, default=47)
    upsell_url = db.Column(db.Text)
    upsell_cta_text = db.Column(db.Text)
    test_date = db.Column(db.Text)  # datetime-local ISO string, ex: "2026-03-27T20:00"


class TimelineEvent(db.Model):
    __tablename__ = 'timeline_events'

    id = db.Column(db.Integer, primary_key=True)
    webinar_id = db.Column(db.Integer, db.ForeignKey('webinar_config.id'))
    trigger_second = db.Column(db.Integer)
    event_type = db.Column(db.Text)  # 'chat' | 'cta_popup' | 'poll'
    payload = db.Column(db.Text)     # JSON string

    webinar = db.relationship('WebinarConfig', backref='events')
