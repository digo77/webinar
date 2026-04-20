import json
import os
import secrets
import tempfile
from datetime import datetime, timedelta
from functools import wraps

import pytz
from flask import (Blueprint, current_app, jsonify, redirect,
                   render_template, request, session, url_for)

from models import (LivePresence, Registrant, TimelineEvent,
                    UserChatMessage, WebinarConfig, db)
from services.scheduler import BRT, DAY_NAMES

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@admin_bp.route('/')
@admin_bp.route('/dashboard')
@login_required
def dashboard():
    webinars = WebinarConfig.query.order_by(WebinarConfig.id.desc()).all()

    total_reg = Registrant.query.count()
    total_attended = Registrant.query.filter_by(attended=True).count()
    total_cta = Registrant.query.filter_by(clicked_cta=True).count()

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


# ---------------------------------------------------------------------------
# CRUD Webinario
# ---------------------------------------------------------------------------

@admin_bp.route('/webinar/new', methods=['POST'])
@login_required
def webinar_create():
    webhook_token = secrets.token_urlsafe(16)
    raw_slug = request.form.get('slug', '').strip().lower().replace(' ', '-')
    webinar = WebinarConfig(
        name=request.form.get('name', ''),
        client_name=request.form.get('client_name', ''),
        webhook_token=webhook_token,
        slug=raw_slug if raw_slug else None,
        vturb_video_id=request.form.get('vturb_video_id', ''),
        is_active=bool(request.form.get('is_active')),
        day_of_week=int(request.form.get('day_of_week', 1)),
        start_hour=int(request.form.get('start_hour', 19)),
        start_minute=int(request.form.get('start_minute', 0)),
        attendee_count_base=int(request.form.get('attendee_count_base', 47)),
        upsell_url=request.form.get('upsell_url', ''),
        upsell_cta_text=request.form.get('upsell_cta_text', ''),
        pitch_second=int(request.form.get('pitch_second', 0) or 0),
        offer_original_price=request.form.get('offer_original_price', ''),
        offer_price=request.form.get('offer_price', ''),
    )
    db.session.add(webinar)
    db.session.commit()
    return redirect(url_for('admin.webinar_detail', webinar_id=webinar.id))


@admin_bp.route('/webinar/<int:webinar_id>')
@login_required
def webinar_detail(webinar_id):
    webinar = WebinarConfig.query.get_or_404(webinar_id)
    registrants = Registrant.query.filter_by(webinar_id=webinar_id) \
        .order_by(Registrant.created_at.desc()).all()
    events = TimelineEvent.query.filter_by(webinar_id=webinar_id) \
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

    # Slug (URL de registro)
    raw_slug = request.form.get('slug', '').strip().lower().replace(' ', '-')
    webinar.slug = raw_slug if raw_slug else webinar.slug

    # Test date (datetime-local, ex: "2026-03-27T20:00")
    test_date_val = request.form.get('test_date', '').strip()
    webinar.test_date = test_date_val if test_date_val else None

    webinar.offer_image_url = request.form.get('offer_image_url', webinar.offer_image_url)
    webinar.offer_original_price = request.form.get('offer_original_price', webinar.offer_original_price)
    webinar.offer_price = request.form.get('offer_price', webinar.offer_price)
    webinar.pitch_second = int(request.form.get('pitch_second', webinar.pitch_second or 0) or 0)
    webinar.chatbot_responses = request.form.get('chatbot_responses', webinar.chatbot_responses)
    webinar.register_mode = int(request.form.get('register_mode', webinar.register_mode or 1))
    webinar.register_headline = request.form.get('register_headline', webinar.register_headline)
    webinar.register_subtitle = request.form.get('register_subtitle', webinar.register_subtitle)
    webinar.register_bg_color = request.form.get('register_bg_color', webinar.register_bg_color)
    webinar.register_bg_image_url = request.form.get('register_bg_image_url', webinar.register_bg_image_url)
    webinar.register_presenter_photo_url = request.form.get('register_presenter_photo_url', webinar.register_presenter_photo_url)
    webinar.register_bullets = request.form.get('register_bullets', webinar.register_bullets)
    webinar.register_button_text = request.form.get('register_button_text', webinar.register_button_text)

    db.session.commit()
    return redirect(url_for('admin.webinar_detail', webinar_id=webinar_id))


@admin_bp.route('/webinar/<int:webinar_id>/delete', methods=['POST'])
@login_required
def webinar_delete(webinar_id):
    webinar = WebinarConfig.query.get_or_404(webinar_id)
    TimelineEvent.query.filter_by(webinar_id=webinar_id).delete()
    Registrant.query.filter_by(webinar_id=webinar_id).delete()
    db.session.delete(webinar)
    db.session.commit()
    return redirect(url_for('admin.dashboard'))


