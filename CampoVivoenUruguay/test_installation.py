#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Скрипт для проверки корректности установки и зависимостей
CampoVivoenUruguay парсера объявлений о продаже земли в Уругвае
"""

import os
import sys
import pkg_resources
import subprocess
import importlib
import logging
from colorama import init, Fore, Style

# Инициализация colorama для цветного вывода
init()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

def success(message):
    """Вывод успешного сообщения"""
    print(f"{Fore.GREEN}✓ {message}{Style.RESET_ALL}")

def error(message):
    """Вывод сообщения об ошибке"""
    print(f"{Fore.RED}✗ {message}{Style.RESET_ALL}")

def warning(message):
    """Вывод предупреждения"""
    print(f"{Fore.YELLOW}! {message}{Style.RESET_ALL}")

def info(message):
    """Вывод информационного сообщения"""
    print(f"{Fore.BLUE}ℹ {message}{Style.RESET_ALL}")

def check_python_version():
    """Проверка версии Python"""
    required_version = (3, 8)
    current_version = sys.version_info
    
    if current_version.major < required_version[0] or \
       (current_version.major == required_version[0] and current_version.minor < required_version[1]):
        error(f"Python версии {required_version[0]}.{required_version[1]} или выше требуется. "
              f"Установлено: {current_version.major}.{current_version.minor}")
        return False
    
    success(f"Python версии {current_version.major}.{current_version.minor} установлен")
    return True

def check_required_packages():
    """Проверка установленных пакетов"""
    required_packages = {
        "playwright": "1.20.0",
        "python-dotenv": "0.19.0",
        "aiohttp": "3.8.0",
        "pydantic": "1.9.0",
        "aiogram": "2.14.0",
        "beautifulsoup4": "4.10.0",
        "colorama": "0.4.4",
    }
    
    missing_packages = []
    outdated_packages = []
    
    for package, min_version in required_packages.items():
        try:
            installed = pkg_resources.get_distribution(package)
            installed_version = installed.version
            
            if pkg_resources.parse_version(installed_version) < pkg_resources.parse_version(min_version):
                outdated_packages.append((package, installed_version, min_version))
            else:
                success(f"Пакет {package} версии {installed_version} установлен")
        except pkg_resources.DistributionNotFound:
            missing_packages.append((package, min_version))
    
    if missing_packages:
        error(f"Отсутствуют необходимые пакеты: {', '.join([p[0] for p in missing_packages])}")
        
        if input("Установить отсутствующие пакеты? (y/n): ").lower() == 'y':
            for package, version in missing_packages:
                try:
                    subprocess.check_call([sys.executable, "-m", "pip", "install", f"{package}>={version}"])
                    success(f"Пакет {package}>={version} установлен")
                except subprocess.CalledProcessError:
                    error(f"Не удалось установить {package}>={version}")
                    return False
        else:
            return False
    
    if outdated_packages:
        warning("Некоторые пакеты устарели:")
        for package, installed_version, min_version in outdated_packages:
            warning(f"  {package}: установленная {installed_version}, требуется {min_version} или выше")
        
        if input("Обновить устаревшие пакеты? (y/n): ").lower() == 'y':
            for package, _, version in outdated_packages:
                try:
                    subprocess.check_call([sys.executable, "-m", "pip", "install", f"{package}>={version}", "--upgrade"])
                    success(f"Пакет {package} обновлен до версии >={version}")
                except subprocess.CalledProcessError:
                    error(f"Не удалось обновить {package}")
                    return False
        else:
            warning("Устаревшие пакеты не были обновлены")
    
    return len(missing_packages) == 0

def check_playwright_browsers():
    """Проверка браузеров Playwright"""
    try:
        import playwright
        from playwright.sync_api import sync_playwright
        
        success("Playwright установлен")
        
        # Проверка установленных браузеров через запуск команды
        result = subprocess.run([sys.executable, "-m", "playwright", "install", "--help"], 
                                capture_output=True, text=True)
        
        # Проверка, установлен ли chromium
        chromium_check = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium", "--dry-run"], 
                                        capture_output=True, text=True)
        
        if "chromium is already installed" in chromium_check.stdout:
            success("Chromium установлен для Playwright")
        else:
            warning("Chromium не установлен для Playwright")
            if input("Установить Chromium для Playwright? (y/n): ").lower() == 'y':
                try:
                    subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
                    success("Chromium успешно установлен")
                except subprocess.CalledProcessError:
                    error("Не удалось установить Chromium")
                    return False
            else:
                error("Chromium требуется для работы парсера")
                return False
                
        return True
    except ImportError:
        error("Playwright не установлен")
        return False
    except Exception as e:
        error(f"Ошибка при проверке Playwright: {e}")
        return False

def check_config_files():
    """Проверка конфигурационных файлов"""
    env_files = [
        (".env", ".env.example"),
        ("config/.env", "config/.env.example")
    ]
    
    for env_file, example_file in env_files:
        if os.path.exists(env_file):
            success(f"Файл {env_file} существует")
        else:
            warning(f"Файл {env_file} не найден")
            
            if os.path.exists(example_file):
                warning(f"Найден файл-пример {example_file}")
                if input(f"Создать {env_file} из примера? (y/n): ").lower() == 'y':
                    try:
                        # Создаем директорию, если ее нет
                        os.makedirs(os.path.dirname(env_file) or '.', exist_ok=True)
                        # Копируем файл
                        with open(example_file, 'r') as src, open(env_file, 'w') as dst:
                            dst.write(src.read())
                        success(f"Файл {env_file} создан из примера")
                    except Exception as e:
                        error(f"Не удалось создать {env_file}: {e}")
            else:
                error(f"Файл-пример {example_file} не найден")
    
    return True

def check_directories():
    """Проверка необходимых директорий"""
    required_dirs = [
        "data",
        "logs", 
        "errors",
        "images"
    ]
    
    for directory in required_dirs:
        if os.path.exists(directory) and os.path.isdir(directory):
            success(f"Директория {directory}/ существует")
        else:
            warning(f"Директория {directory}/ не найдена")
            try:
                os.makedirs(directory)
                success(f"Директория {directory}/ создана")
            except Exception as e:
                error(f"Не удалось создать директорию {directory}/: {e}")
                return False
    
    return True

def check_telegram_settings():
    """Проверка настроек Telegram"""
    try:
        from dotenv import load_dotenv
        
        # Загружаем переменные окружения
        load_dotenv()
        
        telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        if not telegram_bot_token or telegram_bot_token == "YOUR_BOT_TOKEN":
            warning("TELEGRAM_BOT_TOKEN не настроен или имеет значение по умолчанию")
            info("Вам нужно создать бота через @BotFather и получить токен")
        else:
            success("TELEGRAM_BOT_TOKEN настроен")
        
        if not telegram_chat_id or telegram_chat_id == "YOUR_CHAT_ID":
            warning("TELEGRAM_CHAT_ID не настроен или имеет значение по умолчанию")
            info("Вам нужно создать канал и добавить бота как администратора")
        else:
            success("TELEGRAM_CHAT_ID настроен")
        
        return True
    except Exception as e:
        error(f"Ошибка при проверке настроек Telegram: {e}")
        return False

def main():
    """Основная функция проверки установки"""
    print(f"{Fore.CYAN}====== Проверка установки CampoVivoenUruguay ======{Style.RESET_ALL}")
    
    all_checks_passed = True
    
    # Проверка версии Python
    all_checks_passed = check_python_version() and all_checks_passed
    
    # Проверка необходимых пакетов
    print(f"\n{Fore.CYAN}Проверка необходимых пакетов:{Style.RESET_ALL}")
    all_checks_passed = check_required_packages() and all_checks_passed
    
    # Проверка Playwright и браузеров
    print(f"\n{Fore.CYAN}Проверка Playwright:{Style.RESET_ALL}")
    all_checks_passed = check_playwright_browsers() and all_checks_passed
    
    # Проверка директорий
    print(f"\n{Fore.CYAN}Проверка директорий:{Style.RESET_ALL}")
    all_checks_passed = check_directories() and all_checks_passed
    
    # Проверка конфигурационных файлов
    print(f"\n{Fore.CYAN}Проверка конфигурационных файлов:{Style.RESET_ALL}")
    all_checks_passed = check_config_files() and all_checks_passed
    
    # Проверка настроек Telegram
    print(f"\n{Fore.CYAN}Проверка настроек Telegram:{Style.RESET_ALL}")
    all_checks_passed = check_telegram_settings() and all_checks_passed
    
    # Итоговый результат
    print(f"\n{Fore.CYAN}====== Результат проверки ======{Style.RESET_ALL}")
    if all_checks_passed:
        success("Все проверки пройдены успешно!")
        return 0
    else:
        error("Некоторые проверки не пройдены. Устраните проблемы перед запуском парсера.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 