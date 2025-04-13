#!/usr/bin/env python3
import os
import sys

# Добавляем текущую директорию в PATH
sys.path.insert(0, os.path.dirname(__file__))

# Импортируем функцию для запуска из main.py
from main import main as app_main
import asyncio

# Функция для запуска WSGI приложения
def application(environ, start_response):
    """
    Простая WSGI-функция для запуска приложения
    """
    # Заголовки ответа
    status = '200 OK'
    headers = [('Content-type', 'text/plain; charset=utf-8')]
    start_response(status, headers)
    
    # Запуск основной функции через asyncio
    try:
        # Запуск основной функции в фоновом режиме
        asyncio.run(app_main())
        response = "Приложение Campo Vivo en Uruguay запущено успешно!".encode('utf-8')
    except Exception as e:
        response = f"Ошибка при запуске приложения: {str(e)}".encode('utf-8')
    
    return [response]

# Для локального тестирования
if __name__ == "__main__":
    from wsgiref.simple_server import make_server
    httpd = make_server('localhost', 8000, application)
    print("Serving on port 8000...")
    httpd.serve_forever() 