# ---------------------------------------------------------------------------
# Timeline CRUD — via webinar_detail
# ---------------------------------------------------------------------------

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
    elif event_type == 'purchase_notification':
        names_raw = request.form.get('purchase_names', '')
        names = [n.strip() for n in names_raw.split(',') if n.strip()]
        payload = json.dumps({'names': names})
    elif event_type == 'poll':
        question = request.form.get('question', '')
        options_raw = request.form.get('options', '')
        options = [o.strip() for o in options_raw.split(',') if o.strip()]
        payload = json.dumps({'question': question, 'options': options})
    elif event_type == 'end_broadcast':
        payload = json.dumps({})
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

    # Redireciona de volta para onde o form veio
    next_url = request.form.get('next', '')
    if next_url == 'timeline':
        return redirect(url_for('admin.timeline_view', webinar_id=webinar_id))
    return redirect(url_for('admin.webinar_detail', webinar_id=webinar_id))


@admin_bp.route('/timeline/delete/<int:event_id>', methods=['POST'])
@login_required
def timeline_delete(event_id):
    event = TimelineEvent.query.get_or_404(event_id)
    webinar_id = event.webinar_id
    db.session.delete(event)
    db.session.commit()
    next_url = request.form.get('next', '')
    if next_url == 'timeline':
        return redirect(url_for('admin.timeline_view', webinar_id=webinar_id))
    return redirect(url_for('admin.webinar_detail', webinar_id=webinar_id))


# ---------------------------------------------------------------------------
# Timeline visual (Feature 2)
# ---------------------------------------------------------------------------

@admin_bp.route('/timeline/<int:webinar_id>', methods=['GET', 'POST'])
@login_required
def timeline_view(webinar_id):
    webinar = WebinarConfig.query.get_or_404(webinar_id)

    if request.method == 'POST':
        # Reutiliza lógica de timeline_add, porém redireciona de volta aqui
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
        elif event_type == 'poll':
            question = request.form.get('question', '')
            options_raw = request.form.get('options', '')
            options = [o.strip() for o in options_raw.split(',') if o.strip()]
            payload = json.dumps({'question': question, 'options': options})
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
        return redirect(url_for('admin.timeline_view', webinar_id=webinar_id))

    # GET: prepara eventos com payload parseado e tempo formatado
    events_raw = TimelineEvent.query.filter_by(webinar_id=webinar_id) \
        .order_by(TimelineEvent.trigger_second).all()

    events = []
    for e in events_raw:
        try:
            payload_data = json.loads(e.payload) if e.payload else {}
        except (json.JSONDecodeError, TypeError):
            payload_data = {}
        events.append({
            'id': e.id,
            'trigger_second': e.trigger_second,
            'time_fmt': f"{e.trigger_second // 60}:{e.trigger_second % 60:02d}",
            'event_type': e.event_type,
            'payload': payload_data,
        })

    return render_template('admin/timeline.html', webinar=webinar, events=events)


@admin_bp.route('/timeline/<int:webinar_id>/delete/<int:event_id>', methods=['POST'])
@login_required
def timeline_delete_from_view(webinar_id, event_id):
    event = TimelineEvent.query.get_or_404(event_id)
    db.session.delete(event)
    db.session.commit()
    return redirect(url_for('admin.timeline_view', webinar_id=webinar_id))


# ---------------------------------------------------------------------------
# Testar Sala / Preview (Feature 1)
# ---------------------------------------------------------------------------

def _get_or_create_test_registrant(webinar_id, name, email):
    """Cria ou atualiza registrante de teste e define webinar_date."""
    webinar = WebinarConfig.query.get_or_404(webinar_id)

    # Determina data de teste
    if webinar.test_date:
        try:
            test_dt = datetime.fromisoformat(webinar.test_date)
            if test_dt.tzinfo is None:
                test_dt = BRT.localize(test_dt)
        except (ValueError, AttributeError):
            test_dt = datetime.now(BRT) - timedelta(minutes=20)
    else:
        test_dt = datetime.now(BRT) - timedelta(minutes=20)

    naive_dt = test_dt.replace(tzinfo=None)

    registrant = Registrant.query.filter_by(email=email, webinar_id=webinar_id).first()
    if not registrant:
        registrant = Registrant(
            name=name,
            email=email,
            webinar_id=webinar_id,
            webinar_date=naive_dt,
        )
        db.session.add(registrant)
        db.session.commit()
    else:
        registrant.webinar_date = naive_dt
        db.session.commit()

    return registrant


