#!/bin/bash

# Директория проекта
PROJECT_DIR=$(dirname "$0")
cd "$PROJECT_DIR" || exit 1

# Путь к скрипту запуска
RUNNER_SCRIPT="$PROJECT_DIR/run.sh"

# Проверка наличия скрипта запуска
if [ ! -f "$RUNNER_SCRIPT" ]; then
    echo "Ошибка: Скрипт запуска не найден: $RUNNER_SCRIPT"
    exit 1
fi

# Проверка прав на выполнение
if [ ! -x "$RUNNER_SCRIPT" ]; then
    echo "Установка прав на выполнение для $RUNNER_SCRIPT"
    chmod +x "$RUNNER_SCRIPT"
fi

# Функция установки cron задачи
setup_cron() {
    local interval=$1
    local crontab_line
    
    # Формирование crontab команды в зависимости от частоты
    case "$interval" in
        hourly)
            crontab_line="0 * * * * cd $PROJECT_DIR && $RUNNER_SCRIPT > /dev/null 2>&1"
            ;;
        daily)
            crontab_line="0 8 * * * cd $PROJECT_DIR && $RUNNER_SCRIPT > /dev/null 2>&1"
            ;;
        twice_daily)
            crontab_line="0 8,20 * * * cd $PROJECT_DIR && $RUNNER_SCRIPT > /dev/null 2>&1"
            ;;
        custom)
            read -p "Введите crontab выражение (например, '*/30 * * * *' для запуска каждые 30 минут): " custom_cron
            crontab_line="$custom_cron cd $PROJECT_DIR && $RUNNER_SCRIPT > /dev/null 2>&1"
            ;;
        *)
            echo "Неверный интервал: $interval"
            exit 1
            ;;
    esac
    
    # Проверка существующего crontab
    local existing_crontab
    existing_crontab=$(crontab -l 2>/dev/null || echo "")
    
    # Проверка наличия уже существующей задачи
    if echo "$existing_crontab" | grep -q "$RUNNER_SCRIPT"; then
        echo "Задача cron для парсера уже существует. Обновление..."
        existing_crontab=$(echo "$existing_crontab" | grep -v "$RUNNER_SCRIPT")
    fi
    
    # Добавление новой задачи
    echo "$existing_crontab" > /tmp/current_crontab
    echo "$crontab_line" >> /tmp/current_crontab
    
    # Установка нового crontab
    crontab /tmp/current_crontab
    rm /tmp/current_crontab
    
    echo "Cron задача установлена успешно!"
    echo "Настройка: $crontab_line"
}

# Вывод помощи
show_help() {
    echo "Использование: $0 [интервал]"
    echo "  интервал: hourly (каждый час), daily (раз в день), twice_daily (два раза в день), custom (свой интервал)"
    echo ""
    echo "Примеры:"
    echo "  $0 hourly        # запускать парсер каждый час"
    echo "  $0 daily         # запускать парсер раз в день (в 8:00)"
    echo "  $0 twice_daily   # запускать парсер два раза в день (в 8:00 и 20:00)"
    echo "  $0 custom        # задать произвольное расписание cron"
}

# Обработка аргументов
if [ "$1" = "help" ] || [ "$1" = "-h" ] || [ "$1" = "--help" ] || [ -z "$1" ]; then
    show_help
    exit 0
fi

# Установка cron задачи
setup_cron "$1"

echo "Настройка cron завершена!"
echo "Для просмотра текущих cron задач используйте команду: crontab -l" 