#!/bin/bash

# Скрипт для мониторинга парсеров Uruguay Lands и отправки отчетов

# Получаем абсолютный путь к директории скрипта
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Загружаем переменные окружения из .env файла
if [ -f "$SCRIPT_DIR/.env" ]; then
    export $(grep -v '^#' "$SCRIPT_DIR/.env" | xargs)
else
    echo "Ошибка: Файл .env не найден в директории $SCRIPT_DIR"
    exit 1
fi

# Проверяем, что заданы необходимые переменные
if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
    echo "Ошибка: Необходимо указать TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID в файле .env"
    exit 1
fi

# Обеспечиваем существование директорий для логов и результатов
mkdir -p "$SCRIPT_DIR/logs"
mkdir -p "$SCRIPT_DIR/results"

# Функция для отправки сообщения в Telegram
send_to_telegram() {
    local message="$1"
    
    # Экранируем спецсимволы для Markdown
    message=$(echo "$message" | sed 's/\_/\\_/g' | sed 's/\*/\\*/g' | sed 's/\[/\\[/g' | sed 's/\]/\\]/g' | sed 's/\`/\\`/g')
    
    curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
        -d chat_id="$TELEGRAM_CHAT_ID" \
        -d text="$message" \
        -d parse_mode="MarkdownV2" > /dev/null
    
    local result=$?
    if [ $result -ne 0 ]; then
        echo "Ошибка при отправке сообщения в Telegram: код $result"
        return 1
    fi
    
    return 0
}

# Функция для проверки и отправки статуса работы парсеров
check_status() {
    local status_message="📊 *Статус парсеров Uruguay Lands*\n\n"
    
    # Добавляем информацию о системе
    status_message+="🖥 *Система:*\n"
    status_message+="Хост: $(hostname)\n"
    status_message+="Дата: $(date '+%Y-%m-%d %H:%M:%S')\n"
    status_message+="Нагрузка: $(uptime | awk '{print $10 $11 $12}')\n\n"
    
    # Проверяем запущенные процессы парсеров
    status_message+="🔄 *Активные процессы:*\n"
    
    local mercadolibre_processes=$(pgrep -f "run.sh --parser mercadolibre" | wc -l)
    local infocasas_processes=$(pgrep -f "run.sh --parser infocasas" | wc -l)
    
    status_message+="MercadoLibre: $mercadolibre_processes\n"
    status_message+="InfoCasas: $infocasas_processes\n\n"
    
    # Проверяем логи на наличие ошибок за последние 24 часа
    status_message+="⚠️ *Ошибки за последние 24 часа:*\n"
    
    local ml_errors=$(find "$SCRIPT_DIR/logs" -name "mercadolibre_*.log" -mtime -1 -exec grep -l "ERROR" {} \; | wc -l)
    local ic_errors=$(find "$SCRIPT_DIR/logs" -name "infocasas_*.log" -mtime -1 -exec grep -l "ERROR" {} \; | wc -l)
    
    status_message+="MercadoLibre: $ml_errors\n"
    status_message+="InfoCasas: $ic_errors\n\n"
    
    # Статистика по найденным объявлениям
    status_message+="📈 *Статистика объявлений:*\n"
    
    local ml_count=$(find "$SCRIPT_DIR/results" -name "mercadolibre_*.json" -mtime -7 | xargs cat 2>/dev/null | grep -o '"id":' | wc -l)
    local ic_count=$(find "$SCRIPT_DIR/results" -name "infocasas_*.json" -mtime -7 | xargs cat 2>/dev/null | grep -o '"id":' | wc -l)
    
    status_message+="MercadoLibre (7 дней): $ml_count\n"
    status_message+="InfoCasas (7 дней): $ic_count\n\n"
    
    # Статистика по отправленным в Telegram
    status_message+="📲 *Отправлено в Telegram:*\n"
    
    local sent_count=$(grep -o "Сообщение успешно отправлено" "$SCRIPT_DIR/logs/telegram_sender_*.log" 2>/dev/null | wc -l)
    local failed_count=$(grep -o "Ошибка при отправке сообщения" "$SCRIPT_DIR/logs/telegram_sender_*.log" 2>/dev/null | wc -l)
    
    status_message+="Успешно: $sent_count\n"
    status_message+="Ошибки: $failed_count\n\n"
    
    # Состояние дискового пространства
    status_message+="💾 *Дисковое пространство:*\n"
    status_message+="$(df -h . | awk 'NR==2 {print "Использовано: " $5 " (" $3 "/" $2 ")"}')\n\n"
    
    # Отправляем сообщение
    send_to_telegram "$status_message"
    
    echo "Статус парсеров отправлен в Telegram"
    return 0
}

