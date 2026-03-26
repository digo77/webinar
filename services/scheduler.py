from datetime import datetime, timedelta
import pytz

BRT = pytz.timezone('America/Sao_Paulo')


def get_next_tuesday_19h(from_dt=None):
    """Calcula a proxima terca-feira as 19h BRT a partir de uma data."""
    if from_dt is None:
        from_dt = datetime.now(BRT)
    elif from_dt.tzinfo is None:
        from_dt = BRT.localize(from_dt)

    # Dia da semana: 0=segunda, 1=terca
    days_ahead = 1 - from_dt.weekday()  # 1 = terca
    if days_ahead <= 0:
        # Se ja passou terca (ou e terca mas ja passou 19h), pula pra proxima
        if days_ahead < 0 or (days_ahead == 0 and from_dt.hour >= 19):
            days_ahead += 7

    next_tuesday = from_dt + timedelta(days=days_ahead)
    next_tuesday_19h = next_tuesday.replace(hour=19, minute=0, second=0, microsecond=0)

    return next_tuesday_19h


def is_webinar_open(webinar_date):
    """Verifica se o horario atual esta na janela do webinario.

    Janela: 15 min antes das 19h ate meia-noite do mesmo dia.
    """
    now = datetime.now(BRT)

    if webinar_date.tzinfo is None:
        webinar_date = BRT.localize(webinar_date)

    window_start = webinar_date - timedelta(minutes=15)
    window_end = webinar_date.replace(hour=23, minute=59, second=59)

    return window_start <= now <= window_end
