#!/usr/bin/env python3
"""
Модуль для управления прокси-серверами и обработки блокировок.
"""

import os
import json
import random
import logging
import asyncio
import requests
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class ProxyManager:
    """
    Управляет пулом прокси-серверов для обработки блокировок и ротации IP-адресов.
    Отслеживает статус каждого прокси и выбирает оптимальный для запросов.
    """
    
    def __init__(self, config_file: str = "config/proxies.json", cooldown_minutes: int = 30):
        """
        Инициализирует менеджер прокси.
        
        Args:
            config_file: Путь к файлу конфигурации прокси
            cooldown_minutes: Время "охлаждения" прокси после ошибки (в минутах)
        """
        self.config_file = config_file
        self.cooldown_minutes = cooldown_minutes
        self.proxies = []
        self.proxy_status = {}  # Статус каждого прокси
        self.load_proxies()
    
    def load_proxies(self):
        """Загружает конфигурацию прокси из файла."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                self.proxies = config.get('proxies', [])
                logger.info(f"Загружено {len(self.proxies)} прокси-серверов из конфигурации")
                
                # Инициализация статуса для каждого прокси
                for proxy in self.proxies:
                    proxy_id = proxy.get('id', proxy.get('server', 'unknown'))
                    if proxy_id not in self.proxy_status:
                        self.proxy_status[proxy_id] = {
                            'errors': 0,
                            'last_error': None,
                            'last_success': None,
                            'blocked': False,
                            'cooldown_until': None
                        }
            else:
                logger.warning(f"Файл конфигурации прокси {self.config_file} не найден")
        except Exception as e:
            logger.error(f"Ошибка при загрузке конфигурации прокси: {e}")
    
    def save_proxy_status(self):
        """Сохраняет статус прокси-серверов в файл."""
        try:
            status_file = os.path.join(os.path.dirname(self.config_file), "proxy_status.json")
            with open(status_file, 'w', encoding='utf-8') as f:
                json.dump(self.proxy_status, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.error(f"Ошибка при сохранении статуса прокси: {e}")
    
    def get_proxy(self) -> Optional[Dict[str, Any]]:
        """
        Выбирает оптимальный прокси для использования.
        
        Returns:
            Optional[Dict[str, Any]]: Конфигурация прокси или None, если все прокси недоступны
        """
        available_proxies = []
        
        for proxy in self.proxies:
            proxy_id = proxy.get('id', proxy.get('server', 'unknown'))
            status = self.proxy_status.get(proxy_id, {})
            
            # Проверка на блокировку и период охлаждения
            if status.get('blocked', False):
                logger.debug(f"Прокси {proxy_id} заблокирован и недоступен")
                continue
                
            cooldown_until = status.get('cooldown_until')
            if cooldown_until and cooldown_until > datetime.now():
                logger.debug(f"Прокси {proxy_id} находится в периоде охлаждения до {cooldown_until}")
                continue
            
            # Сбрасываем блокировку, если период охлаждения истек
            if status.get('blocked', False) and cooldown_until and cooldown_until <= datetime.now():
                status['blocked'] = False
                status['errors'] = 0
                logger.info(f"Прокси {proxy_id} разблокирован после периода охлаждения")
            
            # Добавляем прокси в список доступных
            available_proxies.append((proxy, status))
        
        if not available_proxies:
            logger.error("Нет доступных прокси-серверов")
            return None
        
        # Сортируем прокси по количеству ошибок (меньше - лучше)
        available_proxies.sort(key=lambda x: x[1].get('errors', 0))
        
        # Выбираем один из трех лучших прокси случайным образом (если доступны)
        top_count = min(3, len(available_proxies))
        selected_proxy, _ = random.choice(available_proxies[:top_count])
        
        logger.info(f"Выбран прокси {selected_proxy.get('id', selected_proxy.get('server', 'unknown'))}")
        return selected_proxy
    
    def report_success(self, proxy: Dict[str, Any]):
        """
        Отмечает успешное использование прокси.
        
        Args:
            proxy: Конфигурация используемого прокси
        """
        proxy_id = proxy.get('id', proxy.get('server', 'unknown'))
        
        if proxy_id in self.proxy_status:
            self.proxy_status[proxy_id]['last_success'] = datetime.now()
            self.proxy_status[proxy_id]['blocked'] = False
            logger.debug(f"Прокси {proxy_id} успешно использован")
            
            # Сбрасываем счетчик ошибок, если последняя ошибка была давно
            last_error = self.proxy_status[proxy_id].get('last_error')
            if last_error and (datetime.now() - last_error) > timedelta(hours=1):
                self.proxy_status[proxy_id]['errors'] = 0
            
            self.save_proxy_status()
    
    def report_error(self, proxy: Dict[str, Any], error_type: str = "general"):
        """
        Отмечает ошибку использования прокси.
        
        Args:
            proxy: Конфигурация используемого прокси
            error_type: Тип ошибки (general, timeout, blocked, captcha)
        """
        proxy_id = proxy.get('id', proxy.get('server', 'unknown'))
        
        if proxy_id in self.proxy_status:
            now = datetime.now()
            status = self.proxy_status[proxy_id]
            
            # Обновляем статистику ошибок
            status['last_error'] = now
            status['errors'] = status.get('errors', 0) + 1
            
            # Определяем действия в зависимости от типа ошибки
            if error_type in ["blocked", "captcha"]:
                # При блокировке или каптче сразу отключаем прокси на период охлаждения
                status['blocked'] = True
                status['cooldown_until'] = now + timedelta(minutes=self.cooldown_minutes)
                logger.warning(f"Прокси {proxy_id} заблокирован до {status['cooldown_until']} из-за ошибки {error_type}")
            elif error_type == "timeout":
                # При таймауте увеличиваем счетчик, но блокируем только после нескольких ошибок
                if status.get('errors', 0) >= 3:
                    status['blocked'] = True
                    status['cooldown_until'] = now + timedelta(minutes=self.cooldown_minutes // 2)
                    logger.warning(f"Прокси {proxy_id} заблокирован до {status['cooldown_until']} после {status['errors']} таймаутов")
            else:
                # Для общих ошибок блокируем после большего количества повторений
                if status.get('errors', 0) >= 5:
                    status['blocked'] = True
                    status['cooldown_until'] = now + timedelta(minutes=self.cooldown_minutes // 3)
                    logger.warning(f"Прокси {proxy_id} заблокирован до {status['cooldown_until']} после {status['errors']} общих ошибок")
            
            self.save_proxy_status()
    
    def is_captcha_detected(self, html_content: str) -> bool:
        """
        Проверяет наличие каптчи в HTML-контенте.
        
        Args:
            html_content: HTML-контент страницы
            
        Returns:
            bool: True, если обнаружена каптча
        """
        captcha_indicators = [
            "captcha", "robot", "i am not a robot", "verification", "verify", 
            "cloudflare", "DDoS protection", "automated request", "bot detection"
        ]
        
        html_lower = html_content.lower()
        for indicator in captcha_indicators:
            if indicator in html_lower:
                logger.warning(f"Обнаружен индикатор каптчи: '{indicator}'")
                return True
        
        return False
    
    def is_ip_blocked(self, html_content: str, status_code: int = 200) -> bool:
        """
        Проверяет, заблокирован ли IP на основе HTML-контента и кода статуса.
        
        Args:
            html_content: HTML-контент страницы
            status_code: Код статуса HTTP
            
        Returns:
            bool: True, если IP заблокирован
        """
        # Проверка кода статуса
        if status_code in [403, 429, 503]:
            logger.warning(f"Обнаружена блокировка IP по коду статуса: {status_code}")
            return True
        
        # Проверка содержимого HTML
        block_indicators = [
            "access denied", "denied access", "ip has been blocked", "too many requests",
            "rate limiting", "blocked", "429 Too Many Requests", "403 Forbidden", 
            "has been temporarily limited", "unusual traffic"
        ]
        
        html_lower = html_content.lower()
        for indicator in block_indicators:
            if indicator in html_lower:
                logger.warning(f"Обнаружен индикатор блокировки: '{indicator}'")
                return True
        
        return False
    
    async def check_proxy(self, proxy: Dict[str, Any]) -> bool:
        """
        Проверяет работоспособность прокси.
        
        Args:
            proxy: Конфигурация прокси для проверки
            
        Returns:
            bool: True, если прокси работает
        """
        proxy_id = proxy.get('id', proxy.get('server', 'unknown'))
        proxy_url = f"http://{proxy.get('server')}"
        
        # Формируем строку аутентификации, если заданы логин и пароль
        auth = None
        if 'user_pattern' in proxy and 'password' in proxy:
            auth = (proxy['user_pattern'], proxy['password'])
        
        try:
            # Выполняем запрос через прокси
            proxies = {
                'http': proxy_url,
                'https': proxy_url
            }
            
            response = requests.get(
                'https://httpbin.org/ip',
                proxies=proxies,
                auth=auth,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                ip = result.get('origin', 'unknown')
                logger.info(f"Прокси {proxy_id} работает, внешний IP: {ip}")
                return True
            else:
                logger.warning(f"Прокси {proxy_id} вернул код статуса {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка при проверке прокси {proxy_id}: {e}")
            return False
    
    async def verify_all_proxies(self) -> Dict[str, bool]:
        """
        Проверяет все прокси и обновляет их статус.
        
        Returns:
            Dict[str, bool]: Словарь с результатами проверки (ID прокси -> статус)
        """
        results = {}
        tasks = []
        
        for proxy in self.proxies:
            proxy_id = proxy.get('id', proxy.get('server', 'unknown'))
            task = asyncio.create_task(self.check_proxy(proxy))
            tasks.append((proxy_id, task))
        
        for proxy_id, task in tasks:
            try:
                is_working = await task
                results[proxy_id] = is_working
                
                # Обновляем статус прокси
                if proxy_id in self.proxy_status:
                    if is_working:
                        # Сбрасываем блокировку, если прокси работает
                        self.proxy_status[proxy_id]['blocked'] = False
                        self.proxy_status[proxy_id]['errors'] = 0
                        self.proxy_status[proxy_id]['last_success'] = datetime.now()
                        self.proxy_status[proxy_id]['cooldown_until'] = None
                    else:
                        # Помечаем прокси как заблокированный
                        self.proxy_status[proxy_id]['blocked'] = True
                        self.proxy_status[proxy_id]['errors'] += 1
                        self.proxy_status[proxy_id]['last_error'] = datetime.now()
                        self.proxy_status[proxy_id]['cooldown_until'] = (
                            datetime.now() + timedelta(minutes=self.cooldown_minutes)
                        )
            except Exception as e:
                logger.error(f"Ошибка при обработке результата проверки прокси {proxy_id}: {e}")
                results[proxy_id] = False
        
        # Сохраняем обновленный статус
        self.save_proxy_status()
        
        return results 