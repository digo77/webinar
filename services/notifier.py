import requests
from datetime import datetime
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


def notify_session_report(webinar_id):
    """Envia relatório pós-sessão para o n8n."""
    url = current_app.config.get('N8N_WEBHOOK_URL')
    if not url:
        return False
    from models import Registrant, UserChatMessage, WebinarConfig
    webinar = WebinarConfig.query.get(webinar_id)
    if not webinar:
        return False
    regs = Registrant.query.filter_by(webinar_id=webinar_id).all()
    total = len(regs)
    attended = sum(1 for r in regs if r.attended)
    cta = sum(1 for r in regs if r.clicked_cta)
    watch_times = [r.watch_time_seconds for r in regs if r.attended and r.watch_time_seconds]
    avg_watch = round(sum(watch_times) / len(watch_times) / 60, 1) if watch_times else 0
    chats_total = UserChatMessage.query.filter_by(webinar_id=webinar_id).count()
    chats_approved = UserChatMessage.query.filter_by(webinar_id=webinar_id, status='approved').count()
    chats_replied = UserChatMessage.query.filter(
        UserChatMessage.webinar_id == webinar_id,
        UserChatMessage.status == 'approved',
        UserChatMessage.admin_reply.isnot(None)
    ).count()
    payload = {
        'webinar_name': webinar.name,
        'webinar_id': webinar_id,
        'session_at': datetime.utcnow().isoformat(),
        'total_registrants': total,
        'attended': attended,
        'attendance_rate': round(attended / total * 100, 1) if total else 0,
        'avg_watch_minutes': avg_watch,
        'clicked_cta': cta,
        'cta_rate': round(cta / total * 100, 1) if total else 0,
        'comments_total': chats_total,
        'comments_approved': chats_approved,
        'comments_replied': chats_replied,
    }
    try:
        resp = requests.post(url, json={'type': 'session_report', 'data': payload}, timeout=10)
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        current_app.logger.error(f'Erro ao enviar relatório: {e}')
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