@admin_bp.route('/webinar/<int:webinar_id>/test-token')
@login_required
def test_token(webinar_id):
    """Testar sala: cria sessão de teste e redireciona para /sala."""
    registrant = _get_or_create_test_registrant(
        webinar_id, 'Admin Teste', f'teste-admin-{webinar_id}@autowebinar.local'
    )
    session['registrant_id'] = registrant.id
    session['webinar_id'] = webinar_id
    return redirect(url_for('sala.sala'))


@admin_bp.route('/preview/<int:webinar_id>')
@login_required
def preview(webinar_id):
    """Preview da sala: cria registrante Preview e abre sala via sessão."""
    registrant = _get_or_create_test_registrant(
        webinar_id, 'Preview', f'preview-{webinar_id}@autowebinar.local'
    )
    session['registrant_id'] = registrant.id
    session['webinar_id'] = webinar_id
    return redirect(url_for('sala.sala'))


# ---------------------------------------------------------------------------
# Gerador de Timeline com IA (Feature 3)
# ---------------------------------------------------------------------------

@admin_bp.route('/ai-provider-status')
@login_required
def ai_provider_status():
    from services.ai_timeline import get_ai_provider
    from flask import jsonify as _jsonify
    return _jsonify({'provider': get_ai_provider()})


@admin_bp.route('/ai-timeline/<int:webinar_id>', methods=['GET', 'POST'])
@login_required
def ai_timeline(webinar_id):
    webinar = WebinarConfig.query.get_or_404(webinar_id)

    if request.method == 'POST':
        product_context = request.form.get('product_context', '').strip()
        mode = request.form.get('mode', 'audio')  # 'audio' ou 'text'

        from services.ai_timeline import suggest_chat_events, transcribe_audio, parse_transcript_text

        # ── Modo texto: transcrição colada ──────────────────────────────────
        if mode == 'text':
            transcript_text = request.form.get('transcript_text', '').strip()
            if not transcript_text:
                return jsonify({'error': 'Cole a transcrição antes de gerar.'}), 400
            try:
                segments = parse_transcript_text(transcript_text)
                if not segments:
                    return jsonify({'error': 'Nenhum timestamp encontrado no texto. Verifique o formato (ex: [0:45] texto).'}), 400
                suggestions = suggest_chat_events(segments, product_context)
                return jsonify({'ok': True, 'segments_count': len(segments), 'suggestions': suggestions})
            except Exception as exc:
                current_app.logger.exception('Erro no ai-timeline (text mode)')
                return jsonify({'error': str(exc)}), 500

        # ── Modo áudio: upload + Whisper ────────────────────────────────────
        audio_file = request.files.get('audio_file')
        if not audio_file or not audio_file.filename:
            return jsonify({'error': 'Nenhum arquivo de áudio enviado.'}), 400

        _, ext = os.path.splitext(audio_file.filename)
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext or '.mp3')
        try:
            os.close(tmp_fd)
            audio_file.save(tmp_path)
            segments = transcribe_audio(tmp_path)
            suggestions = suggest_chat_events(segments, product_context)
            return jsonify({'ok': True, 'segments_count': len(segments), 'suggestions': suggestions})
        except Exception as exc:
            current_app.logger.exception('Erro no ai-timeline (audio mode)')
            return jsonify({'error': str(exc)}), 500
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # GET
    return render_template('admin/ai_timeline.html', webinar=webinar)


@admin_bp.route('/webinar/<int:webinar_id>/support')
@login_required
def support_messages(webinar_id):
    from models import SupportMessage
    webinar = WebinarConfig.query.get_or_404(webinar_id)
    messages = SupportMessage.query.filter_by(webinar_id=webinar_id).order_by(SupportMessage.created_at.desc()).all()
    return render_template('admin/support.html', webinar=webinar, messages=messages)


@admin_bp.route('/webinar/<int:webinar_id>/support/<int:msg_id>/answer', methods=['POST'])
@login_required
def support_answer(webinar_id, msg_id):
    from models import SupportMessage
    msg = SupportMessage.query.get_or_404(msg_id)
    msg.answered = True
    db.session.commit()
    return redirect(url_for('admin.support_messages', webinar_id=webinar_id))


