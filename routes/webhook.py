import hashlib
import hmac
import json
from flask import Blueprint, request, jsonify, current_app
from models import db, Registrant
from services.scheduler import get_next_tuesday_19h
from services.token_service import generate_token
from services.notifier import notify_n8n, notify_sendflow

webhook_bp = Blueprint('webhook', __name__)


def validate_hotmart_signature(payload_body, signature):
    """Valida HMAC SHA-1 do header hottok da Hotmart."""
    secret = current_app.config['HOTMART_SECRET']
    if not secret:
        current_app.logger.warning('HOTMART_SECRET nao configurado, pulando validacao')
        return True

    expected = hmac.new(
        secret.encode('utf-8'),
        payload_body,
        hashlib.sha1
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


@webhook_bp.route('/webhook/hotmart', methods=['POST'])
def hotmart_webhook():
    """Recebe webhook da Hotmart quando alguem compra Cookie Sandwich."""
    # Valida assinatura
    hottok = request.headers.get('X-Hotmart-Hottok', '')
    if not validate_hotmart_signature(request.get_data(), hottok):
        return jsonify({'error': 'Assinatura invalida'}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Payload vazio'}), 400

    # Extrai dados do comprador
    buyer = data.get('data', {}).get('buyer', {})
    purchase = data.get('data', {}).get('purchase', {})

    name = buyer.get('name', '')
    email = buyer.get('email', '')
    phone = buyer.get('phone', '')
    transaction = purchase.get('transaction', '')

    if not transaction:
        return jsonify({'error': 'Transaction ausente'}), 400

    # Verifica duplicata
    existing = Registrant.query.filter_by(hotmart_transaction=transaction).first()
    if existing:
        return jsonify({'status': 'already_registered', 'token': existing.token}), 200

    # Calcula proxima terca 19h BRT
    webinar_date = get_next_tuesday_19h()

    # Cria registrant
    registrant = Registrant(
        name=name,
        email=email,
        phone=phone,
        hotmart_transaction=transaction,
        webinar_date=webinar_date,
    )
    db.session.add(registrant)
    db.session.flush()  # gera o ID

    # Gera token JWT
    token = generate_token(registrant.id, email)
    registrant.token = token
    db.session.commit()

    # Monta link da sala
    sala_link = f"{request.host_url}sala?token={token}"

    # Notifica n8n e SendFlow em background
    registrant_data = {
        'name': name,
        'email': email,
        'phone': phone,
        'webinar_date': webinar_date.isoformat(),
        'sala_link': sala_link,
        'transaction': transaction,
    }

    notify_n8n(registrant_data)

    if phone:
        msg = (
            f"Oi {name.split()[0] if name else ''}! "
            f"Sua vaga no webinario do Chef Aureo esta confirmada. "
            f"Acesse na terca as 19h: {sala_link}"
        )
        notify_sendflow(phone, msg)

    return jsonify({
        'status': 'registered',
        'token': token,
        'webinar_date': webinar_date.isoformat(),
        'sala_link': sala_link,
    }), 201
