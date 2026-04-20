import json
from datetime import datetime
from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for
from models import LivePresence, Registrant, TimelineEvent, UserChatMessage, WebinarConfig, db
from services.scheduler import BRT, is_webinar_open

sala_bp = Blueprint('sala', __name__)


@sala_bp.route('/sala/preview/<slug>')
def sala_preview(slug):
    """Preview público da sala — ignora horário, cria registrante marcado como preview.

    Esse registrante NÃO entra em estatísticas nem em live_presence (name começa
    com 'PREVIEW_'). Útil pra testar a sala a qualquer hora, sem cadastro real.
    """
    config = WebinarConfig.query.filter_by(slug=slug).first()
    if not config:
        return render_template('sala.html', error='Webinário não encontrado.'), 404

    preview_email = f'preview-public-{config.id}@autowebinar.local'
    registrant = Registrant.query.filter_by(email=preview_email, webinar_id=config.id).first()
    if not registrant:
        registrant = Registrant(
            name='PREVIEW_Visitante',
            email=preview_email,
            webinar_id=config.id,
            webinar_date=datetime.utcnow(),
        )
        db.session.add(registrant)
        db.session.commit()
    else:
        registrant.webinar_date = datetime.utcnow()
        db.session.commit()

    session['registrant_id'] = registrant.id
    session['webinar_id'] = config.id
    session['is_preview'] = True

    return render_template('sala.html',
                           registrant=registrant,
                           config=config,
                           is_preview=True,
                           error=None,
                           waiting=False)


@sala_bp.route('/sala')
def sala():
    """Sala do webinário. Requer sessão ativa (registrant_id + webinar_id)."""
    registrant_id = session.get('registrant_id')
    webinar_id = session.get('webinar_id')

    if not registrant_id:
        # Tenta redirecionar para o registrar do webinário correto
        if webinar_id:
            config = WebinarConfig.query.get(webinar_id)
            if config and config.slug:
                return redirect(url_for('registrar.register') + f'?w={config.slug}')
        return render_template('sala.html',
                               error='Para acessar, faça seu cadastro primeiro.'), 401

    registrant = Registrant.query.get(registrant_id)
    if not registrant:
        session.clear()
        return render_template('sala.html',
                               error='Cadastro não encontrado. Registre-se novamente.'), 404

    # Verifica se o webinário está aberto
    if not registrant.webinar_date or not is_webinar_open(registrant.webinar_date):
        next_date = registrant.webinar_date
        if next_date:
            if next_date.tzinfo is None:
                next_date = BRT.localize(next_date)
            return render_template('sala.html',
                                   waiting=True,
                                   webinar_date=next_date.isoformat(),
                                   name=registrant.name)
        return render_template('sala.html',
                               error='Data do webinário não definida.'), 400

    # Marca presença
    if not registrant.attended:
        registrant.attended = True
        db.session.commit()

    # Busca configuração do webinário
    config = None
    if registrant.webinar_id:
        config = WebinarConfig.query.get(registrant.webinar_id)
    if not config:
        config = WebinarConfig.query.filter_by(is_active=True).first()

    return render_template('sala.html',
                           registrant=registrant,
                           config=config,
                           error=None,
                           waiting=False)


@sala_bp.route('/api/events')
def api_events():
    """Retorna timeline_events do webinário. Usa ?webinar_id= ou sessão ou webinário ativo."""
    webinar_id = request.args.get('webinar_id') or session.get('webinar_id')
    if webinar_id:
        config = WebinarConfig.query.get(int(webinar_id))
    else:
        config = WebinarConfig.query.filter_by(is_active=True).first()

    if not config:
        return jsonify([])

    events = TimelineEvent.query.filter_by(webinar_id=config.id) \
        .order_by(TimelineEvent.trigger_second).all()

    return jsonify([
        {
            'id': e.id,
            'trigger_second': e.trigger_second,
            'event_type': e.event_type,
            'payload': json.loads(e.payload) if e.payload else {},
        }
        for e in events
    ])


