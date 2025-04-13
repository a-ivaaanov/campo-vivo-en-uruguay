#!/usr/bin/env python3
"""
Модуль конфигурации приложения.
Загружает настройки из переменных окружения и .env файла.
"""

import os
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from dotenv import load_dotenv

# Определяем корневую директорию проекта
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Путь к .env файлу
ENV_PATH = PROJECT_ROOT / 'config' / '.env'

# Загружаем переменные окружения из .env файла
load_dotenv(ENV_PATH)

# Общие настройки
HEADLESS_MODE = os.getenv('HEADLESS_MODE', 'True').lower() in ('true', '1', 't', 'yes')
MAX_RETRIES = int(os.getenv('MAX_RETRIES', '3'))
REQUEST_DELAY_MIN = int(os.getenv('REQUEST_DELAY_MIN', '3'))
REQUEST_DELAY_MAX = int(os.getenv('REQUEST_DELAY_MAX', '8'))

# Настройки Telegram бота
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN') or os.getenv('BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID') or os.getenv('CHAT_ID')

# Настройки SmartProxy
SMARTPROXY_CONFIG = {
    "server": os.getenv('SMARTPROXY_SERVER', 'http://gate.smartproxy.com:10005'),
    "user_pattern": os.getenv('SMARTPROXY_USER', 'spgai22txz'),
    "password": os.getenv('SMARTPROXY_PASSWORD', 'jtx6i24Jpb~ewWaFA9')
}

# Добавление альтернативных серверов для ротации прокси
alternative_servers_str = os.getenv('ALTERNATIVE_PROXY_SERVERS', '')
if alternative_servers_str:
    SMARTPROXY_CONFIG["alternative_servers"] = [server.strip() for server in alternative_servers_str.split(',') if server.strip()]

# Настройки парсинга
MAX_PAGES_TO_PARSE = int(os.getenv('MAX_PAGES_TO_PARSE', '1'))
MAX_LISTINGS_TO_PARSE = int(os.getenv('MAX_LISTINGS_TO_PARSE', '10'))
MAX_LISTINGS_TO_SEND = int(os.getenv('MAX_LISTINGS_TO_SEND', '5'))

# Пути к файлам и директориям
DATA_DIR = PROJECT_ROOT / 'data'
LOGS_DIR = PROJECT_ROOT / 'logs'
ERRORS_DIR = PROJECT_ROOT / 'errors'
RESULTS_DIR = PROJECT_ROOT / 'results'
CACHE_DIR = PROJECT_ROOT / '.cache'

# Создаем необходимые директории
for directory in [DATA_DIR, LOGS_DIR, ERRORS_DIR, RESULTS_DIR, CACHE_DIR]:
    directory.mkdir(exist_ok=True)

# Файлы данных
SEEN_LISTINGS_FILE = DATA_DIR / 'seen_listings.json'
LISTINGS_DATA_FILE = DATA_DIR / 'listings.json'
ERROR_SCREENSHOTS_DIR = ERRORS_DIR

# Настройки логирования
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = LOGS_DIR / 'parser.log'
LOG_FORMAT = os.getenv('LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Настраиваем логирование
def setup_logging():
    """Настройка системы логирования"""
    # Уровень логирования
    log_level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    
    # Настраиваем базовое логирование
    logging.basicConfig(
        level=log_level,
        format=LOG_FORMAT,
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler()
        ]
    )

# Настройки сайтов для парсинга
SITES_CONFIG = {
    'mercadolibre': {
        'enabled': True,
        'base_url': 'https://listado.mercadolibre.com.uy/inmuebles/terrenos/venta',
        'smartproxy_config': SMARTPROXY_CONFIG
    },
    'gallito': {
        'enabled': False,
        'base_url': 'https://www.gallito.com.uy/inmuebles/terrenos/venta',
        'smartproxy_config': SMARTPROXY_CONFIG
    },
    'infocasas': {
        'enabled': False,
        'base_url': 'https://www.infocasas.com.uy/terrenos/venta',
        'smartproxy_config': SMARTPROXY_CONFIG
    }
}

# Настройки Telegram
TELEGRAM_SETTINGS = {
    'bot_token': TELEGRAM_BOT_TOKEN,
    'chat_id': TELEGRAM_CHAT_ID,
    'max_retries': MAX_RETRIES,
    'retry_delay': REQUEST_DELAY_MIN,
    'max_images_per_listing': 5,
    'cache_file': CACHE_DIR / 'sent_listings.json'
}

if __name__ == "__main__":
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Загружена конфигурация приложения")
    
    # Вывод основных настроек для отладки
    logger.debug(f"HEADLESS_MODE: {HEADLESS_MODE}")
    logger.debug(f"MAX_PAGES_TO_PARSE: {MAX_PAGES_TO_PARSE}")
    logger.debug(f"MAX_LISTINGS_TO_PARSE: {MAX_LISTINGS_TO_PARSE}")
    logger.debug(f"MAX_LISTINGS_TO_SEND: {MAX_LISTINGS_TO_SEND}")
    
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        logger.debug("Telegram settings configured")
    else:
        logger.warning("Telegram settings missing or incomplete")
    
    logger.debug(f"Smartproxy config: {SMARTPROXY_CONFIG['server']}")
    if 'alternative_servers' in SMARTPROXY_CONFIG:
        logger.debug(f"Alternative servers: {SMARTPROXY_CONFIG['alternative_servers']}") 