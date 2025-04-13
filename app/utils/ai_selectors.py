#!/usr/bin/env python3
"""
Модуль для интеллектуального поиска элементов на веб-страницах
с использованием семантического понимания контента.
"""

import logging
import re
import json
from typing import List, Dict, Any, Union, Optional, Tuple, Set
from playwright.async_api import Page, ElementHandle, Locator

logger = logging.getLogger(__name__)

class AISelector:
    """
    Класс для интеллектуального выбора элементов на основе их смыслового содержания.
    Используется для поиска элементов, когда стандартные CSS-селекторы могут измениться.
    """
    
    # Словарь паттернов для различных типов элементов
    ELEMENT_PATTERNS = {
        # Шаблоны для заголовков
        "title": [
            r"h1", r"h2", r"h3", 
            r'[class*="title"]', 
            r'[class*="heading"]',
            r"header", 
            r'span[class*="titulo"]'
        ],
        
        # Шаблоны для ссылок на объявления
        "url": [
            r'a[href*="mercadolibre"]', 
            r'a[href*="inmuebles"]',
            r'a[href*="terreno"]',
            r'a[class*="card"]'
        ],
        
        # Шаблоны для цен
        "price": [
            r'[class*="price"]', 
            r'[class*="precio"]',
            r'span[class*="money"]', 
            r'span[class*="fraction"]',
            r'[class*="currency"]'
        ],
        
        # Шаблоны для местоположения
        "location": [
            r'[class*="location"]', 
            r'[class*="ubicacion"]',
            r'[class*="address"]', 
            r'p[class*="direccion"]',
            r'span[class*="item__location"]'
        ],
        
        # Шаблоны для площади
        "area": [
            r'[class*="area"]', 
            r'[class*="superficie"]',
            r'li[class*="attributes"]', 
            r'span[class*="m2"]',
            r'[class*="hectarea"]'
        ],
        
        # Шаблоны для изображений
        "image": [
            r'img[src*="http"]', 
            r'img[data-src]',
            r'[class*="image"] img', 
            r'[class*="picture"] img',
            r'[class*="thumbnail"] img'
        ],
        
        # Шаблоны для описания
        "description": [
            r'[class*="description"]', 
            r'[class*="descripcion"]',
            r'div[class*="content"] p', 
            r'[class*="detail"] p',
            r'[itemprop="description"]'
        ],
        
        # Шаблоны для карточек объявлений
        "product cards": [
            r'li[class*="search-layout__item"]',
            r'div[class*="ui-search-result"]',
            r'ol[class*="ui-search-layout"] > li',
            r'[class*="results-item"]'
        ]
    }
    
    # Словарь ключевых слов для различных типов элементов на испанском и английском
    ELEMENT_KEYWORDS = {
        "title": ["título", "titulo", "title", "nombre", "name", "terreno", "lote", "parcela"],
        "price": ["precio", "price", "valor", "value", "costo", "cost", "usd", "u$s", "$"],
        "location": ["ubicación", "ubicacion", "location", "dirección", "direccion", "address", "departamento", "barrio"],
        "area": ["superficie", "area", "metros", "m²", "m2", "hectáreas", "hectareas", "ha", "tamaño", "tamano", "size"],
        "description": ["descripción", "descripcion", "description", "detalle", "detail", "característica", "caracteristica"],
        "image": ["imagen", "image", "foto", "photo", "picture"],
        "product cards": ["resultados", "results", "items", "anuncios", "listings", "propiedades", "properties"]
    }
    
    @classmethod
    def get_patterns_for_type(cls, element_type: str) -> List[str]:
        """
        Возвращает список паттернов для указанного типа элемента.
        
        Args:
            element_type: Тип элемента для которого нужны паттерны
            
        Returns:
            List[str]: Список CSS-селекторов для данного типа
        """
        element_type = element_type.lower()
        
        # Проверяем точное совпадение по ключу
        if element_type in cls.ELEMENT_PATTERNS:
            return cls.ELEMENT_PATTERNS[element_type]
            
        # Проверяем частичное совпадение
        for key, patterns in cls.ELEMENT_PATTERNS.items():
            if element_type in key or key in element_type:
                return patterns
                
        # Возвращаем пустой список, если не нашли подходящих паттернов
        return []
    
    @classmethod
    def get_keywords_for_type(cls, element_type: str) -> List[str]:
        """
        Возвращает список ключевых слов для указанного типа элемента.
        
        Args:
            element_type: Тип элемента для которого нужны ключевые слова
            
        Returns:
            List[str]: Список ключевых слов для этого типа
        """
        element_type = element_type.lower()
        
        # Проверяем точное совпадение по ключу
        if element_type in cls.ELEMENT_KEYWORDS:
            return cls.ELEMENT_KEYWORDS[element_type]
            
        # Проверяем частичное совпадение
        for key, keywords in cls.ELEMENT_KEYWORDS.items():
            if element_type in key or key in element_type:
                return keywords
                
        # Возвращаем пустой список, если не нашли подходящих ключевых слов
        return []
        
