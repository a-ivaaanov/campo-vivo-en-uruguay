#!/usr/bin/env python3
"""
Инструмент для проверки связи с Telegram и отправки тестовых сообщений.
"""

import os
import sys
import argparse
from pathlib import Path
import asyncio

# Добавляем корневую директорию проекта в sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from dotenv import load_dotenv

# Загружаем .env
dotenv_path = PROJECT_ROOT / 'config' / '.env'
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path)

# Импортируем модули для отправки сообщений
from app.telegram_poster import send_telegram_direct, post_to_telegram

def check_telegram_config():
    """Проверяет наличие настроек Telegram."""
    bot_token = os.getenv('BOT_TOKEN')
    chat_id = os.getenv('CHAT_ID')
    
    if not bot_token:
        print("❌ BOT_TOKEN не найден в .env файле")
        return False
    
    if not chat_id:
        print("❌ CHAT_ID не найден в .env файле")
        return False
    
    print(f"✅ Конфигурация Telegram найдена:")
    print(f"  - Токен бота: {bot_token[:5]}...{bot_token[-5:]}")
    print(f"  - ID чата: {chat_id}")
    
    return True

def send_test_message_sync(message="Тестовое сообщение от CampoVivoenUruguay"):
    """Отправляет тестовое сообщение синхронным методом."""
    print(f"Отправка сообщения: '{message}'")
    result = send_telegram_direct(message)
    
    if result:
        print("✅ Сообщение успешно отправлено")
    else:
        print("❌ Не удалось отправить сообщение")
    
    return result

async def send_test_message_async(message="Тестовое асинхронное сообщение от CampoVivoenUruguay"):
    """Отправляет тестовое сообщение асинхронным методом."""
    print(f"Отправка асинхронного сообщения: '{message}'")
    
    # Создаем тестовый листинг
    test_listing = {
        'title': 'Тестовый листинг',
        'description': 'Это тестовое сообщение для проверки отправки в Telegram',
        'price': 'US$ 10,000',
        'location': 'Montevideo, Uruguay',
        'area': '1000 m²',
        'url': 'https://www.ejemplo.com/test',
        'source': 'Test',
        'custom_message': message
    }
    
    result = await post_to_telegram(test_listing)
    
    if result:
        print("✅ Асинхронное сообщение успешно отправлено")
    else:
        print("❌ Не удалось отправить асинхронное сообщение")
    
    return result

async def main():
    """Основная функция."""
    parser = argparse.ArgumentParser(description='Проверка связи с Telegram')
    parser.add_argument('--message', '-m', default='Тестовое сообщение от CampoVivoenUruguay',
                       help='Текст сообщения для отправки')
    parser.add_argument('--async', '-a', action='store_true', dest='async_mode',
                       help='Использовать асинхронный метод отправки')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Подробный вывод')
    
    args = parser.parse_args()
    
    print("=== Проверка настроек Telegram ===")
    if not check_telegram_config():
        print("\nНастройка Telegram не завершена. Пожалуйста, проверьте файлы .env")
        sys.exit(1)
    
    print("\n=== Отправка тестового сообщения ===")
    if args.async_mode:
        result = await send_test_message_async(args.message)
    else:
        result = send_test_message_sync(args.message)
    
    if result:
        print("\n✅ Тест пройден успешно! Telegram настроен корректно.")
        sys.exit(0)
    else:
        print("\n❌ Тест не пройден! Проверьте настройки Telegram и сетевое соединение.")
        sys.exit(1)

if __name__ == '__main__':
    asyncio.run(main()) 