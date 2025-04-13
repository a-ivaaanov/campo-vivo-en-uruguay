#!/usr/bin/env python3
"""
Инструмент для проверки настроек прокси и соединения с уругвайскими сайтами.
"""

import os
import sys
import requests
import json
import argparse
from pathlib import Path

# Добавляем корневую директорию проекта в sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from dotenv import load_dotenv

# Загружаем .env
dotenv_path = PROJECT_ROOT / 'config' / '.env'
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path)

def get_ip_info(proxy=None):
    """Получает информацию об IP-адресе."""
    try:
        if proxy:
            print(f"Использование прокси: {proxy}")
            proxies = {
                'http': proxy,
                'https': proxy
            }
            response = requests.get('https://ipinfo.io/json', proxies=proxies, timeout=10)
        else:
            print("Без использования прокси")
            response = requests.get('https://ipinfo.io/json', timeout=10)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Ошибка получения IP информации: {response.status_code}")
            return None
    except Exception as e:
        print(f"Ошибка при запросе IP информации: {e}")
        return None

def check_site_access(url, proxy=None):
    """Проверяет доступность сайта."""
    try:
        if proxy:
            proxies = {
                'http': proxy,
                'https': proxy
            }
            response = requests.get(url, proxies=proxies, timeout=10)
        else:
            response = requests.get(url, timeout=10)
        
        return {
            'url': url,
            'status_code': response.status_code,
            'accessible': response.status_code == 200,
            'content_length': len(response.content)
        }
    except Exception as e:
        return {
            'url': url,
            'status_code': None,
            'accessible': False,
            'error': str(e)
        }

def main():
    """Основная функция."""
    parser = argparse.ArgumentParser(description='Проверка настроек прокси для CampoVivoenUruguay')
    parser.add_argument('--proxy', help='Прокси для проверки (http://user:pass@host:port)')
    parser.add_argument('--env', action='store_true', help='Использовать прокси из .env файла')
    parser.add_argument('--verbose', '-v', action='store_true', help='Подробный вывод')
    
    args = parser.parse_args()
    
    # Получаем прокси из аргументов или .env
    proxy = None
    if args.env:
        if os.getenv('USE_PROXY') == 'true':
            server = os.getenv('SMARTPROXY_SERVER', '')
            user = os.getenv('SMARTPROXY_USER', '')
            password = os.getenv('SMARTPROXY_PASSWORD', '')
            
            if server and user and password:
                proxy = f"http://{user}:{password}@{server}"
                print(f"Использование прокси из .env: {server}")
            else:
                print("Ошибка: Не все параметры прокси указаны в .env")
        else:
            print("Прокси не включен в .env (USE_PROXY != true)")
    elif args.proxy:
        proxy = args.proxy
    
    # Проверяем текущий IP
    print("=== Информация о текущем IP ===")
    ip_info = get_ip_info(proxy)
    if ip_info:
        print(f"IP: {ip_info.get('ip')}")
        print(f"Страна: {ip_info.get('country')}")
        print(f"Регион: {ip_info.get('region')}")
        print(f"Город: {ip_info.get('city')}")
        print(f"Провайдер: {ip_info.get('org')}")
        if args.verbose:
            print("Полная информация:")
            print(json.dumps(ip_info, indent=2))
    
    # Проверяем доступность уругвайских сайтов
    print("\n=== Проверка доступности сайтов ===")
    sites = [
        'https://www.mercadolibre.com.uy',
        'https://www.infocasas.com.uy',
        'https://www.gallito.com.uy'
    ]
    
    for site in sites:
        result = check_site_access(site, proxy)
        status = "✅ Доступен" if result.get('accessible') else "❌ Недоступен"
        print(f"{site}: {status}")
        if args.verbose:
            print(f"  Статус код: {result.get('status_code')}")
            print(f"  Размер контента: {result.get('content_length')} байт")
            if 'error' in result:
                print(f"  Ошибка: {result.get('error')}")
    
    # Выводим рекомендации
    print("\n=== Рекомендации ===")
    if ip_info and ip_info.get('country') == 'UY':
        print("✅ Ваш IP определяется как уругвайский. Прокси настроен корректно.")
    else:
        print("⚠️ Ваш IP не определяется как уругвайский.")
        if not proxy:
            print("   Рекомендуется настроить прокси в Уругвае для корректной работы парсеров.")
        else:
            print("   Проверьте настройки прокси. Возможно, прокси не работает или не находится в Уругвае.")

if __name__ == '__main__':
    main() 