async def find_element_by_ai(page_or_element: Union[Page, ElementHandle], 
                            element_type: str, 
                            query: str = None) -> Union[ElementHandle, List[ElementHandle], None]:
    """
    Находит элемент(ы) с использованием AI-подхода, комбинируя селекторы и текстовый анализ.
    
    Args:
        page_or_element: Страница или родительский элемент для поиска
        element_type: Тип искомого элемента (title, price, url, и т.д.)
        query: Дополнительный поисковый запрос или контекст
        
    Returns:
        Найденный элемент, список элементов или None если ничего не найдено
    """
    logger.info(f"AI-поиск элемента типа: {element_type}, контекст: {query}")
    
    # Получаем паттерны для указанного типа элемента
    patterns = AISelector.get_patterns_for_type(element_type)
    
    if not patterns:
        logger.warning(f"Не найдены паттерны для типа элемента: {element_type}")
        return None
    
    # Пробуем найти элемент по каждому паттерну
    for pattern in patterns:
        try:
            # Пробуем найти элемент по селектору
            if isinstance(page_or_element, Page):
                elements = await page_or_element.query_selector_all(pattern)
            else:
                elements = await page_or_element.query_selector_all(pattern)
                
            if elements and len(elements) > 0:
                # Если нашли элементы, проверяем их содержимое если есть query
                if query:
                    # Фильтруем элементы по тексту, который соответствует запросу
                    filtered_elements = []
                    keywords = AISelector.get_keywords_for_type(element_type)
                    
                    for element in elements:
                        # Проверяем текст
                        try:
                            text = await element.inner_text()
                            
                            # Проверяем на соответствие ключевым словам и запросу
                            if any(kw.lower() in text.lower() for kw in keywords):
                                filtered_elements.append(element)
                                continue
                                
                            # Проверяем атрибуты
                            for attr in ['title', 'alt', 'placeholder', 'name', 'id', 'aria-label']:
                                attr_value = await element.get_attribute(attr)
                                if attr_value and any(kw.lower() in attr_value.lower() for kw in keywords):
                                    filtered_elements.append(element)
                                    break
                        except:
                            pass
                            
                    if filtered_elements:
                        if len(filtered_elements) == 1:
                            return filtered_elements[0]
                        else:
                            return filtered_elements
                else:
                    # Если запрос не указан, возвращаем все найденные элементы
                    if len(elements) == 1:
                        return elements[0]
                    else:
                        return elements
        except Exception as e:
            logger.error(f"Ошибка при поиске по паттерну {pattern}: {e}")
            continue
            
    # Если ни один паттерн не сработал, возвращаем None
    return None

async def smart_find_element(page_or_element: Union[Page, ElementHandle], 
                           element_type: str, 
                           query: str = None,
                           css_selectors: List[str] = None) -> Union[ElementHandle, List[ElementHandle], None]:
    """
    Умный поиск элемента с использованием комбинации традиционных селекторов и AI-подхода.
    
    Args:
        page_or_element: Страница или родительский элемент
        element_type: Тип искомого элемента
        query: Дополнительный текстовый запрос
        css_selectors: Список традиционных CSS-селекторов для этого типа
        
    Returns:
        Найденный элемент или None
    """
    # Сначала пробуем найти по традиционным селекторам
    if css_selectors:
        for selector in css_selectors:
            try:
                if isinstance(page_or_element, Page):
                    element = await page_or_element.query_selector(selector)
                else:
                    element = await page_or_element.query_selector(selector)
                    
                if element:
                    return element
            except:
                pass
    
    # Если не нашли, используем AI-селекторы
    logger.info(f"Традиционные селекторы не сработали, используем AI-селекторы для поиска: {query or element_type}")
    return await find_element_by_ai(page_or_element, element_type, query)

