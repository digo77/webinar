import jwt
from datetime import datetime, timedelta
from flask import current_app


def generate_token(registrant_id, email):
    """Gera JWT com expiracao de 30 dias."""
    payload = {
        'sub': registrant_id,
        'email': email,
        'exp': datetime.utcnow() + timedelta(days=current_app.config['JWT_EXPIRATION_DAYS']),
        'iat': datetime.utcnow(),
    }
    return jwt.encode(payload, current_app.config['JWT_SECRET'], algorithm='HS256')


def validate_token(token):
    """Valida JWT e retorna payload ou None."""
    try:
        payload = jwt.decode(token, current_app.config['JWT_SECRET'], algorithms=['HS256'])
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None
