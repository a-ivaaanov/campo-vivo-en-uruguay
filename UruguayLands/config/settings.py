"""
Конфигурация для Telegram и других сервисов.
"""

import os
from dotenv import load_dotenv
from pathlib import Path

# Базовый путь к проекту
BASE_DIR = Path(__file__).resolve().parent.parent

# Загрузка переменных окружения
env_path = BASE_DIR / 'config' / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

# Настройки Telegram
TELEGRAM_SETTINGS = {
    'token': os.getenv('TELEGRAM_BOT_TOKEN', ''),
    'channel_id': os.getenv('TELEGRAM_CHANNEL_ID', ''),
    'admin_id': os.getenv('TELEGRAM_ADMIN_ID', ''),
    'notification_id': os.getenv('TELEGRAM_NOTIFICATION_ID', ''),
    'debug': os.getenv('TELEGRAM_DEBUG', 'false').lower() == 'true',
    'delay_seconds': int(os.getenv('TELEGRAM_DELAY_SECONDS', '10')),
    'image_width': int(os.getenv('TELEGRAM_IMAGE_WIDTH', '800')),
}

# Настройки для прокси
PROXY_SETTINGS = {
    'use_proxy': os.getenv('USE_PROXY', 'false').lower() == 'true',
    'proxy_url': os.getenv('PROXY_URL', ''),
    'proxy_user': os.getenv('PROXY_USER', ''),
    'proxy_password': os.getenv('PROXY_PASSWORD', ''),
}

# Другие настройки
DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO') 