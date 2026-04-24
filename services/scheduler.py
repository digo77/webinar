from datetime import datetime, timedelta
import pytz

BRT = pytz.timezone('America/Sao_Paulo')

DAY_NAMES = ['Segunda', 'Terca', 'Quarta', 'Quinta', 'Sexta', 'Sabado', 'Domingo']


def get_next_webinar_date(day_of_week=1, start_hour=19, start_minute=0, from_dt=None):
    """Calcula a proxima data do webinario baseado no dia da semana e horario.

    Args:
        day_of_week: 0=segunda, 1=terca, ..., 6=domingo
        start_hour: hora de inicio (0-23)
        start_minute: minuto de inicio (0-59)
        from_dt: datetime de referencia (default: agora BRT)
    """
    if from_dt is None:
        from_dt = datetime.now(BRT)
    elif from_dt.tzinfo is None:
        from_dt = BRT.localize(from_dt)

    days_ahead = day_of_week - from_dt.weekday()
    if days_ahead < 0:
        days_ahead += 7
    elif days_ahead == 0:
        # Mesmo dia: se ja passou o horario, pula pra proxima semana
        start_time = from_dt.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
        if from_dt >= start_time:
            days_ahead += 7

    next_date = from_dt + timedelta(days=days_ahead)
    next_date = next_date.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)

    return next_date


def get_active_session_date(day_of_week=1, start_hour=19, start_minute=0):
    """Retorna a sessão atual se estiver dentro de 30 min após o início, senão a próxima."""
    now = datetime.now(BRT)
    days_back = (now.weekday() - day_of_week) % 7
    prev_date = (now - timedelta(days=days_back)).replace(
        hour=start_hour, minute=start_minute, second=0, microsecond=0
    )
    if prev_date > now:
        prev_date -= timedelta(days=7)
    elapsed = (now - prev_date).total_seconds()
    if 0 <= elapsed <= 30 * 60:
        return prev_date
    return get_next_webinar_date(day_of_week, start_hour, start_minute)


# Alias retrocompativel
def get_next_tuesday_19h(from_dt=None):
    return get_next_webinar_date(day_of_week=1, start_hour=19, start_minute=0, from_dt=from_dt)


def is_webinar_open(webinar_date):
    """Verifica se o horario atual esta na janela do webinario.

    Janela: 15 min antes do horario ate meia-noite do mesmo dia.
    """
    now = datetime.now(BRT)

    if webinar_date.tzinfo is None:
        webinar_date = BRT.localize(webinar_date)

    window_start = webinar_date - timedelta(minutes=15)
    window_end = webinar_date.replace(hour=23, minute=59, second=59)

    return window_start <= now <= window_end
