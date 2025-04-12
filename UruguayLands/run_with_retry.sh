#!/bin/bash

# Скрипт для запуска парсеров UruguayLands с автоматическими повторными попытками
# Автор: Nick
# Дата: июль 2024

# Получаем абсолютный путь к директории скрипта
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Загружаем переменные окружения из .env файла
if [ -f "$SCRIPT_DIR/.env" ]; then
    export $(grep -v '^#' "$SCRIPT_DIR/.env" | xargs)
else
    echo "Ошибка: Файл .env не найден в директории $SCRIPT_DIR"
    exit 1
fi

# Настройки по умолчанию
PARSER="all"
MAX_PAGES=1
HEADLESS=false
WITH_DETAILS=false
MAX_RETRIES=3
RETRY_DELAY=60  # секунд между повторными попытками
ROTATE_PROXY=true

# Функция для отображения справки
show_help() {
    echo "Использование: $0 [ОПЦИИ]"
    echo ""
    echo "Скрипт для запуска парсеров UruguayLands с автоматическими повторными попытками"
    echo ""
    echo "Опции:"
    echo "  --parser PARSER      Выбор парсера (mercadolibre, infocasas, all). По умолчанию: all"
    echo "  --pages N            Количество страниц для обработки. По умолчанию: 1"
    echo "  --headless           Запустить браузер в фоновом режиме"
    echo "  --with-details       Обрабатывать детали объявлений"
    echo "  --retries N          Максимальное количество повторных попыток. По умолчанию: 3"
    echo "  --retry-delay N      Задержка между повторными попытками (сек). По умолчанию: 60"
    echo "  --no-proxy-rotation  Отключить ротацию прокси между попытками"
    echo "  --help               Показать эту справку"
    echo ""
    echo "Примеры:"
    echo "  $0 --parser mercadolibre --pages 5 --headless --with-details"
    echo "  $0 --parser all --retries 5 --retry-delay 120"
}

# Разбор аргументов командной строки
while [[ $# -gt 0 ]]; do
    case "$1" in
        --parser)
            PARSER="$2"
            shift 2
            ;;
        --pages)
            MAX_PAGES="$2"
            shift 2
            ;;
        --headless)
            HEADLESS=true
            shift
            ;;
        --with-details)
            WITH_DETAILS=true
            shift
            ;;
        --retries)
            MAX_RETRIES="$2"
            shift 2
            ;;
        --retry-delay)
            RETRY_DELAY="$2"
            shift 2
            ;;
        --no-proxy-rotation)
            ROTATE_PROXY=false
            shift
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

# Проверяем корректность значения парсера
if [[ "$PARSER" != "mercadolibre" && "$PARSER" != "infocasas" && "$PARSER" != "all" ]]; then
    echo "Ошибка: Неизвестный парсер $PARSER. Допустимые значения: mercadolibre, infocasas, all"
    exit 1
fi

# Функция для ротации прокси
rotate_proxy() {
    if [ "$ROTATE_PROXY" = true ] && [ -n "$PROXY_LIST" ]; then
        # Получаем текущий прокси из .env файла
        current_proxy=$(grep "^PROXY=" "$SCRIPT_DIR/.env" | cut -d'=' -f2)
        
        # Получаем следующий прокси из списка
        proxy_list=($PROXY_LIST)
        proxy_count=${#proxy_list[@]}
        
        if [ $proxy_count -gt 0 ]; then
            # Находим индекс текущего прокси в списке
            current_index=-1
            for i in "${!proxy_list[@]}"; do
                if [[ "${proxy_list[$i]}" = "$current_proxy" ]]; then
                    current_index=$i
                    break
                fi
            done
            
            # Вычисляем индекс следующего прокси
            next_index=$(( (current_index + 1) % proxy_count ))
            next_proxy="${proxy_list[$next_index]}"
            
            # Обновляем прокси в .env файле
            sed -i.bak "s|^PROXY=.*|PROXY=$next_proxy|" "$SCRIPT_DIR/.env"
            rm -f "$SCRIPT_DIR/.env.bak"
            
            echo "Прокси изменен на: $next_proxy"
        else
            echo "Список прокси пуст, ротация невозможна"
        fi
    else
        echo "Ротация прокси отключена или список прокси не настроен"
    fi
}

# Функция для запуска Python-скрипта с повторными попытками
run_python_script_with_retry() {
    local parser_name="$1"
    local retry_count=0
    local success=false
    
    while [ $retry_count -lt $MAX_RETRIES ] && [ "$success" = false ]; do
        # Увеличиваем счетчик попыток
        retry_count=$((retry_count + 1))
        local timestamp=$(date +"%Y%m%d_%H%M%S")
        local log_file="$SCRIPT_DIR/logs/${parser_name}_${timestamp}_attempt${retry_count}.log"
        
        echo "Попытка $retry_count из $MAX_RETRIES для парсера $parser_name..."
        
        # Формируем команду
        local cmd="cd $SCRIPT_DIR && python -m app.main --parser $parser_name"
        
        # Добавляем дополнительные параметры
        if [ "$HEADLESS" = true ]; then
            cmd="$cmd --headless"
        fi
        
        if [ "$WITH_DETAILS" = true ]; then
            cmd="$cmd --with-details"
        fi
        
        if [ -n "$MAX_PAGES" ]; then
            cmd="$cmd --max-pages $MAX_PAGES"
        fi
        
        # Запускаем команду и перенаправляем вывод в лог-файл
        echo "Запуск парсера $parser_name..."
        echo "Команда: $cmd"
        echo "Лог-файл: $log_file"
        
        eval "$cmd" > "$log_file" 2>&1
        local exit_code=$?
        
        if [ $exit_code -eq 0 ]; then
            echo "Парсер $parser_name успешно завершил работу. Код возврата: $exit_code"
            success=true
        else
            echo "Ошибка при выполнении парсера $parser_name. Код возврата: $exit_code"
            echo "Последние 10 строк лога:"
            tail -10 "$log_file"
            
            if [ $retry_count -lt $MAX_RETRIES ]; then
                echo "Ожидание $RETRY_DELAY секунд перед следующей попыткой..."
                rotate_proxy
                sleep $RETRY_DELAY
            else
                echo "Достигнуто максимальное количество попыток ($MAX_RETRIES) для парсера $parser_name"
            fi
        fi
    done
    
    if [ "$success" = true ]; then
        return 0
    else
        return 1
    fi
}

# Создаем директории для логов и результатов, если их нет
mkdir -p "$SCRIPT_DIR/logs"
mkdir -p "$SCRIPT_DIR/results"

# Запуск парсеров с повторными попытками
if [ "$PARSER" = "all" ] || [ "$PARSER" = "mercadolibre" ]; then
    run_python_script_with_retry "mercadolibre"
    MERCADOLIBRE_EXIT=$?
else
    MERCADOLIBRE_EXIT=0
fi

if [ "$PARSER" = "all" ] || [ "$PARSER" = "infocasas" ]; then
    run_python_script_with_retry "infocasas"
    INFOCASAS_EXIT=$?
else
    INFOCASAS_EXIT=0
fi

# Проверяем успешность выполнения
if [ $MERCADOLIBRE_EXIT -ne 0 ] || [ $INFOCASAS_EXIT -ne 0 ]; then
    echo "Обнаружены ошибки при выполнении парсеров"
    exit 1
else
    echo "Все парсеры успешно завершили работу"
    exit 0
fi 