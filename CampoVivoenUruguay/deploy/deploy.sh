#!/bin/bash
# Скрипт для развертывания проекта CampoVivoenUruguay на сервере

set -e # Выход при любой ошибке

# Функция для логирования с временной меткой
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Проверяем наличие необходимых команд
commands=("python3" "git" "pip" "virtualenv")
for cmd in "${commands[@]}"; do
    if ! command -v $cmd &> /dev/null; then
        log "ERROR: Команда $cmd не найдена. Пожалуйста, установите её."
        exit 1
    fi
done

# Настройки
DEPLOY_DIR="${1:-/opt/campovivouruguay}"
VENV_DIR="$DEPLOY_DIR/venv"
REPO_URL="${2:-https://github.com/yourusername/CampoVivoenUruguay.git}"
CONFIG_SRC="${3:-./config-production}" # Директория с конфигурацией для продакшн

log "Начало развертывания CampoVivoenUruguay"
log "Целевая директория: $DEPLOY_DIR"
log "Репозиторий: $REPO_URL"

# Создаем директорию для проекта, если её нет
if [ ! -d "$DEPLOY_DIR" ]; then
    log "Создание директории $DEPLOY_DIR"
    sudo mkdir -p "$DEPLOY_DIR"
    sudo chown $(whoami) "$DEPLOY_DIR"
fi

# Перейдем в директорию
cd "$DEPLOY_DIR"
log "Рабочая директория: $(pwd)"

# Клонируем репозиторий или обновляем его
if [ -d ".git" ]; then
    log "Обновление существующего репозитория"
    git pull
else
    log "Клонирование репозитория"
    git clone "$REPO_URL" .
fi

# Создаем или активируем виртуальное окружение
if [ ! -d "$VENV_DIR" ]; then
    log "Создание виртуального окружения"
    virtualenv -p python3 "$VENV_DIR"
else
    log "Виртуальное окружение уже существует"
fi

# Активируем виртуальное окружение
source "$VENV_DIR/bin/activate"
log "Виртуальное окружение активировано"

# Устанавливаем зависимости
log "Установка основных зависимостей"
pip install -r requirements.txt

# Запуск скрипта проверки зависимостей
log "Проверка зависимостей с помощью test_installation.py"
python test_installation.py
if [ $? -ne 0 ]; then
    log "ОШИБКА: Не все необходимые зависимости установлены"
    log "Пожалуйста, запустите python test_installation.py вручную для устранения проблем"
    exit 1
fi

# Установка Playwright уже проверяется в test_installation.py

# Копируем конфигурационные файлы, если они предоставлены
if [ -d "$CONFIG_SRC" ]; then
    log "Копирование конфигурации из $CONFIG_SRC"
    cp -v "$CONFIG_SRC/.env" .
    cp -v "$CONFIG_SRC/config.env" config/.env
else
    # Проверяем наличие конфигурационных файлов
    if [ ! -f ".env" ]; then
        log "ПРЕДУПРЕЖДЕНИЕ: Файл .env не найден. Копирование из примера."
        cp .env.example .env
    fi
    
    if [ ! -f "config/.env" ]; then
        log "ПРЕДУПРЕЖДЕНИЕ: Файл config/.env не найден. Копирование из примера."
        cp config/.env.example config/.env
    fi
fi

# Создаем нужные директории
log "Создание директорий для данных"
mkdir -p data logs errors images cache .cache examples

# Настройка прав доступа
log "Настройка прав доступа"
chmod +x run.py main.py cron_scheduler.py tools/*.py run_parser.sh setup.sh test_installation.py

# Установка systemd-сервиса
if [ -f "/etc/systemd/system/campovivo-parser.service" ]; then
    log "Сервис systemd уже существует, обновляем"
    sudo systemctl stop campovivo-parser.service
else
    log "Настройка сервиса systemd"
fi

# Копируем файл systemd и настраиваем его
sed -e "s|/path/to/CampoVivoenUruguay|$DEPLOY_DIR|g" \
    -e "s|your_username|$(whoami)|g" \
    -e "s|/usr/bin/python3|$VENV_DIR/bin/python|g" \
    systemd/campovivo-parser.service > /tmp/campovivo-parser.service

sudo cp /tmp/campovivo-parser.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable campovivo-parser.service
sudo systemctl start campovivo-parser.service

log "Проверка статуса сервиса"
sudo systemctl status campovivo-parser.service

log "Деплой завершен успешно!"
log "Проверьте логи сервиса: sudo journalctl -u campovivo-parser.service -f" 