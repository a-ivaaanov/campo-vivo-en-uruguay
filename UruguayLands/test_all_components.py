#!/usr/bin/env python3
"""
Скрипт для тестирования всех компонентов системы.
"""

import os
import sys
import asyncio
import logging
import argparse
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"test_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    ]
)

logger = logging.getLogger("test_all")

# Импортируем компоненты системы
from app.parsers.mercadolibre import MercadoLibreParser
from app.parsers.infocasas import InfoCasasParser
from app.telegram_sender import send_listings_to_telegram, TelegramSender

async def test_mercadolibre_parser(headless=False, max_pages=1):
    """
    Тестирует парсер MercadoLibre.
    
    Args:
        headless: Запускать браузер в фоновом режиме
        max_pages: Максимальное количество страниц для обработки
    
    Returns:
        List[Listing]: Список объявлений
    """
    logger.info(f"Тестирование парсера MercadoLibre (страниц: {max_pages}, headless: {headless})")
    
    try:
        parser = MercadoLibreParser(headless_mode=headless)
        
        # Тестируем получение списка объявлений
        listings = await parser.run(max_pages=max_pages, headless=headless)
        logger.info(f"MercadoLibre: получено {len(listings)} объявлений со страниц списка")
        
        # Берем первые 2 объявления для тестирования получения деталей
        if listings and len(listings) > 0:
            test_listings = listings[:2]
            logger.info(f"Тестирование извлечения деталей для {len(test_listings)} объявлений")
            
            detailed_listings = await parser.run_with_details(listings=test_listings, headless=headless)
            logger.info(f"MercadoLibre: получены детали для {len(detailed_listings)} объявлений")
            
            # Сохраняем детальную информацию для проверки
            save_test_results("mercadolibre", detailed_listings)
            
            return detailed_listings
        else:
            logger.warning("MercadoLibre: не найдено объявлений для тестирования")
            return []
    
    except Exception as e:
        logger.error(f"Ошибка при тестировании парсера MercadoLibre: {e}")
        return []
    finally:
        await parser.close()

async def test_telegram_sender(listings):
    """
    Тестирует отправку объявлений в Telegram.
    
    Args:
        listings: Список объявлений для отправки
    
    Returns:
        bool: True, если тестирование прошло успешно
    """
    if not listings:
        logger.warning("Нет объявлений для тестирования отправки в Telegram")
        return False
    
    logger.info(f"Тестирование отправки в Telegram ({len(listings)} объявлений)")
    
    # Проверяем наличие переменных окружения
    if not os.getenv("TELEGRAM_BOT_TOKEN") or not os.getenv("TELEGRAM_CHAT_ID"):
        logger.error("Не настроены переменные окружения для Telegram. Тестирование невозможно.")
        return False
    
    try:
        # Создаем тестовое объявление с маркировкой для различения от реальных
        test_listing = listings[0]
        test_listing.title = f"[ТЕСТ] {test_listing.title}"
        
        # Создаем отправщика Telegram
        sender = TelegramSender()
        
        # Отправляем тестовое объявление
        success = await sender.send_listing(test_listing)
        
        if success:
            logger.info("Тестовое объявление успешно отправлено в Telegram")
            return True
        else:
            logger.error("Не удалось отправить тестовое объявление в Telegram")
            return False
    
    except Exception as e:
        logger.error(f"Ошибка при тестировании отправки в Telegram: {e}")
        return False

def save_test_results(source, listings):
    """
    Сохраняет результаты тестирования в файл.
    
    Args:
        source: Название источника (mercadolibre, infocasas)
        listings: Список объявлений
    """
    if not listings:
        logger.warning(f"Нет объявлений для сохранения результатов тестирования {source}")
        return
    
    # Создаем директорию для тестовых результатов
    os.makedirs("test_results", exist_ok=True)
    
    filename = f"test_results/{source}_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    try:
        with open(filename, "w", encoding="utf-8") as f:
            for i, listing in enumerate(listings):
                f.write(f"Объявление {i+1}:\n")
                f.write(f"  URL: {listing.url}\n")
                f.write(f"  Заголовок: {listing.title}\n")
                f.write(f"  Цена: {listing.price}\n")
                f.write(f"  Расположение: {listing.location}\n")
                f.write(f"  Площадь: {listing.area}\n")
                
                if listing.description:
                    f.write(f"  Описание: {listing.description[:200]}...\n")
                
                if listing.image_url:
                    f.write(f"  Изображение: {listing.image_url}\n")
                
                if listing.utilities:
                    f.write(f"  Коммуникации: {listing.utilities}\n")
                
                # Проверяем, есть ли дополнительные характеристики
                if hasattr(listing, 'attributes') and listing.attributes:
                    f.write("  Дополнительные характеристики:\n")
                    for key, value in listing.attributes.items():
                        f.write(f"    {key}: {value}\n")
                
                # Проверяем, является ли объявление новым
                is_recent = False
                if hasattr(listing, 'attributes') and listing.attributes:
                    is_recent = listing.attributes.get('is_recent', False)
                f.write(f"  Новое: {'Да' if is_recent else 'Нет'}\n")
                
                f.write("\n")
        
        logger.info(f"Результаты тестирования {source} сохранены в {filename}")
    
    except Exception as e:
        logger.error(f"Ошибка при сохранении результатов тестирования {source}: {e}")

async def main():
    """Основная функция тестирования всех компонентов."""
    parser = argparse.ArgumentParser(description="Тестирование всех компонентов системы")
    parser.add_argument("--headless", action="store_true", 
                        help="Запускать браузер в фоновом режиме")
    parser.add_argument("--no-telegram", action="store_true", 
                        help="Не тестировать отправку в Telegram")
    
    args = parser.parse_args()
    
    # Определяем режим запуска браузера
    headless = args.headless
    
    logger.info(f"Начало тестирования всех компонентов (headless: {headless})")
    
    # Шаг 1: Тестирование парсера MercadoLibre
    listings = await test_mercadolibre_parser(headless=headless)
    
    # Шаг 2: Тестирование отправки в Telegram
    if not args.no_telegram and listings:
        await test_telegram_sender(listings)
    
    logger.info("Тестирование завершено.")

if __name__ == "__main__":
    asyncio.run(main()) 