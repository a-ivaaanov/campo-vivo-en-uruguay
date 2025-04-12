#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Prometheus экспортер для проекта Uruguay Lands
Собирает метрики о работе парсеров и экспортирует их для Prometheus
"""

import os
import time
import json
import glob
import logging
from datetime import datetime, timedelta
from pathlib import Path
import subprocess

from prometheus_client import start_http_server, Gauge, Counter, Summary, Info

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs', 'prometheus_exporter.log'))
    ]
)

logger = logging.getLogger('prometheus_exporter')

# Определение директории проекта
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(PROJECT_DIR, 'results')
LOGS_DIR = os.path.join(PROJECT_DIR, 'logs')

# Создаем директории для логов и результатов, если их нет
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# Метрики Prometheus
# Информация о проекте
project_info = Info('uruguaylands_info', 'Информация о проекте Uruguay Lands')
project_info.info({
    'version': '1.0.0',
    'description': 'Парсер земельных участков в Уругвае',
    'project_dir': PROJECT_DIR
})

# Метрики для собранных объявлений
listings_count = Gauge('uruguaylands_listings_total', 'Общее количество собранных объявлений', ['source'])
listings_last_day = Gauge('uruguaylands_listings_last_day', 'Количество объявлений за последние 24 часа', ['source'])
listings_last_week = Gauge('uruguaylands_listings_last_week', 'Количество объявлений за последнюю неделю', ['source'])

# Метрики для файлов результатов
result_files_count = Gauge('uruguaylands_result_files_total', 'Общее количество файлов с результатами', ['source'])
result_files_last_day = Gauge('uruguaylands_result_files_last_day', 'Количество файлов за последние 24 часа', ['source'])

# Метрики для ошибок парсеров
parser_errors = Counter('uruguaylands_parser_errors_total', 'Общее количество ошибок при парсинге', ['source', 'error_type'])
parser_error_rate = Gauge('uruguaylands_parser_error_rate', 'Доля ошибок при парсинге', ['source'])

# Метрики для времени выполнения парсеров
parser_execution_time = Summary('uruguaylands_parser_execution_seconds', 'Время выполнения парсера', ['source'])
parser_last_execution = Gauge('uruguaylands_parser_last_execution_timestamp', 'Время последнего запуска парсера', ['source'])

# Метрики для системных ресурсов
disk_usage = Gauge('uruguaylands_disk_usage_bytes', 'Использование дискового пространства', ['type'])
process_count = Gauge('uruguaylands_process_count', 'Количество активных процессов парсеров', ['source'])


def count_listings_by_source(source, time_filter=None):
    """
    Подсчитывает количество объявлений по источнику с опциональной фильтрацией по времени
    
    Args:
        source (str): Источник данных (mercadolibre, infocasas)
        time_filter (datetime, optional): Фильтр по времени создания файла
        
    Returns:
        int: Количество объявлений
    """
    total_listings = 0
    
    # Получаем список файлов результатов для указанного источника
    pattern = f"{source}*.json"
    result_files = glob.glob(os.path.join(RESULTS_DIR, pattern))
    
    for file_path in result_files:
        file_stat = os.stat(file_path)
        file_time = datetime.fromtimestamp(file_stat.st_mtime)
        
        # Применяем фильтр по времени, если указан
        if time_filter and file_time < time_filter:
            continue
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    total_listings += len(data)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Ошибка при чтении файла {file_path}: {e}")
            parser_errors.labels(source=source, error_type='json_decode').inc()
    
    return total_listings


def count_result_files(source, time_filter=None):
    """
    Подсчитывает количество файлов результатов по источнику с опциональной фильтрацией по времени
    
    Args:
        source (str): Источник данных (mercadolibre, infocasas)
        time_filter (datetime, optional): Фильтр по времени создания файла
        
    Returns:
        int: Количество файлов
    """
    pattern = f"{source}*.json"
    result_files = glob.glob(os.path.join(RESULTS_DIR, pattern))
    
    if time_filter:
        result_files = [f for f in result_files if datetime.fromtimestamp(os.stat(f).st_mtime) >= time_filter]
    
    return len(result_files)


def count_errors_in_logs(source, time_filter=None):
    """
    Подсчитывает количество ошибок в логах по источнику
    
    Args:
        source (str): Источник данных (mercadolibre, infocasas)
        time_filter (datetime, optional): Фильтр по времени создания файла лога
        
    Returns:
        dict: Словарь с типами ошибок и их количеством
    """
    error_counts = {
        'error': 0,
        'exception': 0,
        'failed': 0
    }
    
    # Поиск файлов логов для указанного источника
    pattern = f"{source}*.log"
    log_files = glob.glob(os.path.join(LOGS_DIR, pattern))
    
    for log_file in log_files:
        file_stat = os.stat(log_file)
        file_time = datetime.fromtimestamp(file_stat.st_mtime)
        
        # Применяем фильтр по времени, если указан
        if time_filter and file_time < time_filter:
            continue
            
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read().lower()
                error_counts['error'] += content.count('error')
                error_counts['exception'] += content.count('exception')
                error_counts['failed'] += content.count('failed')
        except IOError as e:
            logger.error(f"Ошибка при чтении файла лога {log_file}: {e}")
    
    return error_counts


def get_last_execution_time(source):
    """
    Получает время последнего запуска парсера по логам
    
    Args:
        source (str): Источник данных (mercadolibre, infocasas)
        
    Returns:
        float: Unix timestamp времени последнего запуска или None
    """
    pattern = f"{source}*.log"
    log_files = glob.glob(os.path.join(LOGS_DIR, pattern))
    
    if not log_files:
        return None
        
    # Сортируем по времени изменения файла (от новых к старым)
    log_files.sort(key=lambda x: os.stat(x).st_mtime, reverse=True)
    
    # Берем самый свежий лог-файл
    latest_log = log_files[0]
    
    try:
        # Проверяем содержимое файла на наличие строки о запуске парсера
        with open(latest_log, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if 'starting' in line.lower() or 'запуск' in line.lower():
                    # Извлекаем дату из строки лога (формат стандартного логирования Python)
                    try:
                        date_str = line.split(' - ')[0].strip()
                        dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S,%f')
                        return dt.timestamp()
                    except (ValueError, IndexError):
                        pass
    except IOError as e:
        logger.error(f"Ошибка при чтении файла лога {latest_log}: {e}")
    
    # Если не нашли явной метки запуска, возвращаем время создания файла
    return os.stat(latest_log).st_mtime


def get_disk_usage():
    """
    Получает информацию об использовании дискового пространства
    
    Returns:
        dict: Словарь с информацией об использовании диска
    """
    try:
        # Получаем общую информацию о диске
        total, used, free = None, None, None
        
        if os.name == 'posix':  # Linux, macOS
            output = subprocess.check_output(['df', '-k', PROJECT_DIR]).decode('utf-8')
            lines = output.strip().split('\n')
            if len(lines) >= 2:
                parts = lines[1].split()
                total = int(parts[1]) * 1024  # в байтах
                used = int(parts[2]) * 1024   # в байтах
                free = int(parts[3]) * 1024   # в байтах
        elif os.name == 'nt':  # Windows
            output = subprocess.check_output(['wmic', 'logicaldisk', 'get', 'size,freespace,caption']).decode('utf-8')
            lines = output.strip().split('\n')
            drive = os.path.splitdrive(PROJECT_DIR)[0] + '\\'
            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 3 and parts[0].strip().rstrip(':') + ':' == drive.rstrip('\\'):
                    free = int(parts[1])
                    total = int(parts[2])
                    used = total - free
                    break
        
        # Информация о директориях проекта
        results_size = sum(os.path.getsize(f) for f in glob.glob(os.path.join(RESULTS_DIR, '**'), recursive=True) if os.path.isfile(f))
        logs_size = sum(os.path.getsize(f) for f in glob.glob(os.path.join(LOGS_DIR, '**'), recursive=True) if os.path.isfile(f))
        
        return {
            'total': total,
            'used': used,
            'free': free,
            'results_dir': results_size,
            'logs_dir': logs_size
        }
    except (subprocess.SubprocessError, ValueError, IndexError) as e:
        logger.error(f"Ошибка при получении информации о диске: {e}")
        return {'total': None, 'used': None, 'free': None, 'results_dir': 0, 'logs_dir': 0}


def count_active_processes(source):
    """
    Подсчитывает количество активных процессов парсера
    
    Args:
        source (str): Источник данных (mercadolibre, infocasas)
        
    Returns:
        int: Количество активных процессов
    """
    try:
        if os.name == 'posix':  # Linux, macOS
            output = subprocess.check_output(['pgrep', '-f', f'python.*{source}'], stderr=subprocess.DEVNULL).decode('utf-8')
            return len(output.strip().split('\n'))
        elif os.name == 'nt':  # Windows
            output = subprocess.check_output(['tasklist', '/FI', f'IMAGENAME eq python.exe', '/FO', 'CSV'], stderr=subprocess.DEVNULL).decode('utf-8')
            return output.lower().count(source.lower())
    except subprocess.SubprocessError:
        return 0


def update_metrics():
    """
    Обновляет все метрики Prometheus
    """
    sources = ['mercadolibre', 'infocasas']
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    last_week = now - timedelta(days=7)
    
    # Обновляем метрики для каждого источника
    for source in sources:
        # Метрики для объявлений
        total_listings = count_listings_by_source(source)
        listings_count.labels(source=source).set(total_listings)
        
        day_listings = count_listings_by_source(source, yesterday)
        listings_last_day.labels(source=source).set(day_listings)
        
        week_listings = count_listings_by_source(source, last_week)
        listings_last_week.labels(source=source).set(week_listings)
        
        # Метрики для файлов результатов
        total_files = count_result_files(source)
        result_files_count.labels(source=source).set(total_files)
        
        day_files = count_result_files(source, yesterday)
        result_files_last_day.labels(source=source).set(day_files)
        
        # Метрики ошибок
        error_counts = count_errors_in_logs(source, last_week)
        for error_type, count in error_counts.items():
            parser_errors.labels(source=source, error_type=error_type)._value.set(count)
        
        total_errors = sum(error_counts.values())
        if total_listings > 0:
            error_rate = total_errors / (total_listings + total_errors)
            parser_error_rate.labels(source=source).set(error_rate)
        else:
            parser_error_rate.labels(source=source).set(0)
        
        # Время последнего запуска
        last_execution = get_last_execution_time(source)
        if last_execution:
            parser_last_execution.labels(source=source).set(last_execution)
        
        # Активные процессы
        active_processes = count_active_processes(source)
        process_count.labels(source=source).set(active_processes)
    
    # Метрики использования диска
    disk_info = get_disk_usage()
    for key, value in disk_info.items():
        if value is not None:
            disk_usage.labels(type=key).set(value)
    
    logger.info("Метрики успешно обновлены")


def main():
    """
    Основная функция экспортера метрик
    """
    # Порт для Prometheus (по умолчанию 9080)
    port = int(os.environ.get('PROMETHEUS_PORT', 9080))
    
    logger.info(f"Запуск Prometheus экспортера на порту {port}")
    
    # Запускаем HTTP-сервер для экспортера
    start_http_server(port)
    
    # Интервал обновления метрик (по умолчанию 60 секунд)
    interval = int(os.environ.get('METRICS_UPDATE_INTERVAL', 60))
    
    logger.info(f"Метрики будут обновляться каждые {interval} секунд")
    
    # Инициализируем метрики в первый раз
    update_metrics()
    
    # Запускаем бесконечный цикл обновления метрик
    while True:
        try:
            time.sleep(interval)
            update_metrics()
        except KeyboardInterrupt:
            logger.info("Экспортер остановлен пользователем")
            break
        except Exception as e:
            logger.error(f"Ошибка при обновлении метрик: {e}")
            # Продолжаем работу даже при ошибках


if __name__ == "__main__":
    main() 