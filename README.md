# UruguayLands

Парсер объявлений о земельных участках в Уругвае с отправкой результатов в Telegram-канал.

## Возможности

- Парсинг земельных участков с MercadoLibre и InfoCasas
- Фильтрация дубликатов и уже отправленных объявлений
- Отправка объявлений в канал Telegram с фотографиями
- Настраиваемые параметры поиска (цена, площадь, регионы)
- Проксирование запросов для обхода ограничений
- Автоматический запуск по расписанию

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/yourusername/UruguayLands.git
cd UruguayLands
```

2. Создайте и активируйте виртуальное окружение:
```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

4. Установите драйверы Playwright:
```bash
playwright install
```

5. Создайте файл `.env` на основе `.env.example` и заполните необходимые параметры.

## Настройка

В файле `.env` настройте следующие параметры:

- `TELEGRAM_BOT_TOKEN` - токен вашего бота Telegram
- `TELEGRAM_CHAT_ID` - ID канала или чата для отправки объявлений
- Параметры поиска (MIN_PRICE, MAX_PRICE, MIN_AREA, MAX_AREA)
- Список регионов для поиска (REGIONS)
- Настройки прокси (при необходимости)

## Запуск

### Разовый запуск парсера

```bash
# Запуск парсера MercadoLibre на 5 страниц с получением деталей
python run.py --parser mercadolibre --pages 5 --headless --with-details

# Запуск парсера InfoCasas на 3 страницы
python run.py --parser infocasas --pages 3 --headless 
```

### Тестирование

```bash
# Тест парсера MercadoLibre с отправкой в Telegram
python test_telegram_parser.py
```

### Запуск в производственном режиме

```bash
# Запуск с настройками из .env файла
python app/main.py
```

## Структура проекта

```
UruguayLands/
├── app/
│   ├── parsers/
│   │   ├── mercadolibre.py   # Парсер MercadoLibre
│   │   └── infocasas.py      # Парсер InfoCasas
│   ├── utils/
│   │   ├── duplicate_checker.py  # Проверка дубликатов
│   │   └── proxy_manager.py      # Управление прокси
│   ├── models.py             # Модели данных
│   ├── telegram_sender.py    # Отправка в Telegram
│   └── main.py               # Основной модуль
├── run.py                    # Скрипт быстрого запуска
├── test_telegram_parser.py   # Тестирование парсеров
├── requirements.txt          # Зависимости проекта
└── .env.example              # Пример конфигурации
```

## Планы по развитию

- Добавление поддержки других площадок (Gallito, etc.)
- Интеграция с базой данных для хранения истории
- Улучшение распознавания характеристик объявлений
- Интерактивный бот для управления парсерами

## Лицензия

MIT 