# Функция для проверки и отправки отчета о результатах
check_results() {
    # Ищем новые файлы с результатами за последний час
    local new_ml_files=$(find "$SCRIPT_DIR/results" -name "mercadolibre_*.json" -mmin -60 | wc -l)
    local new_ic_files=$(find "$SCRIPT_DIR/results" -name "infocasas_*.json" -mmin -60 | wc -l)
    
    # Если нет новых файлов, выходим
    if [ "$new_ml_files" -eq 0 ] && [ "$new_ic_files" -eq 0 ]; then
        echo "Новых результатов не найдено."
        return 0
    fi
    
    # Считаем количество новых объявлений
    local ml_new_count=0
    local ic_new_count=0
    
    if [ "$new_ml_files" -gt 0 ]; then
        ml_new_count=$(find "$SCRIPT_DIR/results" -name "mercadolibre_*.json" -mmin -60 | xargs cat 2>/dev/null | grep -o '"id":' | wc -l)
    fi
    
    if [ "$new_ic_files" -gt 0 ]; then
        ic_new_count=$(find "$SCRIPT_DIR/results" -name "infocasas_*.json" -mmin -60 | xargs cat 2>/dev/null | grep -o '"id":' | wc -l)
    fi
    
    # Формируем сообщение
    local results_message="🔍 *Новые результаты парсинга*\n\n"
    
    if [ "$new_ml_files" -gt 0 ]; then
        results_message+="MercadoLibre: $ml_new_count объявлений в $new_ml_files файлах\n"
    fi
    
    if [ "$new_ic_files" -gt 0 ]; then
        results_message+="InfoCasas: $ic_new_count объявлений в $new_ic_files файлах\n"
    fi
    
    results_message+="\nВремя: $(date '+%Y-%m-%d %H:%M:%S')"
    
    # Отправляем сообщение
    send_to_telegram "$results_message"
    
    echo "Отчет о новых результатах отправлен в Telegram"
    return 0
}

# Функция для очистки старых файлов логов и результатов
cleanup() {
    echo "Очистка старых файлов..."
    
    # Удаляем логи старше 30 дней
    find "$SCRIPT_DIR/logs" -name "*.log" -mtime +30 -delete
    
    # Удаляем результаты старше 90 дней
    find "$SCRIPT_DIR/results" -name "*.json" -mtime +90 -delete
    
    echo "Очистка завершена."
    return 0
}

# Функция для отображения справки
show_help() {
    echo "Скрипт для мониторинга парсеров Uruguay Lands и отправки отчетов"
    echo ""
    echo "Использование: $0 <команда>"
    echo ""
    echo "Команды:"
    echo "  status    Проверяет и отправляет статус работы парсеров в Telegram"
    echo "  results   Проверяет наличие новых результатов и отправляет отчет"
    echo "  cleanup   Очищает старые файлы логов и результатов"
    echo "  help      Показывает эту справку"
    echo ""
    echo "Примеры:"
    echo "  $0 status"
    echo "  $0 results"
    echo "  $0 cleanup"
}

# Если нет аргументов, показываем справку
if [ $# -eq 0 ]; then
    show_help
    exit 0
fi

# Обработка команд
case "$1" in
    status)
        check_status
        exit $?
        ;;
    results)
        check_results
        exit $?
        ;;
    cleanup)
        cleanup
        exit $?
        ;;
    help)
        show_help
        exit 0
        ;;
    *)
        echo "Неизвестная команда: $1"
        show_help
        exit 1
        ;;
esac

exit 0 