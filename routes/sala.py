import json
from flask import Blueprint, request, render_template, jsonify
from models import db, Registrant, WebinarConfig, TimelineEvent
from services.token_service import validate_token
from services.scheduler import is_webinar_open, get_next_tuesday_19h, BRT
from datetime import datetime

sala_bp = Blueprint('sala', __name__)


@sala_bp.route('/sala')
def sala():
    """Pagina da sala do webinario. Valida token e horario."""
    token = request.args.get('token', '')
    if not token:
        return render_template('sala.html', error='Token nao fornecido'), 400

    payload = validate_token(token)
    if not payload:
        return render_template('sala.html', error='Token invalido ou expirado'), 401

    registrant = Registrant.query.filter_by(token=token).first()
    if not registrant:
        return render_template('sala.html', error='Registrante nao encontrado'), 404

    # Verifica se o webinario esta aberto
    if not is_webinar_open(registrant.webinar_date):
        next_date = registrant.webinar_date
        if next_date.tzinfo is None:
            from services.scheduler import BRT
            next_date = BRT.localize(next_date)
        return render_template('sala.html',
                               waiting=True,
                               webinar_date=next_date.isoformat(),
                               name=registrant.name)

    # Marca presenca
    if not registrant.attended:
        registrant.attended = True
        db.session.commit()

    # Busca config do webinario ativo
    config = WebinarConfig.query.filter_by(is_active=True).first()

    return render_template('sala.html',
                           registrant=registrant,
                           config=config,
                           error=None,
                           waiting=False)


@sala_bp.route('/api/events')
def api_events():
    """Retorna timeline_events do webinario ativo para o JS."""
    config = WebinarConfig.query.filter_by(is_active=True).first()
    if not config:
        return jsonify([])

    events = TimelineEvent.query.filter_by(webinar_id=config.id)\
        .order_by(TimelineEvent.trigger_second).all()

    result = []
    for e in events:
        result.append({
            'id': e.id,
            'trigger_second': e.trigger_second,
            'event_type': e.event_type,
            'payload': json.loads(e.payload) if e.payload else {},
        })

    return jsonify(result)


@sala_bp.route('/api/track', methods=['POST'])
def track():
    """Recebe tracking do frontend: tempo assistido, clique no CTA."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'no data'}), 400

    token = data.get('token', '')
    registrant = Registrant.query.filter_by(token=token).first()
    if not registrant:
        return jsonify({'error': 'not found'}), 404

    if 'watch_time' in data:
        registrant.watch_time_seconds = max(registrant.watch_time_seconds, int(data['watch_time']))

    if data.get('clicked_cta'):
        registrant.clicked_cta = True

    db.session.commit()
    return jsonify({'ok': True})
