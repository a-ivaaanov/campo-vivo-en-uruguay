#!/usr/bin/env python3
"""
Парсер для MercadoLibre.com.uy
"""

import os
import re
import json
import asyncio
import random
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Set, Tuple, Union, cast
from urllib.parse import urljoin
from pathlib import Path

from playwright.async_api import Page, ElementHandle, TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from .base import BaseParser, RetryException
from app.models import Listing
from app.utils.ai_selectors import find_element_by_ai, smart_find_element

# Получаем логгер
logger = logging.getLogger(__name__)

# Вспомогательные функции, которые обычно находятся в отдельных модулях
def clean_text(text: str) -> str:
    """Очищает текст от лишних пробелов и переносов строк."""
    if not text:
        return ""
    # Заменяем несколько пробелов на один
    text = re.sub(r'\s+', ' ', text)
    # Убираем пробелы в начале и конце
    return text.strip()

def extract_first_number(text: str) -> Optional[float]:
    """Извлекает первое число из текста."""
    if not text:
        return None
    match = re.search(r'(\d+[.,]?\d*)', text)
    if match:
        number_str = match.group(1).replace(',', '.')
        try:
            return float(number_str)
        except ValueError:
            return None
    return None

async def get_browser_context(headless: bool = True, proxy_config: Optional[Dict[str, str]] = None):
    """Создает и возвращает контекст браузера Playwright."""
    # Заглушка для функции, которая обычно находится в browser_utils
    # В реальном коде здесь должен быть полноценный метод создания контекста
    return None

