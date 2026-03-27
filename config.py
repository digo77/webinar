import os


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-me-in-production')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///autowebinar.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Hotmart webhook secret (hottok HMAC validation)
    HOTMART_SECRET = os.environ.get('HOTMART_SECRET', '')

    # n8n webhook URL for email automation
    N8N_WEBHOOK_URL = os.environ.get('N8N_WEBHOOK_URL', '')

    # SendFlow API for WhatsApp notifications
    SENDFLOW_TOKEN = os.environ.get('SENDFLOW_TOKEN', '')
    SENDFLOW_API_URL = os.environ.get('SENDFLOW_API_URL', 'https://backend.sendflow.pro/api/v1/messages/send')

    # JWT secret (can be same as SECRET_KEY or separate)
    JWT_SECRET = os.environ.get('JWT_SECRET', SECRET_KEY)
    JWT_EXPIRATION_DAYS = 30

    # Admin password
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

    # AI APIs
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
