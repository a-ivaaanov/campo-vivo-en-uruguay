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
    Класс для проверки дубликатов объявлений с различными стратегиями.
    Поддерживает проверку по URL, хешу содержимого и комбинированную проверку.
    """
    
    def __init__(
        self, 
        cache_file: str = "cache/listings_cache.json",
        max_age_days: int = 30,
        auto_save: bool = True,
        strategies: List[str] = None
    ):
        """
        Инициализация проверки дубликатов.
        
        Args:
            cache_file: Путь к файлу для хранения кэша объявлений
            max_age_days: Максимальный возраст записей в кэше (в днях)
            auto_save: Автоматически сохранять кэш при добавлении новых записей
            strategies: Список стратегий проверки дубликатов
                Доступные стратегии: 'url', 'content_hash', 'address_price'
        """
        self.cache_file = cache_file
        self.max_age_days = max_age_days
        self.auto_save = auto_save
        
        # Устанавливаем стратегии проверки дубликатов
        self.strategies = strategies or ['url', 'content_hash']
        
        # Словари для хранения кэша по разным стратегиям
        self.url_cache: Set[str] = set()
        self.content_hash_cache: Set[str] = set()
        self.address_price_cache: Set[str] = set()
        
        # Словарь дата-время последнего обновления для каждого элемента
        self.last_seen: Dict[str, datetime] = {}
        
        # Загружаем кэш при инициализации
        self._ensure_cache_dir()
        self.load_cache()
    
    def _ensure_cache_dir(self) -> None:
        """Убедиться, что директория для кэша существует"""
        cache_dir = os.path.dirname(self.cache_file)
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir, exist_ok=True)
            logger.info(f"Создана директория для кэша: {cache_dir}")
    
    def load_cache(self) -> None:
        """Загрузить кэш из файла"""
        if not os.path.exists(self.cache_file):
            logger.info(f"Файл кэша не найден: {self.cache_file}. Будет создан новый.")
            return
        
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                
                self.url_cache = set(cache_data.get('url_cache', []))
                self.content_hash_cache = set(cache_data.get('content_hash_cache', []))
                self.address_price_cache = set(cache_data.get('address_price_cache', []))
                
                # Преобразуем строки с датами в объекты datetime
                self.last_seen = {
                    k: datetime.fromisoformat(v) 
                    for k, v in cache_data.get('last_seen', {}).items()
                }
                
            logger.info(f"Загружен кэш: {len(self.url_cache)} URL, "
                      f"{len(self.content_hash_cache)} хешей содержимого")
            
            # Очищаем устаревшие записи при загрузке
            self.cleanup_old_entries()
        except Exception as e:
            logger.error(f"Ошибка загрузки кэша: {e}")
            # Инициализируем пустой кэш при ошибке
            self.url_cache = set()
            self.content_hash_cache = set()
            self.address_price_cache = set()
            self.last_seen = {}
    
    def save_cache(self) -> None:
        """Сохранить кэш в файл"""
        try:
            cache_data = {
                'url_cache': list(self.url_cache),
                'content_hash_cache': list(self.content_hash_cache),
                'address_price_cache': list(self.address_price_cache),
                'last_seen': {k: v.isoformat() for k, v in self.last_seen.items()}
            }
            
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
                
            logger.debug(f"Кэш сохранен: {len(self.url_cache)} URL, "
                       f"{len(self.content_hash_cache)} хешей содержимого")
        except Exception as e:
            logger.error(f"Ошибка сохранения кэша: {e}")
    
    def cleanup_old_entries(self) -> None:
        """Удалить устаревшие записи из кэша"""
        if self.max_age_days <= 0:
            return
        
        now = datetime.now()
        cutoff_date = now - timedelta(days=self.max_age_days)
        
        old_entries = [k for k, v in self.last_seen.items() if v < cutoff_date]
        
        if not old_entries:
            return
        
        logger.info(f"Удаление {len(old_entries)} устаревших записей из кэша")
        
        for key in old_entries:
            self.last_seen.pop(key, None)
            
            # Удаляем из всех кэшей по возможности
            self.url_cache.discard(key)
            self.content_hash_cache.discard(key)
            self.address_price_cache.discard(key)
        
        if self.auto_save:
            self.save_cache()
    
    def generate_content_hash(self, listing: Listing) -> str:
        """
        Генерирует хеш содержимого объявления,
        используя наиболее релевантные поля
        """
        # Собираем все значимые поля для создания хеша
        content_parts = []
        
        # Основные характеристики
        if listing.title:
            content_parts.append(str(listing.title))
        if listing.price:
            content_parts.append(str(listing.price))
        if listing.area:
            content_parts.append(str(listing.area))
        if listing.location:
            content_parts.append(str(listing.location))
        if listing.description:
            # Используем первые 200 символов описания для уменьшения влияния форматирования
            content_parts.append(str(listing.description)[:200])
        
        # Соединяем части для создания хеша
        content_string = "||".join([p.strip().lower() for p in content_parts if p])
        
        # Генерируем хеш
        return hashlib.md5(content_string.encode('utf-8')).hexdigest()
    
    def generate_address_price_key(self, listing: Listing) -> Optional[str]:
        """
        Генерирует ключ на основе адреса и цены для сравнения объявлений.
        Возвращает None, если недостаточно данных.
        """
        if not listing.location or not listing.price:
            return None
        
        # Очищаем адрес от ненужных деталей
        address = listing.location.strip().lower()
        
        # Включаем цену с округлением до сотен для допуска небольших отклонений
        price_rounded = round(int(listing.price) / 100) * 100
        
        key = f"{address}||{price_rounded}"
        return hashlib.md5(key.encode('utf-8')).hexdigest()
    
    def is_duplicate(self, listing: Listing) -> bool:
        """
        Проверяет, является ли объявление дубликатом по выбранным стратегиям.
        
        Args:
            listing: Объект объявления для проверки
            
        Returns:
            bool: True, если объявление является дубликатом, иначе False
        """
        # Проверка по URL
        if 'url' in self.strategies and listing.url in self.url_cache:
            logger.debug(f"Дубликат по URL: {listing.url}")
            self._update_last_seen(listing.url)
            return True
        
        # Проверка по хешу содержимого
        if 'content_hash' in self.strategies:
            content_hash = self.generate_content_hash(listing)
            listing.content_hash = content_hash  # Сохраняем хеш в объекте для возможного использования
            
            if content_hash in self.content_hash_cache:
                logger.debug(f"Дубликат по хешу содержимого: {content_hash}")
                self._update_last_seen(content_hash)
                return True
        
        # Проверка по адресу и цене
        if 'address_price' in self.strategies:
            address_price_key = self.generate_address_price_key(listing)
            
            if address_price_key and address_price_key in self.address_price_cache:
                logger.debug(f"Дубликат по адресу и цене: {listing.location}, {listing.price}")
                self._update_last_seen(address_price_key)
                return True
        
        # Если не найден дубликат, добавляем в кэш
        self.add_to_cache(listing)
        return False
    
    def _update_last_seen(self, key: str) -> None:
        """Обновляет временную метку последнего обнаружения для ключа"""
        self.last_seen[key] = datetime.now()
    
    def add_to_cache(self, listing: Listing) -> None:
        """
        Добавляет объявление в кэш по всем активным стратегиям
        
        Args:
            listing: Объект объявления для добавления в кэш
        """
        now = datetime.now()
        
        # Добавляем URL в кэш
        if 'url' in self.strategies and listing.url:
            self.url_cache.add(listing.url)
            self.last_seen[listing.url] = now
        
        # Добавляем хеш содержимого в кэш
        if 'content_hash' in self.strategies:
            content_hash = listing.content_hash or self.generate_content_hash(listing)
            self.content_hash_cache.add(content_hash)
            self.last_seen[content_hash] = now
        
        # Добавляем ключ адрес+цена в кэш
        if 'address_price' in self.strategies:
            address_price_key = self.generate_address_price_key(listing)
            if address_price_key:
                self.address_price_cache.add(address_price_key)
                self.last_seen[address_price_key] = now
        
        if self.auto_save:
            self.save_cache()
    
    def filter_duplicates(self, listings: List[Listing]) -> List[Listing]:
        """
        Фильтрует список объявлений, удаляя дубликаты
        
        Args:
            listings: Список объявлений для фильтрации
            
        Returns:
            List[Listing]: Список уникальных объявлений
        """
        unique_listings = []
        duplicates_count = 0
        
        for listing in listings:
            if not self.is_duplicate(listing):
                unique_listings.append(listing)
            else:
                duplicates_count += 1
        
        if duplicates_count > 0:
            logger.info(f"Отфильтровано {duplicates_count} дубликатов из {len(listings)} объявлений")
        
        return unique_listings 