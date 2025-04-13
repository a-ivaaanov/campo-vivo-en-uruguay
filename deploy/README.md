# Деплой Campo Vivo en Uruguay

В этой директории находятся файлы для развертывания проекта в production среде.

## Быстрый старт

1. Убедитесь, что у вас установлены Docker и Docker Compose:
```bash
docker --version
docker-compose --version
```

2. Скопируйте пример конфигурации:
```bash
cp ../.env.example ../.env
```

3. Отредактируйте `.env` файл, указав ваши настройки Telegram и другие параметры.

4. Запустите проект в Docker:
```bash
docker-compose up -d
```

5. Проверьте логи:
```bash
docker-compose logs -f campo-vivo
```

## Мониторинг

После запуска, мониторинг доступен по следующим адресам:

- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (логин: admin, пароль: admin)

### Настройка Grafana:

1. Войдите в Grafana с учетными данными по умолчанию
2. Добавьте источник данных Prometheus (URL: http://prometheus:9090)
3. Импортируйте дашборд из `deploy/grafana/dashboards/campo-vivo.json`

## Управление системой

- **Остановка сервисов**:
```bash
docker-compose down
```

- **Перезапуск парсеров**:
```bash
docker-compose restart campo-vivo
```

- **Просмотр логов**:
```bash
docker-compose logs -f campo-vivo
```

- **Запуск парсера вручную**:
```bash
docker-compose exec campo-vivo python run.py --parser all --pages 2 --headless
```

## Резервное копирование

Важные данные хранятся в томах Docker и директориях на хост-машине:
- `../data/`: Данные парсеров
- `../logs/`: Логи выполнения
- `../results/`: Результаты парсинга 