@admin_bp.route('/webinar/<int:webinar_id>/export-csv')
@login_required
def export_csv(webinar_id):
    """Exporta registrados do webinário como CSV."""
    import csv
    import io
    from datetime import date
    from flask import make_response
    webinar = WebinarConfig.query.get_or_404(webinar_id)
    registrants = Registrant.query.filter_by(webinar_id=webinar_id) \
        .order_by(Registrant.created_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Nome', 'Email', 'Telefone', 'Data Webinário',
                     'Assistiu', 'Tempo (min)', 'Clicou CTA',
                     'UTM Source', 'UTM Medium', 'UTM Campaign', 'Criado em'])
    for r in registrants:
        phone = ''
        if r.phone_number:
            phone = (r.phone_country_code or '') + ' ' + r.phone_number
        watched = 'Sim' if (r.watch_time_seconds or 0) > 30 else 'Não'
        writer.writerow([
            r.name or '',
            r.email or '',
            phone.strip(),
            r.webinar_date.strftime('%d/%m/%Y %H:%M') if r.webinar_date else '',
            watched,
            round((r.watch_time_seconds or 0) / 60, 1),
            'Sim' if r.clicked_cta else 'Não',
            r.utm_source or '',
            r.utm_medium or '',
            r.utm_campaign or '',
            r.created_at.strftime('%d/%m/%Y %H:%M') if r.created_at else '',
        ])

    output.seek(0)
    slug = webinar.slug or str(webinar_id)
    filename = f"registrados-{slug}-{date.today().isoformat()}.csv"
    response = make_response('\ufeff' + output.getvalue())  # BOM para Excel
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@admin_bp.route('/timeline/<int:webinar_id>/event/<int:event_id>')
@login_required
def timeline_event_get(webinar_id, event_id):
    """Retorna dados de um evento para edição (JSON)."""
    event = TimelineEvent.query.get_or_404(event_id)
    try:
        payload = json.loads(event.payload) if event.payload else {}
    except (json.JSONDecodeError, TypeError):
        payload = {}
    return jsonify({
        'id': event.id,
        'trigger_second': event.trigger_second,
        'event_type': event.event_type,
        'payload': payload,
    })


@admin_bp.route('/timeline/<int:webinar_id>/event/<int:event_id>/edit', methods=['POST'])
@login_required
def timeline_event_edit(webinar_id, event_id):
    """Atualiza um evento existente na timeline."""
    event = TimelineEvent.query.get_or_404(event_id)
    event.trigger_second = int(request.form.get('trigger_second', event.trigger_second))
    event_type = request.form.get('event_type', event.event_type)
    event.event_type = event_type

    if event_type == 'chat':
        event.payload = json.dumps({
            'author': request.form.get('author', ''),
            'message': request.form.get('message', ''),
        })
    elif event_type == 'cta_popup':
        event.payload = json.dumps({
            'title': request.form.get('title', ''),
            'countdown_minutes': int(request.form.get('countdown_minutes', 15) or 15),
            'url': request.form.get('url', ''),
        })
    elif event_type == 'poll':
        options = [o.strip() for o in request.form.get('options', '').split(',') if o.strip()]
        event.payload = json.dumps({
            'question': request.form.get('question', ''),
            'options': options,
        })
    else:
        event.payload = json.dumps({})

    db.session.commit()
    return redirect(url_for('admin.timeline_view', webinar_id=webinar_id))


# ---------------------------------------------------------------------------
# LIVE: presença real + chat real
# ---------------------------------------------------------------------------

LIVE_WINDOW_SECONDS = 45  # considera "ao vivo" quem deu heartbeat nos últimos 45s


@admin_bp.route('/webinar/<int:webinar_id>/live')
@login_required
def live_view(webinar_id):
    webinar = WebinarConfig.query.get_or_404(webinar_id)
    return render_template('admin/live.html', webinar=webinar)