@sala_bp.route('/api/track', methods=['POST'])
def track():
    """Recebe tracking do frontend: tempo assistido e clique no CTA."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'no data'}), 400

    registrant_id = session.get('registrant_id')
    if not registrant_id:
        return jsonify({'error': 'no session'}), 401

    registrant = Registrant.query.get(registrant_id)
    if not registrant:
        return jsonify({'error': 'not found'}), 404

    # Preview público: não grava métricas
    if session.get('is_preview'):
        return jsonify({'ok': True, 'preview': True})

    if 'watch_time' in data:
        registrant.watch_time_seconds = max(
            registrant.watch_time_seconds or 0,
            int(data['watch_time'])
        )

    if data.get('clicked_cta'):
        registrant.clicked_cta = True

    db.session.commit()
    return jsonify({'ok': True})


@sala_bp.route('/api/support', methods=['POST'])
def support():
    """Recebe mensagens de suporte do usuário durante a sala."""
    from models import SupportMessage
    data = request.get_json(silent=True)
    if not data or not data.get('message'):
        return jsonify({'error': 'no message'}), 400

    registrant_id = session.get('registrant_id')
    webinar_id = session.get('webinar_id')

    msg = SupportMessage(
        registrant_id=registrant_id,
        webinar_id=webinar_id,
        message=data['message']
    )
    db.session.add(msg)
    db.session.commit()
    return jsonify({'ok': True})


@sala_bp.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    """Ping de presença. Frontend chama a cada ~15s enquanto a sala está aberta."""
    registrant_id = session.get('registrant_id')
    webinar_id = session.get('webinar_id')
    if not registrant_id or not webinar_id:
        return jsonify({'error': 'no session'}), 401

    # Preview público NÃO conta como presença real
    if session.get('is_preview'):
        return jsonify({'ok': True, 'preview': True})

    presence = LivePresence.query.filter_by(registrant_id=registrant_id).first()
    now = datetime.utcnow()
    ua = (request.headers.get('User-Agent') or '')[:255]
    if presence:
        presence.last_seen = now
        presence.webinar_id = webinar_id
        presence.user_agent = ua
    else:
        presence = LivePresence(
            registrant_id=registrant_id,
            webinar_id=webinar_id,
            last_seen=now,
            user_agent=ua,
        )
        db.session.add(presence)
    db.session.commit()
    return jsonify({'ok': True})


@sala_bp.route('/api/user-chat', methods=['POST'])
def user_chat_post():
    """Persiste mensagem do usuário. Só o próprio usuário e o admin veem depois."""
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'empty'}), 400
    if len(message) > 500:
        message = message[:500]

    registrant_id = session.get('registrant_id')
    webinar_id = session.get('webinar_id')
    if not registrant_id:
        return jsonify({'error': 'no session'}), 401

    # Preview público: não persiste no feed do admin
    if session.get('is_preview'):
        return jsonify({'ok': True, 'preview': True, 'id': 0, 'created_at': datetime.utcnow().isoformat()})

    msg = UserChatMessage(
        registrant_id=registrant_id,
        webinar_id=webinar_id,
        message=message,
    )
    db.session.add(msg)
    db.session.commit()
    return jsonify({'ok': True, 'id': msg.id, 'created_at': msg.created_at.isoformat()})


@sala_bp.route('/api/my-chat')
def my_chat():
    """Retorna as mensagens do próprio usuário (com respostas do admin, se houver)."""
    registrant_id = session.get('registrant_id')
    if not registrant_id:
        return jsonify([])
    since_id = int(request.args.get('since_id', 0) or 0)

    q = UserChatMessage.query.filter_by(registrant_id=registrant_id)
    if since_id:
        q = q.filter(UserChatMessage.id > since_id)
    msgs = q.order_by(UserChatMessage.created_at).limit(100).all()

    return jsonify([
        {
            'id': m.id,
            'message': m.message,
            'created_at': m.created_at.isoformat() if m.created_at else None,
            'admin_reply': m.admin_reply,
            'replied_at': m.replied_at.isoformat() if m.replied_at else None,
        }
        for m in msgs
    ])
