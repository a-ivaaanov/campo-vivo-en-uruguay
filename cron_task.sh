#!/bin/bash

# Скрипт для настройки регулярного запуска парсера через cron

# Получаем абсолютный путь к директории скрипта
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_SCRIPT="$SCRIPT_DIR/run.sh"
MONITOR_SCRIPT="$SCRIPT_DIR/monitor.sh"

# Проверка прав на выполнение скриптов
if [ ! -x "$RUN_SCRIPT" ]; then
    echo "Установка прав на выполнение для run.sh"
    chmod +x "$RUN_SCRIPT"
fi

if [ ! -x "$MONITOR_SCRIPT" ]; then
    echo "Установка прав на выполнение для monitor.sh"
    chmod +x "$MONITOR_SCRIPT"
fi

# Функция для установки cron-задания
setup_cron() {
    local schedule="$1"
    local command="$2"
    local comment="$3"
    
    # Проверяем, существует ли уже такое задание
    if crontab -l 2>/dev/null | grep -q "$command"; then
        echo "Задание уже существует в crontab: $command"
        return
    fi
    
    # Добавляем новое задание
    (crontab -l 2>/dev/null; echo "# $comment"; echo "$schedule $command") | crontab -
    
    echo "Задание добавлено в crontab: $schedule $command"
}

# Показать текущие установленные задания
show_cron_jobs() {
    echo "Текущие задания cron:"
    crontab -l 2>/dev/null || echo "Задания cron не найдены"
}

# Удалить все задания, связанные с парсером
remove_cron_jobs() {
    # Создаем временный файл
    local tempfile=$(mktemp)
    
    # Получаем текущие задания и исключаем строки с нашими скриптами
    crontab -l 2>/dev/null | grep -v "$SCRIPT_DIR" > "$tempfile"
    
    # Устанавливаем новый crontab
    crontab "$tempfile"
    
    # Удаляем временный файл
    rm "$tempfile"
    
    echo "Удалены все задания cron, связанные с парсером"
}

# Отображение справки
show_help() {
    echo "Использование: $0 [команда]"
    echo ""
    echo "Команды:"
    echo "  install      Установить регулярные задания cron для парсера"
    echo "  remove       Удалить все задания cron, связанные с парсером"
    echo "  show         Показать текущие задания cron"
    echo "  help         Показать эту справку"
    echo ""
    echo "По умолчанию, если не указана команда, выполняется 'install'"
}

# Установка заданий cron для парсера
install_cron_jobs() {
    # Запуск основного парсера каждый день в 8:00 утра
    setup_cron "0 8 * * *" "cd $SCRIPT_DIR && ./run.sh --parser all --pages 10 --headless true --details true" "Ежедневный запуск парсера в 8:00 утра"
    
    # Запуск проверки ошибок каждые 2 часа
    setup_cron "0 */2 * * *" "cd $SCRIPT_DIR && ./monitor.sh monitor" "Проверка ошибок парсера каждые 2 часа"
    
    # Отправка отчета о статусе каждый день в 9:00 утра
    setup_cron "0 9 * * *" "cd $SCRIPT_DIR && ./monitor.sh status" "Отправка ежедневного отчета о статусе в 9:00 утра"
    
    echo "Задания cron успешно установлены!"
}

# Обработка аргументов командной строки
COMMAND=${1:-install}

case "$COMMAND" in
    install)
        install_cron_jobs
        ;;
    remove)
        remove_cron_jobs
        ;;
    show)
        show_cron_jobs
        ;;
    help|-h|--help)
        show_help
        ;;
    *)
        echo "Неизвестная команда: $COMMAND"
        show_help
        exit 1
        ;;
esac

exit 0 