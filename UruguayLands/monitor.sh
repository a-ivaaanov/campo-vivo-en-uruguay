#!/bin/bash

# Скрипт мониторинга для проекта Uruguay Lands
# Проверяет состояние парсеров, отправляет отчеты в Telegram

# Получаем абсолютный путь к директории скрипта
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Загружаем переменные окружения из .env файла
if [ -f "$SCRIPT_DIR/.env" ]; then
    export $(grep -v '^#' "$SCRIPT_DIR/.env" | xargs)
else
    echo "Ошибка: Файл .env не найден в директории $SCRIPT_DIR"
    exit 1
fi

# Проверяем наличие обязательных переменных
if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
    echo "Ошибка: Не найдены переменные TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID в файле .env"
    exit 1
fi

# Создаем директории для логов и результатов, если их нет
mkdir -p "$SCRIPT_DIR/logs"
mkdir -p "$SCRIPT_DIR/results"

# Файл для хранения временных меток проверки результатов
LAST_CHECK_FILE="$SCRIPT_DIR/.last_results_check"
touch "$LAST_CHECK_FILE"

# Функция для отправки сообщений в Telegram
send_to_telegram() {
    local message="$1"
    local parse_mode="${2:-HTML}"  # по умолчанию используем HTML форматирование
    
    # Подготовка данных для отправки
    local data_json
    data_json=$(jq -n \
                   --arg chat_id "$TELEGRAM_CHAT_ID" \
                   --arg text "$message" \
                   --arg parse_mode "$parse_mode" \
                   '{"chat_id": $chat_id, "text": $text, "parse_mode": $parse_mode}')
    
    # Отправка сообщения через API Telegram
    response=$(curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
                -H "Content-Type: application/json" \
                -d "$data_json")
    
    # Проверка ответа от Telegram API
    if echo "$response" | grep -q '"ok":true'; then
        echo "Сообщение успешно отправлено в Telegram"
    else
        echo "Ошибка при отправке сообщения в Telegram:"
        echo "$response"
    fi
}

# Функция для проверки статуса парсеров
check_status() {
    echo "Проверка статуса парсеров..."
    
    # Текущие дата и время
    local timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    
    # Формируем сообщение для отчета
    local message="<b>📊 Статус парсеров Uruguay Lands</b>\n"
    message+="<i>$timestamp</i>\n\n"
    
    # Информация о системе
    message+="<b>🖥️ Системная информация:</b>\n"
    message+="<code>$(uname -a)</code>\n"
    
    # Проверка свободного места на диске
    local disk_space=$(df -h / | awk 'NR==2 {print $4 " свободно из " $2 " (" $5 " занято)"}')
    message+="<b>💾 Дисковое пространство:</b> $disk_space\n\n"
    
    # Проверка активных процессов парсеров
    message+="<b>🔄 Активные процессы:</b>\n"
    local mercadolibre_count=$(pgrep -f "python.*mercadolibre" | wc -l | tr -d ' ')
    local infocasas_count=$(pgrep -f "python.*infocasas" | wc -l | tr -d ' ')
    
    if [ "$mercadolibre_count" -gt 0 ]; then
        message+="MercadoLibre: $mercadolibre_count активных процессов\n"
    else
        message+="MercadoLibre: не активен\n"
    fi
    
    if [ "$infocasas_count" -gt 0 ]; then
        message+="InfoCasas: $infocasas_count активных процессов\n"
    else
        message+="InfoCasas: не активен\n"
    fi
    
    message+="\n"
    
    # Проверка наличия ошибок в логах
    message+="<b>⚠️ Проверка логов на ошибки:</b>\n"
    local recent_logs=$(find "$SCRIPT_DIR/logs" -type f -name "*.log" -mtime -1)
    local error_count=0
    
    for log in $recent_logs; do
        local log_errors=$(grep -i "error\|exception\|failed" "$log" | wc -l)
        error_count=$((error_count + log_errors))
        
        # Получаем имя парсера из имени файла лога
        local parser_name=$(basename "$log" | cut -d'_' -f1)
        
        if [ "$log_errors" -gt 0 ]; then
            message+="$parser_name: <b>$log_errors ошибок</b> в $(basename "$log")\n"
            
            # Добавляем последние 3 ошибки
            local last_errors=$(grep -i "error\|exception\|failed" "$log" | tail -3)
            if [ -n "$last_errors" ]; then
                message+="<code>$(echo "$last_errors" | sed 's/</\&lt;/g; s/>/\&gt;/g')</code>\n"
            fi
        fi
    done
    
    if [ "$error_count" -eq 0 ]; then
        message+="Ошибок не обнаружено\n"
    fi
    
    message+="\n"
    
    # Статистика по результатам парсеров
    message+="<b>📈 Статистика результатов:</b>\n"
    
    # Подсчет файлов результатов
    local mercadolibre_results=$(find "$SCRIPT_DIR/results" -type f -name "mercadolibre*.json" | wc -l | tr -d ' ')
    local infocasas_results=$(find "$SCRIPT_DIR/results" -type f -name "infocasas*.json" | wc -l | tr -d ' ')
    
    message+="MercadoLibre: $mercadolibre_results файлов с результатами\n"
    message+="InfoCasas: $infocasas_results файлов с результатами\n"
    
    # Общее количество объявлений
    local total_listings=0
    
    for file in $(find "$SCRIPT_DIR/results" -type f -name "*.json" -mtime -7); do
        local file_listings=$(jq '. | length' "$file" 2>/dev/null || echo 0)
        total_listings=$((total_listings + file_listings))
    done
    
    message+="Всего объявлений за последние 7 дней: $total_listings\n"
    
    # Отправляем сообщение в Telegram
    send_to_telegram "$message"
}

