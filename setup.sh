#!/bin/bash
# Скрипт для локальной установки и настройки проекта CampoVivoenUruguay

set -e # Выход при любой ошибке

# Функция для логирования с временной меткой
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "Начало установки CampoVivoenUruguay"

# Проверка наличия Python 3.8+
python_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
required_version="3.8"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    log "ОШИБКА: Требуется Python версии $required_version или выше. У вас версия $python_version"
    exit 1
else
    log "Python версии $python_version найден"
fi

# Создание виртуального окружения
if [ ! -d "venv" ]; then
    log "Создание виртуального окружения"
    python3 -m venv venv
else
    log "Виртуальное окружение уже существует"
fi

# Активация виртуального окружения
log "Активация виртуального окружения"
source venv/bin/activate

# Установка зависимостей
log "Установка зависимостей из requirements.txt"
pip install -r requirements.txt

# Запуск скрипта проверки зависимостей
log "Проверка зависимостей с помощью test_installation.py"
python test_installation.py
if [ $? -ne 0 ]; then
    log "ОШИБКА: Не все необходимые зависимости установлены"
    log "Запустите python test_installation.py вручную для интерактивной установки"
    exit 1
fi

# Создание конфигурационных файлов, если их нет
if [ ! -f ".env" ]; then
    log "Создание файла .env из примера"
    cp .env.example .env
    log "ВАЖНО: Отредактируйте файл .env, указав правильные значения для вашей конфигурации"
fi

if [ ! -f "config/.env" ]; then
    log "Создание файла config/.env из примера"
    mkdir -p config
    cp config/.env.example config/.env
    log "ВАЖНО: Отредактируйте файл config/.env, указав правильные значения для вашей конфигурации"
fi

# Создание необходимых директорий
log "Создание директорий для данных"
mkdir -p data logs errors images cache .cache examples

# Настройка прав доступа
log "Настройка прав доступа"
chmod +x run.py main.py cron_scheduler.py tools/*.py run_parser.sh test_installation.py

log "Установка завершена успешно!"
log "Для запуска парсера используйте: ./run_parser.sh"
log "Для запуска с определенными параметрами: ./run.py --help"

# Вывод инструкций по заполнению конфигурации
echo ""
echo "====================== СЛЕДУЮЩИЕ ШАГИ ======================"
echo "1. Отредактируйте файл .env, указав:"
echo "   - TELEGRAM_BOT_TOKEN - токен вашего Telegram бота"
echo "   - TELEGRAM_CHAT_ID - ID канала или чата для отправки объявлений"
echo ""
echo "2. Если вы планируете использовать прокси, укажите настройки в config/.env:"
echo "   - PROXY_HOST, PROXY_PORT, PROXY_USERNAME, PROXY_PASSWORD"
echo ""
echo "3. Для тестового запуска парсера выполните:"
echo "   source venv/bin/activate"
echo "   python run.py --parser mercadolibre --pages 1"
echo ""
echo "4. Для автоматического запуска через cron настройте задачу:"
echo "   crontab -e"
echo "   # Добавьте строку для запуска каждый час:"
echo "   0 * * * * cd $(pwd) && ./run_parser.sh >> logs/cron.log 2>&1"
echo "================================================================" 