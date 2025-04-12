#!/usr/bin/env python3
"""
Модуль для проверки и фильтрации дубликатов объявлений.
"""

import os
import json
import logging
import hashlib
from typing import List, Dict, Any, Optional, Set, Tuple
from datetime import datetime, timedelta
from app.models import Listing

logger = logging.getLogger(__name__)

class DuplicateChecker:
    """
    Класс для проверки и фильтрации дубликатов объявлений.
    Использует несколько стратегий для определения дубликатов:
    1. По URL (точное совпадение)
    2. По хешу содержимого (совпадение основных полей)
    3. По адресу и цене (для объявлений с разных источников)
    """
    
    def __init__(self, cache_file: str = "data/listings_cache.json", max_age_days: int = 30):
        """
        Инициализирует проверку дубликатов.
        
        Args:
            cache_file: Путь к файлу кэша для хранения обработанных объявлений
            max_age_days: Максимальный возраст записей в кэше (в днях)
        """
        self.cache_file = cache_file
        self.max_age_days = max_age_days
        self.cache = self._load_cache()
        self.urls_seen = set(item.get('url', '') for item in self.cache)
        self.content_hashes = set(item.get('content_hash', '') for item in self.cache)
        
        # Очистка устаревших записей при инициализации
        self._cleanup_old_listings()
    
    def _load_cache(self) -> List[Dict[str, Any]]:
        """Загружает кэш обработанных объявлений из файла."""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return []
        except Exception as e:
            logger.error(f"Ошибка при загрузке кэша дубликатов: {e}")
            return []
    
    def _save_cache(self):
        """Сохраняет кэш обработанных объявлений в файл."""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка при сохранении кэша дубликатов: {e}")
    
    def _cleanup_old_listings(self):
        """Удаляет устаревшие записи из кэша."""
        if not self.cache:
            return
            
        current_time = datetime.now()
        cutoff_time = current_time - timedelta(days=self.max_age_days)
        cutoff_str = cutoff_time.isoformat()
        
        # Фильтруем кэш, оставляя только актуальные записи
        new_cache = []
        for item in self.cache:
            date_str = item.get('timestamp', '')
            try:
                if date_str and datetime.fromisoformat(date_str) >= cutoff_time:
                    new_cache.append(item)
            except (ValueError, TypeError):
                # Если не удалось разобрать дату, оставляем запись
                new_cache.append(item)
        
        # Обновляем кэш и множества для быстрой проверки
        self.cache = new_cache
        self.urls_seen = set(item.get('url', '') for item in self.cache)
        self.content_hashes = set(item.get('content_hash', '') for item in self.cache)
        
        # Сохраняем обновленный кэш
        self._save_cache()
        
        removed_count = len(self.cache) - len(new_cache)
        if removed_count > 0:
            logger.info(f"Удалено {removed_count} устаревших записей из кэша дубликатов")
    
    def _generate_content_hash(self, listing: Listing) -> str:
        """
        Генерирует хеш содержимого объявления на основе ключевых полей.
        
        Args:
            listing: Объект объявления
            
        Returns:
            str: Хеш содержимого
        """
        # Создаем строку из ключевых полей
        content_string = (
            f"{listing.title}{listing.price}{listing.location}"
            f"{listing.area}{listing.description}"
        )
        # Нормализуем строку
        content_string = content_string.lower().strip()
        # Создаем хеш
        return hashlib.md5(content_string.encode('utf-8')).hexdigest()
    
    def _is_address_price_duplicate(self, listing: Listing) -> bool:
        """
        Проверяет, является ли объявление дубликатом по адресу и цене.
        
        Args:
            listing: Объект объявления
            
        Returns:
            bool: True, если найден дубликат
        """
        if not listing.location or not listing.price:
            return False
            
        price = listing.price.lower().strip() if listing.price else ""
        location = listing.location.lower().strip() if listing.location else ""
        area = listing.area.lower().strip() if listing.area else ""
        
        # Если нет цены или адреса, не считаем дубликатом
        if not price or not location:
            return False
        
        # Проверяем кэш на наличие объявлений с теми же адресом и ценой
        for item in self.cache:
            item_price = item.get('price', '').lower().strip()
            item_location = item.get('location', '').lower().strip()
            item_area = item.get('area', '').lower().strip()
            
            # Считаем дубликатом, если совпадают цена и адрес (с небольшой погрешностью)
            if price == item_price and self._similar_strings(location, item_location, threshold=0.8):
                # Дополнительно проверяем площадь, если она указана
                if not area or not item_area or self._similar_strings(area, item_area, threshold=0.8):
                    logger.debug(f"Найден дубликат по адресу и цене: {listing.url}")
                    return True
        
        return False
    
    def _similar_strings(self, str1: str, str2: str, threshold: float = 0.8) -> bool:
        """
        Проверяет сходство двух строк.
        
        Args:
            str1: Первая строка
            str2: Вторая строка
            threshold: Порог сходства (0.0 - 1.0)
            
        Returns:
            bool: True, если строки похожи
        """
        # Простая проверка на включение одной строки в другую
        if str1 in str2 or str2 in str1:
            return True
        
        # Если строки короткие, требуем более высокого сходства
        if len(str1) < 10 or len(str2) < 10:
            threshold = 0.9
        
        # Упрощенный расчет сходства
        words1 = set(str1.lower().split())
        words2 = set(str2.lower().split())
        
        if not words1 or not words2:
            return False
            
        common_words = words1.intersection(words2)
        similarity = len(common_words) / max(len(words1), len(words2))
        
        return similarity >= threshold
    
    def is_duplicate(self, listing: Listing) -> bool:
        """
        Проверяет, является ли объявление дубликатом.
        
        Args:
            listing: Объект объявления
            
        Returns:
            bool: True, если объявление является дубликатом
        """
        # Проверка по URL
        if listing.url in self.urls_seen:
            logger.debug(f"Найден дубликат по URL: {listing.url}")
            return True
        
        # Проверка по хешу содержимого
        content_hash = self._generate_content_hash(listing)
        if content_hash in self.content_hashes:
            logger.debug(f"Найден дубликат по хешу содержимого: {listing.url}")
            return True
        
        # Проверка по адресу и цене
        if self._is_address_price_duplicate(listing):
            return True
        
        return False
    
    def add_to_cache(self, listing: Listing):
        """
        Добавляет объявление в кэш дубликатов.
        
        Args:
            listing: Объект объявления
        """
        content_hash = self._generate_content_hash(listing)
        
        # Объявление могло существовать ранее, но другом сайте
        cache_item = {
            'url': str(listing.url),
            'title': listing.title,
            'price': listing.price,
            'location': listing.location,
            'area': listing.area,
            'timestamp': datetime.now().isoformat(),
            'content_hash': content_hash,
            'source': listing.source
        }
        
        # Добавляем в множества для быстрой проверки
        self.urls_seen.add(str(listing.url))
        self.content_hashes.add(content_hash)
        
        # Добавляем в кэш
        self.cache.append(cache_item)
        
        # Сохраняем кэш
        self._save_cache()
    
    def filter_duplicates(self, listings: List[Listing]) -> List[Listing]:
        """
        Фильтрует список объявлений, удаляя дубликаты.
        
        Args:
            listings: Список объявлений
            
        Returns:
            List[Listing]: Отфильтрованный список без дубликатов
        """
        unique_listings = []
        duplicate_count = 0
        
        for listing in listings:
            if not self.is_duplicate(listing):
                unique_listings.append(listing)
                self.add_to_cache(listing)
            else:
                duplicate_count += 1
        
        logger.info(f"Отфильтровано {duplicate_count} дубликатов из {len(listings)} объявлений")
        return unique_listings 