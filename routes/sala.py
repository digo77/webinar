import json
from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for
from models import Registrant, TimelineEvent, WebinarConfig, db
from services.scheduler import BRT, is_webinar_open

sala_bp = Blueprint('sala', __name__)


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

    if 'watch_time' in data:
        registrant.watch_time_seconds = max(
            registrant.watch_time_seconds or 0,
            int(data['watch_time'])
        )

    if data.get('clicked_cta'):
        registrant.clicked_cta = True

    db.session.commit()
    return jsonify({'ok': True})
