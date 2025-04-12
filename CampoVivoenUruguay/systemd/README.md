# Настройка автозапуска через systemd

Этот документ описывает настройку автоматического запуска парсера CampoVivoenUruguay через systemd на Linux-серверах.

## Установка сервиса

1. Скопируйте файл `campovivo-parser.service` в директорию systemd:

```bash
sudo cp campovivo-parser.service /etc/systemd/system/
```

2. Отредактируйте файл, указав правильные пути и пользователя:

```bash
sudo nano /etc/systemd/system/campovivo-parser.service
```

Измените следующие строки:
- `User=your_username` - укажите имя пользователя, от которого будет запускаться сервис
- `Group=your_username` - укажите группу пользователя
- `WorkingDirectory=/path/to/CampoVivoenUruguay` - укажите полный путь к директории проекта

3. Обновите конфигурацию systemd:

```bash
sudo systemctl daemon-reload
```

4. Включите сервис для автозапуска при загрузке:

```bash
sudo systemctl enable campovivo-parser.service
```

5. Запустите сервис:

```bash
sudo systemctl start campovivo-parser.service
```

## Управление сервисом

### Проверка статуса
```bash
sudo systemctl status campovivo-parser.service
```

### Просмотр логов
```bash
sudo journalctl -u campovivo-parser.service -f
```

### Остановка сервиса
```bash
sudo systemctl stop campovivo-parser.service
```

### Перезапуск сервиса
```bash
sudo systemctl restart campovivo-parser.service
```

## Настройка параметров

Параметры запуска парсера можно настроить в файле сервиса, изменив строку `ExecStart`.

Примеры настроек:
- `--interval 180` - запуск каждые 3 часа (180 минут)
- `--telegram` - отправка результатов в Telegram
- `--pages 2` - количество страниц для парсинга

```bash
ExecStart=/usr/bin/python3 cron_scheduler.py --interval 180 --telegram --pages 2
``` 