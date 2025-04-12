#!/usr/bin/env python3
"""
Модуль для сбора и анализа статистики по объявлениям.
"""

import os
import json
import logging
import statistics
import re
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from collections import Counter
from app.models import Listing

logger = logging.getLogger(__name__)

class ListingAnalytics:
    """
    Класс для сбора и анализа статистики по объявлениям о земельных участках.
    Отслеживает цены, местоположения и другие характеристики.
    """
    
    def __init__(self, data_file: str = "data/analytics/listings_stats.json"):
        """
        Инициализирует анализатор объявлений.
        
        Args:
            data_file: Путь к файлу данных для хранения статистики
        """
        self.data_file = data_file
        self.stats = self._load_stats()
        self.current_batch = []
    
    def _load_stats(self) -> Dict[str, Any]:
        """Загружает статистику из файла."""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            
            # Если файл не существует, создаем базовую структуру
            return {
                "last_update": datetime.now().isoformat(),
                "total_listings": 0,
                "price_stats": {
                    "min": None,
                    "max": None,
                    "median": None,
                    "average": None,
                    "by_location": {},
                    "by_area": {},
                    "by_period": {}
                },
                "location_stats": {
                    "top_locations": [],
                    "location_count": {}
                },
                "area_stats": {
                    "min": None,
                    "max": None,
                    "median": None,
                    "average": None
                },
                "source_stats": {},
                "utilities_stats": {},
                "price_history": []
            }
        except Exception as e:
            logger.error(f"Ошибка при загрузке статистики: {e}")
            return {}
    
    def _save_stats(self):
        """Сохраняет статистику в файл."""
        try:
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.stats, f, ensure_ascii=False, indent=2, default=str)
            logger.info(f"Статистика сохранена в {self.data_file}")
        except Exception as e:
            logger.error(f"Ошибка при сохранении статистики: {e}")
    
    def _extract_price_number(self, price: str) -> Optional[float]:
        """
        Извлекает числовое значение цены из строки.
        
        Args:
            price: Строка с ценой, например 'USD 50,000'
            
        Returns:
            Optional[float]: Числовое значение цены или None, если не удалось извлечь
        """
        if not price:
            return None
            
        # Пытаемся извлечь числовое значение с помощью регулярного выражения
        match = re.search(r'[\d.,]+', price.replace(' ', ''))
        if match:
            price_str = match.group(0).replace(',', '.')
            try:
                # Заменяем все лишние точки, кроме последней
                parts = price_str.split('.')
                if len(parts) > 2:
                    price_str = ''.join(parts[:-1]) + '.' + parts[-1]
                return float(price_str)
            except ValueError:
                return None
        return None
    
    def _extract_area_number(self, area: str) -> Optional[float]:
        """
        Извлекает числовое значение площади из строки.
        
        Args:
            area: Строка с площадью, например '1000 m²' или '5 ha'
            
        Returns:
            Optional[float]: Числовое значение площади в м² или None, если не удалось извлечь
        """
        if not area:
            return None
            
        # Пытаемся извлечь числовое значение и единицу измерения
        match = re.search(r'([\d.,]+)\s*([hm²²]|ha)', area.lower())
        if match:
            area_str = match.group(1).replace(',', '.')
            unit = match.group(2)
            
            try:
                area_value = float(area_str)
                
                # Преобразуем гектары в м²
                if unit in ['h', 'ha']:
                    area_value *= 10000  # 1 га = 10,000 м²
                
                return area_value
            except ValueError:
                return None
        return None
    
    def _get_location_key(self, location: str) -> str:
        """
        Нормализует местоположение для использования в статистике.
        
        Args:
            location: Исходное местоположение
            
        Returns:
            str: Нормализованное местоположение
        """
        if not location:
            return "Unknown"
            
        # Нормализуем местоположение
        location = location.strip().lower()
        
        # Извлекаем основной регион/город (обычно первая часть до запятой)
        parts = location.split(',')
        main_location = parts[0].strip().title()
        
        return main_location
    
    def add_listing(self, listing: Listing):
        """
        Добавляет объявление в текущий пакет для анализа.
        
        Args:
            listing: Объект объявления
        """
        self.current_batch.append(listing)
    
    def add_listings(self, listings: List[Listing]):
        """
        Добавляет список объявлений в текущий пакет для анализа.
        
        Args:
            listings: Список объявлений
        """
        self.current_batch.extend(listings)
    
    def process_batch(self, save: bool = True):
        """
        Обрабатывает текущий пакет объявлений и обновляет статистику.
        
        Args:
            save: Сохранять ли статистику в файл после обработки
        """
        if not self.current_batch:
            logger.info("Нет новых объявлений для обработки")
            return
        
        logger.info(f"Обработка пакета из {len(self.current_batch)} объявлений")
        
        # Обновляем общую статистику
        self.stats["total_listings"] += len(self.current_batch)
        self.stats["last_update"] = datetime.now().isoformat()
        
        # Подготавливаем данные для обновления статистики
        prices = []
        areas = []
        locations = []
        sources = []
        utilities = []
        
        # Извлекаем данные из объявлений
        for listing in self.current_batch:
            # Цена
            price_value = self._extract_price_number(listing.price)
            if price_value:
                prices.append(price_value)
            
            # Площадь
            area_value = self._extract_area_number(listing.area)
            if area_value:
                areas.append(area_value)
            
            # Местоположение
            if listing.location:
                location_key = self._get_location_key(listing.location)
                locations.append(location_key)
            
            # Источник
            if listing.source:
                sources.append(listing.source)
            
            # Коммуникации
            if listing.utilities:
                # Разбиваем строку коммуникаций на отдельные элементы
                utils_list = [u.strip() for u in listing.utilities.split(',')]
                utilities.extend(utils_list)
        
        # Обновляем статистику цен
        if prices:
            price_stats = self.stats["price_stats"]
            
            # Обновляем минимальную и максимальную цену
            if price_stats["min"] is None or min(prices) < price_stats["min"]:
                price_stats["min"] = min(prices)
            
            if price_stats["max"] is None or max(prices) > price_stats["max"]:
                price_stats["max"] = max(prices)
            
            # Обновляем среднюю и медиану
            all_prices = prices  # TODO: добавить сохранение всех цен для более точного расчета
            price_stats["median"] = statistics.median(all_prices)
            price_stats["average"] = statistics.mean(all_prices)
            
            # Добавляем текущие цены в историю
            current_date = datetime.now().strftime("%Y-%m-%d")
            self.stats["price_history"].append({
                "date": current_date,
                "count": len(prices),
                "min": min(prices),
                "max": max(prices),
                "median": statistics.median(prices),
                "average": statistics.mean(prices)
            })
            
            # Обновляем статистику цен по местоположению
            for listing in self.current_batch:
                price_value = self._extract_price_number(listing.price)
                if price_value and listing.location:
                    location_key = self._get_location_key(listing.location)
                    
                    if location_key not in price_stats["by_location"]:
                        price_stats["by_location"][location_key] = {
                            "count": 0,
                            "min": None,
                            "max": None,
                            "total": 0
                        }
                    
                    loc_stats = price_stats["by_location"][location_key]
                    loc_stats["count"] += 1
                    loc_stats["total"] += price_value
                    
                    if loc_stats["min"] is None or price_value < loc_stats["min"]:
                        loc_stats["min"] = price_value
                    
                    if loc_stats["max"] is None or price_value > loc_stats["max"]:
                        loc_stats["max"] = price_value
                    
                    # Обновляем среднюю цену
                    loc_stats["average"] = loc_stats["total"] / loc_stats["count"]
            
            # Обновляем статистику цен по размеру участка
            for listing in self.current_batch:
                price_value = self._extract_price_number(listing.price)
                area_value = self._extract_area_number(listing.area)
                
                if price_value and area_value:
                    # Определяем диапазон площади
                    area_range = self._get_area_range(area_value)
                    
                    if area_range not in price_stats["by_area"]:
                        price_stats["by_area"][area_range] = {
                            "count": 0,
                            "min": None,
                            "max": None,
                            "total": 0
                        }
                    
                    area_stats = price_stats["by_area"][area_range]
                    area_stats["count"] += 1
                    area_stats["total"] += price_value
                    
                    if area_stats["min"] is None or price_value < area_stats["min"]:
                        area_stats["min"] = price_value
                    
                    if area_stats["max"] is None or price_value > area_stats["max"]:
                        area_stats["max"] = price_value
                    
                    # Обновляем среднюю цену
                    area_stats["average"] = area_stats["total"] / area_stats["count"]
        
        # Обновляем статистику площади
        if areas:
            area_stats = self.stats["area_stats"]
            
            # Обновляем минимальную и максимальную площадь
            if area_stats["min"] is None or min(areas) < area_stats["min"]:
                area_stats["min"] = min(areas)
            
            if area_stats["max"] is None or max(areas) > area_stats["max"]:
                area_stats["max"] = max(areas)
            
            # Обновляем среднюю и медиану
            area_stats["median"] = statistics.median(areas)
            area_stats["average"] = statistics.mean(areas)
        
        # Обновляем статистику местоположений
        if locations:
            location_stats = self.stats["location_stats"]
            location_counter = Counter(locations)
            
            # Обновляем счетчик местоположений
            for location, count in location_counter.items():
                if location not in location_stats["location_count"]:
                    location_stats["location_count"][location] = 0
                
                location_stats["location_count"][location] += count
            
            # Обновляем топ местоположений
            top_locations = sorted(
                location_stats["location_count"].items(),
                key=lambda x: x[1],
                reverse=True
            )
            location_stats["top_locations"] = top_locations[:10]
        
        # Обновляем статистику источников
        if sources:
            source_counter = Counter(sources)
            for source, count in source_counter.items():
                if source not in self.stats["source_stats"]:
                    self.stats["source_stats"][source] = 0
                
                self.stats["source_stats"][source] += count
        
        # Обновляем статистику коммуникаций
        if utilities:
            utility_counter = Counter(utilities)
            for utility, count in utility_counter.items():
                if utility not in self.stats["utilities_stats"]:
                    self.stats["utilities_stats"][utility] = 0
                
                self.stats["utilities_stats"][utility] += count
        
        # Сохраняем обновленную статистику
        if save:
            self._save_stats()
        
        # Очищаем текущий пакет
        self.current_batch = []
        
        logger.info("Статистика успешно обновлена")
    
    def _get_area_range(self, area_value: float) -> str:
        """
        Определяет диапазон площади для группировки статистики.
        
        Args:
            area_value: Площадь в м²
            
        Returns:
            str: Строка с диапазоном площади
        """
        # Определяем диапазоны в м²
        if area_value < 1000:
            return "< 1,000 м²"
        elif area_value < 5000:
            return "1,000 - 5,000 м²"
        elif area_value < 10000:
            return "5,000 - 10,000 м²"
        elif area_value < 50000:
            return "1 - 5 га"
        elif area_value < 100000:
            return "5 - 10 га"
        else:
            return "> 10 га"
    
    def get_price_summary(self) -> Dict[str, Any]:
        """
        Возвращает сводку по ценам.
        
        Returns:
            Dict[str, Any]: Сводка по ценам
        """
        return self.stats.get("price_stats", {})
    
    def get_location_summary(self) -> Dict[str, Any]:
        """
        Возвращает сводку по местоположениям.
        
        Returns:
            Dict[str, Any]: Сводка по местоположениям
        """
        return self.stats.get("location_stats", {})
    
    def get_area_summary(self) -> Dict[str, Any]:
        """
        Возвращает сводку по площади.
        
        Returns:
            Dict[str, Any]: Сводка по площади
        """
        return self.stats.get("area_stats", {})
    
    def get_source_summary(self) -> Dict[str, Any]:
        """
        Возвращает сводку по источникам.
        
        Returns:
            Dict[str, Any]: Сводка по источникам
        """
        return self.stats.get("source_stats", {})
    
    def get_utilities_summary(self) -> Dict[str, Any]:
        """
        Возвращает сводку по коммуникациям.
        
        Returns:
            Dict[str, Any]: Сводка по коммуникациям
        """
        return self.stats.get("utilities_stats", {})
    
    def get_price_history(self) -> List[Dict[str, Any]]:
        """
        Возвращает историю цен.
        
        Returns:
            List[Dict[str, Any]]: История цен
        """
        return self.stats.get("price_history", []) 