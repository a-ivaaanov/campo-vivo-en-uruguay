#!/usr/bin/env python3
"""
Основной модуль для парсинга и отправки объявлений о земельных участках в Уругвае.
"""

import os
import sys
import json
import asyncio
import logging
import argparse
from datetime import datetime
from typing import List, Dict, Any, Optional

# Добавляем директорию проекта в путь для импорта
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Импортируем необходимые модули
from app.models import Listing
from app.parsers.mercadolibre import MercadoLibreParser
from app.telegram_sender import TelegramSender, send_listings_to_telegram
from app.utils.duplicate_checker import DuplicateChecker
from app.utils.proxy_manager import ProxyManager
from app.utils.analytics import ListingAnalytics
from app.config import setup_logging, load_config

# Конфигурируем логирование
setup_logging()
logger = logging.getLogger(__name__)

async def main():
    """
    Основная функция для запуска процесса парсинга и отправки объявлений.
    """
    # Парсинг аргументов командной строки
    parser = argparse.ArgumentParser(description="Парсер земельных участков в Уругвае")
    parser.add_argument("--no-send", action="store_true", help="Не отправлять объявления в Telegram")
    parser.add_argument("--max-pages", type=int, default=3, help="Максимальное количество страниц для парсинга")
    parser.add_argument("--debug", action="store_true", help="Режим отладки")
    parser.add_argument("--headless", action="store_true", help="Запускать браузер в фоновом режиме")
    args = parser.parse_args()
    
    # Загружаем конфигурацию
    config = load_config()
    
    # Создаем директории для результатов
    os.makedirs("data", exist_ok=True)
    os.makedirs("data/analytics", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    os.makedirs("logs/screenshots", exist_ok=True)
    
    # Устанавливаем режим логирования
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Включен режим отладки")
    
    try:
        # Инициализируем менеджер прокси
        proxy_manager = ProxyManager(config_file="config/proxies.json")
        
        # Проверяем состояние прокси
        logger.info("Проверка доступных прокси...")
        proxy_results = await proxy_manager.verify_all_proxies()
        
        working_proxies = sum(1 for status in proxy_results.values() if status)
        logger.info(f"Доступно {working_proxies} из {len(proxy_results)} прокси")
        
        # Получаем оптимальный прокси для использования
        proxy = proxy_manager.get_proxy()
        
        if not proxy:
            logger.warning("Нет доступных прокси, запуск без прокси")
        
        # Инициализируем парсер
        logger.info("Инициализация парсера MercadoLibre")
        ml_parser = MercadoLibreParser(
            headless_mode=args.headless, 
            proxy=proxy,
            min_request_delay=2.0,
            max_request_delay=5.0
        )
        
        # Запускаем парсер
        logger.info(f"Запуск парсера (макс. страниц: {args.max_pages})")
        listings = await ml_parser.run(max_pages=args.max_pages, headless=args.headless)
        
        if not listings:
            logger.error("Не найдено объявлений при парсинге")
            return 1
        
        logger.info(f"Найдено {len(listings)} объявлений")
        
        # Сохраняем сырые результаты
        os.makedirs("data/raw", exist_ok=True)
        with open(f"data/raw/listings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", "w", encoding="utf-8") as f:
            json.dump([listing.to_dict() for listing in listings], f, ensure_ascii=False, indent=2)
        
        # Получаем дополнительные детали для объявлений
        logger.info("Получение детальной информации для объявлений")
        detailed_listings = await ml_parser.run_with_details(listings=listings, headless=args.headless)
        
        if not detailed_listings:
            logger.error("Не удалось получить детальную информацию для объявлений")
            return 1
        
        logger.info(f"Получена детальная информация для {len(detailed_listings)} объявлений")
        
        # Сохраняем детальные результаты
        with open(f"data/raw/detailed_listings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", "w", encoding="utf-8") as f:
            json.dump([listing.to_dict() for listing in detailed_listings], f, ensure_ascii=False, indent=2)
        
        # Проверяем и фильтруем дубликаты
        logger.info("Проверка на дубликаты")
        duplicate_checker = DuplicateChecker()
        unique_listings = duplicate_checker.filter_duplicates(detailed_listings)
        
        logger.info(f"После фильтрации дубликатов осталось {len(unique_listings)} объявлений")
        
        # Анализируем данные
        logger.info("Обновление статистики")
        analytics = ListingAnalytics()
        analytics.add_listings(unique_listings)
        analytics.process_batch(save=True)
        
        # Если указан флаг --no-send, не отправляем объявления
        if args.no_send:
            logger.info("Отправка в Telegram отключена")
            return 0
        
        # Проверяем наличие настроек Telegram
        if not config.get("TELEGRAM_BOT_TOKEN") or not config.get("TELEGRAM_CHAT_ID"):
            logger.error("Не указаны токен бота или ID чата Telegram. Отправка невозможна.")
            return 1
        
        # Отправляем объявления в Telegram
        logger.info("Отправка объявлений в Telegram")
        
        # Инициализируем отправитель Telegram
        telegram_sender = TelegramSender(
            token=config["TELEGRAM_BOT_TOKEN"],
            chat_id=config["TELEGRAM_CHAT_ID"]
        )
        
        # Отправляем объявления
        sent_count = 0
        for i, listing in enumerate(unique_listings):
            logger.info(f"Отправка объявления {i+1}/{len(unique_listings)}: {listing.title}")
            
            try:
                sent = await telegram_sender.send_listing(listing)
                if sent:
                    logger.info(f"Объявление успешно отправлено: {listing.title}")
                    sent_count += 1
                else:
                    logger.error(f"Не удалось отправить объявление: {listing.title}")
                
                # Делаем паузу между отправками, чтобы не превысить лимиты API
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Ошибка при отправке объявления {listing.title}: {e}")
        
        logger.info(f"Отправлено {sent_count} из {len(unique_listings)} объявлений")
        
        # Закрываем парсер и освобождаем ресурсы
        await ml_parser.close()
        
        return 0
    
    except Exception as e:
        logger.error(f"Критическая ошибка при выполнении: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    # Запускаем основную функцию
    exit_code = asyncio.run(main())
    
    # Выход с кодом, отражающим успешность выполнения
    sys.exit(exit_code) 