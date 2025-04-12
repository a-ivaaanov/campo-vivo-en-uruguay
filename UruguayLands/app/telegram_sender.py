#!/usr/bin/env python3
"""
Модуль для отправки объявлений в Telegram-канал.
"""

import os
import logging
import asyncio
import requests
from typing import List, Optional, Dict, Any
from datetime import datetime
from io import BytesIO
from pydantic import HttpUrl
from urllib.parse import urlparse

from app.models import Listing

logger = logging.getLogger(__name__)

class TelegramSender:
    """
    Класс для отправки объявлений в Telegram-канал.
    """
    
    def __init__(self, token: str = None, chat_id: str = None):
        """
        Инициализирует отправщик Telegram.
        
        Args:
            token: Токен бота Telegram
            chat_id: ID чата или канала
        """
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        
        if not self.token:
            raise ValueError("Не указан токен Telegram-бота. Установите переменную окружения TELEGRAM_BOT_TOKEN")
        
        if not self.chat_id:
            raise ValueError("Не указан ID чата Telegram. Установите переменную окружения TELEGRAM_CHAT_ID")
        
        self.api_url = f"https://api.telegram.org/bot{self.token}"
        self.seen_listings = self._load_seen_listings()
    
    def _load_seen_listings(self) -> set:
        """Загружает множество ID уже отправленных объявлений."""
        try:
            cache_file = "data/telegram_sent_cache.txt"
            if os.path.exists(cache_file):
                with open(cache_file, "r", encoding="utf-8") as f:
                    return set(line.strip() for line in f if line.strip())
            return set()
        except Exception as e:
            logger.error(f"Ошибка при загрузке кеша отправленных объявлений: {e}")
            return set()
    
    def _save_seen_listings(self):
        """Сохраняет множество ID отправленных объявлений."""
        try:
            cache_file = "data/telegram_sent_cache.txt"
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                for listing_id in self.seen_listings:
                    f.write(f"{listing_id}\n")
        except Exception as e:
            logger.error(f"Ошибка при сохранении кеша отправленных объявлений: {e}")
    
    def _format_message(self, listing: Listing) -> str:
        """
        Форматирует сообщение для отправки в Telegram.
        
        Args:
            listing: Объект объявления
            
        Returns:
            str: Отформатированное сообщение
        """
        # Эмодзи для лучшего форматирования
        header_emoji = "🏞️"
        price_emoji = "💰"
        location_emoji = "📍"
        area_emoji = "📏"
        source_emoji = "🔍"
        
        # Форматирование сообщения
        message = []
        
        # Заголовок
        message.append(f"*{header_emoji} {listing.title}*")
        message.append("")
        
        # Цена
        if listing.price:
            message.append(f"{price_emoji} *Цена:* {listing.price}")
        
        # Расположение
        if listing.location:
            message.append(f"{location_emoji} *Расположение:* {listing.location}")
        
        # Площадь
        if listing.area:
            message.append(f"{area_emoji} *Площадь:* {listing.area}")
        
        # Коммуникации
        if listing.utilities and listing.utilities != "Не указано":
            message.append(f"🔌 *Коммуникации:* {listing.utilities}")
        
        # Пустая строка перед описанием
        message.append("")
        
        # Описание (если есть)
        if listing.description:
            # Ограничиваем длину описания
            max_desc_len = 300
            desc = listing.description
            if len(desc) > max_desc_len:
                desc = desc[:max_desc_len] + "..."
            message.append(desc)
            message.append("")
        
        # Источник и ссылка
        source_name = {
            "mercadolibre": "MercadoLibre",
            "infocasas": "InfoCasas",
            "gallito": "Gallito"
        }.get(listing.source, listing.source)
        
        message.append(f"{source_emoji} *Источник:* {source_name}")
        message.append(f"[Посмотреть объявление]({listing.url})")
        
        # Добавляем хештеги
        message.append("")
        hashtags = ["#Uruguay", f"#{source_name}", "#Terreno"]
        
        # Добавляем локацию в хештеги, если она есть
        if listing.location and listing.location != "Uruguay":
            # Обрабатываем только первое слово локации для хештега
            location_hashtag = listing.location.split(',')[0].strip().replace(' ', '')
            hashtags.append(f"#{location_hashtag}")
        
        message.append(" ".join(hashtags))
        
        return "\n".join(message)
    
    def _escape_markdown(self, text: str) -> str:
        """
        Экранирует символы разметки Markdown.
        
        Args:
            text: Исходный текст
            
        Returns:
            str: Экранированный текст
        """
        if not text:
            return ""
        
        # Символы, которые нужно экранировать в Markdown V2
        escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        
        for char in escape_chars:
            text = text.replace(char, f"\\{char}")
        
        return text
    
    async def download_image(self, url: str) -> Optional[bytes]:
        """
        Загружает изображение по URL.
        
        Args:
            url: URL изображения
            
        Returns:
            Optional[bytes]: Двоичные данные изображения или None в случае ошибки
        """
        try:
            # Проверяем, является ли URL локальным файлом
            if url.startswith("/") or url.startswith("./") or url.startswith("../"):
                # Это локальный файл
                with open(url, "rb") as f:
                    return f.read()
            
            # Это URL - загружаем через requests
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"Ошибка при загрузке изображения {url}: {e}")
            return None
    
    async def send_listing(self, listing: Listing) -> bool:
        """
        Отправляет объявление в Telegram-канал.
        
        Args:
            listing: Объект объявления
            
        Returns:
            bool: True, если отправка успешна
        """
        # Отладочная информация для проверки chat_id и token
        logger.info(f"Отправка объявления в Telegram с использованием chat_id: {self.chat_id} и token: {self.token[:10]}...")
        
        # Проверяем, было ли это объявление уже отправлено
        listing_id = str(listing.url)
        if listing_id in self.seen_listings:
            logger.info(f"Объявление {listing_id} уже было отправлено ранее")
            return False
        
        # Форматируем сообщение
        message_text = self._format_message(listing)
        
        try:
            # Если есть изображение, отправляем с изображением
            if listing.image_url:
                image_data = await self.download_image(str(listing.image_url))
                
                if image_data:
                    # Отправляем фото с подписью
                    files = {'photo': image_data}
                    data = {
                        'chat_id': self.chat_id,
                        'caption': message_text,
                        'parse_mode': 'Markdown'
                    }
                    
                    response = requests.post(f"{self.api_url}/sendPhoto", files=files, data=data)
                    
                    if response.status_code == 200:
                        self.seen_listings.add(listing_id)
                        self._save_seen_listings()
                        logger.info(f"Объявление {listing_id} успешно отправлено в Telegram с изображением")
                        return True
                    else:
                        logger.error(f"Ошибка при отправке фото в Telegram: {response.text}")
                
                # Если не удалось отправить с фото, отправляем только текст
                logger.warning(f"Не удалось загрузить изображение, отправляем только текст")
            
            # Отправляем только текст
            data = {
                'chat_id': self.chat_id,
                'text': message_text,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': False
            }
            
            response = requests.post(f"{self.api_url}/sendMessage", json=data)
            
            if response.status_code == 200:
                self.seen_listings.add(listing_id)
                self._save_seen_listings()
                logger.info(f"Объявление {listing_id} успешно отправлено в Telegram (только текст)")
                return True
            else:
                logger.error(f"Ошибка при отправке сообщения в Telegram: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка при отправке объявления {listing_id} в Telegram: {e}")
            return False
    
    async def send_listings(self, listings: List[Listing], only_recent: bool = True) -> Dict[str, int]:
        """
        Отправляет список объявлений в Telegram-канал.
        
        Args:
            listings: Список объявлений для отправки
            only_recent: Отправлять только недавние объявления (за последние 12 часов)
            
        Returns:
            Dict[str, int]: Статистика отправки по источникам
        """
        if not listings:
            logger.info("Нет объявлений для отправки")
            return {}
        
        logger.info(f"Начинаем отправку {len(listings)} объявлений в Telegram-канал")
        
        stats = {
            "total": len(listings),
            "sent": 0,
            "skipped": 0,
            "errors": 0
        }
        
        # Статистика по источникам
        source_stats = {}
        
        for listing in listings:
            source = listing.source
            if source not in source_stats:
                source_stats[source] = {"total": 0, "sent": 0}
            
            source_stats[source]["total"] += 1
            
            # Проверяем, является ли объявление недавним (если нужно)
            is_recent = True  # По умолчанию считаем, что объявление недавнее
            
            if only_recent:
                # Проверяем по дате публикации или через атрибут is_recent
                has_recent_attribute = (
                    listing.attributes and 
                    isinstance(listing.attributes, dict) and 
                    listing.attributes.get("is_recent", False)
                )
                
                if has_recent_attribute:
                    is_recent = True
                elif hasattr(listing, "date_published") and listing.date_published:
                    # Проверяем, что объявление опубликовано не более 12 часов назад
                    hours_diff = (datetime.now() - listing.date_published).total_seconds() / 3600
                    is_recent = hours_diff <= 12
                else:
                    # Если нет даты, используем дату скрапинга
                    if hasattr(listing, "date_scraped") and listing.date_scraped:
                        hours_diff = (datetime.now() - listing.date_scraped).total_seconds() / 3600
                        is_recent = hours_diff <= 1  # Для date_scraped используем 1 час
            
            # Если объявление не недавнее, пропускаем
            if only_recent and not is_recent:
                logger.info(f"Пропускаем не недавнее объявление {listing.url}")
                stats["skipped"] += 1
                continue
            
            # Отправляем объявление
            try:
                success = await self.send_listing(listing)
                
                if success:
                    stats["sent"] += 1
                    source_stats[source]["sent"] += 1
                else:
                    stats["skipped"] += 1
                
                # Делаем паузу между отправками, чтобы не превысить лимиты API
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Ошибка при отправке объявления {listing.url}: {e}")
                stats["errors"] += 1
        
        # Логируем статистику
        logger.info(f"Отправка объявлений завершена. Всего: {stats['total']}, "
                   f"отправлено: {stats['sent']}, пропущено: {stats['skipped']}, "
                   f"ошибок: {stats['errors']}")
        
        for source, source_stat in source_stats.items():
            logger.info(f"Источник {source}: всего {source_stat['total']}, отправлено {source_stat['sent']}")
        
        return source_stats

