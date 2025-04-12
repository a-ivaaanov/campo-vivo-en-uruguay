import asyncio
import aiohttp
import json
import os
import logging
import re
import time
from pathlib import Path
from typing import List, Dict, Optional, Union, Set
from aiohttp import ClientSession, ClientTimeout
from datetime import datetime, timezone

from app.models import Listing

class TelegramSender:
    """Класс для отправки форматированных сообщений о земельных участках в канал Telegram."""
    
    def __init__(
        self, 
        bot_token: str, 
        chat_id: str,
        cache_dir: str = "cache",
        max_retries: int = 3,
        retry_delay: int = 5,
        max_images: int = 5,
        download_images: bool = True
    ):
        """
        Инициализирует отправителя Telegram.
        
        :param bot_token: Токен Telegram бота
        :param chat_id: ID чата/канала для отправки сообщений
        :param cache_dir: Директория для хранения кэша отправленных объявлений
        :param max_retries: Максимальное количество попыток при ошибках
        :param retry_delay: Задержка между повторными попытками в секундах
        :param max_images: Максимальное количество изображений для отправки
        :param download_images: Скачивать изображения перед отправкой
        """
        self.logger = logging.getLogger(__name__)
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
        self.cache_dir = Path(cache_dir)
        self.sent_listings_file = self.cache_dir / "sent_listings.json"
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.max_images = max_images
        self.download_images = download_images
        
        # Журнал отправленных объявлений (хранит URLs)
        self.sent_listings: Set[str] = set()
        
        # Убедимся, что директория кэша существует
        self._ensure_cache_dir()
        
        # Загрузим ранее отправленные объявления
        self._load_sent_listings()
    
    def _ensure_cache_dir(self):
        """Убеждается, что директория кэша существует."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_sent_listings(self):
        """Загружает ранее отправленные объявления из файла."""
        if self.sent_listings_file.exists():
            try:
                with open(self.sent_listings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.sent_listings = set(data)
                self.logger.info(f"Загружено {len(self.sent_listings)} ранее отправленных объявлений")
            except Exception as e:
                self.logger.error(f"Ошибка при загрузке отправленных объявлений: {e}")
                # Создаем новый файл, если старый поврежден
                self._save_sent_listings()
    
    def _save_sent_listings(self):
        """Сохраняет отправленные объявления в файл."""
        try:
            with open(self.sent_listings_file, 'w', encoding='utf-8') as f:
                json.dump(list(self.sent_listings), f, ensure_ascii=False, indent=2)
            self.logger.debug(f"Сохранено {len(self.sent_listings)} отправленных объявлений")
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении отправленных объявлений: {e}")
    
    def _escape_markdown(self, text: str) -> str:
        """
        Экранирует специальные символы для Markdown V2.
        
        :param text: Исходный текст
        :return: Экранированный текст для Markdown V2
        """
        if not text:
            return ""
            
        # Символы, которые нужно экранировать: _ * [ ] ( ) ~ ` > # + - = | { } . !
        escape_chars = r'_*[]()~`>#+-=|{}.!'
        
        for char in escape_chars:
            text = text.replace(char, f'\\{char}')
        
        return text
    
    def format_message(self, listing: Listing) -> str:
        """
        Форматирует сообщение для отправки в Telegram.
        
        :param listing: Объект объявления
        :return: Отформатированное сообщение с Markdown V2
        """
        # Основная информация (заголовок, цена, площадь)
        title = self._escape_markdown(listing.title or "Земельный участок")
        price = self._escape_markdown(listing.format_price() or "Цена не указана")
        area = self._escape_markdown(listing.format_area() or "Площадь не указана")
        
        # Перевод в гектары, если площадь достаточно большая
        if listing.area and listing.area > 10000:  # Больше 1 га
            ha = listing.to_hectares()
            if ha:
                area += f" \\({ha:.2f} га\\)"
        
        # Цена за квадратный метр
        price_per_sqm = ""
        if listing.price_per_sqm:
            price_per_sqm = f"\n💵 *Цена за м²*: {self._escape_markdown(f'{listing.price_per_sqm:.1f} {listing.price_currency}')}"
        elif listing.price and listing.area and listing.area > 0:
            price_per_sqm_value = listing.price / listing.area
            price_per_sqm = f"\n💵 *Цена за м²*: {self._escape_markdown(f'{price_per_sqm_value:.1f} {listing.price_currency}')}"
        
        # Местоположение
        location = self._escape_markdown(listing.location or "Местоположение не указано")
        
        # Коммуникации и характеристики
        features = []
        
        if listing.has_water:
            features.append("📋 Вода")
        if listing.has_electricity:
            features.append("⚡ Электричество")
        if listing.has_internet:
            features.append("🌐 Интернет")
        if listing.zoning:
            features.append(f"🏢 Зонирование: {self._escape_markdown(listing.zoning)}")
        if listing.terrain_type:
            features.append(f"🏞 Тип местности: {self._escape_markdown(listing.terrain_type)}")
            
        # Добавляем дополнительные атрибуты, если они есть
        if listing.attributes:
            for key, value in listing.attributes.items():
                if value and key not in ["price", "area", "location", "title"]:
                    features.append(f"• {self._escape_markdown(str(key))}: {self._escape_markdown(str(value))}")
        
        features_text = "\n".join(features) if features else "Характеристики не указаны"
        
        # Описание (ограничиваем длину)
        description = ""
        if listing.description:
            # Ограничиваем длину описания
            max_desc_length = 300
            desc = listing.description[:max_desc_length]
            if len(listing.description) > max_desc_length:
                desc += "..."
            description = f"\n\n📝 *Описание*:\n{self._escape_markdown(desc)}"
        
        # Формируем полное сообщение
        message = f"🏞 *{title}*\n\n"
        message += f"💰 *Цена*: {price}\n"
        message += f"📏 *Площадь*: {area}{price_per_sqm}\n"
        message += f"📍 *Местоположение*: {location}\n\n"
        message += f"*Характеристики*:\n{features_text}{description}\n\n"
        
        # Дата обнаружения и источник
        source_name = {
            "mercadolibre": "MercadoLibre",
            "infocasas": "InfoCasas",
            "gallito": "Gallito"
        }.get(listing.source, listing.source)
        
        found_date = listing.crawled_at.strftime("%d.%m.%Y")
        
        message += f"🔍 Найдено {found_date} на {self._escape_markdown(source_name)}\n"
        
        # Ссылка на оригинальное объявление
        url = str(listing.url)
        message += f"🔗 [Перейти к объявлению]({url})"
        
        return message
    
    async def download_image(self, image_url: str, session: ClientSession) -> Optional[str]:
        """
        Скачивает изображение и возвращает путь к локальному файлу.
        
        :param image_url: URL изображения
        :param session: Сессия aiohttp
        :return: Путь к скачанному файлу или None в случае ошибки
        """
        if not image_url:
            return None
            
        try:
            # Создаем папку для изображений, если её нет
            images_dir = self.cache_dir / "images"
            images_dir.mkdir(parents=True, exist_ok=True)
            
            # Генерируем имя файла на основе URL и текущего времени
            filename = f"{int(time.time())}_{hash(image_url) % 10000}.jpg"
            file_path = images_dir / filename
            
            # Скачиваем изображение
            async with session.get(image_url, timeout=ClientTimeout(total=30)) as response:
                if response.status != 200:
                    self.logger.warning(f"Не удалось скачать изображение {image_url}, код статуса: {response.status}")
                    return None
                    
                # Записываем изображение в файл
                image_data = await response.read()
                with open(file_path, 'wb') as f:
                    f.write(image_data)
                
                return str(file_path)
        except Exception as e:
            self.logger.error(f"Ошибка при скачивании изображения {image_url}: {e}")
            return None
    
    async def _send_request(self, method: str, params: Dict, session: ClientSession, files: Optional[Dict] = None) -> Dict:
        """
        Отправляет запрос к Telegram API с повторными попытками при ошибках.
        
        :param method: Метод API
        :param params: Параметры запроса
        :param session: Сессия aiohttp
        :param files: Файлы для отправки
        :return: Ответ от API
        """
        url = f"{self.api_url}/{method}"
        attempts = 0
        
        while attempts < self.max_retries:
            try:
                if files:
                    # Отправка файлов через multipart/form-data
                    data = aiohttp.FormData()
                    
                    # Добавляем обычные параметры
                    for key, value in params.items():
                        data.add_field(key, str(value))
                    
                    # Добавляем файлы
                    for file_key, file_path in files.items():
                        with open(file_path, 'rb') as f:
                            data.add_field(file_key, f, filename=os.path.basename(file_path))
                    
                    async with session.post(url, data=data) as response:
                        result = await response.json()
                else:
                    # Обычный POST запрос для текстовых сообщений
                    async with session.post(url, json=params) as response:
                        result = await response.json()
                
                if result.get('ok'):
                    return result
                else:
                    error_msg = result.get('description', 'Неизвестная ошибка')
                    self.logger.warning(f"Ошибка API Telegram: {error_msg}")
                    
                    # Проверяем, стоит ли повторять запрос
                    if 'retry_after' in result:
                        retry_after = int(result['retry_after'])
                        self.logger.info(f"Превышен лимит запросов, ожидаем {retry_after} секунд")
                        await asyncio.sleep(retry_after)
                    elif 'Too Many Requests' in error_msg:
                        # Если API не указал время ожидания, используем наше значение
                        await asyncio.sleep(self.retry_delay * (attempts + 1))
                    else:
                        # Для других ошибок тоже делаем повторную попытку
                        await asyncio.sleep(self.retry_delay)
            
            except Exception as e:
                self.logger.error(f"Ошибка при отправке запроса к Telegram API: {e}")
                await asyncio.sleep(self.retry_delay)
            
            attempts += 1
        
        raise Exception(f"Не удалось отправить запрос к Telegram API после {self.max_retries} попыток")
    
    async def send_message(self, text: str, session: ClientSession) -> Dict:
        """
        Отправляет текстовое сообщение в канал Telegram.
        
        :param text: Текст сообщения с разметкой Markdown V2
        :param session: Сессия aiohttp
        :return: Ответ от API
        """
        params = {
            'chat_id': self.chat_id,
            'text': text,
            'parse_mode': 'MarkdownV2',
            'disable_web_page_preview': False
        }
        
        return await self._send_request('sendMessage', params, session)
    
    async def send_photo(self, photo_path: str, caption: str, session: ClientSession) -> Dict:
        """
        Отправляет изображение с подписью в канал Telegram.
        
        :param photo_path: Путь к файлу изображения
        :param caption: Подпись к изображению с разметкой Markdown V2
        :param session: Сессия aiohttp
        :return: Ответ от API
        """
        params = {
            'chat_id': self.chat_id,
            'caption': caption,
            'parse_mode': 'MarkdownV2'
        }
        
        files = {'photo': photo_path}
        
        return await self._send_request('sendPhoto', params, session, files)
    
    async def send_media_group(self, media_paths: List[str], caption: str, session: ClientSession) -> Dict:
        """
        Отправляет группу медиафайлов в канал Telegram.
        
        :param media_paths: Пути к файлам изображений
        :param caption: Подпись к медиагруппе с разметкой Markdown V2
        :param session: Сессия aiohttp
        :return: Ответ от API
        """
        # Ограничиваем количество изображений до максимального
        media_paths = media_paths[:self.max_images]
        
        # Подготавливаем медиа-группу
        media = []
        for i, path in enumerate(media_paths):
            media_item = {
                'type': 'photo',
                'media': f'attach://{i}'
            }
            
            # Добавляем подпись только к первому медиафайлу
            if i == 0 and caption:
                media_item['caption'] = caption
                media_item['parse_mode'] = 'MarkdownV2'
            
            media.append(media_item)
        
        params = {
            'chat_id': self.chat_id,
            'media': json.dumps(media)
        }
        
        files = {str(i): path for i, path in enumerate(media_paths)}
        
        return await self._send_request('sendMediaGroup', params, session, files)
    
    async def send_listing(self, listing: Listing) -> bool:
        """
        Отправляет объявление в канал Telegram.
        
        :param listing: Объект объявления
        :return: True если отправка успешна, False в противном случае
        """
        # Проверяем, было ли объявление уже отправлено
        listing_url = str(listing.url)
        if listing_url in self.sent_listings:
            self.logger.info(f"Объявление {listing_url} уже было отправлено ранее")
            return False
        
        # Форматируем сообщение
        message = self.format_message(listing)
        
        # Проверяем, есть ли изображения
        has_images = listing.images and len(listing.images) > 0
        
        async with aiohttp.ClientSession() as session:
            try:
                if has_images and self.download_images:
                    # Скачиваем изображения
                    image_paths = []
                    for image_url in listing.images[:self.max_images]:
                        image_path = await self.download_image(image_url, session)
                        if image_path:
                            image_paths.append(image_path)
                    
                    # Если есть скачанные изображения, отправляем их
                    if image_paths:
                        if len(image_paths) == 1:
                            # Отправляем одно изображение с подписью
                            await self.send_photo(image_paths[0], message, session)
                        else:
                            # Отправляем группу изображений с подписью
                            await self.send_media_group(image_paths, message, session)
                        
                        # Удаляем скачанные изображения
                        for path in image_paths:
                            try:
                                os.remove(path)
                            except:
                                pass
                    else:
                        # Если не удалось скачать изображения, отправляем текстовое сообщение
                        await self.send_message(message, session)
                else:
                    # Отправляем текстовое сообщение без изображений
                    await self.send_message(message, session)
                
                # Добавляем URL в список отправленных и сохраняем
                self.sent_listings.add(listing_url)
                self._save_sent_listings()
                
                self.logger.info(f"Объявление {listing_url} успешно отправлено в Telegram")
                return True
                
            except Exception as e:
                self.logger.error(f"Ошибка при отправке объявления {listing_url} в Telegram: {e}")
                return False
    
    async def send_listings(self, listings: List[Listing], delay: float = 1.0) -> int:
        """
        Отправляет несколько объявлений в канал Telegram с задержкой между сообщениями.
        
        :param listings: Список объектов объявлений
        :param delay: Задержка между отправками в секундах
        :return: Количество успешно отправленных объявлений
        """
        sent_count = 0
        
        for listing in listings:
            success = await self.send_listing(listing)
            if success:
                sent_count += 1
            
            # Делаем паузу между отправками, чтобы не превысить лимиты API Telegram
            if listing != listings[-1]:  # Пропускаем задержку после последнего элемента
                await asyncio.sleep(delay)
        
        return sent_count

# Функция для тестирования отправки
async def test_telegram_sender():
    """Тестирует отправку тестового объявления в Telegram."""
    from dotenv import load_dotenv
    load_dotenv()
    
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        logging.error("Не заданы TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID в переменных окружения")
        return
    
    # Создаем тестовое объявление
    test_listing = Listing(
        id="test123",
        url="https://example.com/listing/123",
        source="test",
        title="Тестовый земельный участок у озера",
        price=75000,
        price_currency="USD",
        area=5000,
        area_unit="m²",
        location="Canelones, Uruguay",
        description="Прекрасный земельный участок с видом на озеро. Идеально подходит для строительства загородного дома.",
        images=["https://picsum.photos/800/600", "https://picsum.photos/800/601"],
        has_water=True,
        has_electricity=True,
        terrain_type="Холмистый"
    )
    
    # Инициализируем отправителя
    sender = TelegramSender(bot_token, chat_id)
    
    # Отправляем тестовое объявление
    result = await sender.send_listing(test_listing)
    
    if result:
        logging.info("Тестовое объявление успешно отправлено")
    else:
        logging.error("Не удалось отправить тестовое объявление")

if __name__ == "__main__":
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Запускаем тест
    asyncio.run(test_telegram_sender()) 