#!/usr/bin/env python3
"""
Планировщик запуска парсеров через cron.
Запускает парсеры каждые 4 часа в дневное время и 1 раз ночью.
"""

import os
import sys
import asyncio
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"logs/scheduler_{datetime.now().strftime('%Y%m%d')}.log", mode='a')
    ]
)

logger = logging.getLogger("scheduler")

# Импортируем парсеры
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.parsers.mercadolibre import MercadoLibreParser
from app.parsers.infocasas import InfoCasasParser
from app.telegram_sender import send_listings_to_telegram

# Конфигурация расписания
DAYTIME_HOURS = [8, 12, 16, 20]  # Запуск в 8:00, 12:00, 16:00, 20:00
NIGHTTIME_HOUR = 2               # Ночной запуск в 2:00

async def run_parsers(is_nighttime=False, send_to_telegram=True):
    """
    Запускает все парсеры, настраивая параметры в зависимости от времени суток.
    
    Args:
        is_nighttime: True, если запуск происходит ночью
        send_to_telegram: Отправлять результаты в Telegram
    """
    # Создаем директории для хранения результатов и логов
    os.makedirs("logs", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    os.makedirs("errors", exist_ok=True)
    os.makedirs("images", exist_ok=True)
    
    # Определяем параметры в зависимости от времени суток
    max_pages = 3 if is_nighttime else 2
    headless = True  # В боевом режиме запускаем в фоне
    
    # Записываем время запуска
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    logger.info(f"Запуск парсеров {timestamp} ({'ночь' if is_nighttime else 'день'})")
    
    # Создаем экземпляры парсеров
    ml_parser = MercadoLibreParser(headless_mode=headless)
    ic_parser = InfoCasasParser(headless_mode=headless)
    
    all_listings = []
    
    try:
        # Запускаем парсер MercadoLibre
        logger.info("Запуск MercadoLibre парсера")
        ml_listings = await ml_parser.run_with_details(max_pages=max_pages, headless=headless)
        logger.info(f"MercadoLibre: получено {len(ml_listings)} объявлений")
        
        # Сохраняем результаты
        save_results("mercadolibre", ml_listings)
        all_listings.extend(ml_listings)
        
        # Запускаем парсер InfoCasas
        logger.info("Запуск InfoCasas парсера")
        ic_listings = await ic_parser.run_with_details(max_pages=max_pages, headless=headless)
        logger.info(f"InfoCasas: получено {len(ic_listings)} объявлений")
        
        # Сохраняем результаты
        save_results("infocasas", ic_listings)
        all_listings.extend(ic_listings)
        
        # Отправляем объявления в Telegram
        if send_to_telegram and all_listings:
            logger.info("Отправка объявлений в Telegram")
            
            # Проверяем наличие переменных окружения для Telegram
            if not os.getenv("TELEGRAM_BOT_TOKEN") or not os.getenv("TELEGRAM_CHAT_ID"):
                logger.warning("Не настроены переменные окружения для Telegram. Проверьте TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID")
            else:
                # Отправляем только новые объявления (за последние 12 часов)
                results = await send_listings_to_telegram(all_listings, only_recent=True)
                
                # Логируем результаты отправки
                if "error" in results:
                    logger.error(f"Ошибка при отправке в Telegram: {results['error']}")
                else:
                    for source, stats in results.items():
                        if isinstance(stats, dict):
                            logger.info(f"Отправлено в Telegram ({source}): {stats.get('sent', 0)} из {stats.get('total', 0)}")
        
    except Exception as e:
        logger.error(f"Ошибка при запуске парсеров: {e}")
    
    finally:
        # Закрываем ресурсы
        await ml_parser.close()
        await ic_parser.close()
        logger.info("Работа планировщика завершена")

def save_results(source, listings):
    """
    Сохраняет результаты в файл.
    
    Args:
        source: Название источника (mercadolibre, infocasas)
        listings: Список объявлений
    """
    if not listings:
        logger.warning(f"Нет объявлений для сохранения из {source}")
        return
    
    filename = f"data/{source}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    try:
        with open(filename, "w", encoding="utf-8") as f:
            for i, listing in enumerate(listings):
                f.write(f"Объявление {i+1}:\n")
                f.write(f"  URL: {listing.url}\n")
                f.write(f"  Заголовок: {listing.title}\n")
                f.write(f"  Цена: {listing.price}\n")
                f.write(f"  Расположение: {listing.location}\n")
                f.write(f"  Площадь: {listing.area}\n")
                f.write(f"  Дата обнаружения: {listing.date_scraped}\n")
                if listing.description:
                    f.write(f"  Описание: {listing.description[:200]}...\n")
                
                # Отмечаем, является ли объявление новым (за последние 12 часов)
                is_recent = False
                if hasattr(listing, 'attributes') and listing.attributes:
                    is_recent = listing.attributes.get('is_recent', False)
                f.write(f"  Новое: {'Да' if is_recent else 'Нет'}\n")
                f.write("\n")
        logger.info(f"Результаты {source} сохранены в {filename}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении результатов {source}: {e}")

def setup_cron():
    """
    Настраивает cron-задачи для автоматического запуска парсеров.
    Выводит команды, которые нужно добавить в crontab.
    """
    script_path = os.path.abspath(__file__)
    print("\nДля настройки cron выполните следующие шаги:")
    print("1. Запустите редактор crontab командой: crontab -e")
    print("2. Добавьте следующие строки:\n")
    
    # Дневные запуски (каждые 4 часа)
    for hour in DAYTIME_HOURS:
        print(f"0 {hour} * * * cd {os.path.dirname(script_path)} && python3 {script_path} --daytime")
    
    # Ночной запуск (1 раз)
    print(f"0 {NIGHTTIME_HOUR} * * * cd {os.path.dirname(script_path)} && python3 {script_path} --nighttime")
    
    print("\n3. Сохраните файл и закройте редактор.")
    print("4. Проверьте настройки командой: crontab -l\n")
    
    # Настройка переменных окружения для Telegram
    print("5. Для отправки объявлений в Telegram добавьте следующие переменные окружения в ~/.bashrc или ~/.zshrc:")
    print("   export TELEGRAM_BOT_TOKEN='your_bot_token'")
    print("   export TELEGRAM_CHAT_ID='your_chat_id'")
    print("6. Примените изменения: source ~/.bashrc (или source ~/.zshrc)")
    print("7. Проверьте настройку с помощью команды: env | grep TELEGRAM")

def setup_env_file():
    """Создает файл .env для хранения переменных окружения."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    
    if os.path.exists(env_path):
        print(f"Файл .env уже существует: {env_path}")
        return
    
    print("\nСоздание файла .env для переменных окружения")
    
    bot_token = input("Введите токен Telegram-бота: ")
    chat_id = input("Введите ID чата или канала Telegram: ")
    
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(f"TELEGRAM_BOT_TOKEN={bot_token}\n")
        f.write(f"TELEGRAM_CHAT_ID={chat_id}\n")
        f.write("# Прокси настройки\n")
        f.write("PROXY_SERVER=uy.smartproxy.com:15001\n")
        f.write("PROXY_USER=spgai22txz\n")
        f.write("PROXY_PASSWORD=jtx6i24Jpb~eweNw2eo\n")
    
    print(f"Файл .env создан: {env_path}")
    print("При запуске из cron убедитесь, что переменные окружения доступны или используйте python-dotenv")

def main():
    """Основная функция для запуска парсеров с учетом времени суток."""
    parser = argparse.ArgumentParser(description="Планировщик запуска парсеров")
    parser.add_argument("--setup", action="store_true", help="Настройка cron-заданий")
    parser.add_argument("--setup-env", action="store_true", help="Настройка файла .env")
    parser.add_argument("--daytime", action="store_true", help="Дневной запуск")
    parser.add_argument("--nighttime", action="store_true", help="Ночной запуск")
    parser.add_argument("--no-telegram", action="store_true", help="Не отправлять результаты в Telegram")
    
    args = parser.parse_args()
    
    if args.setup:
        setup_cron()
        return
    
    if args.setup_env:
        setup_env_file()
        return
    
    # Определяем режим запуска (день/ночь)
    is_nighttime = args.nighttime
    
    # Если не указан конкретный режим, определяем по текущему времени
    if not (args.daytime or args.nighttime):
        current_hour = datetime.now().hour
        is_nighttime = current_hour not in range(8, 22)  # Ночь с 22:00 до 8:00
    
    # Запускаем парсеры
    asyncio.run(run_parsers(is_nighttime, not args.no_telegram))

if __name__ == "__main__":
    main() 