# Функция для извлечения характеристик участков из текста описания
async def extract_land_characteristics(description_text: str) -> Dict[str, Any]:
    """
    Извлекает характеристики земельного участка из текста описания.
    
    Args:
        description_text: Текст описания земельного участка
        
    Returns:
        Dict[str, Any]: Словарь с характеристиками участка
    """
    # Словарь с результатами
    characteristics = {
        "area": None,           # Площадь
        "utilities": [],        # Коммуникации
        "topography": None,     # Топография
        "zoning": None,         # Зонирование
        "access_road": None,    # Тип подъездной дороги
        "distance_to_city": None,  # Расстояние до города
        "water_source": None,   # Источник воды
    }
    
    # Определяем ключевые слова для каждой характеристики на испанском
    keywords_map = {
        "area": ["superficie", "area", "tamaño", "metros", "hectáreas", "hectareas", "m²", "m2", "ha"],
        "utilities": ["servicios", "luz", "agua", "electricidad", "saneamiento", "gas", "OSE", "UTE"],
        "topography": ["topografía", "topografia", "relieve", "plano", "pendiente", "desnivel", "llano"],
        "zoning": ["zonificación", "zonificacion", "zona", "rural", "urbano", "suburbano", "suburbana", "categoría"],
        "access_road": ["acceso", "calle", "ruta", "camino", "entrada", "asfalto", "pavimento", "asfaltado"],
        "water_source": ["agua", "pozo", "arroyo", "río", "rio", "cañada", "laguna", "tanque", "aljibe"],
        "distance_to_city": ["distancia", "km", "kilómetros", "kilometros", "minutos", "centro", "ciudad"]
    }
    
    # Регулярные выражения для извлечения различных данных
    regex_patterns = {
        "area": [
            r'(\d+[\.,]?\d*)\s*(?:m2|m²|metros|metros cuadrados)',
            r'(\d+[\.,]?\d*)\s*(?:ha|hás|hectáreas|hectareas)',
            r'superficie\D*(\d+[\.,]?\d*)',
            r'área\D*(\d+[\.,]?\d*)',
            r'area\D*(\d+[\.,]?\d*)',
            r'(\d+[\.,]?\d*)\s*hectáreas',
            r'(\d+[\.,]?\d*)\s*hectareas',
        ],
        "utilities": [
            r'servicios\s*[:-]?\s*([^\.]+)',
            r'servicios\W+([\w\s,]+)',
            r'luz\W+([\w\s,]+)',
            r'agua\W+([\w\s,]+)',
            r'electricidad\W+([\w\s,]+)',
        ],
        "topography": [
            r'topografía\s*[:-]?\s*([^\.]+)',
            r'topografia\s*[:-]?\s*([^\.]+)',
            r'relieve\s*[:-]?\s*([^\.]+)',
        ],
        "zoning": [
            r'zona\s*[:-]?\s*([^\.]+)',
            r'zonificación\s*[:-]?\s*([^\.]+)',
            r'zonificacion\s*[:-]?\s*([^\.]+)',
            r'categoría\s*[:-]?\s*([^\.]+)',
        ],
        "access_road": [
            r'acceso\s*[:-]?\s*([^\.]+)',
            r'calle\s*[:-]?\s*([^\.]+)',
            r'camino\s*[:-]?\s*([^\.]+)',
        ],
        "water_source": [
            r'agua\s*[:-]?\s*([^\.]+)',
            r'pozo\s*[:-]?\s*([^\.]+)',
            r'(\w+\s+\w+)\s*de agua',
        ],
        "distance_to_city": [
            r'a\s+(\d+[\.,]?\d*)\s*(?:km|kilómetros|kilometros)',
            r'distancia\s*[:-]?\s*(\d+[\.,]?\d*)',
            r'a\s+(\d+)\s*minutos',
        ]
    }
    
    # Для каждой характеристики применяем соответствующие регулярные выражения
    for char_type, patterns in regex_patterns.items():
        for pattern in patterns:
            matches = re.search(pattern, description_text.lower(), re.IGNORECASE)
            if matches:
                if char_type == "utilities":
                    # Для коммуникаций собираем список
                    utilities = matches.group(1).strip().split(',')
                    characteristics["utilities"].extend([util.strip() for util in utilities if util.strip()])
                else:
                    # Для других характеристик берем первое совпадение
                    characteristics[char_type] = matches.group(1).strip()
                break
                
    # Также проверяем наличие ключевых слов для коммуникаций
    for keyword in ["luz", "agua", "electricidad", "OSE", "UTE", "saneamiento", "gas"]:
        if keyword in description_text.lower() and keyword not in characteristics["utilities"]:
            characteristics["utilities"].append(keyword)
            
    # Приведение значений к правильному формату
    if characteristics["utilities"]:
        characteristics["utilities"] = list(set(characteristics["utilities"]))  # Удаляем дубликаты
        
    return characteristics 