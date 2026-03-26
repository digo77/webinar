import requests
from flask import current_app


def notify_n8n(registrant_data):
    """Envia dados do registrant para o webhook n8n (automacao de emails)."""
    url = current_app.config['N8N_WEBHOOK_URL']
    if not url:
        current_app.logger.warning('N8N_WEBHOOK_URL nao configurada, pulando notificacao')
        return False

    try:
        resp = requests.post(url, json=registrant_data, timeout=10)
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        current_app.logger.error(f'Erro ao notificar n8n: {e}')
        return False


def notify_sendflow(phone, message):
    """Envia mensagem WhatsApp via SendFlow."""
    token = current_app.config['SENDFLOW_TOKEN']
    url = current_app.config['SENDFLOW_API_URL']
    if not token:
        current_app.logger.warning('SENDFLOW_TOKEN nao configurado, pulando WhatsApp')
        return False

    try:
        resp = requests.post(url, json={
            'phone': phone,
            'message': message,
        }, headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }, timeout=10)
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        current_app.logger.error(f'Erro ao enviar WhatsApp: {e}')
        return False
