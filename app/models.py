#!/usr/bin/env python3
"""
Модели данных Pydantic для проекта UruguayLands.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, validator

class Listing(BaseModel):
    """Модель объявления о земельном участке"""
    
    # Основные данные
    id: str = Field(..., description="Уникальный идентификатор объявления")
    url: str = Field(..., description="URL объявления")
    title: str = Field(..., description="Заголовок объявления")
    source: str = Field(..., description="Источник объявления (MercadoLibre, InfoCasas и т.д.)")
    
    # Ценовая информация
    price: Optional[int] = Field(None, description="Цена в USD")
    price_currency: str = Field("USD", description="Валюта цены")
    price_per_sqm: Optional[float] = Field(None, description="Цена за квадратный метр")
    
    # Местоположение
    location: Optional[str] = Field(None, description="Местоположение участка")
    region: Optional[str] = Field(None, description="Регион (департамент)")
    city: Optional[str] = Field(None, description="Город или населенный пункт")
    
    # Характеристики участка
    area: Optional[int] = Field(None, description="Площадь участка в кв.м.")
    area_unit: str = Field("sqm", description="Единица измерения площади")
    
    # Коммуникации и зонирование
    has_water: Optional[bool] = Field(None, description="Наличие воды")
    has_electricity: Optional[bool] = Field(None, description="Наличие электричества")
    has_internet: Optional[bool] = Field(None, description="Наличие интернета")
    zoning: Optional[str] = Field(None, description="Зонирование (сельское, городское и т.д.)")
    
    # Описание и дополнительная информация
    description: Optional[str] = Field(None, description="Полное описание объявления")
    characteristics: Optional[Dict[str, Any]] = Field(None, description="Характеристики участка в виде ключ-значение")
    
    # Медиа-контент
    images: Optional[List[str]] = Field(None, description="Список URL изображений")
    image_count: Optional[int] = Field(None, description="Количество изображений")
    
    # Метаданные
    created_at: Optional[datetime] = Field(None, description="Дата создания объявления")
    updated_at: Optional[datetime] = Field(None, description="Дата обновления объявления")
    crawled_at: datetime = Field(default_factory=datetime.now, description="Дата парсинга объявления")
    
    # Хэш для проверки дубликатов
    content_hash: Optional[str] = Field(None, description="Хэш содержимого для определения дубликатов")
    
    @validator('price_per_sqm', pre=True, always=False)
    def calculate_price_per_sqm(cls, v, values):
        """Расчет цены за квадратный метр, если не указана"""
        if v is not None:
            return v
        if values.get('price') and values.get('area') and values.get('area') > 0:
            return round(values['price'] / values['area'], 2)
        return None
    
    @validator('image_count', pre=True, always=False)
    def count_images(cls, v, values):
        """Подсчет количества изображений, если не указано"""
        if v is not None:
            return v
        if values.get('images'):
            return len(values['images'])
        return None
    
    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        } 