class MercadoLibreParser(BaseParser):
    """
    Парсер для MercadoLibre.com.uy
    Реализует специфическую логику для сайта MercadoLibre.
    """
    SOURCE_NAME = "mercadolibre"
    BASE_URL = "https://www.mercadolibre.com.uy"
    
    # Константы для генерации URL
    URL_TEMPLATE = "https://listado.mercadolibre.com.uy/inmuebles/terrenos/terrenos_Desde_{offset}_NoIndex_True"
    ITEMS_PER_PAGE = 48
    
    # Ограничения и настройки
    MAX_CONCURRENT_DETAIL_PAGES = 4  # Максимальное количество одновременно открытых страниц деталей
    DETAIL_PAGE_TIMEOUT = 90000  # Таймаут для страницы деталей (мс)
    PAGE_LOAD_TIMEOUT = 60000  # Общий таймаут загрузки страницы (мс)
    
    # Селекторы для карточек объявлений
    CARD_SELECTORS = [
        'div.ui-search-result', 
        'li.ui-search-layout__item',
        'div[class*="ui-search-result"]',
        'article.ui-search-layout__item'
    ]
    
    # Селекторы для ожидания загрузки страницы
    WAIT_SELECTORS = [
        'div.ui-search-result',
        'div.ui-search-layout',
        'div.ui-search-breadcrumb',
        'nav.andes-breadcrumb'
    ]
    
    # Индикаторы блокировки и каптчи
    CAPTCHA_INDICATORS = [
        "captcha", "robot", "i am not a robot", "verification", "verify", 
        "cloudflare", "DDoS protection", "automated request", "bot detection"
    ]
    
    BLOCK_INDICATORS = [
        "access denied", "denied access", "ip has been blocked", "too many requests",
        "rate limiting", "blocked", "429 Too Many Requests", "403 Forbidden", 
        "has been temporarily limited", "unusual traffic"
    ]
    
    # Обновляем селекторы с добавлением запасных вариантов
    SELECTORS = {
        # Карточки листингов
        "listing_cards": [
            "div.ui-search-result",
            "li.ui-search-layout__item",
            "div[class*='search-results-item']",  # Альтернативный селектор
            "ol.ui-search-layout li",  # Еще один запасной селектор
        ],
        "card_url": [
            "a.ui-search-link",
            "a.ui-search-result__content",
            "a[href*='/MLU-']",  # Запасной селектор по паттерну URL
        ],
        "card_title": [
            "h2.ui-search-item__title",
            ".ui-search-item__group--title h2",
            "h2[class*='item__title']",  # Запасной селектор
        ],
        "card_price": [
            "span.price-tag-amount",
            ".ui-search-price__second-line span.price-tag-amount",
            ".price-tag-amount",  # Упрощенный запасной селектор
        ],
        "card_location": [
            "span.ui-search-item__location-label",
            ".ui-search-item__group--location span",
            "span[class*='location']",  # Запасной селектор
        ],
        "card_area": [
            "li.ui-search-card-attributes__attribute",
            "span.ui-search-card-attributes__attribute",
            "[class*='attributes'] span", # Запасной селектор
        ],
        "card_image": [
            "img.ui-search-result-image__element",
            "img[data-src]",
            "img[src*='http']",  # Запасной селектор
        ],
        
        # Страница деталей
        "detail_title": [
            "h1.ui-pdp-title",
            ".ui-pdp-container h1",
            "h1[class*='title']", # Запасной селектор
        ],
        "detail_price": [
            "span.andes-money-amount__fraction",
            ".ui-pdp-price__second-line span.andes-money-amount__fraction",
            "span[class*='price']", # Запасной селектор
        ],
        "detail_location": [
            ".ui-pdp-media__title",
            ".ui-vip-location__title",
            "h2[class*='location']", # Запасной селектор
            "div[class*='location']", # Еще один запасной селектор 
        ],
        "detail_description": [
            ".ui-pdp-description__content",
            "p.ui-pdp-description__content",
            "div[class*='description']", # Запасной селектор
        ],
        "detail_seller": [
            ".ui-pdp-seller__header__title",
            ".ui-pdp-action-modal h2",
            "span[class*='seller']", # Запасной селектор
        ],
        "detail_attributes": [
            ".ui-pdp-specs__table",
            ".ui-vip-specifications__table",
            "table[class*='specs']", # Запасной селектор
        ],
        "detail_images": [
            ".ui-pdp-gallery__figure img",
            ".ui-pdp-thumbnail__image",
            "img[class*='gallery']", # Запасной селектор
            "img[data-zoom]", # Запасной селектор по атрибуту
        ],
        
        # Области с характеристиками
        "area_section": [
            "tr th:contains('Superficie total'), tr td",
            "tr th:contains('Área total'), tr td",
            "tr th:contains('Área del terreno'), tr td",
            "tr th:contains('Superficie del terreno'), tr td",
            "tr th:contains('Superficie del lote'), tr td",
            "tr:contains('Superficie'), tr:contains('Área')",  # Запасной селектор
            "div.ui-pdp-specs table tr",  # Общий селектор для таблицы характеристик
        ],
        
        # Селекторы для коммуникаций
        "utilities_section": [
            "tr th:contains('Servicios'), tr td",
            "tr th:contains('Servicios públicos'), tr td",
            "div:contains('Servicios')",
            "section:contains('Servicios')",
        ],
        
        # Селекторы для зонирования
        "zoning_section": [
            "tr th:contains('Zonificación'), tr td",
            "tr th:contains('Tipo de zona'), tr td",
            "div:contains('Zonificación')",
            "section:contains('Zonificación')",
            "p:contains('zona')", # Запасной селектор для поиска в описании
        ],
    }
    
    def __init__(self, 
                 proxy_manager = None,
                 headless_mode: bool = True, 
                 min_request_delay: float = 2.0,
                 max_request_delay: float = 5.0,
                 max_retries: int = 5):
        """
        Инициализация парсера MercadoLibre.
        
        Args:
            proxy_manager: Менеджер прокси-серверов (если None, будет создан новый)
            headless_mode: Запускать браузер в фоновом режиме
            min_request_delay: Минимальная задержка между запросами в секундах
            max_request_delay: Максимальная задержка между запросами в секундах
            max_retries: Максимальное число повторных попыток при ошибках
        """
        super().__init__()
        self.headless_mode = headless_mode
        self.min_request_delay = min_request_delay
        self.max_request_delay = max_request_delay
        self.max_retries = max_retries
        self.logger = logging.getLogger(__name__)
        
        # Инициализация или использование существующего менеджера прокси
        if proxy_manager is None:
            from app.utils.proxy_manager import ProxyManager
            self.proxy_manager = ProxyManager()
        else:
            self.proxy_manager = proxy_manager
            
        # Получаем оптимальный прокси для использования
        self.proxy = self.proxy_manager.get_proxy()
        
        self.semaphore = None  # Будет инициализирован в run()
        self.browser = None
        self.context = None
        self.current_page = None
        
        self.logger.info(f"Инициализирован парсер {self.SOURCE_NAME}" + 
                       (f" с прокси {self.proxy}" if self.proxy else " без прокси"))
    
    async def _init_browser(self) -> bool:
        """
        Инициализирует браузер и контекст с защитой от обнаружения.
        
        Returns:
            bool: True, если браузер успешно инициализирован
        """
        try:
            self.logger.info(f"Инициализация браузера (headless={self.headless_mode})")
            
            # Запускаем Playwright
            playwright = await async_playwright().start()
            
            # Создаем конфигурацию для запуска браузера
            browser_config = {
                "headless": self.headless_mode
            }
            
            # Запуск браузера
            self.browser = await playwright.chromium.launch(**browser_config)
            
            # Опции для контекста браузера
            context_options = self._generate_browser_context_options()
            
            # Создаем контекст
            self.context = await self.browser.new_context(**context_options)
            
            # Устанавливаем таймауты для всех страниц
            self.context.set_default_timeout(self.PAGE_LOAD_TIMEOUT)
            
            # Применяем дополнительные методы для маскировки автоматизации
            # Примечание: stealth_async удален, так как он недоступен
            test_page = await self.context.new_page()
            await test_page.close()
            
            self.logger.info("Браузер успешно инициализирован")
            return True
                
        except Exception as e:
            self.logger.error(f"Ошибка при инициализации браузера: {e}")
            await self.close()
            raise RetryException(f"Ошибка инициализации браузера: {str(e)}")
    
    def _generate_browser_context_options(self) -> Dict[str, Any]:
        """
        Генерирует опции для контекста браузера с учетом прокси.
        
        Returns:
            Dict[str, Any]: Опции для создания контекста браузера
        """
        # Базовые опции контекста
        options = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": self._get_random_user_agent(),
            "locale": "es-UY",
            "timezone_id": "America/Montevideo",
            "geolocation": {
                "longitude": -56.1645, 
                "latitude": -34.9011
            },
            "permissions": ["geolocation"],
            "color_scheme": "light",
            "reduced_motion": "no-preference",
            "has_touch": False
        }
        
        # Добавляем настройки прокси, если он указан
        if self.proxy:
            # Формируем настройки прокси в зависимости от формата
            if isinstance(self.proxy, dict):
                # Если передан словарь с настройками
                server = self.proxy.get('server')
                if server:
                    proxy_config = {"server": server}
                    
                    # Добавляем учетные данные, если они указаны
                    if 'user_pattern' in self.proxy and 'password' in self.proxy:
                        proxy_config['username'] = self.proxy['user_pattern']
                        proxy_config['password'] = self.proxy['password']
                    
                    options["proxy"] = proxy_config
            elif isinstance(self.proxy, str):
                # Если передана строка с адресом прокси
                options["proxy"] = {"server": self.proxy}
        
        return options
    
    async def _create_new_page(self) -> Page:
        """
        Создает новую страницу с применением stealth режима.
        
        Returns:
            Page: Новая страница браузера
        """
        page = await self.context.new_page()
        # Удалено использование stealth_async
        return page
    
    async def close(self):
        """Закрывает браузер и освобождает ресурсы."""
        try:
            if self.context:
                await self.context.close()
                self.context = None
                
            if self.browser:
                await self.browser.close()
                self.browser = None
                
            self.logger.info("Браузер успешно закрыт")
        except Exception as e:
            self.logger.error(f"Ошибка при закрытии браузера: {e}")
            
    async def _is_captcha_present(self, page: Page) -> bool:
        """
        Проверяет наличие каптчи на странице.
        
        Args:
            page: Страница для проверки
            
        Returns:
            bool: True, если обнаружена каптча
        """
        try:
            # Получаем HTML содержимое страницы
            content = await page.content()
            html_lower = content.lower()
            
            # Проверяем наличие индикаторов каптчи
            for indicator in self.CAPTCHA_INDICATORS:
                if indicator in html_lower:
                    self.logger.warning(f"Обнаружен индикатор каптчи: '{indicator}'")
                    return True
            
            # Проверяем наличие элементов каптчи
            captcha_selectors = [
                "iframe[src*='captcha']",
                "iframe[src*='recaptcha']",
                "iframe[src*='cloudflare']",
                "div.g-recaptcha",
                "div[class*='captcha']"
            ]
            
            for selector in captcha_selectors:
                element = await page.query_selector(selector)
                if element:
                    self.logger.warning(f"Обнаружен элемент каптчи: '{selector}'")
                    return True
                    
            return False
        except Exception as e:
            self.logger.error(f"Ошибка при проверке наличия каптчи: {e}")
            return False
    
    async def _is_page_blocked(self, page: Page) -> bool:
        """
        Проверяет, заблокирована ли страница.
        
        Args:
            page: Страница для проверки
            
        Returns:
            bool: True, если страница заблокирована
        """
        try:
            # Проверяем код ответа
            response = await page.evaluate("window.performance.getEntries()[0].responseStatus")
            if response and response in [403, 429, 503]:
                self.logger.warning(f"Обнаружена блокировка по коду ответа: {response}")
                return True
            
            # Получаем HTML содержимое страницы
            content = await page.content()
            html_lower = content.lower()
            
            # Проверяем наличие индикаторов блокировки
            for indicator in self.BLOCK_INDICATORS:
                if indicator in html_lower:
                    self.logger.warning(f"Обнаружен индикатор блокировки: '{indicator}'")
                    return True
            
            return False
        except Exception as e:
            self.logger.error(f"Ошибка при проверке блокировки страницы: {e}")
            return False
            
    async def _handle_captcha(self, page: Page) -> bool:
        """
        Пытается обработать каптчу.
        В текущей версии - только меняет прокси и перезагружает страницу.
        
        Args:
            page: Страница с каптчей
            
        Returns:
            bool: True, если удалось обойти каптчу
        """
        self.logger.warning("Обнаружена каптча, пытаемся обойти...")
        
        # Сообщаем прокси-менеджеру об ошибке каптчи
        if self.proxy:
            self.proxy_manager.report_error(self.proxy, error_type="captcha")
        
        # Получаем новый прокси
        new_proxy = self.proxy_manager.get_proxy()
        if not new_proxy:
            self.logger.error("Нет доступных прокси для обхода каптчи")
            return False
        
        self.logger.info(f"Меняем прокси на {new_proxy.get('server', new_proxy)} и перезагружаем страницу")
        
        # Меняем прокси
        self.proxy = new_proxy
        
        # Закрываем текущий контекст
        if self.context:
            await self.context.close()
        
        # Создаем новый контекст с новым прокси
        context_options = self._generate_browser_context_options()
        self.context = await self.browser.new_context(**context_options)
        
        # Устанавливаем таймауты
        self.context.set_default_timeout(self.PAGE_LOAD_TIMEOUT)
        
        # Применяем стелс-методы
        # Примечание: stealth_async удален, так как он недоступен
        test_page = await self.context.new_page()
        await test_page.close()
        
        return True
    
    async def _wait_for_page_load(self, page: Page, url: str, timeout: int = None) -> bool:
        """
        Ожидает загрузки страницы и проверяет наличие каптчи/блокировки.
        
        Args:
            page: Страница для проверки
            url: URL для загрузки
            timeout: Таймаут ожидания в миллисекундах
            
        Returns:
            bool: True, если страница успешно загружена
        """
        if timeout is None:
            timeout = self.PAGE_LOAD_TIMEOUT
            
        try:
            # Загружаем страницу
            await page.goto(url, timeout=timeout)
            
            # Ждем загрузки DOM
            await page.wait_for_load_state("domcontentloaded")
            
            # Пытаемся дождаться появления хотя бы одного из селекторов
            for selector in self.WAIT_SELECTORS:
                try:
                    await page.wait_for_selector(selector, timeout=5000)
                    self.logger.debug(f"Страница загружена, найден селектор: {selector}")
                    break
                except:
                    continue
            
            # Делаем дополнительную паузу для подгрузки динамического контента
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
            # Проверяем наличие каптчи
            if await self._is_captcha_present(page):
                self.logger.warning(f"Обнаружена каптча при загрузке {url}")
                if await self._handle_captcha(page):
                    # Если удалось обойти каптчу, перезагружаем страницу
                    return await self._wait_for_page_load(page, url, timeout)
                return False
            
            # Проверяем блокировку
            if await self._is_page_blocked(page):
                self.logger.warning(f"Обнаружена блокировка при загрузке {url}")
                if self.proxy:
                    self.proxy_manager.report_error(self.proxy, error_type="blocked")
                    # Получаем новый прокси и пробуем заново
                    new_proxy = self.proxy_manager.get_proxy()
                    if new_proxy:
                        self.proxy = new_proxy
                        # Закрываем текущий контекст
                        if self.context:
                            await self.context.close()
                        
                        # Создаем новый контекст с новым прокси
                        context_options = self._generate_browser_context_options()
                        self.context = await self.browser.new_context(**context_options)
                        
                        # Устанавливаем таймауты
                        self.context.set_default_timeout(self.PAGE_LOAD_TIMEOUT)
                        
                        # Создаем новую страницу
                        page = await self._create_new_page()
                        
                        # Пробуем снова загрузить страницу
                        return await self._wait_for_page_load(page, url, timeout)
                return False
            
            # Имитируем человеческое поведение
            await self._simulate_human_behavior(page)
            
            return True
            
        except PlaywrightTimeoutError:
            self.logger.error(f"Таймаут при загрузке страницы {url}")
            if self.proxy:
                self.proxy_manager.report_error(self.proxy, error_type="timeout")
            return False
        except Exception as e:
            self.logger.error(f"Ошибка при загрузке страницы {url}: {e}")
            return False

    async def _get_page_url(self, page_number: int) -> str:
        """Возвращает URL для страницы результатов MercadoLibre."""
        # У MercadoLibre URL меняется иначе - через параметр _Desde
        if page_number == 1:
            # Для первой страницы используем базовый URL без сортировки
            return self.BASE_URL.rstrip("/")
        else:
            # Для последующих страниц добавляем смещение и сортировку по цене (_OrderId_PRICE)
            # Каждый элемент - 1 лот, на странице обычно 48
            offset = (page_number - 1) * 48 + 1
            return f"{self.BASE_URL.rstrip('/')}_Desde_{offset}_OrderId_PRICE"
            
    def _add_random_delay(self):
        """
        Добавляет случайную задержку между запросами для имитации человеческого поведения
        и снижения вероятности блокировки.
        """
        delay = random.uniform(self.min_request_delay, self.max_request_delay)
        self.logger.debug(f"Случайная задержка: {delay:.2f} секунд")
        return asyncio.sleep(delay)
        
    async def _get_listing_details(
        self, page: Page, listing: Listing, only_missing: bool = True
    ) -> Optional[Listing]:
        """
        Получает детальную информацию о листинге.
        
        Args:
            page: Инстанс страницы Playwright
            listing: Объект листинга с базовой информацией
            only_missing: Получать только отсутствующие данные
            
        Returns:
            Обновленный объект листинга с детальной информацией или None в случае ошибки
        """
        if not listing.url:
            self.logger.error(f"No URL for listing: {listing}")
            return None
            
        try:
            self.logger.info(f"Getting details for listing: {listing.url}")
            
            # Добавляем случайную задержку перед запросом
            await self._add_random_delay()
            
            # Переходим на страницу объявления
            await page.goto(listing.url, timeout=30000)
            await page.wait_for_load_state("domcontentloaded")
            
            # Дополнительная случайная задержка перед парсингом данных
            await self._add_random_delay()
            
            # Проверка на наличие каптчи
            if await self._is_captcha_present(page):
                self.logger.warning("Captcha detected, trying to solve...")
                if not await self._handle_captcha(page):
                    self.logger.error("Failed to solve captcha")
                    return None
            
            # Получаем детальную информацию
            # Используя AI селекторы и стандартные методы
            
            # Извлекаем основную информацию
            title = await self._extract_title(page)
            price = await self._extract_price(page)
            description = await self._extract_description(page)
            location = await self._extract_location(page)
            area = await self._extract_area_size(page)
            utilities = await self._extract_utilities(page)
            image_url = await self._extract_main_image(page, str(listing.url))
            
            # Обновляем объект листинга
            if title:
                listing.title = title
            if price:
                listing.price = price
            if description:
                listing.description = description
            if location:
                listing.location = location
            if area:
                listing.area = area
            if utilities:
                listing.utilities = utilities
            if image_url:
                listing.image_url = image_url
            
            # Дополнительные атрибуты
            listing.source = self.SOURCE_NAME
            listing.date_scraped = datetime.now()
            
            return listing
            
        except PlaywrightTimeoutError as e:
            self.logger.error(f"Timeout error when getting details for {listing.url}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error getting details for listing {listing.url}: {e}")
            return None

    async def _extract_card_data_with_ai(self, page: Page, card: ElementHandle, index: int) -> Dict[str, Any]:
        """
        Извлекает данные из карточки объявления с использованием AI-селекторов.
        
        Args:
            page: Объект страницы для выполнения JavaScript
            card: Элемент карточки объявления
            index: Индекс карточки для логирования
            
        Returns:
            Dict[str, Any]: Словарь с данными объявления
        """
        self.logger.debug(f"--- Начало обработки карточки {index+1} через AI-селекторы ---")
        listing_data = {
            'source': self.SOURCE_NAME,
            'date_scraped': datetime.now()
        }
        
        try:
            # 1. Извлечение URL
            url_elem = await smart_find_element(card, "url", "Найди ссылку на объявление о продаже земельного участка")
            
            if url_elem:
                href = await url_elem.get_attribute('href')
                if href and href.startswith('http'):
                    listing_data['url'] = href
                    self.logger.debug(f"Карточка {index+1}: URL найден через AI: {href}")
            
            # Если AI-селектор не сработал, используем стандартные методы
            if 'url' not in listing_data:
                self.logger.debug(f"Карточка {index+1}: URL не найден через AI, пробуем стандартные селекторы")
                
                for selector in [self.list_selectors['url']] + self.list_selectors['url_alt']:
                    url_elem = await card.query_selector(selector)
                    if url_elem:
                        href = await url_elem.get_attribute('href')
                        if href and href.startswith('http'):
                            listing_data['url'] = href
                            self.logger.debug(f"Карточка {index+1}: URL найден по селектору: {href}")
                            break
                
                # Если URL не найден, пропускаем карточку
                if 'url' not in listing_data:
                    self.logger.warning(f"Карточка {index+1}: URL не найден, пропуск карточки")
                    return {}
            
            # 2. Извлечение заголовка
            title_elem = await smart_find_element(card, "title", "Найди заголовок объявления о земельном участке")
            if title_elem:
                title = await title_elem.inner_text()
                if title and title.strip():
                    listing_data['title'] = title.strip()
                    self.logger.debug(f"Карточка {index+1}: Заголовок найден через AI: {title.strip()}")
            
            # Если AI не сработал, пробуем стандартные селекторы для заголовка
            if 'title' not in listing_data:
                for selector in [self.list_selectors['title']] + self.list_selectors['title_alt']:
                    title_elem = await card.query_selector(selector)
                    if title_elem:
                        title = await title_elem.inner_text()
                        if title and title.strip():
                            listing_data['title'] = title.strip()
                            self.logger.debug(f"Карточка {index+1}: Заголовок найден по селектору: {title.strip()}")
                            break
            
            # 3. Извлечение цены
            price_context = await card.inner_text()
            price_elem = await smart_find_element(card, "price", 
                                           "Найди цену объявления о земельном участке. Она состоит из валюты и суммы.")
            
            if price_elem:
                price_text = await price_elem.inner_text()
                if price_text and price_text.strip():
                    # Обработка текста цены (может включать валюту и сумму)
                    price_text = price_text.strip()
                    listing_data['price'] = price_text
                    self.logger.debug(f"Карточка {index+1}: Цена найдена через AI: {price_text}")
            
            # Если AI не сработал, пробуем стандартные селекторы для цены
            if 'price' not in listing_data:
                # Поиск цены и валюты отдельно
                price_elem = await card.query_selector(self.list_selectors['price'])
                currency_elem = await card.query_selector(self.list_selectors['currency'])
                
                if price_elem and currency_elem:
                    price_fraction = await price_elem.inner_text()
                    price_currency = await currency_elem.inner_text()
                    
                    if price_fraction and price_currency:
                        listing_data['price'] = f"{price_currency.strip()} {price_fraction.strip()}".strip()
                        self.logger.debug(f"Карточка {index+1}: Цена найдена по селекторам: {listing_data['price']}")
            
            # 4. Извлечение локации
            location_elem = await smart_find_element(card, "location", 
                                               "Найди местоположение земельного участка (город, район)")
            
            if location_elem:
                location = await location_elem.inner_text()
                if location and location.strip():
                    listing_data['location'] = location.strip()
                    self.logger.debug(f"Карточка {index+1}: Локация найдена через AI: {location.strip()}")
            
            # Если AI не сработал, пробуем стандартные селекторы для локации
            if 'location' not in listing_data:
                for selector in [self.list_selectors['address']] + self.list_selectors['address_alt']:
                    location_elem = await card.query_selector(selector)
                    if location_elem:
                        location = await location_elem.inner_text()
                        if location and location.strip():
                            listing_data['location'] = location.strip()
                            self.logger.debug(f"Карточка {index+1}: Локация найдена по селектору: {location.strip()}")
                            break
            
            # 5. Извлечение площади
            area_elem = await smart_find_element(card, "area", 
                                          "Найди площадь земельного участка (может быть в м² или гектарах)")
            
            if area_elem:
                area = await area_elem.inner_text()
                if area and area.strip():
                    listing_data['area'] = area.strip()
                    self.logger.debug(f"Карточка {index+1}: Площадь найдена через AI: {area.strip()}")
            
            # Если AI не сработал, пробуем обычные селекторы
            if 'area' not in listing_data:
                area_elements = await card.query_selector_all(self.list_selectors['area'])
                
                for element in area_elements:
                    area_text = await element.inner_text()
                    if area_text and ('m²' in area_text or 'ha' in area_text.lower()):
                        listing_data['area'] = area_text.strip()
                        self.logger.debug(f"Карточка {index+1}: Площадь найдена по селектору: {area_text.strip()}")
                        break
            
            # 6. Извлечение URL изображения
            image_elem = await smart_find_element(card, "image", 
                                            "Найди основное изображение земельного участка")
            
            if image_elem:
                for attr in ['src', 'data-src']:
                    img_url = await image_elem.get_attribute(attr)
                    if img_url and img_url.startswith('http') and not img_url.startswith('data:'):
                        listing_data['image_url'] = img_url
                        self.logger.debug(f"Карточка {index+1}: Изображение найдено через AI: {img_url[:50]}...")
                        break
            
            # Если AI не сработал, пробуем обычные селекторы
            if 'image_url' not in listing_data:
                img_elem = await card.query_selector(self.list_selectors['image'])
                
                if img_elem:
                    for attr in ['src', 'data-src']:
                        img_url = await img_elem.get_attribute(attr)
                        if img_url and img_url.startswith('http') and not img_url.startswith('data:'):
                            listing_data['image_url'] = img_url
                            self.logger.debug(f"Карточка {index+1}: Изображение найдено по селектору: {img_url[:50]}...")
                            break
            
            # 7. Устанавливаем значения по умолчанию для оставшихся полей
            listing_data.setdefault('description', None)
            listing_data.setdefault('utilities', None)
            listing_data.setdefault('deal_type', 'Venta')
            
            return listing_data
        
        except Exception as e:
            self.logger.error(f"Карточка {index+1}: Ошибка при извлечении данных через AI: {e}")
            return {}

    async def _extract_listings_from_page(self, page: Page) -> List[Listing]:
        """
        Извлекает объявления со страницы поиска MercadoLibre.
        
        Args:
            page: Объект страницы браузера
            
        Returns:
            List[Listing]: Список объявлений
        """
        listings = []
        cards = []
        
        self.logger.debug("Ожидание загрузки карточек объявлений...")
        
        # Проверяем и закрываем диалог о куках, если появился
        await self._handle_cookie_dialog(page)
        
        # Имитируем поведение человека (скроллинг, паузы)
        await self._simulate_human_behavior(page)
        
        # Пытаемся найти карточки объявлений
        for attempt in range(3):
            try:
                # Попытка найти карточки через разные селекторы
                for selector in self.CARD_SELECTORS:
                    self.logger.debug(f"Попытка найти карточки через селектор: {selector}")
                    cards = await page.query_selector_all(selector)
                    if cards:
                        self.logger.debug(f"Найдено {len(cards)} карточек через селектор: {selector}")
                        break
                
                # Если карточки не найдены, попробуем AI-селектор
                if not cards:
                    self.logger.debug("Попытка найти карточки через AI-селектор")
                    cards = await page.get_by_role("article").all()
                    self.logger.debug(f"Найдено {len(cards)} карточек через AI-селектор")
                
                if cards:
                    break
                    
                # Если не нашли карточки, подождем еще немного и попробуем снова
                wait_time = 2 * (attempt + 1)
                self.logger.warning(f"Карточки не найдены, ждем {wait_time} сек и пробуем снова")
                await asyncio.sleep(wait_time)
                
            except Exception as e:
                self.logger.warning(f"Ошибка при поиске карточек (попытка {attempt+1}/3): {e}")
                if attempt < 2:
                    await asyncio.sleep(2 * (attempt + 1))
        
        if not cards:
            self.logger.error(f"Не удалось найти карточки объявлений после всех попыток")
            
            # Сохраняем скриншот для отладки
            try:
                screenshot_dir = Path("logs/screenshots")
                screenshot_dir.mkdir(exist_ok=True, parents=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = screenshot_dir / f"no_cards_{timestamp}.png"
                await page.screenshot(path=str(screenshot_path))
                self.logger.info(f"Скриншот сохранен: {screenshot_path}")
            except Exception as screenshot_error:
                self.logger.error(f"Не удалось сохранить скриншот: {screenshot_error}")
                
            return []
        
        self.logger.info(f"Найдено карточек объявлений: {len(cards)}")
        
        # Извлекаем базовые данные из карточек
        basic_listings = []
        
        for i, card in enumerate(cards):
            try:
                basic_listing = await self._extract_basic_listing_data(card, page)
                if basic_listing:
                    basic_listings.append(basic_listing)
            except Exception as e:
                self.logger.error(f"Ошибка при извлечении данных из карточки {i+1}: {e}")
        
        self.logger.info(f"Извлечено базовых данных из {len(basic_listings)} карточек")
        
        # Асинхронно получаем детали для каждого объявления
        tasks = []
        for basic_listing in basic_listings:
            # Создаем таск для получения деталей
            task = asyncio.create_task(self._get_listing_details(basic_listing))
            tasks.append(task)
        
        # Обрабатываем результаты асинхронно
        for completed_task in asyncio.as_completed(tasks):
            try:
                listing = await completed_task
                if listing:
                    listings.append(listing)
            except Exception as e:
                self.logger.error(f"Ошибка при получении деталей объявления: {e}")
        
        return listings

    async def _get_listing_details(self, basic_listing: Listing) -> Optional[Listing]:
        """
        Асинхронно получает детали объявления с использованием семафора.
        
        Args:
            basic_listing: Объявление с базовой информацией
            
        Returns:
            Optional[Listing]: Объявление с полной информацией или None при ошибке
        """
        async with self.semaphore:
            return await self._with_retry(
                lambda: self._extract_listing_details(basic_listing),
                f"извлечение деталей объявления {basic_listing.url}",
                max_retries=3
            )

    async def _extract_listing_details(self, page: Page, listing: Listing) -> Optional[Listing]:
        """
        Извлекает детальную информацию об объявлении с детальной страницы.
        
        Args:
            page: Страница объявления
            listing: Объявление с базовой информацией
            
        Returns:
            Optional[Listing]: Объявление с полной информацией или None при ошибке
        """
        self.logger.debug(f"Получение деталей для {listing.url}")
        
        try:
            # Извлекаем основные данные
            title = await self._extract_title(page)
            price = await self._extract_price(page)
            description = await self._extract_description(page)
            location = await self._extract_location(page)
            area_size = await self._extract_area_size(page)
            utilities = await self._extract_utilities(page)
            image_url = await self._get_main_image_from_detail_page(page, str(listing.url))
            
            # Обновляем объявление полученными данными
            if title and not listing.title:
                listing.title = title
                
            if price and not listing.price:
                listing.price = price
                
            if description:
                listing.description = description
                
            if location:
                listing.location = location
                
            if area_size:
                listing.area = area_size
                
            if utilities:
                listing.utilities = utilities
                
            if image_url:
                listing.image_url = image_url
            
            # Получаем дополнительные атрибуты
            attributes = await self._extract_attributes(page)
            if attributes:
                # Расширяем объект листинга дополнительными данными
                for key, value in attributes.items():
                    # Избегаем дублирования уже существующих полей
                    if not hasattr(listing, key) or getattr(listing, key) is None:
                        setattr(listing, key, value)
            
            # Получаем характеристики земельного участка с использованием AI-селекторов
            land_chars = await self._extract_land_characteristics(page)
            if land_chars:
                # Обновляем информацию о площади, если она не была получена ранее
                if 'area' in land_chars and not listing.area:
                    listing.area = land_chars['area']
                
                # Обновляем информацию о коммуникациях, если она не была получена ранее
                if 'utilities' in land_chars and not listing.utilities:
                    listing.utilities = land_chars['utilities']
                
                # Добавляем дополнительные характеристики
                if 'zoning' in land_chars:
                    listing.zoning = land_chars['zoning']
                
                if 'features' in land_chars:
                    listing.features = land_chars['features']
            
            # Заполняем обязательные поля, если они отсутствуют
            if not listing.source:
                listing.source = self.SOURCE_NAME
                
            if not listing.date_scraped:
                listing.date_scraped = datetime.now()
                
            if not listing.deal_type:
                listing.deal_type = "Venta"  # По умолчанию
            
            self.logger.debug(f"Успешно получены детали для {listing.url}")
            return listing
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении деталей для {listing.url}: {e}")
            return None

    # <<< Обновленный метод парсинга деталей >>>
    async def _get_main_image_from_detail_page(self, page: Page, url: str) -> Optional[str]:
        """
        Извлекает URL главного изображения со страницы деталей объявления.
        Использует несколько методов для максимальной надежности.
        """
        self.logger.info(f"Извлечение главного изображения для: {url}")
        try:
            # Метод 1: Извлечение изображений через прямые запросы к API
            try:
                # Проверяем URL на наличие ID объявления
                mlu_match = re.search(r'MLU-?(\d+)', url)
                if mlu_match:
                    mlu_id = mlu_match.group(0).replace('-', '')
                    item_numeric_id = re.sub(r'^MLU', '', mlu_id)
                    
                    # Пытаемся извлечь ID изображения напрямую из HTML-кода страницы
                    html_content = await page.content()
                    img_id_patterns = [
                        r'"picture_id":"([^"]+)"',
                        r'"image_id":"([^"]+)"',
                        r'data-zoom="https://http2\.mlstatic\.com/D_NQ_NP_\d*_?([^"\.]+)',
                        r'https://http2\.mlstatic\.com/D_NQ_NP_\d*_?([^"\.]+)\.webp',
                        r'<img[^>]+src="https://http2\.mlstatic\.com/D_NQ_NP_[^"]*?(\d+[^"\.]+)'
                    ]
                    
                    image_id = None
                    for pattern in img_id_patterns:
                        matches = re.findall(pattern, html_content)
                        if matches:
                            image_id = matches[0]
                            self.logger.info(f"Извлечен ID изображения из страницы: {image_id}")
                            break
                    
                    if image_id:
                        # Формируем URL на основе найденного ID
                        img_urls = [
                            f"https://http2.mlstatic.com/D_NQ_NP_2X_{image_id}.webp",
                            f"https://http2.mlstatic.com/D_NQ_NP_{image_id}.webp",
                        ]
                        
                        # Проверяем доступность через HEAD-запрос
                        for img_url in img_urls:
                            response = await page.evaluate(f"""
                            async () => {{
                                try {{
                                    const resp = await fetch('{img_url}', {{ method: 'HEAD' }});
                                    if (resp.ok) return '{img_url}';
                                    return null;
                                }} catch (e) {{
                                    return null;
                                }}
                            }}
                            """)
                            
                            if response:
                                self.logger.info(f"Найдено изображение через извлеченный ID: {response}")
                                return response
                    
                    # Если ID не найден или URL недоступен, пробуем прямую ссылку по ID объявления
                    img_templates = [
                        f"https://http2.mlstatic.com/D_NQ_NP_2X_{mlu_id}-F.webp",
                        f"https://http2.mlstatic.com/D_NQ_NP_{mlu_id}-F.webp",
                        f"https://http2.mlstatic.com/D_NQ_NP_2X_845364-{mlu_id}-F.webp",
                        f"https://http2.mlstatic.com/D_NQ_NP_2X_683091{item_numeric_id}-F.webp",
                        f"https://http2.mlstatic.com/D_NQ_NP_2X_820071{item_numeric_id}-F.webp",
                        f"https://http2.mlstatic.com/D_NQ_NP_2X_637399{item_numeric_id}-F.webp",
                        f"https://http2.mlstatic.com/D_NQ_NP_2X_994265{item_numeric_id}-F.webp"
                    ]
                    
                    for img_url in img_templates:
                        response = await page.evaluate(f"""
                        async () => {{
                            try {{
                                const resp = await fetch('{img_url}', {{ method: 'HEAD' }});
                                if (resp.ok) return '{img_url}';
                                return null;
                            }} catch (e) {{
                                return null;
                            }}
                        }}
                        """)
                        
                        if response:
                            self.logger.info(f"Найдено изображение через API: {response}")
                            return response
                    
                    # Если не нашли прямыми методами, ищем готовые URL в HTML
                    img_url_patterns = [
                        r'(https://http2\.mlstatic\.com/D_NQ_NP_[^"]+\.webp)"',
                        r'(https://http2\.mlstatic\.com/D_NQ_NP_[^"]+\.jpg)"',
                        r'content="(https://http2\.mlstatic\.com/D_NQ_NP_[^"]+\.(webp|jpg))"'
                    ]
                    
                    for pattern in img_url_patterns:
                        img_matches = re.findall(pattern, html_content)
                        if img_matches:
                            for img_match in img_matches:
                                img_url = img_match[0] if isinstance(img_match, tuple) else img_match
                                if img_url.startswith('http') and 'http2.mlstatic.com' in img_url:
                                    # Проверяем, что это не заглушка
                                    if not any(x in img_url for x in ['mercadolibre.com/homes', 'placeholder', 'org-img']):
                                        self.logger.info(f"Найдено изображение через HTML: {img_url}")
                                        return img_url
            except Exception as api_err:
                self.logger.debug(f"Ошибка при попытке прямого доступа к API изображений: {api_err}")

            # Метод 2: Использование JavaScript для поиска и ранжирования всех изображений
            js_script = """
            () => {
                // Функция для проверки URL на валидность как изображение
                const isValidImageUrl = (url) => {
                    if (!url) return false;
                    if (url.startsWith('data:')) return false;
                    // Исключаем генерируемые заглушки
                    if (url.includes('mercadolibre.com/homes')) return false;
                    if (url.includes('mercadolibre.com/myML/')) return false;
                    if (url.includes('mercadolibre.com/org-img/')) return false;
                    if (url.includes('UI/public/placeholder')) return false;
                    return url.match(/\\.(jpeg|jpg|png|webp)(\\?.*)?$/i) || 
                           url.includes('image') || 
                           url.includes('img');
                };
                
                // Массив для хранения всех найденных изображений с метаданными о приоритете
                const images = [];
                
                // 1. Ищем изображения через медиа-галерею
                const galleryImages = document.querySelectorAll('.ui-pdp-gallery__figure img, .ui-pdp-gallery img, .ui-pdp-image img');
                galleryImages.forEach((img, index) => {
                    // Проверяем сначала data-zoom атрибут для высокого разрешения
                    const zoomSrc = img.getAttribute('data-zoom');
                    if (zoomSrc && isValidImageUrl(zoomSrc)) {
                        images.push({ 
                            src: zoomSrc, 
                            priority: 1, 
                            position: index,
                            source: 'gallery-zoom'
                        });
                    }
                    
                    // Затем проверяем обычный src
                    const src = img.getAttribute('src');
                    if (src && isValidImageUrl(src)) {
                        images.push({ 
                            src, 
                            priority: 1 + index * 0.1, // Первое изображение имеет высший приоритет
                            position: index,
                            source: 'gallery'
                        });
                    }
                });
                
                // 2. Ищем в мета-тегах OpenGraph
                const metaOgImage = document.querySelector('meta[property="og:image"]');
                if (metaOgImage) {
                    const src = metaOgImage.getAttribute('content');
                    if (isValidImageUrl(src)) {
                        images.push({ 
                            src, 
                            priority: 2,
                            source: 'og-meta'
                        });
                    }
                }
                
                // 3. Ищем в структурированных данных JSON-LD
                try {
                    const jsonLdScripts = document.querySelectorAll('script[type="application/ld+json"]');
                    jsonLdScripts.forEach(script => {
                        try {
                            const data = JSON.parse(script.textContent);
                            if (data && data.image) {
                                // Может быть массивом или строкой
                                const imageUrls = Array.isArray(data.image) ? data.image : [data.image];
                                imageUrls.forEach((imageUrl, index) => {
                                    if (isValidImageUrl(imageUrl)) {
                                        images.push({ 
                                            src: imageUrl, 
                                            priority: 3 + index * 0.1,
                                            source: 'json-ld'
                                        });
                                    }
                                });
                            }
                        } catch (e) {
                            // Игнорируем ошибки парсинга JSON
                        }
                    });
                } catch (e) {
                    // Игнорируем ошибки при работе с JSON-LD
                }
                
                // 4. Ищем скрытую галерею изображений
                try {
                    const scriptTags = document.querySelectorAll('script:not([type])');
                    scriptTags.forEach(script => {
                        const content = script.textContent;
                        // Ищем определение galleryApi
                        if (content && content.includes('galleryApi') && content.includes('pictures')) {
                            const galleryMatch = content.match(/galleryApi[\s\S]*?=[\s\S]*?({[\s\S]*?pictures[\s\S]*?})/);
                            if (galleryMatch && galleryMatch[1]) {
                                try {
                                    // Заменяем одинарные кавычки и очищаем код для парсинга
                                    const cleanJson = galleryMatch[1]
                                        .replace(/'/g, '"')
                                        .replace(/([{,]\s*)(\w+)(\s*:)/g, '$1"$2"$3'); // Заключаем ключи в кавычки
                                    
                                    // Пытаемся распарсить JSON
                                    const galleryData = JSON.parse(cleanJson);
                                    if (galleryData && galleryData.pictures && Array.isArray(galleryData.pictures)) {
                                        galleryData.pictures.forEach((pic, index) => {
                                            if (pic.url && isValidImageUrl(pic.url)) {
                                                images.push({ 
                                                    src: pic.url, 
                                                    priority: 2 + index * 0.1,
                                                    source: 'gallery-api'
                                                });
                                            }
                                        });
                                    }
                                } catch (e) {
                                    // Игнорируем ошибки парсинга
                                }
                            }
                        }
                    });
                } catch (e) {
                    // Игнорируем ошибки при поиске галереи
                }
                
                // 5. Общий поиск по всем img-тегам на странице
                const allImages = document.querySelectorAll('img');
                allImages.forEach((img, index) => {
                    // Пропускаем маленькие изображения и иконки
                    const width = img.naturalWidth || img.width || 0;
                    const height = img.naturalHeight || img.height || 0;
                    
                    // Только достаточно большие изображения
                    if (width >= 300 || height >= 300) {
                        const src = img.getAttribute('src');
                        if (src && isValidImageUrl(src)) {
                            // Проверяем, находится ли изображение в основном контенте
                            const isInProductArea = img.closest('.ui-pdp-container, .vip-container') !== null;
                            const priority = isInProductArea ? 4 : 5;
                            
                            images.push({ 
                                src, 
                                priority,
                                position: index,
                                width,
                                height,
                                source: 'img-tag'
                            });
                        }
                    }
                });
                
                // Сортируем изображения по приоритету (меньше = важнее)
                images.sort((a, b) => a.priority - b.priority);
                
                // Проверяем наличие изображений по доменам
                const mluIds = location.href.match(/MLU-?\\d+/g);
                if (mluIds && mluIds.length) {
                    const mluId = mluIds[0].replace('-', '');
                    // Добавляем прямую ссылку на API МерадоЛибре
                    images.unshift({
                        src: `https://http2.mlstatic.com/D_NQ_NP_2X_${mluId}-F.webp`,
                        priority: 0,
                        source: 'direct-api'
                    });
                }
                
                // Если не удалось найти, пробуем сформировать URL на основе ID
                const idMatch = document.body.innerHTML.match(/andes-spinner--large[\\s\\S]*?data-js="shipping-status-info"[\\s\\S]*?(MLU\\d+)/);
                if (idMatch && idMatch[1]) {
                    // Альтернативный способ формирования URL
                    images.unshift({
                        src: `https://http2.mlstatic.com/D_NQ_NP_2X_${idMatch[1]}-F.webp`,
                        priority: 0.5,
                        source: 'dom-parsed'
                    });
                }
                
                // Возвращаем массив найденных изображений для проверки
                return images.map(img => img.src);
            }
            """
            images = await page.evaluate(js_script)
            
            if images and len(images) > 0:
                # Проверяем каждое изображение на доступность
                for img_url in images:
                    try:
                        # Проверяем доступность через HEAD-запрос
                        is_available = await page.evaluate(f"""
                        async () => {{
                            try {{
                                const resp = await fetch('{img_url}', {{ method: 'HEAD' }});
                                return resp.ok;
                            }} catch (e) {{
                                return false;
                            }}
                        }}
                        """)
                        
                        if is_available:
                            self.logger.info(f"Подтверждено доступное изображение: {img_url[:50]}...")
                            return img_url
                    except Exception as check_err:
                        self.logger.debug(f"Ошибка при проверке изображения {img_url[:30]}...: {check_err}")
                        continue
                
                # Если не смогли проверить, просто берем первое
                main_image_url = images[0]
                self.logger.info(f"Использую первое найденное изображение: {main_image_url[:50]}...")
                return main_image_url
            
            # Если ничего не найдено через JavaScript, пробуем использовать прямые селекторы
            self.logger.info("JavaScript не нашел изображений, используем прямые селекторы")
            
            selectors = [
                'figure.ui-pdp-gallery__figure img', 
                'div.ui-pdp-gallery img',
                'div.ui-pdp-image img',
                '.ui-pdp-gallery__figure div',
                'figure.gallery-image-container img'
            ]
            
            for selector in selectors:
                try:
                    image_elem = await page.query_selector(selector)
                    if image_elem:
                        for attr in ['data-zoom', 'src', 'data-src']:
                            img_url = await image_elem.get_attribute(attr)
                            if img_url and img_url.startswith('http') and not img_url.startswith('data:'):
                                self.logger.info(f"Найдено изображение через селектор {selector}: {img_url[:50]}...")
                                return img_url
                except Exception as e:
                    self.logger.debug(f"Ошибка при извлечении изображения через селектор {selector}: {e}")
            
            # Как последнее средство, ищем ID объявления и формируем прямую ссылку
            try:
                mlu_match = re.search(r'MLU-?(\d+)', url)
                if mlu_match:
                    mlu_id = mlu_match.group(0).replace('-', '')
                    direct_url = f"https://http2.mlstatic.com/D_NQ_NP_2X_{mlu_id}-F.webp"
                    self.logger.info(f"Формирование прямой ссылки на основе ID: {direct_url}")
                    return direct_url
            except Exception as id_err:
                self.logger.debug(f"Ошибка при формировании ссылки из ID: {id_err}")
            
            self.logger.warning(f"Не удалось найти изображение для {url} всеми методами")
            return None
            
        except Exception as e:
            self.logger.error(f"Ошибка при извлечении главного изображения: {e}")
            return None

    async def _extract_land_characteristics(self, page: Page) -> Dict[str, Any]:
        """
        Извлекает характеристики земельного участка с использованием AI-селекторов.
        
        Args:
            page: Объект страницы деталей объявления
            
        Returns:
            Dict[str, Any]: Словарь с характеристиками участка
        """
        characteristics = {}
        
        try:
            # Вспомогательная функция для безопасного получения текста из элемента
            async def safe_get_text(element, element_type):
                if element is None:
                    return None
                    
                try:
                    text = await element.inner_text()
                    text = clean_text(text)
                    return text if text else None
                except Exception as e:
                    self.logger.warning(f"Ошибка при извлечении текста из {element_type}: {e}")
                    return None
            
            # --- ИЗВЛЕЧЕНИЕ ПЛОЩАДИ ---
            # 1. Пробуем найти через AI-селектор
            area_elem = await smart_find_element(page, "area", "Найди информацию о площади земельного участка (м² или гектары)")
            
            if area_elem:
                area = await safe_get_text(area_elem, "area")
                if area:
                    characteristics['area'] = area
                    self.logger.debug(f"Площадь найдена через AI: {area}")
            
            # 2. Если площадь не найдена, ищем в таблице характеристик по ключевым словам
            if 'area' not in characteristics:
                area_keywords = ['superficie', 'area', 'metraje', 'metros', 'tamaño', 'm²', 'hectáreas', 'ha']
                
                # 2.1 Сначала ищем в таблице характеристик (часто структурированная)
                table_rows = await page.query_selector_all('div.ui-pdp-specs__table tr')
                
                for row in table_rows:
                    row_text = await safe_get_text(row, "table row")
                    if not row_text:
                        continue
                    
                    row_text_lower = row_text.lower()
                    if any(keyword in row_text_lower for keyword in area_keywords):
                        # Извлекаем числа и единицы измерения
                        area_match = re.search(r'(\d+[\.,]?\d*)\s*(m²|ha|hectáreas|metros)', row_text_lower)
                        if area_match:
                            value, unit = area_match.groups()
                            
                            # Преобразуем значение в стандартный формат
                            value = value.replace(',', '.')
                            
                            # Стандартизируем единицы измерения
                            if unit in ['ha', 'hectáreas']:
                                area_text = f"{value} ha"
                            else:
                                area_text = f"{value} m²"
                                
                            characteristics['area'] = area_text
                            self.logger.debug(f"Площадь найдена в таблице характеристик: {area_text}")
                            break
                        else:
                            # Если формат не удалось распознать, сохраняем весь текст
                            characteristics['area'] = row_text
                            self.logger.debug(f"Площадь найдена в таблице характеристик (необработанная): {row_text}")
                            break
            
            # 3. Если площадь не найдена, пробуем через CSS селекторы для таблиц спецификаций
            if 'area' not in characteristics:
                try:
                    # Проверяем часто используемые селекторы для площади в MercadoLibre (без :contains)
                    area_selectors = [
                        '.ui-pdp-specs__table tr',
                        '.andes-table__row',
                        'tr',
                        '.ui-pdp-specs__table-row'
                    ]
                    
                    for selector in area_selectors:
                        elements = await page.query_selector_all(selector)
                        for element in elements:
                            element_text = await element.inner_text()
                            element_text_lower = element_text.lower()
                            
                            # Проверяем наличие ключевых слов о площади
                            if any(keyword in element_text_lower for keyword in area_keywords):
                                # Нормализуем и извлекаем площадь
                                # 1. Извлекаем числа с единицами измерения
                                area_matches = re.findall(r'(\d+[\.,]?\d*)\s*(m²|ha|metros|hectáreas)', element_text_lower)
                                
                                if area_matches:
                                    if len(area_matches) == 1:
                                        # Один размер
                                        value, unit = area_matches[0]
                                        value = value.replace(',', '.')
                                        
                                        if unit in ['ha', 'hectáreas']:
                                            area_text = f"{value} ha"
                                        else:
                                            area_text = f"{value} m²"
                                    
                                    elif len(area_matches) == 2:
                                        # Диапазон размеров
                                        min_value, min_unit = area_matches[0]
                                        max_value, max_unit = area_matches[1]
                                        
                                        min_value = min_value.replace(',', '.')
                                        max_value = max_value.replace(',', '.')
                                        
                                        # Проверяем, одинаковые ли единицы измерения
                                        if (min_unit in ['ha', 'hectáreas'] and max_unit in ['ha', 'hectáreas']) or \
                                           (min_unit in ['m²', 'metros'] and max_unit in ['m²', 'metros']):
                                            # Единицы измерения совпадают
                                            unit = "ha" if min_unit in ['ha', 'hectáreas'] else "m²"
                                            area_text = f"{min_value} {unit} - {max_value} {unit}"
                                        else:
                                            # Разные единицы измерения
                                            min_unit = "ha" if min_unit in ['ha', 'hectáreas'] else "m²"
                                            max_unit = "ha" if max_unit in ['ha', 'hectáreas'] else "m²"
                                            area_text = f"{min_value} {min_unit} - {max_value} {max_unit}"
                                    else:
                                        # Более двух значений, берем минимальное и максимальное
                                        values = [float(match[0].replace(',', '.')) for match in area_matches]
                                        units = [match[1] for match in area_matches]
                                        
                                        min_value = min(values)
                                        max_value = max(values)
                                        
                                        # Определяем единицы измерения
                                        if all(unit in ['ha', 'hectáreas'] for unit in units):
                                            area_text = f"{min_value} ha - {max_value} ha"
                                        elif all(unit in ['m²', 'metros'] for unit in units):
                                            area_text = f"{min_value} m² - {max_value} m²"
                                        else:
                                            # Смешанные единицы - конвертируем в м²
                                            # TODO: добавить конвертацию между га и м²
                                            area_text = element_text
                                    
                                    characteristics['area'] = area_text
                                    self.logger.debug(f"Площадь найдена через селектор: {area_text}")
                                    break
                                else:
                                    # Если числа не найдены, но есть ключевые слова, сохраняем текст
                                    characteristics['area'] = element_text
                                    self.logger.debug(f"Площадь найдена (необработанная): {element_text}")
                                    break
                        
                        # Если нашли площадь, прерываем цикл по селекторам
                        if 'area' in characteristics:
                            break
                
                except Exception as area_err:
                    self.logger.warning(f"Ошибка при извлечении площади через селекторы: {area_err}")
            
            # 4. Если площадь всё ещё не найдена, пытаемся найти в описании
            if 'area' not in characteristics:
                try:
                    description_elem = await page.query_selector('div.ui-pdp-description__content')
                    if description_elem:
                        description_text = await safe_get_text(description_elem, "description")
                        
                        if description_text:
                            # Ищем в описании упоминания площади
                            area_matches = re.findall(r'(\d+[\.,]?\d*)\s*(m²|ha|metros|hectáreas)', description_text.lower())
                            
                            if area_matches:
                                # Берем первое найденное значение
                                value, unit = area_matches[0]
                                value = value.replace(',', '.')
                                
                                if unit in ['ha', 'hectáreas']:
                                    area_text = f"{value} ha"
                                else:
                                    area_text = f"{value} m²"
                                
                                characteristics['area'] = area_text
                                self.logger.debug(f"Площадь найдена в описании: {area_text}")
                                
                                # Также проверяем, есть ли упоминание диапазона
                                if len(area_matches) > 1:
                                    area_context = description_text.lower()
                                    if "entre" in area_context and "y" in area_context:
                                        # Возможный диапазон
                                        min_value, min_unit = area_matches[0]
                                        max_value, max_unit = area_matches[1]
                                        
                                        min_value = min_value.replace(',', '.')
                                        max_value = max_value.replace(',', '.')
                                        
                                        if (min_unit in ['ha', 'hectáreas'] and max_unit in ['ha', 'hectáreas']) or \
                                           (min_unit in ['m²', 'metros'] and max_unit in ['m²', 'metros']):
                                            # Единицы измерения совпадают
                                            unit = "ha" if min_unit in ['ha', 'hectáreas'] else "m²"
                                            area_text = f"{min_value} {unit} - {max_value} {unit}"
                                            characteristics['area'] = area_text
                
                except Exception as desc_err:
                    self.logger.warning(f"Ошибка при поиске площади в описании: {desc_err}")
            
            # --- ИЗВЛЕЧЕНИЕ КОММУНИКАЦИЙ ---
            # Ключевые слова для коммуникаций
            utilities_keywords = {
                'agua': 'Вода',
                'luz': 'Электричество',
                'electricidad': 'Электричество',
                'gas': 'Газ',
                'saneamiento': 'Канализация',
                'desagüe': 'Канализация',
                'cloacas': 'Канализация',
                'internet': 'Интернет',
                'fibra': 'Интернет',
                'cable': 'Кабельное ТВ',
                'teléfono': 'Телефон',
                'alcantarillado': 'Ливневая канализация'
            }
            
            # 1. Используем AI-селектор
            utilities_elem = await smart_find_element(page, "utilities", "Найди информацию о коммуникациях на участке (свет, вода, газ, интернет)")
            
            if utilities_elem:
                utilities_text = await safe_get_text(utilities_elem, "utilities")
                if utilities_text:
                    characteristics['utilities'] = utilities_text
                    self.logger.debug(f"Коммуникации найдены через AI: {utilities_text}")
            
            # 2. Если коммуникации не найдены, ищем в таблице характеристик
            if 'utilities' not in characteristics:
                available_utilities = []
                
                # Проверяем таблицу характеристик
                table_rows = await page.query_selector_all('div.ui-pdp-specs__table tr')
                
                for row in table_rows:
                    row_text = await safe_get_text(row, "table row")
                    if not row_text:
                        continue
                    
                    row_text_lower = row_text.lower()
                    for keyword, name in utilities_keywords.items():
                        if keyword in row_text_lower:
                            # Проверяем, не отрицание ли это
                            if not any(neg in row_text_lower for neg in ['no disponible', 'no hay', 'sin']):
                                available_utilities.append(name)
                                break
                
                # Проверяем характеристики в отдельных блоках
                characteristics_blocks = await page.query_selector_all('div.ui-pdp-highlighted-specs-res span.ui-pdp-label')
                
                for block in characteristics_blocks:
                    block_text = await safe_get_text(block, "characteristics block")
                    if not block_text:
                        continue
                    
                    block_text_lower = block_text.lower()
                    for keyword, name in utilities_keywords.items():
                        if keyword in block_text_lower:
                            if not any(neg in block_text_lower for neg in ['no disponible', 'no hay', 'sin']):
                                if name not in available_utilities:
                                    available_utilities.append(name)
                                break
                
                # Проверяем описание
                description_elem = await page.query_selector('div.ui-pdp-description__content')
                if description_elem:
                    description_text = await safe_get_text(description_elem, "description")
                    
                    if description_text:
                        description_text_lower = description_text.lower()
                        
                        # Проверка на контекстное упоминание коммуникаций
                        for keyword, name in utilities_keywords.items():
                            if keyword in description_text_lower:
                                context_range = 20  # Символов до и после ключевого слова
                                
                                # Получаем позицию ключевого слова
                                keyword_pos = description_text_lower.find(keyword)
                                
                                # Получаем контекст вокруг ключевого слова
                                start_pos = max(0, keyword_pos - context_range)
                                end_pos = min(len(description_text_lower), keyword_pos + len(keyword) + context_range)
                                
                                context = description_text_lower[start_pos:end_pos]
                                
                                # Проверяем, нет ли отрицания рядом
                                if not any(neg in context for neg in ['no disponible', 'no hay', 'sin']):
                                    if name not in available_utilities:
                                        available_utilities.append(name)
                
                # Если нашли коммуникации, формируем строку
                if available_utilities:
                    characteristics['utilities'] = ", ".join(available_utilities)
                    self.logger.debug(f"Коммуникации найдены: {characteristics['utilities']}")
                else:
                    characteristics['utilities'] = "Не указано"
            
            # --- ИЗВЛЕЧЕНИЕ ДОПОЛНИТЕЛЬНЫХ ХАРАКТЕРИСТИК ---
            # Зонирование
            zoning_elem = await smart_find_element(page, "zoning", "Найди информацию о зонировании или разрешениях на использование участка")
            if zoning_elem:
                zoning = await safe_get_text(zoning_elem, "zoning")
                if zoning:
                    characteristics['zoning'] = zoning
                    self.logger.debug(f"Зонирование найдено: {zoning}")
            
            # Топография
            topography_elem = await smart_find_element(page, "topography", "Найди информацию о рельефе, топографии или особенностях ландшафта участка")
            if topography_elem:
                topography = await safe_get_text(topography_elem, "topography")
                if topography:
                    characteristics['topography'] = topography
                    self.logger.debug(f"Топография найдена: {topography}")
            
            # Доступность
            access_elem = await smart_find_element(page, "access", "Найди информацию о доступности участка, дорогах, транспорте")
            if access_elem:
                access = await safe_get_text(access_elem, "access")
                if access:
                    characteristics['access'] = access
                    self.logger.debug(f"Доступность найдена: {access}")
            
            # Проверяем контекст описания на наличие ключевых фраз с дополнительной информацией
            description_elem = await page.query_selector('div.ui-pdp-description__content')
            if description_elem:
                description_text = await safe_get_text(description_elem, "description")
                
                if description_text:
                    description_text_lower = description_text.lower()
                    
                    # Проверка на упоминание зонирования
                    zoning_keywords = ['zonificación', 'zona', 'uso del suelo', 'residencial', 'comercial', 'industrial', 'rural', 'urbano']
                    if 'zoning' not in characteristics:
                        for keyword in zoning_keywords:
                            if keyword in description_text_lower:
                                # Извлекаем контекст вокруг ключевого слова
                                sentence_pattern = r'[^.!?]*\b' + keyword + r'\b[^.!?]*[.!?]'
                                zoning_match = re.search(sentence_pattern, description_text_lower)
                                
                                if zoning_match:
                                    characteristics['zoning'] = zoning_match.group(0).strip()
                                    self.logger.debug(f"Зонирование найдено в описании: {characteristics['zoning']}")
                                    break
                    
                    # Проверка на упоминание доступности/дорог
                    if 'access' not in characteristics:
                        access_keywords = ['acceso', 'camino', 'ruta', 'carretera', 'calle', 'avenida', 'transporte']
                        for keyword in access_keywords:
                            if keyword in description_text_lower:
                                sentence_pattern = r'[^.!?]*\b' + keyword + r'\b[^.!?]*[.!?]'
                                access_match = re.search(sentence_pattern, description_text_lower)
                                
                                if access_match:
                                    characteristics['access'] = access_match.group(0).strip()
                                    self.logger.debug(f"Доступность найдена в описании: {characteristics['access']}")
                                    break
                    
                    # Проверка на топографию
                    if 'topography' not in characteristics:
                        topo_keywords = ['terreno', 'plano', 'loma', 'pendiente', 'inclinación', 'suelo', 'tierra', 'arena', 'rocoso']
                        for keyword in topo_keywords:
                            if keyword in description_text_lower:
                                sentence_pattern = r'[^.!?]*\b' + keyword + r'\b[^.!?]*[.!?]'
                                topo_match = re.search(sentence_pattern, description_text_lower)
                                
                                if topo_match:
                                    characteristics['topography'] = topo_match.group(0).strip()
                                    self.logger.debug(f"Топография найдена в описании: {characteristics['topography']}")
                                    break
            
            return characteristics
        
        except Exception as e:
            self.logger.error(f"Ошибка при извлечении характеристик земельного участка: {e}")
            return characteristics

    async def _extract_data_from_detail_page(self, page: Page, listing: Listing) -> Optional[Listing]:
        """
        Извлекает детальную информацию об объявлении с его страницы.
        Включает в себя улучшенный механизм повторных попыток и смену прокси.
        
        Args:
            page: Страница браузера
            listing: Базовая информация об объявлении
            
        Returns:
            Optional[Listing]: Обновленное объявление с детальной информацией или None при ошибке
        """
        url = str(listing.url)
        
        # 1. Настраиваем механизм повторных попыток
        max_attempts = self.max_retries  # Берем количество попыток из настроек
        current_attempt = 1
        success = False
        retry_delay = 2  # Начальная задержка в секундах
        
        # Объявляем детальные данные на уровне функции, чтобы они были доступны 
        # после всех попыток, даже если некоторые неудачны
        detailed_data = {}
        
        self.logger.info(f"Начинаем парсинг деталей для: {url}")
        
        # Преобразуем URL в формат, который использует MercadoLibre для деталей
        if "MLU-" in url and "_JM" in url:
            # Меняем домен с terreno.mercadolibre.com.uy на articulo.mercadolibre.com.uy
            url = url.replace("terreno.mercadolibre.com.uy", "articulo.mercadolibre.com.uy")
            self.logger.info(f"URL исправлен: {listing.url} -> {url}")
        
        while current_attempt <= max_attempts and not success:
            try:
                # Если это не первая попытка, обновляем страницу и ждем, чтобы избежать блокировки
                if current_attempt > 1:
                    self.logger.info(f"Попытка {current_attempt}/{max_attempts} для URL: {url}")
                    
                    # Создаем случайную задержку для маскировки под человека
                    random_delay = random.uniform(retry_delay, retry_delay * 1.5)
                    self.logger.info(f"Ожидание {random_delay:.1f} сек перед повторной попыткой...")
                    await asyncio.sleep(random_delay)
                    
                    # Если это третья попытка, пробуем сменить прокси и user-agent
                    if current_attempt == 3 and self.proxy_configs:
                        self.logger.info("Переинициализация браузера с новым прокси...")
                        
                        # Закрываем текущий контекст
                        await self.close()
                        
                        # Инициализируем браузер заново с новым прокси
                        await self._init_browser()
                        
                        # Создаем новую страницу
                        page = await self.context.new_page()
                
                # Переходим на страницу объявления
                self.logger.debug(f"Загрузка детальной страницы: {url}")
                
                # Улучшенный механизм загрузки страницы с повторными попытками
                page_loaded = False
                page_load_attempts = 3  # Количество попыток загрузки страницы
                
                for load_attempt in range(page_load_attempts):
                    try:
                        # Устанавливаем большой таймаут для первой загрузки страницы
                        response = await page.goto(
                            url, 
                            wait_until="domcontentloaded", 
                            timeout=60000 if load_attempt == 0 else 30000
                        )
                        
                        # Проверяем статус ответа
                        if response and response.status == 200:
                            page_loaded = True
                            break
                        elif response:
                            self.logger.warning(f"Получен статус {response.status} при загрузке {url}")
                            if response.status == 404:
                                self.logger.error(f"Страница не найдена (404): {url}")
                                return None
                            elif response.status >= 500:
                                self.logger.error(f"Ошибка сервера ({response.status}): {url}")
                                # При ошибке сервера имеет смысл повторить
                                await asyncio.sleep(2)
                                continue
                        
                        # Если страница загружена с ошибкой, но не 404, делаем небольшую паузу и пробуем еще раз
                        await asyncio.sleep(load_attempt + 1)
                        
                    except PlaywrightTimeoutError:
                        self.logger.warning(f"Таймаут при загрузке страницы (попытка {load_attempt+1}/{page_load_attempts}): {url}")
                        if load_attempt < page_load_attempts - 1:  # Если еще есть попытки
                            await asyncio.sleep(load_attempt + 2)
                            continue
                        else:
                            raise  # Если все попытки исчерпаны, поднимаем исключение
                
                # Если страница не загружена после всех попыток, переходим к следующей итерации внешнего цикла
                if not page_loaded:
                    self.logger.error(f"Не удалось загрузить страницу после {page_load_attempts} попыток: {url}")
                    current_attempt += 1
                    retry_delay *= 2  # Увеличиваем задержку для следующей попытки
                    continue
                
                # Ожидаем рендеринг ключевых элементов страницы
                try:
                    # Ждем загрузки заголовка (h1) или основного содержимого
                    await asyncio.wait([
                        page.wait_for_selector("h1", timeout=5000),
                        page.wait_for_selector("div.ui-pdp-container", timeout=5000)
                    ], return_when=asyncio.FIRST_COMPLETED)
                    
                    # Ждем немного дополнительно, чтобы загрузились все элементы
                    await page.wait_for_timeout(1000)
                    
                except Exception as wait_err:
                    self.logger.warning(f"Предупреждение при ожидании элементов: {wait_err}")
                    # Продолжаем выполнение даже при ошибке ожидания
                
                # Вспомогательная функция для безопасного извлечения текста
                async def safe_get_text(element, element_type):
                    if element is None:
                        return None
                        
                    try:
                        text = await element.inner_text()
                        text = clean_text(text)
                        return text if text else None
                    except Exception as e:
                        self.logger.warning(f"Ошибка при извлечении текста из {element_type}: {e}")
                        return None
                
                # Извлекаем заголовок объявления
                title_elem = await page.query_selector(self.detail_selectors['title'])
                title = await safe_get_text(title_elem, "title")
                
                # Если заголовок не найден по основному селектору, пробуем альтернативные
                if not title:
                    for selector in self.detail_selectors['title_alt']:
                        title_elem = await page.query_selector(selector)
                        title = await safe_get_text(title_elem, "title")
                        if title:
                            break
                
                # Если заголовок не найден, пробуем AI-селектор
                if not title:
                    title_elem = await smart_find_element(page, "title", "Найди заголовок объявления о продаже земельного участка")
                    title = await safe_get_text(title_elem, "title by AI")
                
                if title:
                    detailed_data['title'] = title
                
                # Извлекаем цену
                try:
                    price_fraction_elem = await page.query_selector(self.detail_selectors['price_fraction'])
                    price_currency_elem = await page.query_selector(self.detail_selectors['price_currency'])
                    
                    price_fraction = await safe_get_text(price_fraction_elem, "price_fraction")
                    price_currency = await safe_get_text(price_currency_elem, "price_currency")
                    
                    if price_fraction and price_currency:
                        price = f"{price_currency} {price_fraction}"
                        detailed_data['price'] = price
                except Exception as price_err:
                    self.logger.warning(f"Ошибка при извлечении цены: {price_err}")
                
                # Если цена не найдена, пробуем AI-селектор
                if 'price' not in detailed_data:
                    price_elem = await smart_find_element(page, "price", "Найди цену земельного участка. Она обычно включает валюту (U$S, $) и сумму.")
                    price = await safe_get_text(price_elem, "price by AI")
                    if price:
                        detailed_data['price'] = price
                
                # Извлечение описания
                desc_elem = await page.query_selector(self.detail_selectors['description'])
                description = await safe_get_text(desc_elem, "description")
                
                # Если описание не найдено, пробуем альтернативные селекторы
                if not description:
                    for selector in self.detail_selectors['description_alt']:
                        desc_elem = await page.query_selector(selector)
                        description = await safe_get_text(desc_elem, "description")
                        if description:
                            break
                
                # Если описание не найдено по селекторам, пробуем AI-селектор
                if not description:
                    desc_elem = await smart_find_element(page, "description", "Найди полное описание земельного участка")
                    description = await safe_get_text(desc_elem, "description by AI")
                
                if description:
                    detailed_data['description'] = description
                
                # Извлечение локации
                location_elem = await page.query_selector(self.detail_selectors['location'])
                location = await safe_get_text(location_elem, "location")
                
                # Если локация не найдена, пробуем альтернативные селекторы
                if not location:
                    for selector in self.detail_selectors['location_alt']:
                        location_elem = await page.query_selector(selector)
                        location = await safe_get_text(location_elem, "location")
                        if location:
                            break
                
                # Если локация не найдена, пробуем извлечь из хлебных крошек
                if not location:
                    breadcrumbs = await page.query_selector_all(self.detail_selectors['breadcrumbs_links'])
                    breadcrumb_texts = []
                    
                    for breadcrumb in breadcrumbs:
                        text = await safe_get_text(breadcrumb, "breadcrumb")
                        if text and text not in ["Inmuebles", "Terrenos", "MercadoLibre"]:
                            breadcrumb_texts.append(text)
                    
                    if breadcrumb_texts:
                        location = ", ".join(breadcrumb_texts)
                
                # Если локация все еще не найдена, пробуем AI-селектор
                if not location:
                    location_elem = await smart_find_element(page, "location", "Найди информацию о местоположении земельного участка (город, район, область)")
                    location = await safe_get_text(location_elem, "location by AI")
                
                if location:
                    detailed_data['location'] = location
                
                # Извлекаем характеристики участка
                land_characteristics = await self._extract_land_characteristics(page)
                if land_characteristics:
                    detailed_data.update(land_characteristics)
                
                # Проверяем, свежее ли объявление
                is_recent = await self._is_recent_listing(page)
                if is_recent:
                    detailed_data['is_recent'] = True
                    self.logger.info(f"Объявление {url} помечено как новое (за последние 12 часов)")
                
                # Извлекаем URL главного изображения (если есть)
                main_image_url = await self._get_main_image_from_detail_page(page, url)
                if main_image_url:
                    detailed_data['image_url'] = main_image_url
                
                # Сохраняем исходный URL
                detailed_data['url'] = str(listing.url)
                detailed_data['source'] = self.SOURCE_NAME
                
                # Если у нас достаточно данных, считаем извлечение успешным
                if ('title' in detailed_data and 'price' in detailed_data) or ('description' in detailed_data):
                    success = True
                else:
                    self.logger.warning(f"Недостаточно извлеченных данных для {url}")
                    current_attempt += 1
                    retry_delay *= 2
                    
                    # Сохраняем дебаг-информацию
                    try:
                        debug_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        debug_path = f"errors/detail_debug_{debug_timestamp}.png"
                        await page.screenshot(path=debug_path)
                        self.logger.debug(f"Сохранен скриншот детальной страницы: {debug_path}")
                        
                        html_path = f"errors/detail_html_{debug_timestamp}.html"
                        content = await page.content()
                        with open(html_path, "w", encoding="utf-8") as f:
                            f.write(content)
                        self.logger.debug(f"Сохранен HTML детальной страницы: {html_path}")
                    except Exception as debug_err:
                        self.logger.warning(f"Ошибка при сохранении отладочной информации: {debug_err}")
                
            except Exception as e:
                self.logger.error(f"Ошибка при обработке детальной страницы (попытка {current_attempt}): {e}")
                
                # Сохраняем дебаг-информацию при ошибке
                try:
                    debug_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    debug_path = f"errors/detail_error_{debug_timestamp}.png"
                    await page.screenshot(path=debug_path)
                    self.logger.info(f"Сохранен скриншот ошибки: {debug_path}")
                    
                    html_path = f"errors/detail_error_{debug_timestamp}.html"
                    content = await page.content()
                    with open(html_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    self.logger.info(f"Сохранен HTML ошибки: {html_path}")
                except Exception as debug_err:
                    self.logger.warning(f"Ошибка при сохранении отладочной информации: {debug_err}")
                
                # Увеличиваем счетчик попыток и задержку
                current_attempt += 1
                retry_delay *= 2
                
                # Очищаем куки и кэш перед следующей попыткой
                if current_attempt <= max_attempts:
                    try:
                        await page.context.clear_cookies()
                        self.logger.info("Куки очищены перед следующей попыткой")
                    except Exception as clear_err:
                        self.logger.warning(f"Ошибка при очистке куки: {clear_err}")
        
        # Если после всех попыток не удалось извлечь данные, возвращаем исходное объявление
        if not success:
            self.logger.error(f"Не удалось извлечь данные для {url} после {max_attempts} попыток")
            return listing
        
        # Обновляем объект Listing с извлеченными детальными данными
        self.logger.info(f"Объект Listing успешно обновлен с деталями для: {url}")
        
        # Обновляем поля объекта Listing
        for key, value in detailed_data.items():
            setattr(listing, key, value)
        
        # Если у объявления есть атрибуты, обновляем их или создаем новые
        if not hasattr(listing, "attributes") or not listing.attributes:
            listing.attributes = {}
        
        # Добавляем поля, которые не являются стандартными для модели Listing
        for key, value in detailed_data.items():
            if key not in ['title', 'price', 'location', 'area', 'description', 'image_url', 'url', 'source', 'utilities', 'deal_type', 'is_recent']:
                listing.attributes[key] = value
        
        return listing

    async def _is_recent_listing(self, page: Page) -> bool:
        """
        Проверяет, является ли объявление новым (опубликовано за последние 12 часов).
        
        Args:
            page: Объект страницы деталей объявления
            
        Returns:
            bool: True, если объявление опубликовано за последние 12 часов
        """
        try:
            # Ищем элемент даты с помощью AI-селектора
            date_elem = await smart_find_element(page, "publication date", 
                                           "Найди дату публикации объявления")
            
            if date_elem:
                date_text = await date_elem.inner_text()
                
                # Проверяем на ключевые слова, указывающие на свежесть объявления
                if date_text:
                    self.logger.debug(f"Найдена дата публикации: {date_text}")
                    
                    # Если указано "сегодня" или "несколько часов назад" - это новое объявление
                    lower_date = date_text.lower()
                    recent_keywords = ['hoy', 'horas', 'hora', 'minutos', 'reciente', 'nueva']
                    
                    for keyword in recent_keywords:
                        if keyword in lower_date:
                            self.logger.info(f"Объявление содержит ключевое слово свежести: {keyword}")
                            return True
                    
                    # Если дата указана, пробуем её распарсить и сравнить с текущей
                    try:
                        # Часто формат даты может быть разным, пробуем разные варианты
                        date_patterns = [
                            r'(\d{1,2})/(\d{1,2})/(\d{4})',  # 12/05/2023
                            r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})'  # 12 de mayo de 2023
                        ]
                        
                        # Словарь для преобразования испанских названий месяцев
                        month_names = {
                            'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
                            'julio': 7, 'agosto': 8, 'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
                        }
                        
                        for pattern in date_patterns:
                            match = re.search(pattern, lower_date)
                            if match:
                                if len(match.groups()) == 3:
                                    day, month, year = match.groups()
                                    
                                    # Если месяц как строка, преобразуем его в число
                                    if not month.isdigit():
                                        month = month_names.get(month.lower(), 1)
                                    
                                    # Преобразуем в числа
                                    day = int(day)
                                    month = int(month)
                                    year = int(year)
                                    
                                    # Создаем объект datetime
                                    listing_date = datetime(year, month, day)
                                    
                                    # Проверяем, прошло ли меньше 12 часов
                                    hours_diff = (datetime.now() - listing_date).total_seconds() / 3600
                                    if hours_diff <= 12:
                                        self.logger.info(f"Объявление опубликовано {hours_diff:.1f} часов назад")
                                        return True
                                    
                                    self.logger.debug(f"Объявление опубликовано {hours_diff:.1f} часов назад (больше 12)")
                                    return False
                    except Exception as date_err:
                        self.logger.warning(f"Ошибка при обработке даты публикации: {date_err}")
            
            # Если не смогли определить дату, используем JavaScript для поиска
            try:
                js_script = """
                () => {
                    // Ищем элементы с датой по ключевым словам
                    const dateElements = Array.from(document.querySelectorAll('*')).filter(el => {
                        const text = el.innerText && el.innerText.toLowerCase();
                        return text && (
                            text.includes('publicado') || 
                            text.includes('fecha') || 
                            text.includes('hace') ||
                            text.includes('horas') ||
                            text.includes('hoy') ||
                            text.includes('/20')  // Формат даты 
                        );
                    });
                    
                    // Возвращаем тексты найденных элементов
                    return dateElements.map(el => el.innerText.trim()).filter(Boolean);
                }
                """
                date_texts = await page.evaluate(js_script)
                
                if date_texts and isinstance(date_texts, list) and len(date_texts) > 0:
                    for date_text in date_texts:
                        lower_text = date_text.lower()
                        recent_keywords = ['hoy', 'hora', 'horas', 'minutos', 'reciente']
                        
                        for keyword in recent_keywords:
                            if keyword in lower_text:
                                self.logger.info(f"Найдено указание на свежесть объявления: {date_text}")
                                return True
                
                # Если до сих пор не определили свежесть, считаем объявление не новым
                return False
                
            except Exception as js_err:
                self.logger.warning(f"Ошибка при поиске даты публикации через JavaScript: {js_err}")
                return False
                
        except Exception as e:
            self.logger.error(f"Ошибка при проверке свежести объявления: {e}")
            return False  # В случае ошибки считаем объявление не новым

    # Вспомогательные методы остаются те же
    async def _safe_get_text_from_element(self, element: ElementHandle, selector: str, field_name: str, url: str) -> str:
        # ... (код без изменений)
        pass # Оставим как есть

    async def _safe_get_text(self, page: Page, selector: str, field_name: str, url: str) -> str:
        # ... (код без изменений)
        pass # Оставим как есть

    async def _safe_get_attribute(self, page: Page, selector: str, attribute: str, field_name: str, url: str) -> str:
        # ... (код без изменений)
        pass # Оставим как есть
        
    async def _safe_get_attribute_from_element(self, element: ElementHandle, selector: str, attribute: str, field_name: str, url: str) -> str:
        """Безопасно извлекает атрибут из дочернего элемента, найденного по селектору.
           Возвращает пустую строку, если элемент или атрибут не найдены, или произошла ошибка.
        """
        try:
            target_element = await element.query_selector(selector)
            if target_element:
                value = await target_element.get_attribute(attribute)
                return value.strip() if value else ""
        except Error as e:
            self.logger.debug(f"Ошибка Playwright при извлечении атрибута '{attribute}' поля '{field_name}' по селектору '{selector}' для URL {url}: {e}")
        except Exception as e:
            self.logger.warning(f"Неожиданная ошибка при извлечении атрибута '{attribute}' поля '{field_name}' по селектору '{selector}' для URL {url}: {e}")
        return ""
        
    async def _normalize_data(self, data: Dict[str, Any], url: str) -> Optional[Listing]:
        # ... (код без изменений)
        pass
        
    async def run_with_details(self, listings: Optional[List[Listing]] = None, max_pages: int = 1, headless: bool = True) -> List[Listing]:
        """
        Запускает парсер с получением детальной информации для каждого объявления.
        
        Args:
            listings: Список уже собранных объявлений (если не указан, будет выполнен парсинг)
            max_pages: Максимальное количество страниц для обработки (используется, только если listings не указан)
            headless: Запускать браузер в фоновом режиме
            
        Returns:
            List[Listing]: Список объявлений с детальной информацией
        """
        # Получаем базовый список объявлений, если он не передан
        if listings is None:
            listings = await self.run(max_pages=max_pages, headless=headless)
            
        if not listings:
            self.logger.warning("Не найдено объявлений для получения детальной информации")
            return []
        
        # Инициализируем браузер, если он не инициализирован
        if self.browser is None:
            await self._init_browser()
        
        try:
            # Создаем новую страницу для деталей
            details_page = await self.context.new_page()
            self.logger.info("Создана страница для получения деталей объявлений")
            
            # Устанавливаем таймаут (не используя set_default_timeout)
            # Это исправляет ошибку "object NoneType can't be used in 'await' expression"
            
            # Обрабатываем детали для каждого объявления
            detailed_listings = []
            
            for i, listing in enumerate(listings):
                self.logger.info(f"Получение деталей для объявления {i+1}/{len(listings)}: {listing.url}")
                
                try:
                    # Получаем детальную информацию
                    detailed_listing = await self._extract_data_from_detail_page(details_page, listing)
                    detailed_listings.append(detailed_listing)
                    
                    # Случайная задержка между запросами
                    if i < len(listings) - 1:
                        delay = random.uniform(2.0, 5.0)
                        self.logger.info(f"Ожидание {delay:.1f} сек перед следующим запросом...")
                        await asyncio.sleep(delay)
                    
                except Exception as e:
                    self.logger.error(f"Ошибка при получении деталей для {listing.url}: {e}")
                    detailed_listings.append(listing)  # Добавляем оригинальное объявление без деталей
            
            await details_page.close()
            return detailed_listings
            
        except Exception as e:
            self.logger.error(f"Критическая ошибка при получении деталей объявлений: {e}")
            return listings
        finally:
            # Закрываем браузер
            await self.close()
        
    def _get_random_user_agent(self) -> str:
        """
        Возвращает случайный User-Agent из списка популярных.
        """
        user_agents = [
            # Chrome на macOS
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 11_2_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36",
            
            # Chrome на Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
            
            # Firefox
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:95.0) Gecko/20100101 Firefox/95.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:95.0) Gecko/20100101 Firefox/95.0",
            
            # Safari
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15"
        ]
        return random.choice(user_agents)

    async def _handle_cookie_dialog(self, page):
        """Обработка диалога с куками, если он появился"""
        try:
            # Пробуем найти и закрыть диалог
            cookie_button = await page.query_selector("button.cookie-consent-banner-opt-out__action:not(.cookie-consent-banner-opt-out__action--secondary)")
            if cookie_button:
                self.logger.info("Найден диалог cookie, нажимаем кнопку согласия")
                await cookie_button.click()
                await asyncio.sleep(0.5)
            return True
        except Exception as e:
            self.logger.debug(f"Не найден диалог cookie или ошибка при обработке: {e}")
            return False

    async def _simulate_human_behavior(self, page):
        """
        Имитирует поведение человека на странице для уменьшения вероятности обнаружения бота.
        Выполняет случайные действия: скроллинг, движения мышью, паузы.
        """
        self.logger.debug("Имитация поведения человека на странице")
        
        try:
            # Случайная задержка перед началом взаимодействия
            await asyncio.sleep(random.uniform(1, 3))
            
            # Медленный скроллинг вниз
            viewport_height = await page.evaluate("window.innerHeight")
            page_height = await page.evaluate("document.body.scrollHeight")
            
            # Запустим скроллинг только если страница достаточно длинная
            if page_height > viewport_height * 1.5:
                # Определяем точки остановки для скроллинга
                scroll_steps = min(5, int(page_height / viewport_height))
                
                for step in range(1, scroll_steps + 1):
                    # Рассчитываем новую позицию скролла
                    scroll_position = step * viewport_height * 0.8
                    
                    # Выполняем скролл с плавностью
                    await page.evaluate(f"""
                        window.scrollTo({{
                            top: {scroll_position},
                            behavior: 'smooth'
                        }});
                    """)
                    
                    # Случайная пауза после скролла
                    await asyncio.sleep(random.uniform(1, 3))
                    
                    # Случайное движение мышью (50% шанс)
                    if random.random() < 0.5:
                        x = random.randint(100, 800)
                        y = random.randint(100, 500)
                        await page.mouse.move(x, y)
            
            # Случайная вероятность нажатия на случайный не-ссылочный элемент (20% шанс)
            if random.random() < 0.2:
                # Выбираем случайный неинтерактивный элемент (div, p, span)
                random_elements = await page.query_selector_all("div:not(a):not(button), p:not(a), span:not(a)")
                if random_elements and len(random_elements) > 0:
                    random_element = random.choice(random_elements)
                    # Получаем положение элемента
                    bbox = await random_element.bounding_box()
                    if bbox:
                        # Кликаем в случайную точку этого элемента
                        x = bbox["x"] + random.uniform(5, bbox["width"] - 5)
                        y = bbox["y"] + random.uniform(5, bbox["height"] - 5)
                        await page.mouse.move(x, y)
                        await page.mouse.click(x, y)
                        await asyncio.sleep(random.uniform(0.5, 1.5))
            
            # Возвращаемся наверх страницы
            await page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
            await asyncio.sleep(random.uniform(1, 2))
            
            self.logger.debug("Имитация человеческого поведения завершена")
        except Exception as e:
            self.logger.warning(f"Ошибка при имитации человеческого поведения: {e}")

    async def run(self, max_pages: Optional[int] = None, headless: bool = True) -> List[Listing]:
        """
        Запускает парсер MercadoLibre.
        
        Args:
            max_pages: Максимальное количество страниц для обработки
            headless: Запускать браузер в фоновом режиме
            
        Returns:
            List[Listing]: Список объявлений
        """
        # Инициализируем семафор для ограничения одновременных запросов
        self.semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_DETAIL_PAGES)
        
        # Записываем режим headless
        self.headless_mode = headless
        
        # Результаты парсинга
        all_listings = []
        
        try:
            # Инициализируем браузер
            browser_initialized = await self._init_browser()
            if not browser_initialized:
                self.logger.error("Не удалось инициализировать браузер")
                return []
            
            # Создаем новую страницу
            page = await self._create_new_page()
            
            # Устанавливаем обработчики для перехвата запросов и блокировки ненужных ресурсов
            await self._setup_request_interception(page)
            
            # Ограничиваем количество страниц для парсинга
            pages_to_process = max_pages if max_pages is not None else float('inf')
            
            # Начинаем с первой страницы
            current_page = 1
            
            while current_page <= pages_to_process:
                self.logger.info(f"Обработка страницы {current_page}/{pages_to_process if max_pages is not None else 'все'}")
                
                # Получаем URL страницы результатов
                page_url = await self._get_page_url(current_page)
                self.logger.info(f"URL страницы: {page_url}")
                
                # Загружаем страницу с расширенной обработкой ошибок
                page_loaded = await self._wait_for_page_load(page, page_url)
                if not page_loaded:
                    self.logger.error(f"Не удалось загрузить страницу {current_page}. Пропускаем.")
                    # Пробуем с другим прокси, если есть
                    new_proxy = self.proxy_manager.get_proxy()
                    if new_proxy:
                        self.logger.info(f"Меняем прокси на {new_proxy.get('server', new_proxy)} и пробуем еще раз")
                        self.proxy = new_proxy
                        # Пробуем с новым прокси
                        context_options = self._generate_browser_context_options()
                        await self.context.close()
                        self.context = await self.browser.new_context(**context_options)
                        page = await self._create_new_page()
                        await self._setup_request_interception(page)
                        # Пробуем эту же страницу еще раз
                        continue
                    # Если нет доступных прокси, переходим к следующей странице
                    current_page += 1
                    continue
                
                # Получаем объявления со страницы
                try:
                    page_listings = await self._extract_listings_from_page(page)
                    self.logger.info(f"Найдено {len(page_listings)} объявлений на странице {current_page}")
                    
                    if page_listings:
                        all_listings.extend(page_listings)
                        
                        # Проверяем, нужно ли продолжать парсинг
                        if len(all_listings) >= (max_pages or 1) * self.ITEMS_PER_PAGE:
                            self.logger.info("Достигнуто максимальное количество объявлений")
                            break
                    else:
                        self.logger.warning(f"На странице {current_page} не найдено объявлений")
                        
                        # Проверяем, является ли это последней страницей
                        last_page_indicators = ["no_results", "empty_search", "end_of_list"]
                        is_last_page = False
                        
                        for indicator in last_page_indicators:
                            indicator_elem = await page.query_selector(f"[data-testid='{indicator}'], .{indicator}")
                            if indicator_elem:
                                is_last_page = True
                                self.logger.info(f"Обнаружен индикатор последней страницы: {indicator}")
                                break
                        
                        if is_last_page:
                            self.logger.info("Достигнут конец списка результатов")
                            break
                
                except Exception as e:
                    self.logger.error(f"Ошибка при обработке страницы {current_page}: {e}")
                
                # Сообщаем об успешном использовании прокси
                if self.proxy:
                    self.proxy_manager.report_success(self.proxy)
                
                # Переходим к следующей странице
                current_page += 1
                
                # Добавляем случайную задержку между страницами
                await self._add_random_delay()
            
            self.logger.info(f"Завершен парсинг {current_page - 1} страниц, найдено {len(all_listings)} объявлений")
            return all_listings
            
        except Exception as e:
            self.logger.error(f"Произошла ошибка при запуске парсера: {e}")
            return []
            
        finally:
            # Закрываем браузер в любом случае
            try:
                await self.close()
            except Exception as close_error:
                self.logger.error(f"Ошибка при закрытии браузера: {close_error}")
    
    async def _setup_request_interception(self, page: Page):
        """
        Настраивает перехват запросов для блокировки ненужных ресурсов.
        
        Args:
            page: Страница для настройки
        """
        # Блокируем ненужные ресурсы для ускорения загрузки
        await page.route('**/*.{png,jpg,jpeg,gif,svg,webp,css,woff,woff2,ttf,otf}', lambda route: route.abort() if 'mercadolibre.com/D_NQ_NP' not in route.request.url else route.continue_())
        
        # Блокируем аналитику и трекеры
        await page.route('**/analytics.js', lambda route: route.abort())
        await page.route('**/gtm.js', lambda route: route.abort())
        await page.route('**/fbevents.js', lambda route: route.abort())
        
        # Блокируем рекламу
        await page.route('**/ads/**', lambda route: route.abort())
        await page.route('**/ad/**', lambda route: route.abort())
        
        # Изменяем заголовки запросов для маскировки под обычный браузер
        await page.route('**/*', lambda route: route.continue_(
            headers={
                **route.request.headers,
                'Accept-Language': 'es-UY,es;q=0.9,en;q=0.8',
                'Sec-Ch-Ua': '"Chromium";v="110", "Not A(Brand";v="24", "Google Chrome";v="110"',
                'Sec-Ch-Ua-Platform': '"Windows"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1'
            }
        ) if route.request.resource_type == 'document' else route.continue_())
    
    async def run_with_details(self, listings: List[Listing], headless: bool = True) -> List[Listing]:
        """
        Получает детальную информацию для списка объявлений.
        
        Args:
            listings: Список объявлений
            headless: Запускать браузер в фоновом режиме
            
        Returns:
            List[Listing]: Список объявлений с детальной информацией
        """
        if not listings:
            self.logger.warning("Пустой список объявлений для получения деталей")
            return []
        
        # Инициализируем семафор для ограничения одновременных запросов
        self.semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_DETAIL_PAGES)
        
        # Записываем режим headless
        self.headless_mode = headless
        
        try:
            # Инициализируем браузер
            browser_initialized = await self._init_browser()
            if not browser_initialized:
                self.logger.error("Не удалось инициализировать браузер для получения деталей")
                return []
            
            # Создаем семафор для ограничения одновременных запросов
            semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_DETAIL_PAGES)
            
            # Функция для обработки одного объявления
            async def process_listing(listing: Listing) -> Optional[Listing]:
                async with semaphore:
                    try:
                        # Создаем новую страницу для каждого объявления
                        page = await self._create_new_page()
                        
                        try:
                            # Настраиваем перехват запросов
                            await self._setup_request_interception(page)
                            
                            # Загружаем страницу объявления
                            page_loaded = await self._wait_for_page_load(page, str(listing.url), self.DETAIL_PAGE_TIMEOUT)
                            if not page_loaded:
                                self.logger.error(f"Не удалось загрузить страницу объявления: {listing.url}")
                                return None
                            
                            # Имитируем человеческое поведение
                            await self._simulate_human_behavior(page)
                            
                            # Получаем детальную информацию
                            detailed_listing = await self._extract_listing_details(page, listing)
                            
                            # Сообщаем об успешном использовании прокси
                            if self.proxy:
                                self.proxy_manager.report_success(self.proxy)
                            
                            return detailed_listing
                        finally:
                            # Закрываем страницу в любом случае
                            await page.close()
                    except Exception as e:
                        self.logger.error(f"Ошибка при получении деталей для {listing.url}: {e}")
                        return None
            
            # Создаем задачи для параллельной обработки объявлений
            tasks = [process_listing(listing) for listing in listings]
            
            # Ждем выполнения всех задач
            results = await asyncio.gather(*tasks)
            
            # Фильтруем результаты, убирая None
            detailed_listings = [listing for listing in results if listing is not None]
            
            self.logger.info(f"Получена детальная информация для {len(detailed_listings)} из {len(listings)} объявлений")
            
            return detailed_listings
        
        except Exception as e:
            self.logger.error(f"Произошла ошибка при получении деталей: {e}")
            return []
        
        finally:
            # Закрываем браузер в любом случае
            try:
                await self.close()
            except Exception as close_error:
                self.logger.error(f"Ошибка при закрытии браузера: {close_error}")

    async def _extract_listing_details(self, page: Page, listing: Listing) -> Optional[Listing]:
        """
        Извлекает детальную информацию об объявлении.
        
        Args:
            page: Страница с объявлением
            listing: Объект объявления с базовой информацией
            
        Returns:
            Optional[Listing]: Объявление с детальной информацией или None в случае ошибки
        """
        try:
            self.logger.debug(f"Извлечение деталей для: {listing.url}")
            
            # Получаем заголовок
            if not listing.title or listing.title == "Без названия":
                title = await self._extract_title(page)
                if title:
                    listing.title = title
            
            # Получаем цену
            if not listing.price:
                price = await self._extract_price(page)
                if price:
                    listing.price = price
            
            # Получаем описание
            description = await self._extract_description(page)
            if description:
                listing.description = description
            
            # Получаем местоположение
            location = await self._extract_location(page)
            if location:
                listing.location = location
            
            # Получаем площадь
            area = await self._extract_area_size(page)
            if area:
                listing.area = area
            
            # Получаем коммуникации
            utilities = await self._extract_utilities(page)
            if utilities:
                listing.utilities = utilities
            
            # Получаем изображение
            if not listing.image_url:
                image_url = await self._extract_main_image(page, str(listing.url))
                if image_url:
                    listing.image_url = image_url
            
            # Обновляем дополнительные атрибуты
            attributes = await self._extract_attributes(page)
            if attributes:
                # Создаем атрибуты, если их еще нет
                if not hasattr(listing, 'attributes') or listing.attributes is None:
                    listing.attributes = {}
                
                # Обновляем атрибуты
                for key, value in attributes.items():
                    listing.attributes[key] = value
            
            # Валидируем объект листинга перед возвратом
            if self._validate_listing(listing):
                return listing
            else:
                self.logger.warning(f"Объявление не прошло валидацию: {listing.url}")
                return None
            
        except Exception as e:
            self.logger.error(f"Ошибка при извлечении деталей для {listing.url}: {e}")
            return None

    def _validate_listing(self, listing: Listing) -> bool:
        """
        Проверяет корректность объекта Listing перед сохранением/отправкой.
        
        Args:
            listing: Объект для проверки
            
        Returns:
            bool: True, если объект валиден
        """
        # Проверяем обязательные поля
        if not listing.url:
            self.logger.error("Объявление не содержит URL")
            return False
        
        if not listing.title or listing.title == "Без названия":
            self.logger.warning(f"Объявление {listing.url} не содержит заголовка")
            # Генерируем заголовок из URL
            parts = str(listing.url).split('/')[-1].split('-')
            title = ' '.join([part.capitalize() for part in parts if len(part) > 2 and not part.startswith('MLU')])
            if title:
                listing.title = title
                self.logger.info(f"Сгенерирован заголовок из URL: {title}")
            else:
                listing.title = "Terreno en venta"
                self.logger.info("Установлен заголовок по умолчанию: Terreno en venta")
        
        if not listing.price:
            self.logger.warning(f"Объявление {listing.url} не содержит цены")
            listing.price = "Consultar precio"
        
        if not listing.source:
            self.logger.warning(f"Объявление {listing.url} не содержит источника")
            listing.source = self.SOURCE_NAME
        
        # Устанавливаем значения по умолчанию для необязательных полей
        if not listing.location:
            listing.location = "Uruguay"
        
        if not listing.description:
            listing.description = "Sin descripción"
        
        if not listing.utilities:
            listing.utilities = "No especificado"
        
        if not listing.attributes:
            listing.attributes = {}
        
        # Проверяем формат полей
        try:
            str(listing.url)
            str(listing.title)
            str(listing.price)
            str(listing.location)
            str(listing.description)
            if listing.image_url:
                str(listing.image_url)
        except Exception as e:
            self.logger.error(f"Ошибка при проверке формата полей: {e}")
            return False
        
        return True

    async def _extract_attributes_from_table(self, page, listing):
        """
        Извлекает атрибуты объявления из таблицы характеристик.
        
        Args:
            page: Объект страницы playwright
            listing: Объект листинга для обновления
        """
        try:
            # Извлекаем площадь
            if not listing.area:
                # Используем все селекторы области
                for selector in self.SELECTORS["area_section"]:
                    try:
                        area_text = await self._find_element_text(page, selector)
                        if area_text:
                            area = self._extract_area_from_text(area_text)
                            if area:
                                listing.area = area
                                break
                    except Exception as e:
                        logging.debug(f"Не удалось извлечь площадь с селектором {selector}: {str(e)}")
                
                # Если площадь не найдена, пытаемся использовать JavaScript для поиска
                if not listing.area:
                    area_js = """
                    (() => {
                        const rows = Array.from(document.querySelectorAll('table tr'));
                        for (const row of rows) {
                            const text = row.textContent.toLowerCase();
                            if (text.includes('superficie') || text.includes('área') || 
                                text.includes('terreno') || text.includes('lote')) {
                                return row.textContent;
                            }
                        }
                        return null;
                    })()
                    """
                    area_text = await page.evaluate(area_js)
                    if area_text:
                        area = self._extract_area_from_text(area_text)
                        if area:
                            listing.area = area
                
            # Извлекаем коммуникации
            if not listing.utilities:
                # Используем все селекторы коммуникаций
                for selector in self.SELECTORS["utilities_section"]:
                    try:
                        utilities_text = await self._find_element_text(page, selector)
                        if utilities_text:
                            utilities = self._extract_utilities_from_text(utilities_text)
                            if utilities:
                                listing.utilities = utilities
                                break
                    except Exception as e:
                        logging.debug(f"Не удалось извлечь коммуникации с селектором {selector}: {str(e)}")
                
                # Если коммуникации не найдены, пытаемся использовать JavaScript для поиска
                if not listing.utilities:
                    utilities_js = """
                    (() => {
                        const rows = Array.from(document.querySelectorAll('table tr'));
                        for (const row of rows) {
                            const text = row.textContent.toLowerCase();
                            if (text.includes('servicios') || text.includes('agua') || 
                                text.includes('luz') || text.includes('electricidad')) {
                                return row.textContent;
                            }
                        }
                        
                        // Поиск в описании
                        const description = document.querySelector('.ui-pdp-description__content');
                        if (description) {
                            const text = description.textContent.toLowerCase();
                            if (text.includes('servicios') || text.includes('agua') || 
                                text.includes('luz') || text.includes('electricidad')) {
                                const sentences = description.textContent.split('.');
                                for (const sentence of sentences) {
                                    if (sentence.toLowerCase().includes('servicios') || 
                                        sentence.toLowerCase().includes('agua') || 
                                        sentence.toLowerCase().includes('luz') || 
                                        sentence.toLowerCase().includes('electricidad')) {
                                        return sentence;
                                    }
                                }
                            }
                        }
                        
                        return null;
                    })()
                    """
                    utilities_text = await page.evaluate(utilities_js)
                    if utilities_text:
                        utilities = self._extract_utilities_from_text(utilities_text)
                        if utilities:
                            listing.utilities = utilities
            
            # Извлекаем зонирование
            if not listing.zoning:
                # Используем все селекторы зонирования
                for selector in self.SELECTORS["zoning_section"]:
                    try:
                        zoning_text = await self._find_element_text(page, selector)
                        if zoning_text:
                            zoning = self._extract_zoning_from_text(zoning_text)
                            if zoning:
                                listing.zoning = zoning
                                break
                    except Exception as e:
                        logging.debug(f"Не удалось извлечь зонирование с селектором {selector}: {str(e)}")
                
                # Если зонирование не найдено, пытаемся использовать JavaScript для поиска
                if not listing.zoning:
                    zoning_js = """
                    (() => {
                        const rows = Array.from(document.querySelectorAll('table tr'));
                        for (const row of rows) {
                            const text = row.textContent.toLowerCase();
                            if (text.includes('zona') || text.includes('zonificación') || 
                                text.includes('categoría') || text.includes('uso del suelo')) {
                                return row.textContent;
                            }
                        }
                        
                        // Поиск в описании
                        const description = document.querySelector('.ui-pdp-description__content');
                        if (description) {
                            const text = description.textContent.toLowerCase();
                            if (text.includes('zona') || text.includes('zonificación') || 
                                text.includes('categoría') || text.includes('rural') || 
                                text.includes('urbano')) {
                                const sentences = description.textContent.split('.');
                                for (const sentence of sentences) {
                                    if (sentence.toLowerCase().includes('zona') || 
                                        sentence.toLowerCase().includes('zonificación') || 
                                        sentence.toLowerCase().includes('categoría') || 
                                        sentence.toLowerCase().includes('rural') || 
                                        sentence.toLowerCase().includes('urbano')) {
                                        return sentence;
                                    }
                                }
                            }
                        }
                        
                        return null;
                    })()
                    """
                    zoning_text = await page.evaluate(zoning_js)
                    if zoning_text:
                        zoning = self._extract_zoning_from_text(zoning_text)
                        if zoning:
                            listing.zoning = zoning
                
        except Exception as e:
            logging.error(f"Ошибка при извлечении атрибутов из таблицы: {str(e)}")
    
    def _extract_area_from_text(self, text):
        """
        Извлекает площадь из текста.
        
        Args:
            text: Текст, содержащий информацию о площади
            
        Returns:
            Строка с площадью или None, если площадь не найдена
        """
        if not text:
            return None
            
        text = text.lower()
        
        # Пытаемся найти числа с единицами измерения
        hectares_pattern = r"(\d+(?:[.,]\d+)?)\s*(?:ha|has|hectáreas|hectareas)"
        m2_pattern = r"(\d+(?:[.,]\d+)?)\s*(?:m2|m²|metros cuadrados|mts2|mts²)"
        
        # Проверяем наличие гектаров
        hectares_match = re.search(hectares_pattern, text)
        if hectares_match:
            hectares = float(hectares_match.group(1).replace(',', '.'))
            return f"{hectares} ha"
            
        # Проверяем наличие квадратных метров
        m2_match = re.search(m2_pattern, text)
        if m2_match:
            m2 = float(m2_match.group(1).replace(',', '.'))
            
            # Конвертируем в гектары, если площадь большая
            if m2 >= 10000:
                hectares = m2 / 10000
                return f"{hectares:.2f} ha"
            return f"{int(m2)} m²"
            
        # Если единицы измерения не указаны, пытаемся найти числа и контекст
        number_pattern = r"(\d+(?:[.,]\d+)?)"
        numbers = re.findall(number_pattern, text)
        
        if numbers and ("superficie" in text or "área" in text or "terreno" in text):
            area = float(numbers[0].replace(',', '.'))
            
            # Определяем единицы измерения по контексту и величине
            if area < 100 and ("ha" in text or "hectárea" in text or "hectarea" in text):
                return f"{area} ha"
            elif area >= 10000:
                hectares = area / 10000
                return f"{hectares:.2f} ha"
            else:
                return f"{int(area)} m²"
                
        return None
        
    def _extract_utilities_from_text(self, text):
        """
        Извлекает информацию о коммуникациях из текста.
        
        Args:
            text: Текст, содержащий информацию о коммуникациях
            
        Returns:
            Строка с коммуникациями или None, если информация не найдена
        """
        if not text:
            return None
            
        text = text.lower()
        utilities = []
        
        # Проверяем наличие конкретных коммуникаций
        if re.search(r"agua(?!\s*no)", text):
            utilities.append("Agua")
            
        if re.search(r"luz|electricidad(?!\s*no)", text):
            utilities.append("Electricidad")
            
        if re.search(r"gas(?!\s*no)", text):
            utilities.append("Gas")
            
        if re.search(r"internet|fibra|wifi(?!\s*no)", text):
            utilities.append("Internet")
            
        if re.search(r"alcantarillado|saneamiento(?!\s*no)", text):
            utilities.append("Saneamiento")
            
        # Проверяем на отсутствие коммуникаций
        if re.search(r"sin servicios|no tiene servicios", text):
            return "Sin servicios"
            
        # Если нашли хотя бы одну коммуникацию, возвращаем список
        if utilities:
            return ", ".join(utilities)
            
        # Если есть упоминание о коммуникациях, но нет конкретики
        if re.search(r"servicios|conexiones", text):
            # Ищем предложение с упоминанием коммуникаций
            sentences = re.split(r'[.!?]+', text)
            for sentence in sentences:
                if re.search(r"servicios|conexiones", sentence):
                    return sentence.strip()
                    
        return None
        
    def _extract_zoning_from_text(self, text):
        """
        Извлекает информацию о зонировании из текста.
        
        Args:
            text: Текст, содержащий информацию о зонировании
            
        Returns:
            Строка с зонированием или None, если информация не найдена
        """
        if not text:
            return None
            
        text = text.lower()
        
        # Проверяем наличие конкретных типов зонирования
        if re.search(r"rural(?!\s*a\s*urbano)", text):
            return "Rural"
            
        if re.search(r"urbano|urbanizado", text):
            return "Urbano"
            
        if re.search(r"suburbano", text):
            return "Suburbano"
            
        if re.search(r"turístico|turistico", text):
            return "Turístico"
            
        if re.search(r"industrial", text):
            return "Industrial"
            
        if re.search(r"residencial", text):
            return "Residencial"
            
        if re.search(r"comercial", text):
            return "Comercial"
            
        # Если есть упоминание о зонировании, но нет конкретики
        if re.search(r"zona|zonificación|zonificacion|categoría|categoria|uso del suelo", text):
            # Ищем предложение с упоминанием зонирования
            sentences = re.split(r'[.!?]+', text)
            for sentence in sentences:
                if re.search(r"zona|zonificación|zonificacion|categoría|categoria|uso del suelo", sentence):
                    return sentence.strip()
                    
        return None
        
    async def _find_element_text(self, page, selectors):
        """
        Находит текст элемента по списку селекторов.
        
        Args:
            page: Объект страницы playwright
            selectors: Список селекторов для поиска
            
        Returns:
            Текст элемента или None, если элемент не найден
        """
        if isinstance(selectors, str):
            selectors = [selectors]
            
        for selector in selectors:
            try:
                # Пытаемся найти элемент с заданным селектором
                element = await page.query_selector(selector)
                if element:
                    text = await element.text_content()
                    if text and text.strip():
                        return text.strip()
            except Exception as e:
                logging.debug(f"Не удалось найти элемент с селектором {selector}: {str(e)}")
                
        return None

    async def _extract_listing_details(self, page, listing, only_missing=False):
        """
        Извлекает подробную информацию о листинге.
        
        Args:
            page: Объект страницы playwright
            listing: Объект листинга для обновления
            only_missing: Если True, извлекаются только отсутствующие данные
            
        Returns:
            Обновленный объект листинга или None в случае ошибки
        """
        max_retries = 3
        current_retry = 0
        
        while current_retry < max_retries:
            try:
                if not listing.url:
                    logging.error(f"Невозможно извлечь детали: отсутствует URL")
                    return None
                    
                logging.info(f"Извлечение деталей для {listing.url} (попытка {current_retry + 1}/{max_retries})")
                
                # Переходим на страницу объявления
                await page.goto(listing.url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(2)  # Даем странице время загрузиться
                
                # Проверяем, что страница загрузилась корректно
                title = await page.title()
                if title == "Sorry, this page isn't available" or title == "Lo sentimos, esta página no está disponible":
                    logging.warning(f"Страница недоступна: {listing.url}")
                    
                    # Проверяем, нужно ли делать повторную попытку с другим прокси
                    if current_retry < max_retries - 1:
                        current_retry += 1
                        logging.info(f"Смена контекста и повторная попытка {current_retry + 1}/{max_retries}")
                        
                        # Пересоздаем контекст браузера с другим прокси
                        await self.close_browser()
                        await self.init_browser()
                        
                        # Получаем новую страницу
                        page = await self.browser.new_page()
                        await self._setup_page(page)
                        continue
                    return None
                
                # Проверяем на блокировку доступа
                for block_text in self.BLOCK_TEXTS:
                    if block_text.lower() in title.lower():
                        logging.warning(f"Доступ заблокирован: {block_text}")
                        
                        # Пробуем с другим прокси
                        if current_retry < max_retries - 1:
                            current_retry += 1
                            logging.info(f"Обнаружена блокировка. Смена контекста и повторная попытка {current_retry + 1}/{max_retries}")
                            
                            # Пересоздаем контекст браузера с другим прокси
                            await self.close_browser()
                            await self.init_browser()
                            
                            # Получаем новую страницу
                            page = await self.browser.new_page()
                            await self._setup_page(page)
                            continue
                        return None
                
                # Прокручиваем страницу для загрузки всего контента
                await self._scroll_page(page)
                
                # Обновляем основные характеристики, если они отсутствуют или не требуется only_missing
                if not only_missing or not listing.title:
                    title = await self._find_element_text(page, self.SELECTORS["detail_title"])
                    if title:
                        listing.title = self._clean_text(title)
                
                if not only_missing or not listing.price:
                    price_text = await self._find_element_text(page, self.SELECTORS["detail_price"])
                    if price_text:
                        price = self._extract_price(price_text)
                        if price:
                            listing.price = price
                
                if not only_missing or not listing.location:
                    location = await self._find_element_text(page, self.SELECTORS["detail_location"])
                    if location:
                        listing.location = self._clean_text(location)
                
                # Обновляем описание
                if not only_missing or not listing.description:
                    description = await self._find_element_text(page, self.SELECTORS["detail_description"])
                    if description:
                        listing.description = self._clean_text(description)
                        
                        # Если данные о площади, коммуникациях или зонировании отсутствуют,
                        # пробуем извлечь их из описания
                        if not listing.area:
                            area_from_desc = self._extract_area_from_text(description)
                            if area_from_desc:
                                listing.area = area_from_desc
                                
                        if not listing.utilities:
                            utilities_from_desc = self._extract_utilities_from_text(description)
                            if utilities_from_desc:
                                listing.utilities = utilities_from_desc
                                
                        if not listing.zoning:
                            zoning_from_desc = self._extract_zoning_from_text(description)
                            if zoning_from_desc:
                                listing.zoning = zoning_from_desc
                
                # Извлекаем данные из таблицы характеристик
                await self._extract_attributes_from_table(page, listing)
                
                # Извлекаем изображения
                if not only_missing or not listing.images:
                    images = await self._extract_images_from_detail(page)
                    if images:
                        listing.images = images
                        
                # Извлекаем данные о продавце
                if not only_missing or not listing.seller:
                    seller = await self._find_element_text(page, self.SELECTORS["detail_seller"])
                    if seller:
                        listing.seller = self._clean_text(seller)
                
                logging.info(f"Успешно извлечены детали для {listing.url}")
                return listing
                
            except Exception as e:
                logging.error(f"Ошибка при извлечении деталей листинга: {str(e)}")
                
                # Проверяем, нужно ли делать повторную попытку
                if current_retry < max_retries - 1:
                    current_retry += 1
                    logging.info(f"Повторная попытка {current_retry + 1}/{max_retries} через 5 секунд...")
                    await asyncio.sleep(5)
                else:
                    return None
                    
        return None

# ... (конец файла) ... 