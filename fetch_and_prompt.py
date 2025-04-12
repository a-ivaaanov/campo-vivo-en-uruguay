#!/usr/bin/env python3
"""
Скрипт для:
1. Загрузки HTML-содержимого страницы с выполнением JS (Playwright).
2. Обрезки HTML до заданного лимита.
3. Формирования промпта для LLM с запросом на поиск CSS селекторов.
"""

import asyncio
import argparse
import logging
from pathlib import Path
from typing import Optional, List

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("fetch_and_prompt")

try:
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
except ImportError:
    logger.error("Playwright не установлен. Установите: pip install playwright")
    logger.info("Затем установите браузеры: playwright install")
    exit(1)

CACHE_DIR = Path(".cache")
DEFAULT_TIMEOUT = 60000  # 60 секунд
DEFAULT_MAX_HTML_LENGTH = 30000
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

async def fetch_html(url: str, timeout: int = DEFAULT_TIMEOUT, save_cache: bool = False) -> Optional[str]:
    """Загружает HTML страницы с выполнением JS."""
    logger.info(f"Загрузка URL: {url} (timeout: {timeout}ms)")
    html_content = None
    async with async_playwright() as p:
        try:
            # Используем Firefox для лучшей совместимости с некоторыми сайтами
            browser = await p.firefox.launch(headless=True)
            context = await browser.new_context(
                user_agent=DEFAULT_USER_AGENT,
                viewport={"width": 1920, "height": 1080} # Эмулируем десктоп
            )
            page = await context.new_page()
            
            logger.info("Переход на страницу...")
            # Используем networkidle как аналог networkidle2
            await page.goto(url, wait_until="networkidle", timeout=timeout)
            logger.info("Страница загружена, получение контента...")
            html_content = await page.content()
            logger.info(f"HTML контент получен (длина: {len(html_content)} символов)")
            
            if save_cache:
                CACHE_DIR.mkdir(exist_ok=True)
                filename = url.split('//')[-1].split('/')[0].replace('.', '_') + ".html"
                cache_path = CACHE_DIR / filename
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                logger.info(f"HTML сохранен в кеш: {cache_path}")
                
            await browser.close()
        except PlaywrightTimeoutError:
            logger.error(f"Таймаут при загрузке URL: {url}")
        except Exception as e:
            logger.error(f"Ошибка при загрузке URL {url}: {e}", exc_info=True)
        finally:
            # Убедимся, что браузер закрыт, если он был запущен
            if 'browser' in locals() and browser.is_connected():
                await browser.close()
                
    return html_content

def truncate_html(html: str, max_length: int = DEFAULT_MAX_HTML_LENGTH) -> str:
    """Обрезает HTML до максимальной длины."""
    if len(html) > max_length:
        logger.info(f"HTML обрезан с {len(html)} до {max_length} символов.")
        # Просто обрезаем, можно добавить более умную логику, если нужно
        return html[:max_length]
    return html

def generate_llm_prompt(url: str, html: str, selectors_to_find: List[str]) -> str:
    """Генерирует промпт для LLM."""
    
    selectors_list_str = "\n".join([f"- {s}" for s in selectors_to_find])
    
    prompt = f"""
Вот HTML сайта {url}:

```html
{html}
```

Найди CSS-селекторы для следующих элементов:
{selectors_list_str}

Верни результат в формате JSON объекта, где ключ - название элемента, а значение - найденный CSS-селектор.
Пример:
{{
  "price": ".some-price-class",
  "location": ".some-location-class"
}}
"""
    return prompt

async def main():
    parser = argparse.ArgumentParser(description="Загрузить HTML и сгенерировать промпт для поиска CSS селекторов.")
    parser.add_argument("url", help="URL страницы для анализа")
    parser.add_argument("-s", "--selectors", nargs='+', required=True, 
                        help="Список названий селекторов для поиска (например: price title location area)")
    parser.add_argument("-l", "--limit", type=int, default=DEFAULT_MAX_HTML_LENGTH, 
                        help=f"Максимальная длина HTML для включения в промпт (по умолчанию: {DEFAULT_MAX_HTML_LENGTH})")
    parser.add_argument("-t", "--timeout", type=int, default=DEFAULT_TIMEOUT, 
                        help=f"Таймаут загрузки страницы в миллисекундах (по умолчанию: {DEFAULT_TIMEOUT})")
    parser.add_argument("-c", "--cache", action="store_true", 
                        help="Сохранить загруженный HTML в .cache/")
    parser.add_argument("-o", "--output", type=str, default=None,
                        help="Файл для сохранения сгенерированного промпта")

    args = parser.parse_args()

    html = await fetch_html(args.url, args.timeout, args.cache)

    if html:
        truncated_html = truncate_html(html, args.limit)
        final_prompt = generate_llm_prompt(args.url, truncated_html, args.selectors)
        
        if args.output:
            try:
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write(final_prompt)
                logger.info(f"Промпт сохранен в файл: {args.output}")
            except Exception as e:
                logger.error(f"Ошибка при сохранении промпта в файл {args.output}: {e}")
        else:
            print("\n--- Сгенерированный промпт для LLM ---")
            print(final_prompt)
            print("--- Конец промпта ---\n")
    else:
        logger.error("Не удалось получить HTML. Промпт не сгенерирован.")

if __name__ == "__main__":
    asyncio.run(main()) 