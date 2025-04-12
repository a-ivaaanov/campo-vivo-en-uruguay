#!/usr/bin/env python3
"""
Модуль для отправки объявлений в Telegram-канал.
"""

import os
import logging
import asyncio
import requests
from typing import List, Optional, Dict, Any, Set, Tuple
from datetime import datetime
from io import BytesIO
from pydantic import HttpUrl
from urllib.parse import urlparse
import json
import time
from pathlib import Path

from app.models import Listing

logger = logging.getLogger(__name__)

class TelegramSender:
    """
    Класс для отправки объявлений о земельных участках в Telegram канал.
    Поддерживает форматирование сообщений, загрузку изображений и проверку
    уже отправленных объявлений.
    """
    
    def __init__(
        self, 
        bot_token: str, 
        chat_id: str,
        sent_listings_file: str = "cache/sent_listings.json",
        max_images_per_listing: int = 5,
        max_retries: int = 3,
        retry_delay: int = 2,
    ):
        """
        Инициализация отправителя Telegram.
        
        Args:
            bot_token: Токен Telegram бота
            chat_id: ID чата или канала для отправки сообщений
            sent_listings_file: Путь к файлу для хранения отправленных объявлений
            max_images_per_listing: Максимальное количество изображений для одного объявления
            max_retries: Максимальное количество повторных попыток при ошибке
            retry_delay: Задержка между повторными попытками (в секундах)
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.sent_listings_file = sent_listings_file
        self.max_images_per_listing = max_images_per_listing
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # Множество URL-адресов отправленных объявлений
        self.sent_listings: Set[str] = set()
        
        # Загружаем ранее отправленные объявления при инициализации
        self._ensure_cache_dir()
        self.load_sent_listings()
    
    def _ensure_cache_dir(self) -> None:
        """Убедиться, что директория для кэша существует"""
        cache_dir = os.path.dirname(self.sent_listings_file)
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir, exist_ok=True)
            logger.info(f"Создана директория для кэша отправленных объявлений: {cache_dir}")
    
    def load_sent_listings(self) -> None:
        """Загрузить список ранее отправленных объявлений"""
        if not os.path.exists(self.sent_listings_file):
            logger.info(f"Файл с отправленными объявлениями не найден: {self.sent_listings_file}")
            return
        
        try:
            with open(self.sent_listings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.sent_listings = set(data.get('sent_urls', []))
                
            logger.info(f"Загружено {len(self.sent_listings)} ранее отправленных объявлений")
        except Exception as e:
            logger.error(f"Ошибка при загрузке отправленных объявлений: {e}")
            self.sent_listings = set()
    
    def save_sent_listings(self) -> None:
        """Сохранить список отправленных объявлений"""
        try:
            data = {'sent_urls': list(self.sent_listings)}
            
            with open(self.sent_listings_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
            logger.debug(f"Сохранено {len(self.sent_listings)} отправленных объявлений")
        except Exception as e:
            logger.error(f"Ошибка при сохранении отправленных объявлений: {e}")
    
    def format_message(self, listing: Listing) -> str:
        """
        Форматирует сообщение для Telegram с использованием Markdown V2.
        
        Args:
            listing: Объект объявления
            
        Returns:
            str: Отформатированное сообщение
        """
        # Экранирование специальных символов для Markdown V2
        def escape_md(text):
            if not text:
                return ""
            chars = '_*[]()~`>#+-=|{}.!'
            return ''.join(f'\\{c}' if c in chars else c for c in str(text))
        
        # Форматирование заголовка
        title = f"*🌱 {escape_md(listing.title)}*" if listing.title else "*🌱 Земельный участок*"
        
        # Форматирование цены
        price_line = ""
        if listing.price:
            currency = listing.price_currency if listing.price_currency else "USD"
            price_formatted = f"{int(listing.price):,}".replace(',', ' ')
            price_line = f"💰 *Цена:* {escape_md(price_formatted)} {escape_md(currency)}\n"
            
            # Добавляем цену за м² если есть площадь
            if listing.price_per_sqm and listing.price_per_sqm > 0:
                price_per_sqm = f"{listing.price_per_sqm:.1f}".replace('.0', '')
                price_line += f"📊 *Цена за м²:* {escape_md(price_per_sqm)} {escape_md(currency)}/м²\n"
        
        # Форматирование площади
        area_line = ""
        if listing.area:
            area_formatted = f"{listing.area:,}".replace(',', ' ').replace('.0', '')
            area_line = f"📏 *Площадь:* {escape_md(area_formatted)} м²\n"
            
            # Переводим в гектары если площадь больше 10000 м²
            if listing.area >= 10000:
                hectares = listing.area / 10000
                area_line += f"🌳 *Площадь:* {escape_md(f'{hectares:.2f}'.replace('.00', ''))} га\n"
        
        # Форматирование местоположения
        location_line = ""
        if listing.location:
            location_line = f"📍 *Расположение:* {escape_md(listing.location)}\n"
        
        # Форматирование коммуникаций и характеристик
        features = []
        
        if listing.has_water is True:
            features.append("💧 Вода")
        elif listing.has_water is False:
            features.append("❌ Без воды")
        
        if listing.has_electricity is True:
            features.append("⚡ Электричество")
        elif listing.has_electricity is False:
            features.append("❌ Без электричества")
        
        if listing.has_internet is True:
            features.append("🌐 Интернет")
        
        if listing.zoning:
            features.append(f"🏠 {escape_md(listing.zoning)}")
        
        features_line = ""
        if features:
            features_text = " · ".join(features)
            features_line = f"🔧 *Характеристики:* {features_text}\n"
        
        # Добавляем описание с ограничением по длине
        description_line = ""
        if listing.description:
            # Ограничиваем длину описания
            max_desc_length = 300
            description = listing.description
            if len(description) > max_desc_length:
                description = description[:max_desc_length].strip() + "..."
                
            description_line = f"\n📝 {escape_md(description)}\n"
        
        # Добавляем источник и дату публикации
        source_line = ""
        if listing.source:
            source_name = listing.source.replace("mercadolibre", "MercadoLibre")
            source_name = source_name.replace("infocasas", "InfoCasas")
            source_line = f"🔍 *Источник:* {escape_md(source_name)}"
            
            if listing.crawled_at:
                crawled_date = listing.crawled_at.strftime("%d.%m.%Y")
                source_line += f" · {escape_md(crawled_date)}"
        
        # Формируем ссылку на оригинальное объявление
        url_line = f"\n[Открыть объявление]({escape_md(listing.url)})"
        
        # Собираем все компоненты сообщения
        message_parts = [
            title,
            "\n",
            price_line,
            area_line,
            location_line,
            features_line,
            description_line,
            source_line,
            url_line
        ]
        
        return "".join(message_parts)
    
    async def download_image(self, url: str) -> Optional[bytes]:
        """
        Загружает изображение по URL.
        
        Args:
            url: URL изображения
            
        Returns:
            Optional[bytes]: Данные изображения или None в случае ошибки
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.get(url, timeout=15)
                if response.status_code == 200:
                    logger.debug(f"Успешно загружено изображение: {url}")
                    return response.content
                else:
                    logger.warning(f"Ошибка при загрузке изображения: {url}, статус: {response.status_code}")
            except Exception as e:
                logger.warning(f"Ошибка при загрузке изображения ({attempt}/{self.max_retries}): {url}, {e}")
                
            # Задержка перед повторной попыткой
            if attempt < self.max_retries:
                await asyncio.sleep(self.retry_delay)
        
        return None
    
    async def send_listing(self, listing: Listing) -> bool:
        """
        Отправляет объявление в Telegram.
        
        Args:
            listing: Объект объявления
            
        Returns:
            bool: True в случае успешной отправки, иначе False
        """
        if not self.bot_token or not self.chat_id:
            logger.error("Не указаны токен бота или ID чата")
            return False
        
        # Проверяем, было ли объявление уже отправлено
        if listing.url in self.sent_listings:
            logger.info(f"Объявление уже было отправлено ранее: {listing.url}")
            return False
        
        # Форматируем сообщение
        message_text = self.format_message(listing)
        
        try:
            # API URL для отправки сообщения
            api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMediaGroup"
            
            # Загружаем изображения
            images = []
            if listing.images:
                for i, img_url in enumerate(listing.images[:self.max_images_per_listing]):
                    image_data = await self.download_image(img_url)
                    if image_data:
                        images.append(image_data)
            
            # Если есть изображения, отправляем их группой
            if images:
                media = []
                
                # Первое изображение с подписью (сообщением)
                media.append({
                    'type': 'photo',
                    'media': f'attach://photo0',
                    'caption': message_text,
                    'parse_mode': 'MarkdownV2'
                })
                
                # Остальные изображения
                for i in range(1, len(images)):
                    media.append({
                        'type': 'photo',
                        'media': f'attach://photo{i}'
                    })
                
                # Формируем данные для отправки
                files = {}
                for i, img_data in enumerate(images):
                    files[f'photo{i}'] = img_data
                
                # Параметры запроса
                params = {
                    'chat_id': self.chat_id,
                    'media': json.dumps(media)
                }
                
                # Отправляем группу изображений
                for attempt in range(1, self.max_retries + 1):
                    try:
                        response = requests.post(api_url, params=params, files=files, timeout=30)
                        if response.status_code == 200:
                            logger.info(f"Объявление успешно отправлено в Telegram: {listing.url}")
                            self.sent_listings.add(listing.url)
                            self.save_sent_listings()
                            return True
                        else:
                            logger.warning(f"Ошибка при отправке объявления в Telegram: {listing.url}, "
                                          f"статус: {response.status_code}, ответ: {response.text}")
                    except Exception as e:
                        logger.warning(f"Ошибка при отправке объявления в Telegram ({attempt}/{self.max_retries}): "
                                      f"{listing.url}, {e}")
                    
                    # Задержка перед повторной попыткой
                    if attempt < self.max_retries:
                        await asyncio.sleep(self.retry_delay)
            
            # Если нет изображений или не удалось отправить группой, отправляем текстовое сообщение
            api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            params = {
                'chat_id': self.chat_id,
                'text': message_text,
                'parse_mode': 'MarkdownV2',
                'disable_web_page_preview': False  # Включаем предпросмотр страницы
            }
            
            for attempt in range(1, self.max_retries + 1):
                try:
                    response = requests.post(api_url, json=params, timeout=15)
                    if response.status_code == 200:
                        logger.info(f"Текстовое сообщение успешно отправлено в Telegram: {listing.url}")
                        self.sent_listings.add(listing.url)
                        self.save_sent_listings()
                        return True
                    else:
                        logger.warning(f"Ошибка при отправке текстового сообщения в Telegram: {listing.url}, "
                                      f"статус: {response.status_code}, ответ: {response.text}")
                except Exception as e:
                    logger.warning(f"Ошибка при отправке текстового сообщения в Telegram ({attempt}/{self.max_retries}): "
                                  f"{listing.url}, {e}")
                
                # Задержка перед повторной попыткой
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay)
            
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при отправке объявления в Telegram: {listing.url}, {e}")
        
        return False
    
    async def send_listings(self, listings: List[Listing], delay: float = 2.0) -> Tuple[int, int]:
        """
        Отправляет список объявлений в Telegram с задержкой между сообщениями.
        
        Args:
            listings: Список объявлений
            delay: Задержка между отправками сообщений (в секундах)
            
        Returns:
            Tuple[int, int]: Количество успешно отправленных и пропущенных объявлений
        """
        sent_count = 0
        skipped_count = 0
        
        for listing in listings:
            # Проверяем, было ли объявление уже отправлено
            if listing.url in self.sent_listings:
                logger.debug(f"Пропуск объявления (уже отправлено): {listing.url}")
                skipped_count += 1
                continue
            
            # Отправляем объявление
            success = await self.send_listing(listing)
            
            if success:
                sent_count += 1
            else:
                skipped_count += 1
            
            # Задержка между отправками для избежания ограничений API
            if delay > 0 and listings.index(listing) < len(listings) - 1:
                await asyncio.sleep(delay)
        
        logger.info(f"Отправлено {sent_count} объявлений, пропущено {skipped_count} объявлений")
        return sent_count, skipped_count
    
    async def send_test_message(self, text: str = "Тестовое сообщение") -> bool:
        """
        Отправляет тестовое сообщение для проверки работоспособности.
        
        Args:
            text: Текст тестового сообщения
            
        Returns:
            bool: True в случае успешной отправки, иначе False
        """
        if not self.bot_token or not self.chat_id:
            logger.error("Не указаны токен бота или ID чата")
            return False
        
        api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        params = {
            'chat_id': self.chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        
        try:
            response = requests.post(api_url, json=params, timeout=15)
            if response.status_code == 200:
                logger.info("Тестовое сообщение успешно отправлено")
                return True
            else:
                logger.error(f"Ошибка при отправке тестового сообщения: "
                           f"статус {response.status_code}, ответ: {response.text}")
        except Exception as e:
            logger.error(f"Ошибка при отправке тестового сообщения: {e}")
        
        return False


async def test_telegram_sender():
    """Тестирование отправки в Telegram"""
    from dotenv import load_dotenv
    load_dotenv()
    
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        logger.error("Не указаны токен бота или ID чата в .env файле")
        return
    
    # Создаем тестовое объявление
    test_listing = Listing(
        id="test123",
        url="https://example.com/test",
        title="Прекрасный земельный участок у моря",
        source="test",
        price=45000,
        price_currency="USD",
        location="Роча, Ла-Палома, Уругвай",
        area=1200,
        description="Участок с прекрасным видом на океан. Подходит для строительства дома или туристического бизнеса.",
        images=["https://picsum.photos/800/600", "https://picsum.photos/800/601"],
        has_water=True,
        has_electricity=True,
        has_internet=True,
        zoning="Жилая зона",
        crawled_at=datetime.now()
    )
    
    # Создаем отправителя
    sender = TelegramSender(bot_token=bot_token, chat_id=chat_id)
    
    # Отправляем тестовое сообщение
    await sender.send_test_message("🧪 Тестирование отправки объявлений")
    
    # Отправляем тестовое объявление
    success = await sender.send_listing(test_listing)
    
    if success:
        logger.info("✅ Тестовое объявление успешно отправлено")
    else:
        logger.error("❌ Ошибка при отправке тестового объявления")


if __name__ == "__main__":
    # Настраиваем логирование
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Запускаем тест
    asyncio.run(test_telegram_sender()) 