# Функция для использования в других модулях
async def send_listings_to_telegram(listings: List[Listing], only_recent: bool = True) -> Dict[str, int]:
    """
    Отправляет объявления в Telegram-канал.
    
    Args:
        listings: Список объявлений для отправки
        only_recent: Отправлять только недавние объявления
        
    Returns:
        Dict[str, int]: Статистика отправки
    """
    try:
        # Создаем отправщика Telegram
        sender = TelegramSender()
        
        # Отправляем объявления
        return await sender.send_listings(listings, only_recent)
    except Exception as e:
        logger.error(f"Ошибка при отправке объявлений в Telegram: {e}")
        return {"error": str(e)}

# Тестирование
if __name__ == "__main__":
    from app.models import Listing
    
    async def test_telegram_sender():
        # Создаем тестовое объявление
        test_listing = Listing(
            title="Тестовое объявление",
            price="USD 50,000",
            location="Punta del Este, Maldonado",
            area="1000 m²",
            url="https://www.example.com/listing/123",
            source="test",
            image_url="https://www.example.com/image.jpg",
            description="Это тестовое объявление для проверки отправки в Telegram.",
            utilities="Электричество, вода",
            attributes={"is_recent": True}
        )
        
        # Создаем отправщика Telegram
        sender = TelegramSender()
        
        # Отправляем объявление
        success = await sender.send_listing(test_listing)
        print(f"Отправка тестового объявления: {'успешно' if success else 'ошибка'}")
    
    # Запускаем тест
    asyncio.run(test_telegram_sender()) 