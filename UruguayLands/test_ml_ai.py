#!/usr/bin/env python3
"""
Тестовый скрипт для проверки оптимизированного парсера MercadoLibre с AI-селекторами.
"""

import os
import sys
import asyncio
import logging
from datetime import datetime
from pathlib import Path

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"ml_ai_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    ]
)

logger = logging.getLogger("test_ml_ai")

# Импортируем наш парсер
from app.parsers.mercadolibre import MercadoLibreParser

async def test_parser_with_ai():
    """Тестирует парсер MercadoLibre с AI-селекторами."""
    logger.info("Начинаем тестирование парсера MercadoLibre с AI-селекторами")
    
    # Создаем директории для хранения результатов и отладочной информации
    os.makedirs("test_results", exist_ok=True)
    os.makedirs("errors", exist_ok=True)
    os.makedirs("images", exist_ok=True)
    
    # Создаем экземпляр парсера
    parser = MercadoLibreParser(headless_mode=False)  # False для отображения браузера во время тестирования
    
    try:
        # Запускаем парсер с ограничением в 2 страницы
        logger.info("Извлечение объявлений со списка")
        listings = await parser.run(max_pages=2)
        
        if listings:
            logger.info(f"Найдено {len(listings)} объявлений на страницах списка")
            
            # Сохраняем результаты
            with open(f"test_results/ml_listings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt", "w", encoding="utf-8") as f:
                for i, listing in enumerate(listings):
                    f.write(f"Объявление {i+1}:\n")
                    f.write(f"  URL: {listing.url}\n")
                    f.write(f"  Заголовок: {listing.title}\n")
                    f.write(f"  Цена: {listing.price}\n")
                    f.write(f"  Расположение: {listing.location}\n")
                    f.write(f"  Площадь: {listing.area}\n")
                    f.write(f"  Изображение: {listing.image_url}\n")
                    f.write("\n")
            
            # Тестируем извлечение деталей для первых 3 объявлений
            logger.info("Тестирование извлечения деталей для первых 3 объявлений")
            for i, listing in enumerate(listings[:3]):
                logger.info(f"Извлечение деталей для объявления {i+1}: {listing.url}")
                
                try:
                    updated_listing = await parser.run_with_details(listings=[listing])
                    if updated_listing and updated_listing[0]:
                        logger.info(f"Детали успешно обновлены для {listing.url}")
                        
                        # Сохраняем детальную информацию
                        with open(f"test_results/ml_listing_details_{i+1}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt", "w", encoding="utf-8") as f:
                            listing = updated_listing[0]
                            f.write(f"URL: {listing.url}\n")
                            f.write(f"Заголовок: {listing.title}\n")
                            f.write(f"Цена: {listing.price}\n")
                            f.write(f"Расположение: {listing.location}\n")
                            f.write(f"Площадь: {listing.area}\n")
                            f.write(f"Описание: {listing.description}\n")
                            f.write(f"Изображение: {listing.image_url}\n")
                            f.write(f"Коммуникации: {listing.utilities}\n")
                            f.write(f"Тип сделки: {listing.deal_type}\n")
                            
                            if listing.attributes:
                                f.write("\nДополнительные характеристики:\n")
                                for key, value in listing.attributes.items():
                                    f.write(f"  {key}: {value}\n")
                    else:
                        logger.warning(f"Не удалось обновить детали для {listing.url}")
                except Exception as e:
                    logger.error(f"Ошибка при извлечении деталей для {listing.url}: {e}")
        else:
            logger.warning("Не найдено ни одного объявления!")
    
    except Exception as e:
        logger.error(f"Ошибка при тестировании парсера: {e}")
    
    finally:
        # Закрываем ресурсы
        await parser.close()
        logger.info("Тестирование завершено")

if __name__ == "__main__":
    asyncio.run(test_parser_with_ai()) 