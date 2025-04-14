# Campo Vivo en Uruguay 🌿

![Версия](https://img.shields.io/badge/Версия-1.0.0-blue.svg)
![Лицензия](https://img.shields.io/badge/Лицензия-MIT-green.svg)
![Python](https://img.shields.io/badge/Python-3.9%2B-yellow.svg)

Система мониторинга и анализа объявлений о продаже земельных участков в Уругвае.

## ✨ Возможности

- **Парсинг популярных площадок**: MercadoLibre, InfoCasas и др.
- **Умное обнаружение дубликатов** и уже отправленных объявлений
- **Автоматическое извлечение параметров участка**: коммуникации, зонирование
- **Оповещение в Telegram** с фотографиями и детальной информацией
- **Обход блокировок** с использованием прокси и рандомизацией запросов
- **Мониторинг системы** через Prometheus метрики

## 🔧 Установка

```bash
# Клонирование репозитория
git clone https://github.com/yourusername/campo-vivo-en-uruguay.git
cd campo-vivo-en-uruguay

# Создание виртуального окружения
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows

# Установка зависимостей
pip install -r requirements.txt
playwright install
```

## ⚙️ Настройка

1. Создайте файл конфигурации:
```bash
cp .env.example .env
```

2. Отредактируйте `.env`, указав:
   - Токен Telegram бота
   - ID канала/чата для отправки сообщений
   - Параметры для поиска (цена, площадь, регионы)
   - Настройки прокси (при необходимости)

### 📱 Настройка Telegram

Для отправки объявлений в Telegram необходимо:

1. **Создать бота** через [@BotFather](https://t.me/BotFather) и получить токен
2. **Создать канал или группу** для получения объявлений
3. **Добавить бота** в канал/группу с правами администратора
4. **Указать в файле `.env`**:
   ```
   TELEGRAM_BOT_TOKEN=ваш_токен_бота
   TELEGRAM_CHAT_ID=@имя_канала или -123456789 (ID группы)
   ```

Пример настройки:
```
TELEGRAM_BOT_TOKEN=7682404666:AAFbehrAAZ3MC-DyLk4QKtm7Y4rN1EbGh3A
TELEGRAM_CHAT_ID=@uruguayland
```

## 🚀 Использование

**Запуск парсера:**
```bash
# Запуск всех парсеров
python run.py --parser all --pages 2 --headless

# Запуск конкретного парсера
python run.py --parser mercadolibre --pages 3 --headless
```

**Запуск через планировщик:**
```bash
python cron_scheduler.py
```

**Параметры запуска:**
- `--parser`: Выбор парсера (mercadolibre, infocasas, all)
- `--pages`: Количество страниц для обработки
- `--headless`: Запуск в фоновом режиме
- `--no-telegram`: Отключить отправку в Telegram

## 📁 Структура проекта

```
campo-vivo-en-uruguay/
├── app/
│   ├── parsers/          # Парсеры для различных сайтов
│   ├── services/         # Сервисы (Telegram, обработка изображений)
│   └── utils/            # Вспомогательные функции
├── config/               # Конфигурационные файлы
├── tools/                # Утилиты
├── docs/                 # Документация
├── deploy/               # Скрипты развертывания
└── systemd/              # Systemd сервисы
```

## 📊 Мониторинг

Система поддерживает мониторинг через Prometheus метрики:
- Количество успешных/неуспешных парсингов
- Время выполнения парсеров
- Количество найденных объявлений
- Статус работы системы

## 🧪 Разработка

Добавление нового парсера:
1. Создайте класс в `app/parsers/`
2. Унаследуйте от `BaseParser`
3. Реализуйте методы `run()` и `run_with_details()`
4. Добавьте тесты

## 📄 Лицензия

Этот проект распространяется под лицензией MIT 