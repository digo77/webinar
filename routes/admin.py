import json
import secrets
from functools import wraps
from flask import Blueprint, request, render_template, redirect, url_for, session, jsonify, current_app
from models import db, Registrant, WebinarConfig, TimelineEvent
from services.token_service import generate_token
from services.scheduler import DAY_NAMES

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


# --- Dashboard: lista todos os webinarios ---

@admin_bp.route('/')
@admin_bp.route('/dashboard')
@login_required
def dashboard():
    webinars = WebinarConfig.query.order_by(WebinarConfig.id.desc()).all()

    # Stats globais
    total_reg = Registrant.query.count()
    total_attended = Registrant.query.filter_by(attended=True).count()
    total_cta = Registrant.query.filter_by(clicked_cta=True).count()

    # Stats por webinario
    for w in webinars:
        regs = Registrant.query.filter_by(webinar_id=w.id).all()
        w.stats = {
            'total': len(regs),
            'attended': sum(1 for r in regs if r.attended),
            'clicked_cta': sum(1 for r in regs if r.clicked_cta),
        }
        w.day_name = DAY_NAMES[w.day_of_week] if w.day_of_week is not None else 'Terca'

    stats = {'total': total_reg, 'attended': total_attended, 'clicked_cta': total_cta}

    return render_template('admin/dashboard.html',
                           webinars=webinars,
                           stats=stats,
                           day_names=DAY_NAMES)


# --- CRUD Webinario ---

@admin_bp.route('/webinar/new', methods=['POST'])
@login_required
def webinar_create():
    webhook_token = secrets.token_urlsafe(16)
    webinar = WebinarConfig(
        name=request.form.get('name', ''),
        client_name=request.form.get('client_name', ''),
        webhook_token=webhook_token,
        vturb_video_id=request.form.get('vturb_video_id', ''),
        is_active=bool(request.form.get('is_active')),
        day_of_week=int(request.form.get('day_of_week', 1)),
        start_hour=int(request.form.get('start_hour', 19)),
        start_minute=int(request.form.get('start_minute', 0)),
        attendee_count_base=int(request.form.get('attendee_count_base', 47)),
        upsell_url=request.form.get('upsell_url', ''),
        upsell_cta_text=request.form.get('upsell_cta_text', ''),
    )
    db.session.add(webinar)
    db.session.commit()
    return redirect(url_for('admin.webinar_detail', webinar_id=webinar.id))


@admin_bp.route('/webinar/<int:webinar_id>')
@login_required
def webinar_detail(webinar_id):
    webinar = WebinarConfig.query.get_or_404(webinar_id)
    registrants = Registrant.query.filter_by(webinar_id=webinar_id)\
        .order_by(Registrant.created_at.desc()).all()
    events = TimelineEvent.query.filter_by(webinar_id=webinar_id)\
        .order_by(TimelineEvent.trigger_second).all()

    stats = {
        'total': len(registrants),
        'attended': sum(1 for r in registrants if r.attended),
        'clicked_cta': sum(1 for r in registrants if r.clicked_cta),
    }
    webinar.day_name = DAY_NAMES[webinar.day_of_week] if webinar.day_of_week is not None else 'Terca'

    return render_template('admin/webinar_detail.html',
                           webinar=webinar,
                           registrants=registrants,
                           events=events,
                           stats=stats,
                           day_names=DAY_NAMES)


@admin_bp.route('/webinar/<int:webinar_id>/edit', methods=['POST'])
@login_required
def webinar_edit(webinar_id):
    webinar = WebinarConfig.query.get_or_404(webinar_id)
    webinar.name = request.form.get('name', webinar.name)
    webinar.client_name = request.form.get('client_name', webinar.client_name)
    webinar.vturb_video_id = request.form.get('vturb_video_id', webinar.vturb_video_id)
    webinar.is_active = bool(request.form.get('is_active'))
    webinar.day_of_week = int(request.form.get('day_of_week', webinar.day_of_week or 1))
    webinar.start_hour = int(request.form.get('start_hour', webinar.start_hour or 19))
    webinar.start_minute = int(request.form.get('start_minute', webinar.start_minute or 0))
    webinar.attendee_count_base = int(request.form.get('attendee_count_base', webinar.attendee_count_base or 47))
    webinar.upsell_url = request.form.get('upsell_url', webinar.upsell_url)
    webinar.upsell_cta_text = request.form.get('upsell_cta_text', webinar.upsell_cta_text)
    db.session.commit()
    return redirect(url_for('admin.webinar_detail', webinar_id=webinar_id))


@admin_bp.route('/webinar/<int:webinar_id>/delete', methods=['POST'])
@login_required
def webinar_delete(webinar_id):
    webinar = WebinarConfig.query.get_or_404(webinar_id)
    # Remove eventos e registrants associados
    TimelineEvent.query.filter_by(webinar_id=webinar_id).delete()
    Registrant.query.filter_by(webinar_id=webinar_id).delete()
    db.session.delete(webinar)
    db.session.commit()
    return redirect(url_for('admin.dashboard'))


# --- Timeline CRUD (por webinario) ---

@admin_bp.route('/webinar/<int:webinar_id>/timeline/add', methods=['POST'])
@login_required
def timeline_add(webinar_id):
    WebinarConfig.query.get_or_404(webinar_id)

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
        webinar_id=webinar_id,
        trigger_second=trigger_second,
        event_type=event_type,
        payload=payload,
    )
    db.session.add(event)
    db.session.commit()
    return redirect(url_for('admin.webinar_detail', webinar_id=webinar_id))


@admin_bp.route('/timeline/delete/<int:event_id>', methods=['POST'])
@login_required
def timeline_delete(event_id):
    event = TimelineEvent.query.get_or_404(event_id)
    webinar_id = event.webinar_id
    db.session.delete(event)
    db.session.commit()
    return redirect(url_for('admin.webinar_detail', webinar_id=webinar_id))


# --- Testar Sala ---

@admin_bp.route('/webinar/<int:webinar_id>/test-token')
@login_required
def test_token(webinar_id):
    """Gera um token de teste para visualizar a sala do webinario."""
    webinar = WebinarConfig.query.get_or_404(webinar_id)

    # Busca ou cria registrant de teste
    test_email = f"teste-admin-{webinar_id}@autowebinar.local"
    registrant = Registrant.query.filter_by(email=test_email, webinar_id=webinar_id).first()
    if not registrant:
        from services.scheduler import get_next_webinar_date
        from datetime import datetime
        # Usa datetime.now para que a sala abra imediatamente
        import pytz
        now = datetime.now(pytz.timezone('America/Sao_Paulo'))
        registrant = Registrant(
            name='Admin Teste',
            email=test_email,
            webinar_id=webinar_id,
            webinar_date=now.replace(minute=0, second=0),
        )
        db.session.add(registrant)
        db.session.flush()
        token = generate_token(registrant.id, test_email)
        registrant.token = token
        db.session.commit()

    sala_url = url_for('sala.sala', token=registrant.token, _external=True)
    return redirect(sala_url)
