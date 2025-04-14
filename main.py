#!/usr/bin/env python3
"""
Главный скрипт для запуска парсеров объявлений для UruguayLands на Replit.
"""

import os
import sys
import json
import logging
import asyncio
from datetime import datetime
from pathlib import Path
import traceback

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger()

# Глобальные переменные
published_urls = []

# Функция для загрузки ранее опубликованных URL
def load_published_urls():
    """Загружает ранее опубликованные URL из файла."""
    try:
        with open("published_urls.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.info("Файл с опубликованными URL не найден. Создаем новый.")
        return []
    except Exception as e:
        logger.error(f"Ошибка при загрузке опубликованных URL: {e}")
        return []

# Функция для сохранения опубликованных URL
def save_published_urls():
    """Сохраняет опубликованные URL в файл."""
    try:
        with open("published_urls.json", "w") as f:
            json.dump(published_urls, f)
        logger.info(f"Сохранено {len(published_urls)} ранее опубликованных URL")
    except Exception as e:
        logger.error(f"Ошибка при сохранении опубликованных URL: {e}")

# Функция-обертка для парсера InfoCasas
async def parse_infocasas(max_pages=2):
    """
    Обертка для класса InfoCasasParser.
    Парсит объявления с сайта InfoCasas.
    
    Args:
        max_pages: Максимальное количество страниц для парсинга
        
    Returns:
        list: Список объявлений
    """
    try:
        # Импортируем только при вызове, чтобы не загружать все зависимости сразу
        from app.parsers.infocasas import InfoCasasParser
        
        logger.info(f"Запуск парсера InfoCasas (страниц: {max_pages})")
        
        # Создаем экземпляр парсера
        parser = InfoCasasParser()
        
        # Запускаем парсинг
        result = await parser.run(max_pages=max_pages, headless=True)
        
        logger.info(f"Парсер InfoCasas завершил работу. Найдено {len(result)} объявлений")
        return result
    except ImportError as e:
        logger.error(f"Ошибка импорта: {e}. Убедитесь, что модуль InfoCasasParser доступен.")
        return []
    except Exception as e:
        logger.error(f"Ошибка в парсере InfoCasas: {e}")
        return []

# Функция-обертка для парсера MercadoLibre
async def parse_mercadolibre(max_pages=2):
    """
    Обертка для класса MercadoLibreParser.
    Парсит объявления с сайта MercadoLibre.
    
    Args:
        max_pages: Максимальное количество страниц для парсинга
        
    Returns:
        list: Список объявлений
    """
    try:
        # Импортируем только при вызове
        from app.parsers.mercadolibre import MercadoLibreParser
        
        logger.info(f"Запуск парсера MercadoLibre (страниц: {max_pages})")
        
        # Создаем экземпляр парсера
        parser = MercadoLibreParser()
        
        # Запускаем парсинг
        result = await parser.run(max_pages=max_pages, headless=True)
        
        logger.info(f"Парсер MercadoLibre завершил работу. Найдено {len(result)} объявлений")
        return result
    except ImportError as e:
        logger.error(f"Ошибка импорта: {e}. Убедитесь, что модуль MercadoLibreParser доступен.")
        return []
    except Exception as e:
        logger.error(f"Ошибка в парсере MercadoLibre: {e}")
        return []

# Обработка результатов парсинга
async def process_results(listings):
    """Обрабатывает результаты парсинга и отправляет в Telegram."""
    if not listings:
        logger.info("Нет новых объявлений для обработки.")
        return 0
    
    # Фильтруем только новые объявления
    new_listings = [listing for listing in listings if str(listing.url) not in published_urls]
    logger.info(f"Найдено {len(new_listings)} новых объявлений из {len(listings)} общих.")
    
    if not new_listings:
        logger.info("Все найденные объявления уже были опубликованы.")
        return 0
    
    # Инициализируем отправку в Telegram
    sent_count = 0
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if telegram_bot_token and telegram_chat_id:
        try:
            # Импортируем TelegramSender
            from app.telegram_sender import TelegramSender
            
            # Создаем экземпляр отправителя
            sender = TelegramSender(
                bot_token=telegram_bot_token,
                chat_id=telegram_chat_id
            )
            
            # Отправляем объявления
            logger.info(f"Отправка {len(new_listings)} новых объявлений в Telegram...")
            sent_count, skipped_count = await sender.send_listings(new_listings, delay=3.0)
            
            logger.info(f"Отправлено {sent_count} объявлений в Telegram, пропущено {skipped_count}")
        except Exception as e:
            logger.error(f"Ошибка при отправке объявлений в Telegram: {e}")
            logger.debug(f"Полная ошибка: {traceback.format_exc()}")
    else:
        logger.warning("Не указаны TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID в переменных окружения")
        logger.info("Отправка в Telegram пропущена")
    
    # Добавляем все URL в список опубликованных
    for listing in new_listings:
        published_urls.append(str(listing.url))
    
    # Сохраняем обновленный список опубликованных URL
    save_published_urls()
    
    return len(new_listings)

# Основная функция
async def main():
    """Основная функция приложения."""
    try:
        # Загружаем опубликованные URL
        global published_urls
        published_urls = load_published_urls()
        
        logger.info("Загружено %d ранее опубликованных URL", len(published_urls))
        
        # Запускаем парсеры
        ml_results = await parse_mercadolibre(max_pages=1)
        ic_results = await parse_infocasas(max_pages=1)
        
        # Объединяем результаты
        all_results = ml_results + ic_results
        logger.info(f"Всего найдено {len(all_results)} объявлений (MercadoLibre: {len(ml_results)}, InfoCasas: {len(ic_results)})")
        
        # Обрабатываем результаты
        new_count = await process_results(all_results)
        
        logger.info(f"Обработано {new_count} новых объявлений")
        
        # Ожидание 60 минут до следующего цикла
        logger.info("Ожидание 60 минут до следующего цикла...")
    except Exception as e:
        logger.error(f"Ошибка в цикле выполнения: {e}")
        logger.info("Ожидание 60 минут до следующего цикла...")

# Точка входа
if __name__ == "__main__":
    try:
        # Запуск основной функции
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Выполнение прервано пользователем")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        sys.exit(1)
