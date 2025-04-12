#!/usr/bin/env python3
"""
Простой скрипт для тестирования парсера MercadoLibre без зависимостей от других модулей.
"""

import asyncio
import json
import os
import sys
import logging
import random
import re
import ssl
import time
import aiohttp
from datetime import datetime
from pathlib import Path
import traceback
from typing import List, Dict, Any, Optional, Tuple
import argparse

# Настраиваем путь для импорта модулей проекта
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('test_ml_debug.log')
    ]
)
logger = logging.getLogger('test_ml')

# Импортируем необходимые модули
try:
    from app.parsers.base import BaseParser
    from app.models.listing import Listing
    logger.info("Модули успешно импортированы")
except ImportError as e:
    logger.error(f"Ошибка импорта: {e}")
    traceback.print_exc()
    sys.exit(1)


class ProxyManager:
    """Менеджер прокси для обеспечения ротации прокси-серверов."""
    
    def __init__(self, proxy_file_path: Optional[str] = None):
        """
        Инициализирует менеджер прокси.
        
        Args:
            proxy_file_path: Путь к файлу с прокси-серверами (по строке на прокси)
        """
        self.proxies = []
        self.current_proxy_index = 0
        self.last_rotation_time = time.time()
        
        # Если указан файл с прокси, загружаем прокси из него
        if proxy_file_path and os.path.exists(proxy_file_path):
            self._load_proxies_from_file(proxy_file_path)
            logger.info(f"Загружено {len(self.proxies)} прокси из файла {proxy_file_path}")
        else:
            # Если файл не указан или не существует, используем встроенный список бесплатных прокси
            self._load_default_proxies()
            logger.info(f"Использую {len(self.proxies)} встроенных прокси")
    
    def _load_proxies_from_file(self, file_path: str) -> None:
        """Загружает прокси из файла."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    proxy = line.strip()
                    if proxy and not proxy.startswith('#'):
                        # Нормализуем формат прокси
                        if not proxy.startswith('http://') and not proxy.startswith('https://'):
                            proxy = f"http://{proxy}"
                        self.proxies.append(proxy)
        except Exception as e:
            logger.error(f"Ошибка при загрузке прокси из файла: {e}")
    
    def _load_default_proxies(self) -> None:
        """Загружает список встроенных бесплатных прокси."""
        # Примечание: это тестовые/демонстрационные прокси
        # В реальном приложении следует использовать платные прокси
        default_proxies = [
            "http://203.24.109.74:80",
            "http://85.239.54.119:8085",
            "http://45.156.31.59:9090",
            "http://138.199.48.1:8800",
            "http://185.199.229.156:7492"
        ]
        self.proxies = default_proxies
    
    async def get_current_proxy(self) -> Optional[str]:
        """Возвращает текущий прокси."""
        if not self.proxies:
            return None
        
        # Проверяем, нужно ли выполнить ротацию прокси
        current_time = time.time()
        if current_time - self.last_rotation_time > 300:  # Ротация каждые 5 минут
            self.rotate_proxy()
        
        return self.proxies[self.current_proxy_index]
    
    def rotate_proxy(self) -> None:
        """Выполняет ротацию прокси (переход к следующему прокси в списке)."""
        if not self.proxies:
            return
        
        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxies)
        self.last_rotation_time = time.time()
        logger.info(f"Прокси ротирован. Используется прокси #{self.current_proxy_index}: {self.proxies[self.current_proxy_index]}")
    
    async def check_proxy(self, proxy: str) -> bool:
        """Проверяет работоспособность прокси."""
        try:
            # Создаем SSL-контекст, который принимает любые сертификаты
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # Настраиваем таймаут для запроса
            timeout = aiohttp.ClientTimeout(total=10)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    "https://www.google.com", 
                    proxy=proxy,
                    ssl=ssl_context
                ) as response:
                    return response.status == 200
        except Exception as e:
            logger.debug(f"Прокси {proxy} не работает: {e}")
            return False
    
    async def get_working_proxy(self) -> Optional[str]:
        """Возвращает рабочий прокси, проверяя каждый прокси в списке."""
        if not self.proxies:
            return None
        
        # Пробуем найти рабочий прокси
        for i in range(len(self.proxies)):
            proxy = self.proxies[(self.current_proxy_index + i) % len(self.proxies)]
            
            if await self.check_proxy(proxy):
                # Обновляем индекс текущего прокси
                self.current_proxy_index = (self.current_proxy_index + i) % len(self.proxies)
                self.last_rotation_time = time.time()
                logger.info(f"Найден рабочий прокси: {proxy}")
                return proxy
        
        logger.warning("Не найдено рабочих прокси")
        return None


class ImageDownloader:
    """Класс для загрузки и обработки изображений."""
    
    def __init__(self, save_dir: Path, proxy_manager: Optional[ProxyManager] = None):
        """
        Инициализирует загрузчик изображений.
        
        Args:
            save_dir: Директория для сохранения изображений
            proxy_manager: Менеджер прокси для использования при загрузке
        """
        self.save_dir = save_dir
        self.proxy_manager = proxy_manager
        
        # Создаем директорию для сохранения изображений
        self.save_dir.mkdir(exist_ok=True)
    
    async def download_image(self, url: str, listing_id: str) -> Optional[str]:
        """
        Загружает изображение и возвращает путь к сохраненному файлу.
        
        Args:
            url: URL изображения
            listing_id: Идентификатор объявления
            
        Returns:
            str: Путь к сохраненному файлу или None в случае ошибки
        """
        if not url:
            return None
        
        # Извлекаем расширение файла из URL
        extension = self._get_file_extension(url)
        
        # Формируем имя файла
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{listing_id}_{timestamp}{extension}"
        file_path = self.save_dir / filename
        
        try:
            # Настраиваем SSL-контекст
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # Настраиваем прокси
            proxy = None
            if self.proxy_manager:
                proxy = await self.proxy_manager.get_current_proxy()
            
            # Загружаем изображение
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, 
                    proxy=proxy,
                    ssl=ssl_context,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        logger.warning(f"Не удалось загрузить изображение {url}, статус: {response.status}")
                        
                        # Если прокси используется, пробуем другой прокси
                        if self.proxy_manager:
                            self.proxy_manager.rotate_proxy()
                            proxy = await self.proxy_manager.get_current_proxy()
                            
                            # Повторяем запрос с новым прокси
                            async with session.get(
                                url, 
                                proxy=proxy,
                                ssl=ssl_context,
                                timeout=aiohttp.ClientTimeout(total=30)
                            ) as retry_response:
                                if retry_response.status != 200:
                                    logger.error(f"Повторная попытка не удалась: {retry_response.status}")
                                    return None
                                
                                # Читаем и сохраняем данные
                                data = await retry_response.read()
                        else:
                            return None
                    else:
                        # Читаем данные
                        data = await response.read()
                    
                    # Сохраняем изображение
                    with open(file_path, 'wb') as f:
                        f.write(data)
                    
                    logger.info(f"Изображение сохранено: {file_path}")
                    return str(file_path)
        except Exception as e:
            logger.error(f"Ошибка при загрузке изображения {url}: {e}")
            return None
    
    def _get_file_extension(self, url: str) -> str:
        """Извлекает расширение файла из URL."""
        # Проверяем наличие расширения в URL
        extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
        
        for ext in extensions:
            if url.lower().endswith(ext):
                return ext
        
        # Если расширение не найдено, пробуем извлечь из параметров URL
        if '.' in url and '?' in url:
            ext = url.split('?')[0].split('.')[-1].lower()
            if ext in ('jpg', 'jpeg', 'png', 'webp', 'gif'):
                return f".{ext}"
        
        # По умолчанию используем .jpg
        return '.jpg'


class SimpleMercadoLibreParser(BaseParser):
    """
    Упрощенный парсер для MercadoLibre - только для тестирования.
    """
    SOURCE_NAME = "mercadolibre"
    BASE_URL = "https://listado.mercadolibre.com.uy/inmuebles/terrenos/venta/"
    
    def __init__(self, headless_mode: bool = True, **kwargs):
        """Инициализирует парсер с базовыми параметрами."""
        # Настройка параметров для базового класса
        base_kwargs = {
            "headless_mode": headless_mode,
            "max_retries": 3,
            "request_delay": (2, 5)
        }
        
        # Добавляем другие параметры из kwargs, если они есть
        base_kwargs.update(kwargs)
        
        # Передаем в базовый класс
        super().__init__(**base_kwargs)
        
        logger.info("Инициализация SimpleMercadoLibreParser завершена")
        
        # Селекторы для элементов на странице списка
        self.list_selectors = {
            'item': 'li.ui-search-layout__item',
            'title': 'h2.ui-search-item__title',
            'price': 'span.price-tag-fraction',
            'currency': 'span.price-tag-symbol',
            'url': 'a.ui-search-link',  # Основной селектор для URL
            'url_alt': ['a.ui-search-link', 'div.ui-search-result__content a', 'h2.ui-search-item__title a'],  # Альтернативные селекторы
            'location': 'span.ui-search-item__location',
            'image': 'img.slick-slide, img.ui-search-result-image__element',
            'area': 'li.ui-search-card-attributes__attribute'
        }
        
        # Селекторы для страницы деталей
        self.detail_selectors = {
            'title': 'h1.ui-pdp-title',
            'price': 'span.andes-money-amount__fraction',
            'currency': 'span.andes-money-amount__currency-symbol',
            'location': 'p.ui-pdp-media__title',
            'description': 'div.ui-pdp-description__content',
            'image': 'img.ui-pdp-image',
            'area': 'tr:has-text("Superficie")'
        }
        
        # Создаем директории для сохранения результатов
        self.results_dir = Path(__file__).parent / 'test_results'
        self.results_dir.mkdir(exist_ok=True)
        
        self.images_dir = Path(__file__).parent / 'images'
        self.images_dir.mkdir(exist_ok=True)
        
        # Инициализируем множество для отслеживания обработанных URL
        self.seen_urls = set()
        
        # Глобальные статистические данные
        self.stats = {
            "pages_processed": 0,
            "listings_found": 0,
            "errors": 0,
            "images_downloaded": 0
        }
        
        # Создаем менеджер прокси
        self.proxy_manager = ProxyManager(proxy_file_path=Path(__file__).parent / 'proxies.txt')
        
        # Создаем загрузчик изображений
        self.image_downloader = ImageDownloader(self.images_dir, self.proxy_manager)

    @property
    def browser_closed(self) -> bool:
        """Проверяет, закрыт ли браузер."""
        return self.browser is None

    async def _get_page_url(self, page_number: int) -> str:
        """Возвращает URL для конкретной страницы с результатами."""
        if page_number == 1:
            return self.BASE_URL
        else:
            # MercadoLibre использует смещение в 48 элементов на страницу
            offset = (page_number - 1) * 48 + 1
            return f"{self.BASE_URL}_Desde_{offset}"

    async def _extract_listings_from_page(self, page):
        """Извлекает объявления со страницы списка."""
        listings = []
        
        # Ждем загрузку страницы с повторными попытками
        for attempt in range(3):
            try:
                await page.wait_for_selector(self.list_selectors['item'], timeout=30000)
                logger.info("Селектор карточек найден на странице")
                break
            except Exception as e:
                logger.error(f"Попытка {attempt+1}/3: Ошибка ожидания загрузки селектора карточек: {e}")
                
                if attempt < 2:
                    # Обновляем страницу и ждем
                    logger.info(f"Обновление страницы и повторная попытка через {(attempt+1)*3} сек...")
                    await asyncio.sleep((attempt+1) * 3)
                    await page.reload(wait_until="domcontentloaded", timeout=60000)
                else:
                    # Сохраняем скриншот и HTML для отладки
                    screenshot_path = self.results_dir / f"ml_error_page_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                    await page.screenshot(path=str(screenshot_path))
                    logger.info(f"Сохранен скриншот страницы с ошибкой: {screenshot_path}")
                    
                    html_path = self.results_dir / f"ml_error_page_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
                    html_content = await page.content()
                    with open(html_path, "w", encoding="utf-8") as f:
                        f.write(html_content)
                    logger.info(f"Сохранен HTML страницы с ошибкой: {html_path}")
                    
                    # Пробуем альтернативный метод для обхода ошибки
                    logger.info("Попытка альтернативного метода извлечения данных через JavaScript...")
                    try:
                        # Попытка извлечь данные напрямую через JavaScript
                        listings_data = await page.evaluate("""
                        () => {
                            const results = [];
                            
                            // Ищем любые элементы, которые могут быть карточками объявлений
                            const cards = Array.from(document.querySelectorAll('li[class*="layout__item"], div[class*="search-result"]'));
                            
                            for (const card of cards) {
                                try {
                                    // Извлекаем URL
                                    const links = Array.from(card.querySelectorAll('a')).filter(a => a.href && a.href.includes('MLU-'));
                                    const url = links.length > 0 ? links[0].href : null;
                                    
                                    if (!url) continue;
                                    
                                    // Извлекаем заголовок
                                    const titleElement = card.querySelector('h2[class*="title"]');
                                    const title = titleElement ? titleElement.innerText.trim() : "Без названия";
                                    
                                    // Извлекаем цену
                                    const priceElement = card.querySelector('[class*="price-tag"], [class*="andes-money"]');
                                    const price = priceElement ? priceElement.innerText.trim() : "Consultar";
                                    
                                    // Извлекаем местоположение
                                    const locationElement = card.querySelector('span[class*="location"], p[class*="location"]');
                                    const location = locationElement ? locationElement.innerText.trim() : "Uruguay";
                                    
                                    // Создаем объект с данными
                                    results.push({
                                        url,
                                        title,
                                        price,
                                        location
                                    });
                                } catch (e) {
                                    console.error('Ошибка при обработке карточки:', e);
                                }
                            }
                            
                            return results;
                        }
                        """)
                        
                        if listings_data and len(listings_data) > 0:
                            logger.info(f"Найдено {len(listings_data)} объявлений через JavaScript")
                            
                            # Преобразуем данные в объекты Listing
                            for i, data in enumerate(listings_data[:5]):  # Ограничиваем 5 объявлениями
                                try:
                                    listing = Listing(
                                        title=data.get('title', "Без названия"),
                                        url=data.get('url', ""),
                                        price=data.get('price', "Consultar"),
                                        location=data.get('location', "Uruguay"),
                                        source=self.SOURCE_NAME,
                                        date_scraped=self.now_utc()
                                    )
                                    
                                    listings.append(listing)
                                    self.stats["listings_found"] += 1
                                    logger.info(f"Создан объект Listing через JavaScript для объявления {i+1}")
                                except Exception as listing_err:
                                    logger.error(f"Ошибка при создании Listing из JavaScript-данных: {listing_err}")
                            
                            return listings
                    except Exception as js_err:
                        logger.error(f"Ошибка при использовании альтернативного метода: {js_err}")
                    
                    return []
        
        # Сохраняем скриншот страницы для отладки
        screenshot_path = self.results_dir / f"ml_page_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        await page.screenshot(path=str(screenshot_path))
        logger.info(f"Сохранен скриншот страницы: {screenshot_path}")
        
        # Сохраняем HTML страницы для отладки
        html_path = self.results_dir / f"ml_page_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        html_content = await page.content()
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        logger.info(f"Сохранен HTML страницы: {html_path}")
        
        # Получаем все карточки объявлений с повторными попытками
        items = await page.query_selector_all(self.list_selectors['item'])
        
        if not items or len(items) == 0:
            logger.warning("Не найдены карточки по основному селектору, пробую альтернативные селекторы")
            
            # Пробуем альтернативные селекторы
            alt_selectors = [
                'div.ui-search-result', 
                'li[class*="search-layout__item"]', 
                'div.ui-search-result__wrapper',
                'div[class*="search-layout"]'
            ]
            
            for selector in alt_selectors:
                items = await page.query_selector_all(selector)
                if items and len(items) > 0:
                    logger.info(f"Найдено {len(items)} карточек по альтернативному селектору: {selector}")
                    break
        
        if not items or len(items) == 0:
            logger.error("Не удалось найти карточки ни по одному из селекторов")
            return []
        
        logger.info(f"Найдено {len(items)} карточек объявлений на странице")
        
        # Для вывода статистики эффективности
        success_count = 0
        failed_count = 0
        skipped_count = 0
        
        # Обрабатываем первые 5 объявлений (для быстрого тестирования)
        for i, item in enumerate(items[:5]):
            try:
                # URL объявления - пробуем основной селектор
                url_el = await item.query_selector(self.list_selectors['url'])
                url = await url_el.get_attribute('href') if url_el else None
                
                # Если основной селектор не сработал, пробуем альтернативные
                if not url:
                    logger.warning(f"Карточка {i+1}: URL не найден по основному селектору, пробую альтернативные")
                    for alt_selector in self.list_selectors['url_alt']:
                        url_el = await item.query_selector(alt_selector)
                        if url_el:
                            url = await url_el.get_attribute('href')
                            if url:
                                logger.info(f"Карточка {i+1}: URL найден по альтернативному селектору '{alt_selector}'")
                                break
                
                # Если URL все еще не найден, пробуем JavaScript для извлечения всех ссылок
                if not url:
                    logger.warning(f"Карточка {i+1}: URL не найден по всем селекторам, пробую JavaScript")
                    try:
                        urls = await item.evaluate("""
                        (element) => {
                            const links = element.querySelectorAll('a');
                            return Array.from(links).map(a => a.href).filter(href => href.includes('articulo.mercadolibre') || href.includes('MLU-'));
                        }
                        """)
                        if urls and len(urls) > 0:
                            url = urls[0]
                            logger.info(f"Карточка {i+1}: URL найден через JavaScript: {url}")
                    except Exception as js_err:
                        logger.error(f"Карточка {i+1}: Ошибка при извлечении URL через JavaScript: {js_err}")
                
                # Последняя попытка: извлечь URL из общего JavaScript
                if not url:
                    try:
                        # Получаем позицию элемента на странице
                        position = await item.evaluate("element => Array.from(document.querySelectorAll('li.ui-search-layout__item')).indexOf(element)")
                        
                        # Используем все ссылки на странице и фильтруем по совпадению с позицией
                        all_urls = await page.evaluate("""
                        () => {
                            return Array.from(document.querySelectorAll('a')).map(a => a.href)
                                .filter(href => href.includes('articulo.mercadolibre') || href.includes('MLU-'));
                        }
                        """)
                        
                        if all_urls and len(all_urls) > 0 and position < len(all_urls):
                            url = all_urls[position]
                            logger.info(f"Карточка {i+1}: URL найден через общий JavaScript: {url}")
                    except Exception as js_global_err:
                        logger.error(f"Карточка {i+1}: Ошибка при извлечении URL через общий JavaScript: {js_global_err}")
                
                if not url:
                    logger.warning(f"Карточка {i+1}: URL не найден по всем методам, пропускаю карточку")
                    skipped_count += 1
                    continue
                
                # Пропускаем дубликаты
                if url in self.seen_urls:
                    logger.debug(f"Карточка {i+1}: URL уже обработан ранее: {url}")
                    skipped_count += 1
                    continue
                
                self.seen_urls.add(url)
                logger.info(f"Карточка {i+1}: Обрабатывается URL: {url}")
                
                # Заголовок
                title_el = await item.query_selector(self.list_selectors['title'])
                title = await title_el.inner_text() if title_el else "Без названия"
                logger.info(f"Карточка {i+1}: Заголовок: {title}")
                
                # Цена
                price_el = await item.query_selector(self.list_selectors['price'])
                currency_el = await item.query_selector(self.list_selectors['currency'])
                
                price_text = await price_el.inner_text() if price_el else None
                currency_text = await currency_el.inner_text() if currency_el else None
                
                price = f"{currency_text} {price_text}" if price_text and currency_text else "Consultar"
                logger.info(f"Карточка {i+1}: Цена: {price}")
                
                # Местоположение
                location_el = await item.query_selector(self.list_selectors['location'])
                location = await location_el.inner_text() if location_el else "Uruguay"
                logger.info(f"Карточка {i+1}: Местоположение: {location}")
                
                # Площадь (если есть)
                area_el = await item.query_selector(self.list_selectors['area'])
                area = await area_el.inner_text() if area_el else None
                logger.info(f"Карточка {i+1}: Площадь: {area}")
                
                # Изображение
                image_el = await item.query_selector(self.list_selectors['image'])
                image_url = await image_el.get_attribute('src') if image_el else None
                logger.info(f"Карточка {i+1}: URL изображения: {image_url}")
                
                # Генерируем ID для объявления
                listing_id = re.search(r'MLU-(\d+)', url)
                if listing_id:
                    listing_id = listing_id.group(1)
                else:
                    listing_id = f"ml_{int(time.time())}"
                
                # Создаем объект объявления
                listing = Listing(
                    id=listing_id,
                    title=title,
                    url=url,
                    price=price,
                    location=location,
                    source=self.SOURCE_NAME,
                    date_scraped=self.now_utc(),
                    area=area,
                    image_url=image_url
                )
                
                # Загружаем изображение, если URL доступен
                if image_url:
                    local_image_path = await self.image_downloader.download_image(image_url, listing_id)
                    if local_image_path:
                        listing.local_image_path = local_image_path
                        self.stats["images_downloaded"] += 1
                
                # Сохраняем информацию о каждом объявлении отдельно для отладки
                listing_data = listing.model_dump() if hasattr(listing, 'model_dump') else listing.dict()
                listing_file = self.results_dir / f"ml_obj{i+1}_data_{datetime.now().strftime('%H%M%S')}.json"
                with open(listing_file, 'w', encoding='utf-8') as f:
                    json.dump(listing_data, f, indent=2, ensure_ascii=False, default=str)
                logger.info(f"Сохранены данные объявления {i+1}: {listing_file}")
                
                listings.append(listing)
                self.stats["listings_found"] += 1
                success_count += 1
                
            except Exception as e:
                logger.error(f"Карточка {i+1}: Ошибка при обработке объявления: {e}", exc_info=True)
                self.stats["errors"] += 1
                failed_count += 1
        
        # Выводим статистику
        logger.info(f"Результаты обработки: успешно - {success_count}, пропущено - {skipped_count}, ошибок - {failed_count}")
        
        return listings
        
    async def run(self, max_pages: int = 1, headless: bool = True) -> List[Listing]:
        """Запускает парсер для указанного количества страниц."""
        all_listings = []
        
        try:
            logger.info(f"Запуск парсера с headless_mode={headless}, max_pages={max_pages}")
            
            # Получаем рабочий прокси (если поддерживается)
            working_proxy = None
            if self.proxy_manager and len(self.proxy_manager.proxies) > 0:
                working_proxy = await self.proxy_manager.get_working_proxy()
                if working_proxy:
                    logger.info(f"Используется прокси: {working_proxy}")
                else:
                    logger.warning("Не найден рабочий прокси. Продолжение без прокси.")
            
            # Запускаем браузер с нужными параметрами
            browser_launched = await self._init_browser()
            
            if not browser_launched:
                logger.error("Не удалось запустить браузер. Попытка с другими параметрами...")
                
                # Пробуем запустить без headless режима
                if headless:
                    logger.info("Попытка запуска браузера без headless режима")
                    self.headless_mode = False
                    browser_launched = await self._init_browser()
                
                # Если и это не помогло, завершаем работу
                if not browser_launched:
                    logger.error("Не удалось запустить браузер. Завершение работы.")
                    return []
            
            # Открываем новую страницу
            page = await self.browser.new_page()
            logger.info("Страница браузера создана")
            
            # Устанавливаем таймаут для загрузки страницы
            page.set_default_timeout(60000)  # 60 секунд
            
            # Устанавливаем пользовательский User-Agent
            user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 11.5; rv:90.0) Gecko/20100101 Firefox/90.0"
            ]
            
            await page.set_extra_http_headers({
                "User-Agent": random.choice(user_agents),
                "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1"
            })
            
            # Перебираем страницы результатов
            for page_num in range(1, max_pages + 1):
                try:
                    # Получаем URL страницы
                    page_url = await self._get_page_url(page_num)
                    logger.info(f"Обработка страницы {page_num}/{max_pages}: {page_url}")
                    
                    # Переходим на страницу с повторными попытками
                    success = False
                    for attempt in range(3):
                        try:
                            await page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
                            logger.info(f"Страница {page_num} загружена")
                            success = True
                            break
                        except Exception as nav_error:
                            logger.error(f"Попытка {attempt+1}/3: Ошибка при загрузке страницы: {nav_error}")
                            
                            if working_proxy and self.proxy_manager:
                                # Ротация прокси
                                self.proxy_manager.rotate_proxy()
                                working_proxy = await self.proxy_manager.get_current_proxy()
                                logger.info(f"Сменён прокси на: {working_proxy}")
                            
                            # Ждем перед повторной попыткой
                            await asyncio.sleep((attempt + 1) * 2)
                    
                    if not success:
                        logger.error(f"Не удалось загрузить страницу {page_num} после 3 попыток")
                        self.stats["errors"] += 1
                        continue
                    
                    # Ждем случайное время для имитации человеческого поведения
                    await page.wait_for_timeout(random.randint(2000, 5000))
                    
                    # Случайные действия для имитации человеческого поведения
                    await self._perform_human_actions(page)
                    
                    # Извлекаем объявления
                    page_listings = await self._extract_listings_from_page(page)
                    logger.info(f"Получено {len(page_listings)} объявлений со страницы {page_num}")
                    
                    # Добавляем в общий список
                    all_listings.extend(page_listings)
                    
                    # Обновляем статистику
                    self.stats["pages_processed"] += 1
                    
                    # Выполняем задержку перед следующей страницей
                    if page_num < max_pages:
                        delay = random.uniform(3.0, 7.0)
                        logger.info(f"Ожидание {delay:.1f} сек перед загрузкой следующей страницы...")
                        await asyncio.sleep(delay)
                    
                except Exception as e:
                    logger.error(f"Ошибка при обработке страницы {page_num}: {e}", exc_info=True)
                    self.stats["errors"] += 1
            
            return all_listings
            
        except Exception as e:
            logger.error(f"Критическая ошибка при запуске парсера: {e}", exc_info=True)
            return all_listings
        finally:
            # Закрываем браузер
            await self.close()
    
    async def _perform_human_actions(self, page):
        """Выполняет случайные действия на странице для имитации человеческого поведения."""
        try:
            # Имитация прокрутки страницы
            await page.evaluate("""
            () => {
                const scrollHeight = document.body.scrollHeight;
                const viewportHeight = window.innerHeight;
                const scrollSteps = Math.floor(scrollHeight / viewportHeight) + 1;
                
                // Плавно прокручиваем до случайной позиции
                const targetPosition = Math.random() * 0.7 * scrollHeight;
                window.scrollTo({
                    top: targetPosition,
                    behavior: 'smooth'
                });
            }
            """)
            
            # Ждем немного времени после прокрутки
            await page.wait_for_timeout(random.randint(800, 1500))
            
            # С некоторой вероятностью выполняем дополнительные действия
            if random.random() < 0.3:  # 30% вероятность
                # Прокрутка вверх и вниз
                await page.evaluate("""
                () => {
                    const scrollPosition = window.pageYOffset;
                    
                    // Прокрутка немного вверх
                    window.scrollTo({
                        top: scrollPosition - 100,
                        behavior: 'smooth'
                    });
                    
                    setTimeout(() => {
                        // Затем снова вниз
                        window.scrollTo({
                            top: scrollPosition,
                            behavior: 'smooth'
                        });
                    }, 700);
                }
                """)
                
                await page.wait_for_timeout(random.randint(500, 1200))
        except Exception as e:
            logger.debug(f"Ошибка при выполнении имитации человеческих действий: {e}")
            # Игнорируем ошибки, так как это некритичная функциональность

    async def _extract_data_from_detail_page(self, page, listing):
        """Извлекает детальную информацию с страницы объявления."""
        logger.info(f"Извлечение детальной информации для: {listing.url}")
        
        try:
            # Преобразуем URL в строку, если это HttpUrl объект (из pydantic)
            if hasattr(listing.url, '__str__'):
                url_str = str(listing.url)
            else:
                url_str = listing.url
                
            # Переходим на страницу объявления
            await page.goto(url_str, wait_until="domcontentloaded", timeout=60000)
            logger.info(f"Страница объявления загружена: {url_str}")
            
            # Ждем загрузки контента
            await page.wait_for_timeout(random.randint(2000, 4000))
            
            # Сохраняем скриншот страницы для отладки
            screenshot_path = self.results_dir / f"ml_detail_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            await page.screenshot(path=str(screenshot_path))
            logger.info(f"Сохранен скриншот страницы деталей: {screenshot_path}")
            
            # Сохраняем HTML страницы для отладки
            html_path = self.results_dir / f"ml_detail_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            html_content = await page.content()
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            logger.info(f"Сохранен HTML страницы деталей: {html_path}")
            
            # Извлекаем дополнительные данные
            
            # 1. Заголовок (если он не был найден ранее или был по умолчанию)
            if listing.title == "Без названия":
                title_el = await page.query_selector(self.detail_selectors['title'])
                if title_el:
                    listing.title = await title_el.inner_text()
                    logger.info(f"Обновлен заголовок: {listing.title}")
            
            # 2. Цена (если она не была найдена ранее или была по умолчанию)
            if listing.price == "Consultar":
                price_el = await page.query_selector(self.detail_selectors['price'])
                currency_el = await page.query_selector(self.detail_selectors['currency'])
                
                if price_el and currency_el:
                    price_text = await price_el.inner_text()
                    currency_text = await currency_el.inner_text()
                    
                    if price_text and currency_text:
                        listing.price = f"{currency_text} {price_text}"
                        logger.info(f"Обновлена цена: {listing.price}")
            
            # 3. Описание
            description_el = await page.query_selector(self.detail_selectors['description'])
            if description_el:
                listing.description = await description_el.inner_text()
                logger.info(f"Добавлено описание: {listing.description[:100]}...")
            
            # 4. Изображение (если оно не было найдено ранее)
            if not listing.image_url:
                image_el = await page.query_selector(self.detail_selectors['image'])
                if image_el:
                    listing.image_url = await image_el.get_attribute('src')
                    logger.info(f"Добавлен URL изображения: {listing.image_url}")
                
                # Если основной селектор не сработал, пробуем JavaScript
                if not listing.image_url:
                    try:
                        images = await page.evaluate("""
                        () => {
                            const images = Array.from(document.querySelectorAll('img')).filter(img => {
                                const src = img.src;
                                const width = img.width;
                                return src && src.includes('http') && !src.includes('data:') && width > 200;
                            }).map(img => img.src);
                            return images;
                        }
                        """)
                        
                        if images and len(images) > 0:
                            listing.image_url = images[0]
                            logger.info(f"Добавлен URL изображения через JavaScript: {listing.image_url}")
                    except Exception as js_err:
                        logger.error(f"Ошибка при извлечении изображений через JavaScript: {js_err}")
            
            # 5. Площадь (если она не была найдена ранее)
            if not listing.area:
                try:
                    # Извлекаем площадь через JavaScript
                    area_data = await page.evaluate("""
                    () => {
                        // Ищем по тексту ячейки таблицы характеристик
                        const rows = Array.from(document.querySelectorAll('tr'));
                        
                        // Ищем строку, содержащую упоминание о площади
                        const areaRow = rows.find(row => {
                            const text = row.innerText.toLowerCase();
                            return text.includes('superficie') || 
                                   text.includes('área') || 
                                   text.includes('terreno') || 
                                   text.includes('m²') ||
                                   text.includes('hectárea');
                        });
                        
                        if (areaRow) {
                            // Получаем значение
                            const value = areaRow.querySelector('td, span:nth-child(2)');
                            if (value) return value.innerText.trim();
                        }
                        
                        // Альтернативный поиск в тексте описания
                        const description = document.querySelector('.ui-pdp-description__content');
                        if (description) {
                            const text = description.innerText;
                            
                            // Ищем упоминания площади в описании
                            const m2Match = text.match(/(\d+(?:[\.,]\d+)?)\s*(?:m²|m2|metros cuadrados)/i);
                            if (m2Match) return m2Match[0];
                            
                            const haMatch = text.match(/(\d+(?:[\.,]\d+)?)\s*(?:ha|hectáreas|hectareas)/i);
                            if (haMatch) return haMatch[0];
                        }
                        
                        return null;
                    }
                    """)
                    
                    if area_data:
                        listing.area = area_data
                        logger.info(f"Добавлена площадь: {listing.area}")
                except Exception as area_err:
                    logger.error(f"Ошибка при извлечении площади: {area_err}")
            
            # 6. Местоположение (если оно не было найдено ранее или было по умолчанию)
            if listing.location == "Uruguay":
                location_el = await page.query_selector(self.detail_selectors['location'])
                if location_el:
                    location_text = await location_el.inner_text()
                    if location_text and location_text.strip():
                        listing.location = location_text.strip()
                        logger.info(f"Обновлено местоположение: {listing.location}")
                
                # Если селектор не сработал, пробуем через JavaScript
                if listing.location == "Uruguay":
                    try:
                        location_data = await page.evaluate("""
                        () => {
                            // Пытаемся найти местоположение в разных частях страницы
                            
                            // 1. В заголовке местоположения
                            const locationTitle = document.querySelector('.ui-pdp-media__title');
                            if (locationTitle) return locationTitle.innerText.trim();
                            
                            // 2. В хлебных крошках
                            const breadcrumbs = Array.from(document.querySelectorAll('.andes-breadcrumb__item'));
                            if (breadcrumbs.length > 1) return breadcrumbs[1].innerText.trim();
                            
                            // 3. В любом элементе с географическими данными
                            const geoElement = document.querySelector('[data-testid="map-location"], [itemprop="address"]');
                            if (geoElement) return geoElement.innerText.trim();
                            
                            return null;
                        }
                        """)
                        
                        if location_data:
                            listing.location = location_data
                            logger.info(f"Обновлено местоположение через JavaScript: {listing.location}")
                    except Exception as loc_err:
                        logger.error(f"Ошибка при извлечении местоположения через JavaScript: {loc_err}")
            
            # 7. Извлекаем дополнительные атрибуты (сервисы, удобства и т.д.)
            try:
                attributes = await page.evaluate("""
                () => {
                    const result = {};
                    
                    // Извлекаем данные из таблицы характеристик
                    const rows = Array.from(document.querySelectorAll('tr'));
                    rows.forEach(row => {
                        const cells = Array.from(row.querySelectorAll('th, td'));
                        if (cells.length >= 2) {
                            const key = cells[0].innerText.trim();
                            const value = cells[1].innerText.trim();
                            if (key && value) {
                                result[key] = value;
                            }
                        }
                    });
                    
                    // Извлекаем данные из выделенных спецификаций
                    const specs = Array.from(document.querySelectorAll('.ui-pdp-specs__table'));
                    specs.forEach(spec => {
                        const label = spec.querySelector('.ui-pdp-specs__table-label');
                        const value = spec.querySelector('.ui-pdp-specs__table-value');
                        if (label && value) {
                            result[label.innerText.trim()] = value.innerText.trim();
                        }
                    });
                    
                    return result;
                }
                """)
                
                if attributes and len(attributes) > 0:
                    listing.attributes = attributes
                    logger.info(f"Добавлены атрибуты: {attributes}")
            except Exception as attr_err:
                logger.error(f"Ошибка при извлечении атрибутов: {attr_err}")
            
            # 8. Извлечение координат (если есть)
            try:
                coordinates = await page.evaluate("""
                () => {
                    // Извлекаем координаты из скрипта с картой
                    const scripts = Array.from(document.querySelectorAll('script'));
                    
                    for (const script of scripts) {
                        const content = script.innerText || script.textContent;
                        if (content && (content.includes('latitude') || content.includes('longitude'))) {
                            const latMatch = content.match(/"latitude":\s*(-?\d+\.\d+)/);
                            const lngMatch = content.match(/"longitude":\s*(-?\d+\.\d+)/);
                            
                            if (latMatch && lngMatch) {
                                return {
                                    latitude: parseFloat(latMatch[1]),
                                    longitude: parseFloat(lngMatch[1])
                                };
                            }
                        }
                    }
                    
                    // Альтернативно, ищем в атрибутах элементов
                    const mapElement = document.querySelector('[data-latitude][data-longitude]');
                    if (mapElement) {
                        const lat = mapElement.getAttribute('data-latitude');
                        const lng = mapElement.getAttribute('data-longitude');
                        
                        if (lat && lng) {
                            return {
                                latitude: parseFloat(lat),
                                longitude: parseFloat(lng)
                            };
                        }
                    }
                    
                    return null;
                }
                """)
                
                if coordinates:
                    # Преобразуем словарь координат в кортеж (lat, lng)
                    coords_tuple = (coordinates.get('latitude'), coordinates.get('longitude'))
                    listing.coordinates = coords_tuple
                    logger.info(f"Добавлены координаты: {coords_tuple}")
            except Exception as coord_err:
                logger.error(f"Ошибка при извлечении координат: {coord_err}")
            
            return listing
            
        except Exception as e:
            logger.error(f"Ошибка при извлечении детальной информации: {e}", exc_info=True)
            return listing

    async def run_with_details(self, max_pages: int = 1, headless: bool = True) -> List[Listing]:
        """Запускает парсер с получением детальной информации для каждого объявления."""
        # Получаем базовый список объявлений
        listings = await self.run(max_pages=max_pages, headless=headless)
        
        if not listings:
            logger.warning("Не найдено объявлений для получения детальной информации")
            return []
        
        # Инициализируем браузер, если он закрыт
        if self.browser_closed:
            await self._init_browser()
        
        try:
            # Создаем новую страницу для деталей
            details_page = await self.browser.new_page()
            logger.info("Создана страница для получения деталей объявлений")
            
            # Устанавливаем таймаут
            details_page.set_default_timeout(60000)
            
            # Обрабатываем детали для каждого объявления
            detailed_listings = []
            
            for i, listing in enumerate(listings):
                logger.info(f"Получение деталей для объявления {i+1}/{len(listings)}: {listing.url}")
                
                try:
                    # Получаем детальную информацию
                    detailed_listing = await self._extract_data_from_detail_page(details_page, listing)
                    detailed_listings.append(detailed_listing)
                    
                    # Случайная задержка между запросами
                    if i < len(listings) - 1:
                        delay = random.uniform(2.0, 5.0)
                        logger.info(f"Ожидание {delay:.1f} сек перед следующим запросом...")
                        await asyncio.sleep(delay)
                    
                except Exception as e:
                    logger.error(f"Ошибка при получении деталей для {listing.url}: {e}", exc_info=True)
                    detailed_listings.append(listing)  # Добавляем оригинальное объявление без деталей
            
            return detailed_listings
            
        except Exception as e:
            logger.error(f"Критическая ошибка при получении деталей объявлений: {e}", exc_info=True)
            return listings
        finally:
            # Закрываем браузер
            await self.close()


async def main():
    """Основная функция для запуска тестирования."""
    logger.info("Запуск тестирования парсера MercadoLibre")
    
    try:
        # Создаем экземпляр парсера
        parser = SimpleMercadoLibreParser(headless_mode=True)
        logger.info("Парсер инициализирован")
        
        # Проверяем аргументы командной строки
        arg_parser = argparse.ArgumentParser(description="Тестирование парсера MercadoLibre")
        arg_parser.add_argument("--pages", type=int, default=1, help="Количество страниц для обработки")
        arg_parser.add_argument("--details", action="store_true", help="Получать детальную информацию по объявлениям")
        arg_parser.add_argument("--no-headless", action="store_true", help="Запускать браузер в видимом режиме")
        args = arg_parser.parse_args()
        
        headless_mode = not args.no_headless
        
        logger.info(f"Параметры запуска: страниц={args.pages}, детали={args.details}, headless={headless_mode}")
        
        # Создаем все необходимые директории
        for directory in ['test_results', 'test_backups', 'errors', 'data']:
            dir_path = Path(__file__).parent / directory
            dir_path.mkdir(exist_ok=True)
            
        # Запускаем парсер с соответствующими параметрами
        if args.details:
            logger.info("Запуск парсера с получением детальной информации")
            listings = await parser.run_with_details(max_pages=args.pages, headless=headless_mode)
        else:
            logger.info("Запуск парсера без получения детальной информации")
            listings = await parser.run(max_pages=args.pages, headless=headless_mode)
        
        logger.info(f"Получено {len(listings)} объявлений")
        
        # Проверяем, получили ли мы объявления
        if not listings:
            logger.warning("Не удалось получить объявления. Проверьте лог и отладочные данные.")
            return
        
        # Создаем резервную копию результатов
        backup_file = Path(__file__).parent / 'test_backups' / f"ml_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        # Сохраняем результаты в JSON
        results_file = parser.results_dir / f"ml_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        # Функция для сохранения результатов
        def save_results(file_path):
            with open(file_path, 'w', encoding='utf-8') as f:
                # Поддержка как для Pydantic v1, так и для v2
                if hasattr(listings[0], 'model_dump'):
                    listings_data = [listing.model_dump() for listing in listings]
                else:
                    listings_data = [listing.dict() for listing in listings]
                json.dump(listings_data, f, indent=2, ensure_ascii=False, default=str)
        
        # Сохраняем основной файл результатов
        try:
            save_results(results_file)
            logger.info(f"Результаты сохранены в {results_file}")
        except Exception as save_error:
            logger.error(f"Ошибка при сохранении результатов: {save_error}")
        
        # Сохраняем резервную копию
        try:
            save_results(backup_file)
            logger.info(f"Резервная копия сохранена в {backup_file}")
        except Exception as backup_error:
            logger.error(f"Ошибка при создании резервной копии: {backup_error}")
        
        # Вывод статистики
        logger.info(f"Статистика: {parser.stats}")
        
        # Выводим информацию о первых 3 объявлениях для проверки
        for i, listing in enumerate(listings[:3]):
            logger.info(f"--- Объявление {i+1} ---")
            logger.info(f"URL: {listing.url}")
            logger.info(f"Заголовок: {listing.title}")
            logger.info(f"Цена: {listing.price}")
            logger.info(f"Местоположение: {listing.location}")
            if listing.area:
                logger.info(f"Площадь: {listing.area}")
            if listing.description:
                logger.info(f"Описание: {listing.description[:100]}...")
            if listing.image_url:
                logger.info(f"URL изображения: {listing.image_url}")
            if listing.attributes:
                logger.info(f"Атрибуты: {listing.attributes}")
            if listing.coordinates:
                logger.info(f"Координаты: {listing.coordinates}")
        
    except Exception as e:
        logger.error(f"Ошибка при запуске парсера: {e}", exc_info=True)
    finally:
        # Закрываем ресурсы парсера, если они еще не закрыты
        if 'parser' in locals() and parser and not parser.browser_closed:
            await parser.close()


if __name__ == "__main__":
    try:
        # Создаем все необходимые директории
        for directory in ['test_results', 'test_backups', 'errors', 'data']:
            dir_path = Path(__file__).parent / directory
            dir_path.mkdir(exist_ok=True)
            
        # Запускаем асинхронную функцию
        asyncio.run(main())
        logger.info("Тестирование завершено успешно")
    except KeyboardInterrupt:
        logger.info("Тестирование прервано пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True) 