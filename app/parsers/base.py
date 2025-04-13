#!/usr/bin/env python3
"""
Базовый класс для парсеров недвижимости.
"""

import asyncio
import logging
import random
import os
import time
import traceback
import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any, Set, Tuple, Callable

from playwright.async_api import async_playwright, Browser, Page, BrowserContext, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError
from playwright_stealth import stealth_async

# Импортируем модель данных
from app.models import Listing

class RetryException(Exception):
    """Исключение, указывающее на необходимость повторной попытки."""
    pass

class BaseParser(ABC):
    """
    Абстрактный базовый класс для всех парсеров.
    Определяет интерфейс и базовую функциональность для работы с браузером.
    """
    SOURCE_NAME: str = "base"  # Должен быть переопределен в дочерних классах

    def __init__(self, 
                 max_retries: int = 5, 
                 request_delay: tuple = (2, 5),
                 headless_mode: bool = True,
                 retry_base_delay: float = 2.0,
                 retry_max_delay: float = 60.0):
        """
        Инициализирует парсер.
        
        Args:
            max_retries: Максимальное количество попыток при ошибке
            request_delay: Диапазон задержки между запросами в секундах (мин, макс)
            headless_mode: Запускать браузер в фоновом режиме без GUI
            retry_base_delay: Базовая задержка перед повторной попыткой (секунды)
            retry_max_delay: Максимальная задержка перед повторной попыткой (секунды)
        """
        self.logger = logging.getLogger(f"parsers.{self.SOURCE_NAME}")
        self.max_retries = max_retries
        self.headless_mode = headless_mode
        self.request_delay_min, self.request_delay_max = request_delay
        self.retry_base_delay = retry_base_delay
        self.retry_max_delay = retry_max_delay
        
        # Playwright-ресурсы
        self.browser = None
        self.context = None
        
        # Для отслеживания обработанных URL
        self.seen_urls: Set[str] = set()
        
        # Статистика
        self.stats = {
            "pages_processed": 0,
            "listings_found": 0,
            "errors": 0,
            "retries": 0,
            "start_time": None,
            "end_time": None
        }

        # Список для сохранения данных об ошибках
        self.error_log = []

    async def _init_browser(self) -> bool:
        """
        Инициализирует браузер Playwright.
        
        Returns:
            bool: True если инициализация прошла успешно
        """
        return await self._with_retry(self._init_browser_impl, "инициализация браузера", max_retries=3)

    async def _init_browser_impl(self) -> bool:
        """
        Внутренняя реализация инициализации браузера.
        """
        try:
            self.logger.info(f"Инициализация браузера (headless={self.headless_mode})")
            
            # Запускаем Playwright
            playwright = await async_playwright().start()
            
            # Запуск браузера
            self.browser = await playwright.chromium.launch(
                headless=self.headless_mode
            )
            
            # Создаем контекст с размером окна
            self.context = await self.browser.new_context(
                viewport={"width": 1920, "height": 1080}
            )
            
            # Применяем stealth.js для маскировки автоматизации
            page = await self.context.new_page()
            await stealth_async(page)
            await page.close()
            
            self.logger.info("Браузер успешно инициализирован")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка при инициализации браузера: {e}")
            await self.close()
            raise RetryException(f"Ошибка инициализации браузера: {str(e)}")

    async def _page_navigation(self, page: Page, url: str) -> bool:
        """
        Выполняет навигацию на указанный URL с обработкой ошибок.
        
        Args:
            page: Страница браузера
            url: URL для загрузки
            
        Returns:
            bool: True если навигация успешна
        """
        return await self._with_retry(
            lambda: self._page_navigation_impl(page, url),
            f"навигация на {url}",
            max_retries=self.max_retries
        )

    async def _page_navigation_impl(self, page: Page, url: str) -> bool:
        """
        Внутренняя реализация навигации.
        """
        try:
            self.logger.debug(f"Переход на URL: {url}")
            
            response = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            if response and response.ok:
                self.logger.debug(f"Страница успешно загружена: {url}")
                return True
            else:
                status = response.status if response else "нет ответа"
                err_msg = f"Ошибка загрузки страницы: {status}"
                self.logger.warning(err_msg)
                raise RetryException(err_msg)
                
        except PlaywrightTimeoutError as e:
            self.logger.warning(f"Таймаут при загрузке {url}: {e}")
            raise RetryException(f"Таймаут загрузки страницы: {str(e)}")
            
        except PlaywrightError as e:
            self.logger.warning(f"Ошибка Playwright при загрузке {url}: {e}")
            raise RetryException(f"Ошибка Playwright: {str(e)}")
            
        except Exception as e:
            self.logger.warning(f"Неожиданная ошибка при загрузке {url}: {e}")
            raise RetryException(f"Неожиданная ошибка: {str(e)}")

    async def _with_retry(self, 
                          func: Callable, 
                          operation_name: str, 
                          max_retries: Optional[int] = None, 
                          args: tuple = (), 
                          kwargs: dict = {}) -> Any:
        """
        Универсальная функция для выполнения операций с повторными попытками при ошибке.
        
        Args:
            func: Функция для выполнения
            operation_name: Название операции для логирования
            max_retries: Максимальное количество попыток (если None, используется self.max_retries)
            args: Аргументы для передачи в функцию
            kwargs: Именованные аргументы для передачи в функцию
            
        Returns:
            Any: Результат функции при успешном выполнении
            
        Raises:
            Exception: Если все попытки завершились неудачей
        """
        if max_retries is None:
            max_retries = self.max_retries
            
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    self.logger.info(f"Повторная попытка {attempt+1}/{max_retries} для операции: {operation_name}")
                    self.stats["retries"] += 1
                
                result = await func(*args, **kwargs)
                return result
                
            except RetryException as e:
                if attempt < max_retries - 1:
                    # Экспоненциальная задержка с случайным компонентом
                    retry_delay = min(
                        self.retry_base_delay * (2 ** attempt) + random.uniform(0, 1),
                        self.retry_max_delay
                    )
                    
                    self.logger.debug(f"{operation_name}: {e}. Повторная попытка через {retry_delay:.2f} сек...")
                    await asyncio.sleep(retry_delay)
                else:
                    error_info = {
                        "operation": operation_name,
                        "attempts": attempt + 1,
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    }
                    self.error_log.append(error_info)
                    self.logger.error(f"Операция '{operation_name}' не удалась после {max_retries} попыток: {e}")
                    raise Exception(f"Операция '{operation_name}' не удалась после {max_retries} попыток: {e}")
                    
            except Exception as e:
                error_info = {
                    "operation": operation_name,
                    "attempts": attempt + 1,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                    "timestamp": datetime.now().isoformat()
                }
                self.error_log.append(error_info)
                self.logger.error(f"Критическая ошибка в операции '{operation_name}': {e}")
                raise

    async def _delay(self):
        """Выполняет случайную задержку между запросами с элементом непредсказуемости."""
        # Основная задержка
        base_delay = random.uniform(self.request_delay_min, self.request_delay_max)
        
        # С небольшой вероятностью (10%) делаем более длительную паузу
        if random.random() < 0.1:
            extra_delay = random.uniform(3, 8)
            self.logger.debug(f"Дополнительная задержка: {extra_delay:.2f} сек")
            base_delay += extra_delay
            
        self.logger.debug(f"Задержка: {base_delay:.2f} сек")
        await asyncio.sleep(base_delay)

    async def close(self):
        """Освобождает ресурсы браузера."""
        if self.context:
            try:
                await self.context.close()
            except Exception as e:
                self.logger.error(f"Ошибка при закрытии контекста: {e}")
            finally:
                self.context = None
                
        if self.browser:
            try:
                await self.browser.close()
            except Exception as e:
                self.logger.error(f"Ошибка при закрытии браузера: {e}")
            finally:
                self.browser = None
        
        # Сохраняем лог ошибок, если они были
        if self.error_log:
            try:
                error_log_dir = Path("logs")
                error_log_dir.mkdir(exist_ok=True)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                error_log_path = error_log_dir / f"error_log_{self.SOURCE_NAME}_{timestamp}.json"
                
                with open(error_log_path, "w", encoding="utf-8") as f:
                    json.dump(self.error_log, f, ensure_ascii=False, indent=2)
                    
                self.logger.info(f"Сохранен лог ошибок: {error_log_path}")
            except Exception as e:
                self.logger.error(f"Не удалось сохранить лог ошибок: {e}")

    @abstractmethod
    async def _get_page_url(self, page_number: int) -> str:
        """
        Возвращает URL страницы поиска с учетом номера страницы.
        
        Args:
            page_number: Номер страницы (начиная с 1)
            
        Returns:
            str: URL страницы поиска
        """
        pass

    @abstractmethod
    async def _extract_listings_from_page(self, page: Page) -> List[Listing]:
        """
        Извлекает объявления со страницы поиска.
        
        Args:
            page: Объект страницы браузера
            
        Returns:
            List[Listing]: Список объявлений
        """
        pass

    async def run(self, max_pages: Optional[int] = None, headless: bool = True) -> List[Listing]:
        """
        Основной метод запуска парсера.
        
        Args:
            max_pages: Максимальное количество страниц для обработки
            headless: Запускать браузер в фоновом режиме
            
        Returns:
            List[Listing]: Список объявлений
        """
        if max_pages is None:
            max_pages = int(os.getenv("MAX_PAGES", "2"))
            
        self.headless_mode = headless
        self.stats['start_time'] = datetime.now()
        all_listings: List[Listing] = []
        
        self.logger.info(f"Запуск парсера {self.SOURCE_NAME} (макс. страниц: {max_pages})")
        
        try:
            # Инициализация браузера
            if not await self._init_browser():
                self.logger.error("Не удалось инициализировать браузер")
                return []
            
            # Обработка страниц
            for page_number in range(1, max_pages + 1):
                try:
                    # Получаем URL текущей страницы
                    page_url = await self._get_page_url(page_number)
                    self.logger.info(f"Обработка страницы {page_number}/{max_pages}: {page_url}")
                    
                    # Создаем новую страницу
                    browser_page = await self.context.new_page()
                    
                    # Переходим на страницу
                    if not await self._page_navigation(browser_page, page_url):
                        self.logger.warning(f"Пропуск страницы {page_number} из-за ошибки навигации")
                        await browser_page.close()
                        continue
                    
                    # Извлекаем объявления с текущей страницы
                    try:
                        page_listings = await self._with_retry(
                            lambda: self._extract_listings_from_page(browser_page),
                            f"извлечение объявлений с страницы {page_number}"
                        )
                        self.logger.info(f"Найдено {len(page_listings)} объявлений на странице {page_number}")
                        all_listings.extend(page_listings)
                        self.stats["pages_processed"] += 1
                    except Exception as e:
                        self.logger.error(f"Ошибка при извлечении объявлений: {e}")
                        self.stats["errors"] += 1
                    
                    # Закрываем страницу
                    await browser_page.close()
                    
                    # Делаем задержку перед следующей страницей
                    if page_number < max_pages:
                        await self._delay()
                        
                except Exception as page_error:
                    self.logger.error(f"Ошибка при обработке страницы {page_number}: {page_error}")
                    self.stats["errors"] += 1
                    
                    # Сохраняем текущие результаты даже в случае ошибки
                    if all_listings:
                        self._save_intermediate_results(all_listings, page_number)
            
            # Удаляем дубликаты
            unique_listings = self._remove_duplicates(all_listings)
            
            self.stats["listings_found"] = len(unique_listings)
            self.stats["end_time"] = datetime.now()
            
            duration = (self.stats["end_time"] - self.stats["start_time"]).total_seconds()
            self.logger.info(f"Парсер {self.SOURCE_NAME} завершил работу за {duration:.1f} сек. "
                           f"Обработано страниц: {self.stats['pages_processed']}, "
                           f"найдено объявлений: {self.stats['listings_found']}, "
                           f"ошибок: {self.stats['errors']}, "
                           f"повторных попыток: {self.stats['retries']}")
            
            return unique_listings
            
        except Exception as e:
            self.logger.error(f"Критическая ошибка в парсере {self.SOURCE_NAME}: {e}")
            traceback.print_exc()
            
            # Сохраняем то, что уже получили
            if all_listings:
                self._save_intermediate_results(all_listings, "error")
                
            return all_listings
            
        finally:
            # Освобождаем ресурсы
            await self.close()

    def _save_intermediate_results(self, listings: List[Listing], marker: Any) -> None:
        """
        Сохраняет промежуточные результаты при возникновении ошибок.
        
        Args:
            listings: Список объявлений
            marker: Маркер для имени файла (номер страницы или тип ошибки)
        """
        try:
            results_dir = Path("data/intermediate")
            results_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.SOURCE_NAME}_partial_{marker}_{timestamp}.json"
            
            data = [listing.model_dump() for listing in listings]
            
            with open(results_dir / filename, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
            self.logger.info(f"Сохранены промежуточные результаты: {filename} ({len(listings)} объявлений)")
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении промежуточных результатов: {e}")

    def _remove_duplicates(self, listings: List[Listing]) -> List[Listing]:
        """
        Удаляет дубликаты объявлений по URL.
        
        Args:
            listings: Список объявлений
            
        Returns:
            List[Listing]: Список уникальных объявлений
        """
        seen_urls = set()
        unique_listings = []
        
        for listing in listings:
            url = str(listing.url)
            if url not in seen_urls:
                seen_urls.add(url)
                unique_listings.append(listing)
                
        removed = len(listings) - len(unique_listings)
        if removed > 0:
            self.logger.info(f"Удалено {removed} дубликатов объявлений")
            
        return unique_listings

    def now_utc(self) -> datetime:
        """Возвращает текущее время в UTC."""
        return datetime.now(timezone.utc) 