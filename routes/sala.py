import json
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for
import pytz
from models import LivePresence, Poll, PollVote, Reaction, Registrant, TimelineEvent, UserChatMessage, WebinarConfig, db
from services.scheduler import BRT, is_webinar_open

_REPLAY_CUTOFF_HOUR = 21
_REPLAY_CUTOFF_MINUTE = 15


def _fmt_ts_brt(dt):
    """Converte datetime UTC para string HH:MM no horário de Brasília."""
    if not dt:
        return None
    try:
        return BRT.fromutc(dt).strftime('%H:%M')
    except Exception:
        return None

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
                           is_admin=bool(session.get('admin_logged_in')),
                           error=None,
                           waiting=False)


@sala_bp.route('/sala')
def sala():
    """Sala do webinário. Requer sessão ativa (registrant_id + webinar_id).

    Aceita tambem:
      ?token=<JWT>  -> consome o token gerado no webhook Hotmart
      ?w=<slug>     -> redireciona pra /registrar se nao tiver sessao
    """
    # Magic link via JWT (link enviado no WhatsApp pela Hotmart)
    token = request.args.get('token', '').strip()
    if token and not session.get('registrant_id'):
        from services.token_service import validate_token
        payload = validate_token(token)
        if payload and payload.get('rid'):
            r = Registrant.query.get(payload['rid'])
            if r:
                session['registrant_id'] = r.id
                session['webinar_id'] = r.webinar_id
                # Remove ?token= da URL pra nao vazar no referer
                return redirect(url_for('sala.sala'))

    registrant_id = session.get('registrant_id')
    webinar_id = session.get('webinar_id')

    if not registrant_id:
        # Tenta redirecionar para o registrar (via ?w= ou sessao anterior)
        slug_hint = request.args.get('w', '').strip()
        if slug_hint:
            return redirect(url_for('registrar.register') + f'?w={slug_hint}')
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
        if not registrant.webinar_date:
            return render_template('sala.html', error='Data do webinário não definida.'), 400

        wd = registrant.webinar_date
        if wd.tzinfo is None:
            wd = BRT.localize(wd)
        now_brt = datetime.now(BRT)

        # Replay: webinar foi hoje, live encerrou, mas ainda dentro da janela até 21h15
        if wd.date() == now_brt.date() and wd < now_brt:
            replay_cutoff = wd.replace(
                hour=_REPLAY_CUTOFF_HOUR, minute=_REPLAY_CUTOFF_MINUTE, second=0, microsecond=0
            )
            if now_brt <= replay_cutoff:
                config = None
                if registrant.webinar_id:
                    config = WebinarConfig.query.get(registrant.webinar_id)
                if not config:
                    config = WebinarConfig.query.filter_by(is_active=True).first()
                return render_template('sala.html',
                                       registrant=registrant,
                                       config=config,
                                       is_replay=True,
                                       is_admin=bool(session.get('admin_logged_in')),
                                       error=None,
                                       waiting=False,
                                       session_start_iso=wd.isoformat())

        config = None
        if registrant.webinar_id:
            config = WebinarConfig.query.get(registrant.webinar_id)
        return render_template('sala.html',
                               waiting=True,
                               webinar_date=wd.isoformat(),
                               name=registrant.name,
                               config=config)

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

    session_start_iso = registrant.webinar_date.isoformat() if registrant.webinar_date else ''
    return render_template('sala.html',
                           registrant=registrant,
                           config=config,
                           is_admin=bool(session.get('admin_logged_in')),
                           is_replay=False,
                           session_start_iso=session_start_iso,
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


@sala_bp.route('/api/session-ended', methods=['POST'])
def session_ended():
    """Chamado pelo frontend quando end_broadcast dispara. Envia relatório pós-sessão."""
    webinar_id = session.get('webinar_id')
    if not webinar_id:
        return jsonify({'ok': False})
    if not session.get('is_preview'):
        try:
            from services.notifier import notify_session_report
            notify_session_report(webinar_id)
        except Exception:
            pass
    return jsonify({'ok': True})


@sala_bp.route('/api/public-chat')
def public_chat():
    """Feed público de mensagens aprovadas pelo admin. Inclui comentário fixado."""
    webinar_id = request.args.get('webinar_id') or session.get('webinar_id')
    since_id = int(request.args.get('since_id', 0) or 0)
    if not webinar_id:
        return jsonify({'messages': [], 'pinned': None})
    wid = int(webinar_id)

    # Filtro de sessão: só mensagens desta sessão (evita mensagens de semanas anteriores)
    session_start_str = request.args.get('session_start', '').strip()
    cutoff = datetime.utcnow() - timedelta(hours=12)
    if session_start_str:
        try:
            ss = datetime.fromisoformat(session_start_str.replace('Z', ''))
            # Remove timezone info para comparar com UTC naive
            if hasattr(ss, 'tzinfo') and ss.tzinfo is not None:
                ss = ss.utctimetuple()
                ss = datetime(*ss[:6])
            # Buffer de 30 min antes do início da sessão
            cutoff = max(cutoff, ss - timedelta(minutes=30))
        except (ValueError, TypeError):
            pass

    rows = db.session.query(UserChatMessage, Registrant).outerjoin(
        Registrant, UserChatMessage.registrant_id == Registrant.id
    ).filter(
        UserChatMessage.webinar_id == wid,
        UserChatMessage.status == 'approved',
        UserChatMessage.id > since_id,
        UserChatMessage.created_at >= cutoff,
    ).order_by(UserChatMessage.created_at).limit(50).all()

    pinned_row = db.session.query(UserChatMessage, Registrant).outerjoin(
        Registrant, UserChatMessage.registrant_id == Registrant.id
    ).filter(
        UserChatMessage.webinar_id == wid,
        UserChatMessage.is_pinned == True,
    ).first()
    pinned = None
    if pinned_row:
        pm, pr = pinned_row
        pinned = {'id': pm.id, 'name': pm.sender_name or (pr.name if pr else 'Admin'), 'message': pm.message}

    return jsonify({
        'messages': [{
            'id': m.id,
            'name': m.sender_name or (r.name if r else 'Participante'),
            'message': m.message,
            'admin_reply': m.admin_reply,
            'ts': _fmt_ts_brt(m.created_at),
            'is_equipe': bool(m.sender_name),
        } for m, r in rows],
        'pinned': pinned,
    })


@sala_bp.route('/api/poll/<int:webinar_id>')
def get_poll(webinar_id):
    """Retorna enquete ativa com contagem de votos."""
    poll = Poll.query.filter_by(webinar_id=webinar_id, is_active=True).order_by(Poll.id.desc()).first()
    if not poll:
        return jsonify(None)
    options = json.loads(poll.options)
    votes = PollVote.query.filter_by(poll_id=poll.id).all()
    counts = [0] * len(options)
    for v in votes:
        if 0 <= v.option_index < len(options):
            counts[v.option_index] += 1
    session_key = str(session.get('registrant_id') or '')
    my_vote = None
    if session_key:
        mv = PollVote.query.filter_by(poll_id=poll.id, session_key=session_key).first()
        if mv:
            my_vote = mv.option_index
    return jsonify({'id': poll.id, 'question': poll.question, 'options': options,
                    'counts': counts, 'total': sum(counts), 'my_vote': my_vote})


@sala_bp.route('/api/poll/<int:poll_id>/vote', methods=['POST'])
def vote_poll(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    if not poll.is_active:
        return jsonify({'error': 'closed'}), 400
    data = request.get_json(silent=True) or {}
    option_index = data.get('option_index')
    if option_index is None:
        return jsonify({'error': 'no option'}), 400
    options = json.loads(poll.options)
    if not (0 <= int(option_index) < len(options)):
        return jsonify({'error': 'invalid option'}), 400
    session_key = str(session.get('registrant_id') or request.remote_addr)
    if PollVote.query.filter_by(poll_id=poll_id, session_key=session_key).first():
        return jsonify({'error': 'already voted'}), 400
    db.session.add(PollVote(poll_id=poll_id, session_key=session_key, option_index=int(option_index)))
    db.session.commit()
    return jsonify({'ok': True})


@sala_bp.route('/api/react', methods=['POST'])
def react():
    data = request.get_json(silent=True) or {}
    emoji = (data.get('emoji') or '').strip()
    if emoji not in {'❤️', '👏', '🔥', '😮'}:
        return jsonify({'error': 'invalid'}), 400
    webinar_id = session.get('webinar_id')
    if not webinar_id:
        return jsonify({'error': 'no session'}), 401
    db.session.add(Reaction(webinar_id=webinar_id, emoji=emoji))
    Reaction.query.filter(Reaction.created_at < datetime.utcnow() - timedelta(minutes=5)).delete()
    db.session.commit()
    return jsonify({'ok': True})


@sala_bp.route('/api/reactions/<int:webinar_id>')
def get_reactions(webinar_id):
    since_str = request.args.get('since', '').strip()
    cutoff = datetime.utcnow() - timedelta(seconds=3)
    if since_str:
        try:
            ss = datetime.fromisoformat(since_str.replace('Z', ''))
            if ss > cutoff:
                cutoff = ss
        except (ValueError, TypeError):
            pass
    rows = Reaction.query.filter(
        Reaction.webinar_id == webinar_id,
        Reaction.created_at >= cutoff,
    ).all()
    counts = {}
    for r in rows:
        counts[r.emoji] = counts.get(r.emoji, 0) + 1
    return jsonify({'counts': counts, 'ts': datetime.utcnow().isoformat()})


@sala_bp.route('/api/my-chat')
def my_chat():
    """Retorna as mensagens do próprio usuário (com respostas do admin, se houver).

    Aceita:
      ?since_id=N          — mensagens com id > N (novas mensagens)
      ?replied_since=ISO   — mensagens com replied_at > ISO (respostas novas, mesmo em msgs antigas)
    """
    registrant_id = session.get('registrant_id')
    if not registrant_id:
        return jsonify([])

    since_id = int(request.args.get('since_id', 0) or 0)
    replied_since_str = request.args.get('replied_since', '').strip()

    # Novas mensagens
    q_new = UserChatMessage.query.filter_by(registrant_id=registrant_id)
    if since_id:
        q_new = q_new.filter(UserChatMessage.id > since_id)
    new_msgs = q_new.order_by(UserChatMessage.created_at).limit(100).all()

    # Respostas novas em mensagens antigas (replied_at > replied_since)
    reply_msgs = []
    if replied_since_str:
        try:
            replied_since_dt = datetime.fromisoformat(replied_since_str.replace('Z', ''))
            reply_msgs = UserChatMessage.query.filter_by(registrant_id=registrant_id).filter(
                UserChatMessage.admin_reply.isnot(None),
                UserChatMessage.replied_at > replied_since_dt,
            ).all()
        except (ValueError, TypeError):
            pass

    # Combina e deduplica
    seen = set()
    result = []
    for m in new_msgs + reply_msgs:
        if m.id in seen:
            continue
        seen.add(m.id)
        result.append({
            'id': m.id,
            'message': m.message,
            'created_at': m.created_at.isoformat() if m.created_at else None,
            'admin_reply': m.admin_reply,
            'replied_at': m.replied_at.isoformat() if m.replied_at else None,
        })

    return jsonify(result)
