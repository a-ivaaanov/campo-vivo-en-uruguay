#!/bin/bash
# Скрипт для ручного запуска парсера CampoVivoenUruguay

# Определяем директорию скрипта
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# Функция для логирования
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Проверяем наличие файла .env
if [ ! -f .env ]; then
    log "ОШИБКА: Файл .env не найден. Создайте его из примера .env.example"
    exit 1
fi

# Проверяем наличие файла config/.env
if [ ! -f config/.env ]; then
    log "ОШИБКА: Файл config/.env не найден. Создайте его из примера config/.env.example"
    exit 1
fi

# Выводим меню для выбора парсера
echo "=== ЗАПУСК ПАРСЕРА CAMPOVIVOENuruguay ==="
echo "1) Запустить все парсеры"
echo "2) Запустить только MercadoLibre"
echo "3) Запустить только InfoCasas"
echo "4) Запустить только Gallito"
echo "5) Запустить парсер в режиме отладки"
echo "6) Проверка соединения с Telegram"
echo "7) Выход"
echo "Выберите опцию (1-7): "
read option

case $option in
    1)
        log "Запуск всех парсеров..."
        python run.py --parser all --pages 2 --details --headless
        ;;
    2)
        log "Запуск парсера MercadoLibre..."
        python run.py --parser mercadolibre --pages 2 --details --headless
        ;;
    3)
        log "Запуск парсера InfoCasas..."
        python run.py --parser infocasas --pages 2 --details --headless
        ;;
    4)
        log "Запуск парсера Gallito..."
        python run.py --parser gallito --pages 2 --details --headless
        ;;
    5)
        log "Запуск в режиме отладки (без headless)..."
        python run.py --parser mercadolibre --pages 1 --details
        ;;
    6)
        log "Проверка соединения с Telegram..."
        python -c "from app.telegram_poster import send_telegram_direct; print('Результат отправки:', send_telegram_direct('Тестовое сообщение от CampoVivoenUruguay'))"
        ;;
    7)
        log "Выход из программы"
        exit 0
        ;;
    *)
        log "Неверная опция"
        exit 1
        ;;
esac

log "Работа скрипта завершена" 