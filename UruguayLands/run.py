#!/usr/bin/env python3
"""
Скрипт для быстрого запуска парсеров UruguayLands.
"""

import asyncio
import argparse
import sys
import json
import os
from datetime import datetime
from pathlib import Path

# Решение для импорта без сложностей с модулями
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.parsers.mercadolibre import MercadoLibreParser
from app.parsers.infocasas import InfoCasasParser
from app.models import Listing

def save_listings(listings, filename=None):
    """Сохраняет объявления в JSON файл."""
    # Создаем папку для данных если её нет
    data_dir = Path(__file__).resolve().parent / 'data'
    data_dir.mkdir(exist_ok=True)
    
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"listings_{timestamp}.json"
    
    file_path = data_dir / filename
    
    # Преобразуем Pydantic модели в словари
    listings_data = [listing.dict() for listing in listings]
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(listings_data, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"Результаты сохранены в: {file_path}")
    return str(file_path)

async def run_mercadolibre_parser(max_pages=1, headless=True, with_details=False):
    """Запускает парсер MercadoLibre."""
    print(f"Запуск парсера MercadoLibre (страниц: {max_pages}, детали: {with_details})")
    
    parser = MercadoLibreParser(headless_mode=headless)
    
    try:
        if with_details:
            listings = await parser.run_with_details(max_pages=max_pages, headless=headless)
        else:
            listings = await parser.run(max_pages=max_pages, headless=headless)
            
        print(f"MercadoLibre: получено {len(listings)} объявлений")
        return listings
        
    except Exception as e:
        print(f"Ошибка при запуске парсера MercadoLibre: {e}")
        return []

async def run_infocasas_parser(max_pages=1, headless=True, with_details=False):
    """Запускает парсер InfoCasas."""
    print(f"Запуск парсера InfoCasas (страниц: {max_pages}, детали: {with_details})")
    
    parser = InfoCasasParser(headless_mode=headless)
    
    try:
        if with_details:
            listings = await parser.run_with_details(max_pages=max_pages, headless=headless)
        else:
            listings = await parser.run(max_pages=max_pages, headless=headless)
            
        print(f"InfoCasas: получено {len(listings)} объявлений")
        return listings
        
    except Exception as e:
        print(f"Ошибка при запуске парсера InfoCasas: {e}")
        return []

async def run_with_args():
    """Запускает парсеры с аргументами командной строки."""
    parser = argparse.ArgumentParser(description="Запуск парсеров UruguayLands")
    parser.add_argument("--parser", "-p", choices=["mercadolibre", "infocasas", "all"], 
                        default="all", help="Какой парсер запустить")
    parser.add_argument("--pages", "-n", type=int, default=1, 
                        help="Количество страниц для обработки")
    parser.add_argument("--details", "-d", action="store_true", 
                        help="Обрабатывать детали объявлений")
    parser.add_argument("--headless", action="store_true", 
                        help="Запустить браузер в фоновом режиме")
    
    args = parser.parse_args()
    listings = []
    
    print(f"Запуск парсера: {args.parser}")
    print(f"Количество страниц: {args.pages}")
    print(f"Обрабатывать детали: {args.details}")
    print(f"Фоновый режим: {args.headless}")
    
    if args.parser == "mercadolibre" or args.parser == "all":
        ml_listings = await run_mercadolibre_parser(
            max_pages=args.pages,
            headless=args.headless,
            with_details=args.details
        )
        print(f"MercadoLibre: найдено {len(ml_listings)} объявлений")
        listings.extend(ml_listings)
    
    if args.parser == "infocasas" or args.parser == "all":
        ic_listings = await run_infocasas_parser(
            max_pages=args.pages,
            headless=args.headless,
            with_details=args.details
        )
        print(f"InfoCasas: найдено {len(ic_listings)} объявлений")
        listings.extend(ic_listings)
    
    print(f"Всего найдено: {len(listings)} объявлений")
    
    if listings:
        save_listings(listings)
        print("Результаты сохранены в папку data/")

if __name__ == "__main__":
    try:
        asyncio.run(run_with_args())
    except KeyboardInterrupt:
        print("\nПрограмма остановлена пользователем.")
        sys.exit(0)
    except Exception as e:
        print(f"Ошибка: {e}")
        sys.exit(1) 