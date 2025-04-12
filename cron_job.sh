#!/bin/bash

# Скрипт для настройки регулярного запуска парсеров Uruguay Lands через cron

# Получаем абсолютный путь к директории скрипта
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Проверяем наличие crontab
if ! command -v crontab &> /dev/null; then
    echo "Ошибка: crontab не установлен"
    exit 1
fi

# Функция для отображения справки
show_help() {
    echo "Скрипт для настройки регулярного запуска парсеров Uruguay Lands через cron"
    echo ""
    echo "Использование: $0 [опции]"
    echo ""
    echo "Опции:"
    echo "  --install       Устанавливает задания cron для регулярного запуска парсеров"
    echo "  --remove        Удаляет задания cron для парсеров"
    echo "  --status        Показывает текущий статус заданий cron для парсеров"
    echo "  --help          Показывает эту справку"
    echo ""
    echo "Примеры:"
    echo "  $0 --install"
    echo "  $0 --remove"
    echo "  $0 --status"
}

# Функция для установки cron заданий
install_cron() {
    # Создаем временный файл
    TEMP_CRON=$(mktemp)
    
    # Экспортируем текущие задания cron
    crontab -l > "$TEMP_CRON" 2>/dev/null || echo "" > "$TEMP_CRON"
    
    # Проверяем, нет ли уже наших заданий
    if grep -q "# UruguayLands Parser" "$TEMP_CRON"; then
        echo "Задания для UruguayLands уже установлены. Сначала удалите их с помощью --remove."
        rm "$TEMP_CRON"
        return 1
    fi
    
    # Добавляем заголовок
    echo "" >> "$TEMP_CRON"
    echo "# UruguayLands Parser - Установлено $(date)" >> "$TEMP_CRON"
    
    # Добавляем задание для запуска парсера MercadoLibre каждые 6 часов
    echo "0 */6 * * * cd \"$SCRIPT_DIR\" && ./run.sh --parser mercadolibre --pages 10 --headless true --details true >> \"$SCRIPT_DIR/logs/cron_mercadolibre.log\" 2>&1" >> "$TEMP_CRON"
    
    # Добавляем задание для запуска парсера InfoCasas каждые 12 часов
    echo "0 */12 * * * cd \"$SCRIPT_DIR\" && ./run.sh --parser infocasas --pages 10 --headless true --details true >> \"$SCRIPT_DIR/logs/cron_infocasas.log\" 2>&1" >> "$TEMP_CRON"
    
    # Добавляем задание для отправки отчета о работе каждый день в 9:00
    echo "0 9 * * * cd \"$SCRIPT_DIR\" && ./monitor.sh status >> \"$SCRIPT_DIR/logs/cron_monitor.log\" 2>&1" >> "$TEMP_CRON"
    
    # Добавляем задание для проверки результатов каждые 2 часа
    echo "0 */2 * * * cd \"$SCRIPT_DIR\" && ./monitor.sh results >> \"$SCRIPT_DIR/logs/cron_monitor.log\" 2>&1" >> "$TEMP_CRON"
    
    # Добавляем метку окончания
    echo "# UruguayLands Parser - Конец заданий" >> "$TEMP_CRON"
    echo "" >> "$TEMP_CRON"
    
    # Устанавливаем новые задания cron
    crontab "$TEMP_CRON"
    rm "$TEMP_CRON"
    
    echo "Задания cron для парсеров UruguayLands успешно установлены:"
    echo "- MercadoLibre парсер запускается каждые 6 часов"
    echo "- InfoCasas парсер запускается каждые 12 часов"
    echo "- Отчет о состоянии отправляется каждый день в 9:00"
    echo "- Проверка результатов выполняется каждые 2 часа"
    
    # Делаем запускаемыми скрипты
    chmod +x "$SCRIPT_DIR/run.sh"
    chmod +x "$SCRIPT_DIR/monitor.sh"
    
    return 0
}

# Функция для удаления cron заданий
remove_cron() {
    # Создаем временный файл
    TEMP_CRON=$(mktemp)
    
    # Экспортируем текущие задания cron
    crontab -l > "$TEMP_CRON" 2>/dev/null || echo "" > "$TEMP_CRON"
    
    # Проверяем, есть ли наши задания
    if ! grep -q "# UruguayLands Parser" "$TEMP_CRON"; then
        echo "Задания для UruguayLands не найдены."
        rm "$TEMP_CRON"
        return 1
    fi
    
    # Удаляем все строки между метками начала и конца
    sed -i '/# UruguayLands Parser/,/# UruguayLands Parser - Конец заданий/d' "$TEMP_CRON"
    
    # Устанавливаем обновленные задания cron
    crontab "$TEMP_CRON"
    rm "$TEMP_CRON"
    
    echo "Задания cron для парсеров UruguayLands успешно удалены."
    return 0
}

# Функция для проверки статуса cron заданий
check_status() {
    # Экспортируем текущие задания cron во временный файл
    TEMP_CRON=$(mktemp)
    crontab -l > "$TEMP_CRON" 2>/dev/null || echo "" > "$TEMP_CRON"
    
    # Проверяем, есть ли наши задания
    if ! grep -q "# UruguayLands Parser" "$TEMP_CRON"; then
        echo "Статус: Задания cron для парсеров UruguayLands не установлены."
        rm "$TEMP_CRON"
        return 1
    fi
    
    echo "Статус: Задания cron для парсеров UruguayLands установлены."
    echo "Текущие задания:"
    grep -A 5 "# UruguayLands Parser" "$TEMP_CRON" | grep -v "#"
    
    # Проверяем, запущены ли скрипты в данный момент
    if pgrep -f "run.sh --parser mercadolibre" > /dev/null; then
        echo "- Парсер MercadoLibre в данный момент запущен."
    else
        echo "- Парсер MercadoLibre в данный момент не запущен."
    fi
    
    if pgrep -f "run.sh --parser infocasas" > /dev/null; then
        echo "- Парсер InfoCasas в данный момент запущен."
    else
        echo "- Парсер InfoCasas в данный момент не запущен."
    fi
    
    # Проверяем права на выполнение скриптов
    if [ -x "$SCRIPT_DIR/run.sh" ]; then
        echo "- Скрипт run.sh имеет права на выполнение."
    else
        echo "- ВНИМАНИЕ: Скрипт run.sh не имеет прав на выполнение!"
    fi
    
    if [ -x "$SCRIPT_DIR/monitor.sh" ]; then
        echo "- Скрипт monitor.sh имеет права на выполнение."
    else
        echo "- ВНИМАНИЕ: Скрипт monitor.sh не имеет прав на выполнение!"
    fi
    
    rm "$TEMP_CRON"
    return 0
}

# Если нет аргументов, показываем справку
if [ $# -eq 0 ]; then
    show_help
    exit 0
fi

# Обработка опций командной строки
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        --install)
            install_cron
            exit $?
            ;;
        --remove)
            remove_cron
            exit $?
            ;;
        --status)
            check_status
            exit $?
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            echo "Неизвестный параметр: $1"
            show_help
            exit 1
            ;;
    esac
done

exit 0 