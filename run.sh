#!/bin/bash

# Скрипт для запуска парсеров Uruguay Lands

# Получаем абсолютный путь к директории скрипта
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Загружаем переменные окружения из .env файла
if [ -f "$SCRIPT_DIR/.env" ]; then
    export $(grep -v '^#' "$SCRIPT_DIR/.env" | xargs)
else
    echo "Ошибка: Файл .env не найден в директории $SCRIPT_DIR"
    exit 1
fi

# Обеспечиваем существование директорий для логов и результатов
mkdir -p "$SCRIPT_DIR/logs"
mkdir -p "$SCRIPT_DIR/results"

# Функция для отображения справки
show_help() {
    echo "Скрипт для запуска парсеров Uruguay Lands"
    echo ""
    echo "Использование: $0 [опции]"
    echo ""
    echo "Опции:"
    echo "  --parser PARSER      Парсер для запуска (mercadolibre, infocasas, all). По умолчанию: all"
    echo "  --pages PAGES        Максимальное количество страниц для обработки. По умолчанию: 5"
    echo "  --headless           Запуск в headless режиме (без отображения браузера)"
    echo "  --with-details       Получать детальную информацию о каждом объявлении"
    echo "  --help               Показать эту справку"
    echo ""
    echo "Примеры:"
    echo "  $0 --parser mercadolibre --pages 10 --headless --with-details"
    echo "  $0 --parser infocasas --pages 3"
    echo "  $0 --parser all --headless"
}

# Параметры по умолчанию
PARSER="all"
MAX_PAGES=5
HEADLESS=false
WITH_DETAILS=false

# Парсинг аргументов командной строки
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

# Функция для запуска Python-скрипта
run_python_script() {
    local timestamp=$(date +"%Y%m%d_%H%M%S")
    local log_file="$SCRIPT_DIR/logs/${1}_${timestamp}.log"
    
    # Формируем команду
    local cmd="cd $SCRIPT_DIR && python -m app.main --parser $1"
    
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
    echo "Запуск парсера $1..."
    echo "Команда: $cmd"
    echo "Лог-файл: $log_file"
    
    eval "$cmd" > "$log_file" 2>&1
    local exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        echo "Парсер $1 успешно завершил работу. Код возврата: $exit_code"
    else
        echo "Ошибка при выполнении парсера $1. Код возврата: $exit_code"
        echo "Последние 10 строк лога:"
        tail -10 "$log_file"
    fi
    
    return $exit_code
}

# Запуск парсеров
if [ "$PARSER" = "all" ] || [ "$PARSER" = "mercadolibre" ]; then
    run_python_script "mercadolibre"
    MERCADOLIBRE_EXIT=$?
else
    MERCADOLIBRE_EXIT=0
fi

if [ "$PARSER" = "all" ] || [ "$PARSER" = "infocasas" ]; then
    run_python_script "infocasas"
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