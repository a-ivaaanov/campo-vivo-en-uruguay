FROM python:3.9-slim

# Установка необходимых пакетов
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Установка Playwright и браузеров
RUN pip install playwright && \
    playwright install chromium && \
    playwright install-deps chromium

# Установка рабочей директории
WORKDIR /app

# Копирование файлов зависимостей
COPY requirements.txt .

# Установка зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY . .

# Создание необходимых директорий
RUN mkdir -p logs data errors results images .cache

# Установка прав на выполнение скриптов
RUN chmod +x run_parser.sh cron_scheduler.py

# Создаем непривилегированного пользователя
RUN useradd -m appuser
RUN chown -R appuser:appuser /app
USER appuser

# Запуск планировщика при старте контейнера
CMD ["python", "cron_scheduler.py"] 