# Функция для проверки новых результатов парсеров
check_results() {
    echo "Проверка новых результатов парсеров..."
    
    # Получаем время последней проверки
    local last_check_time=$(cat "$LAST_CHECK_FILE" 2>/dev/null || echo 0)
    local current_time=$(date +%s)
    
    # Обновляем время последней проверки
    echo "$current_time" > "$LAST_CHECK_FILE"
    
    # Проверяем новые файлы результатов
    local new_files=$(find "$SCRIPT_DIR/results" -type f -name "*.json" -newermt "@$last_check_time")
    
    if [ -z "$new_files" ]; then
        echo "Новых результатов не обнаружено"
        return 0
    fi
    
    # Собираем статистику по новым файлам
    local new_mercadolibre_files=0
    local new_infocasas_files=0
    local new_mercadolibre_listings=0
    local new_infocasas_listings=0
    
    for file in $new_files; do
        if [[ "$file" == *"mercadolibre"* ]]; then
            new_mercadolibre_files=$((new_mercadolibre_files + 1))
            local file_listings=$(jq '. | length' "$file" 2>/dev/null || echo 0)
            new_mercadolibre_listings=$((new_mercadolibre_listings + file_listings))
        elif [[ "$file" == *"infocasas"* ]]; then
            new_infocasas_files=$((new_infocasas_files + 1))
            local file_listings=$(jq '. | length' "$file" 2>/dev/null || echo 0)
            new_infocasas_listings=$((new_infocasas_listings + file_listings))
        fi
    done
    
    # Формируем отчет
    local message="<b>🆕 Новые результаты парсеров</b>\n"
    message+="<i>$(date +"%Y-%m-%d %H:%M:%S")</i>\n\n"
    
    if [ "$new_mercadolibre_files" -gt 0 ]; then
        message+="<b>MercadoLibre:</b> $new_mercadolibre_files новых файлов, $new_mercadolibre_listings объявлений\n"
    fi
    
    if [ "$new_infocasas_files" -gt 0 ]; then
        message+="<b>InfoCasas:</b> $new_infocasas_files новых файлов, $new_infocasas_listings объявлений\n"
    fi
    
    # Отправляем отчет в Telegram
    send_to_telegram "$message"
}

# Функция для очистки старых файлов
cleanup() {
    echo "Запуск очистки старых файлов..."
    
    # Удаление файлов логов старше 30 дней
    local old_logs=$(find "$SCRIPT_DIR/logs" -type f -name "*.log" -mtime +30)
    if [ -n "$old_logs" ]; then
        echo "Удаление старых лог-файлов:"
        echo "$old_logs" | xargs rm -f
        echo "Удалено $(echo "$old_logs" | wc -l | tr -d ' ') лог-файлов"
    else
        echo "Не найдено старых лог-файлов для удаления"
    fi
    
    # Удаление файлов результатов старше 90 дней
    local old_results=$(find "$SCRIPT_DIR/results" -type f -name "*.json" -mtime +90)
    if [ -n "$old_results" ]; then
        echo "Удаление старых файлов результатов:"
        echo "$old_results" | xargs rm -f
        echo "Удалено $(echo "$old_results" | wc -l | tr -d ' ') файлов результатов"
    else
        echo "Не найдено старых файлов результатов для удаления"
    fi
}

# Функция для отображения справки
show_help() {
    echo "Скрипт мониторинга для проекта Uruguay Lands"
    echo ""
    echo "Использование: $0 [команда]"
    echo ""
    echo "Команды:"
    echo "  status        Проверить статус парсеров и отправить отчет"
    echo "  results       Проверить наличие новых результатов и отправить отчет"
    echo "  cleanup       Удалить старые логи и файлы результатов"
    echo "  help          Показать эту справку"
    echo ""
    echo "Примеры:"
    echo "  $0 status     # Проверить статус парсеров"
    echo "  $0 results    # Проверить наличие новых результатов"
    echo ""
    echo "Для настройки регулярного выполнения, добавьте скрипт в crontab:"
    echo "  0 */6 * * * $SCRIPT_DIR/monitor.sh status"
    echo "  0 */3 * * * $SCRIPT_DIR/monitor.sh results"
    echo "  0 0 * * 0 $SCRIPT_DIR/monitor.sh cleanup"
}

# Основная логика скрипта
case "${1:-help}" in
    status)
        check_status
        ;;
    results)
        check_results
        ;;
    cleanup)
        cleanup
        ;;
    help|*)
        show_help
        ;;
esac

exit 0 