@admin_bp.route('/api/live-data/<int:webinar_id>')
@login_required
def live_data(webinar_id):
    """JSON com presença ativa + feed de chat. Polled pelo admin."""
    cutoff = datetime.utcnow() - timedelta(seconds=LIVE_WINDOW_SECONDS)

    presence = db.session.query(LivePresence, Registrant).join(
        Registrant, LivePresence.registrant_id == Registrant.id
    ).filter(
        LivePresence.webinar_id == webinar_id,
        LivePresence.last_seen >= cutoff,
        ~Registrant.name.like('PREVIEW_%'),
    ).order_by(LivePresence.last_seen.desc()).all()

    viewers = [
        {
            'registrant_id': r.id,
            'name': r.name or '—',
            'phone': ((r.phone_country_code or '') + ' ' + (r.phone_number or '')).strip() or None,
            'last_seen_sec_ago': int((datetime.utcnow() - p.last_seen).total_seconds()),
        }
        for p, r in presence
    ]

    since_id = int(request.args.get('since_id', 0) or 0)
    q = db.session.query(UserChatMessage, Registrant).join(
        Registrant, UserChatMessage.registrant_id == Registrant.id
    ).filter(UserChatMessage.webinar_id == webinar_id)
    if since_id:
        q = q.filter(UserChatMessage.id > since_id)
    chat_rows = q.order_by(UserChatMessage.created_at.desc()).limit(200).all()

    chat = [
        {
            'id': m.id,
            'registrant_id': r.id,
            'name': r.name or '—',
            'phone': ((r.phone_country_code or '') + ' ' + (r.phone_number or '')).strip() or None,
            'message': m.message,
            'created_at': m.created_at.isoformat() if m.created_at else None,
            'admin_reply': m.admin_reply,
            'replied_at': m.replied_at.isoformat() if m.replied_at else None,
        }
        for m, r in chat_rows
    ]

    return jsonify({
        'viewers': viewers,
        'viewer_count': len(viewers),
        'chat': chat,
    })


@admin_bp.route('/api/chat-reply/<int:chat_id>', methods=['POST'])
@login_required
def chat_reply(chat_id):
    msg = UserChatMessage.query.get_or_404(chat_id)
    data = request.get_json(silent=True) or {}
    reply = (data.get('reply') or '').strip()
    if not reply:
        return jsonify({'error': 'empty'}), 400
    msg.admin_reply = reply[:500]
    msg.replied_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'ok': True, 'replied_at': msg.replied_at.isoformat()})


# ---------------------------------------------------------------------------
# Disparo em lote de WhatsApp via SendFlow
# ---------------------------------------------------------------------------

@admin_bp.route('/webinar/<int:webinar_id>/bulk-whatsapp', methods=['POST'])
@login_required
def bulk_whatsapp(webinar_id):
    from services.notifier import notify_sendflow
    webinar = WebinarConfig.query.get_or_404(webinar_id)

    data = request.get_json(silent=True) or {}
    template = (data.get('template')
                or "Oi {first_name}! Sua aula ao vivo começa em instantes. Acesse pelo link: {link}").strip()
    only_today = bool(data.get('only_today', False))

    if not webinar.slug:
        return jsonify({'error': 'Webinário sem slug. Defina um slug antes de enviar.'}), 400

    base = request.host_url.rstrip('/') + url_for('registrar.register') + f'?w={webinar.slug}'

    q = Registrant.query.filter(
        Registrant.webinar_id == webinar_id,
        Registrant.phone_number.isnot(None),
        Registrant.phone_number != '',
    )
    if only_today:
        today = datetime.now(BRT).date()
        q = q.filter(
            db.func.date(Registrant.webinar_date) == today
        )

    sent = 0
    failed = 0
    skipped = 0
    for r in q.all():
        phone = (r.phone_country_code or '+55').replace('+', '') + (r.phone_number or '').replace(' ', '').replace('(', '').replace(')', '').replace('-', '')
        if len(phone) < 10:
            skipped += 1
            continue
        first_name = (r.name or '').split()[0] if r.name else ''
        # Link personalizado: auto-login via &phone= (se o registrant existe, pula o form)
        personal_link = f'{base}&phone={phone}'
        message = template.replace('{first_name}', first_name).replace('{name}', r.name or '').replace('{link}', personal_link)
        ok = notify_sendflow(phone, message)
        if ok:
            sent += 1
        else:
            failed += 1

    return jsonify({'ok': True, 'sent': sent, 'failed': failed, 'skipped': skipped, 'link': base})


@admin_bp.route('/ai-timeline/<int:webinar_id>/import', methods=['POST'])
@login_required
def ai_timeline_import(webinar_id):
    """Recebe sugestões selecionadas e cria TimelineEvents."""
    WebinarConfig.query.get_or_404(webinar_id)
    data = request.get_json(silent=True) or {}
    suggestions = data.get('suggestions', [])

    created = 0
    for s in suggestions:
        try:
            payload = json.dumps({
                'author': s.get('author', 'Participante'),
                'message': s.get('message', ''),
            })
            event = TimelineEvent(
                webinar_id=webinar_id,
                trigger_second=int(s.get('trigger_second', 0)),
                event_type='chat',
                payload=payload,
            )
            db.session.add(event)
            created += 1
        except Exception:
            pass

    db.session.commit()
    return jsonify({'ok': True, 'created': created})
