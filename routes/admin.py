import json
from functools import wraps
from flask import Blueprint, request, render_template, redirect, url_for, session, jsonify, current_app
from models import db, Registrant, WebinarConfig, TimelineEvent

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated


@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == current_app.config['ADMIN_PASSWORD']:
            session['admin_logged_in'] = True
            return redirect(url_for('admin.dashboard'))
        return render_template('admin/login.html', error='Senha incorreta')
    return render_template('admin/login.html')


@admin_bp.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin.login'))


@admin_bp.route('/')
@admin_bp.route('/dashboard')
@login_required
def dashboard():
    registrants = Registrant.query.order_by(Registrant.created_at.desc()).all()
    config = WebinarConfig.query.filter_by(is_active=True).first()
    stats = {
        'total': len(registrants),
        'attended': sum(1 for r in registrants if r.attended),
        'clicked_cta': sum(1 for r in registrants if r.clicked_cta),
    }
    return render_template('admin/dashboard.html',
                           registrants=registrants,
                           config=config,
                           stats=stats)


@admin_bp.route('/config', methods=['POST'])
@login_required
def save_config():
    config = WebinarConfig.query.filter_by(is_active=True).first()
    if not config:
        config = WebinarConfig(is_active=True)
        db.session.add(config)

    config.name = request.form.get('name', config.name)
    config.vturb_video_id = request.form.get('vturb_video_id', config.vturb_video_id)
    config.attendee_count_base = int(request.form.get('attendee_count_base', 47))
    config.upsell_url = request.form.get('upsell_url', config.upsell_url)
    config.upsell_cta_text = request.form.get('upsell_cta_text', config.upsell_cta_text)
    db.session.commit()
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/timeline')
@login_required
def timeline():
    config = WebinarConfig.query.filter_by(is_active=True).first()
    events = []
    if config:
        events = TimelineEvent.query.filter_by(webinar_id=config.id)\
            .order_by(TimelineEvent.trigger_second).all()
    return render_template('admin/timeline.html', events=events, config=config)


@admin_bp.route('/timeline/add', methods=['POST'])
@login_required
def timeline_add():
    config = WebinarConfig.query.filter_by(is_active=True).first()
    if not config:
        return redirect(url_for('admin.timeline'))

    event_type = request.form.get('event_type', 'chat')
    trigger_second = int(request.form.get('trigger_second', 0))

    if event_type == 'chat':
        payload = json.dumps({
            'author': request.form.get('author', ''),
            'message': request.form.get('message', ''),
        })
    elif event_type == 'cta_popup':
        payload = json.dumps({
            'title': request.form.get('title', ''),
            'countdown_minutes': int(request.form.get('countdown_minutes', 15)),
            'url': request.form.get('url', ''),
        })
    else:
        payload = request.form.get('payload', '{}')

    event = TimelineEvent(
        webinar_id=config.id,
        trigger_second=trigger_second,
        event_type=event_type,
        payload=payload,
    )
    db.session.add(event)
    db.session.commit()
    return redirect(url_for('admin.timeline'))


@admin_bp.route('/timeline/delete/<int:event_id>', methods=['POST'])
@login_required
def timeline_delete(event_id):
    event = TimelineEvent.query.get_or_404(event_id)
    db.session.delete(event)
    db.session.commit()
    return redirect(url_for('admin.timeline'))
