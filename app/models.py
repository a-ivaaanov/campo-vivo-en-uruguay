from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, List, Dict, Any, Union, Literal
from datetime import datetime, timezone

# Вспомогательная функция для получения текущего времени UTC
def now_utc():
    return datetime.now(timezone.utc)

class Listing(BaseModel):
    """Модель данных для одного объявления о земельном участке."""
    # Обязательные поля
    id: str
    url: HttpUrl
    source: str # Источник (например, 'mercadolibre', 'infocasas')
    
    # Основные характеристики
    title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    
    # Изображения
    images: Optional[List[str]] = None
    
    # Цена и валюта
    price: Optional[float] = None  # Цена (число)
    price_currency: Optional[str] = "USD"  # Валюта (по умолчанию USD)
    price_per_sqm: Optional[float] = None  # Цена за квадратный метр
    
    # Площадь
    area: Optional[float] = None  # Площадь в квадратных метрах (число)
    area_unit: Optional[str] = "m²"  # Единица измерения площади
    
    # Коммуникации и характеристики
    has_water: Optional[bool] = None  # Наличие воды
    has_electricity: Optional[bool] = None  # Наличие электричества
    has_internet: Optional[bool] = None  # Наличие интернета
    zoning: Optional[str] = None  # Зонирование участка
    terrain_type: Optional[str] = None  # Тип местности
    
    # Метаданные
    crawled_at: datetime = Field(default_factory=now_utc)  # Дата и время сбора данных
    status: str = "active"  # Статус объявления (active, expired, sold, etc.)
    
    # Дополнительные атрибуты для хранения несистематизированных данных
    attributes: Optional[Dict[str, Any]] = None

    class Config:
        """Конфигурация модели."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        
    def format_price(self) -> str:
        """Форматирует цену с разделителями тысяч."""
        if self.price is None:
            return ""
        
        price_int = int(self.price)
        formatted = f"{price_int:,}".replace(',', ' ')
        
        if self.price_currency:
            return f"{formatted} {self.price_currency}"
        return formatted
    
    def format_area(self) -> str:
        """Форматирует площадь с учетом единиц измерения."""
        if self.area is None:
            return ""
        
        # Форматируем с разделителями тысяч
        area_formatted = f"{self.area:,}".replace(',', ' ').replace('.0', '')
        
        if self.area_unit:
            return f"{area_formatted} {self.area_unit}"
        return area_formatted
    
    def to_hectares(self) -> Optional[float]:
        """Конвертирует площадь в гектары, если применимо."""
        if self.area is None:
            return None
        
        # Если площадь в квадратных метрах, переводим в гектары (1 га = 10000 м²)
        if self.area_unit == "m²":
            return self.area / 10000
        
        # Если уже в гектарах
        if self.area_unit == "ha":
            return self.area
            
        return None
    
    def is_recent(self, hours: int = 24) -> bool:
        """Проверяет, является ли объявление недавним (в пределах указанного количества часов)."""
        if not self.crawled_at:
            return False
            
        time_diff = datetime.now(timezone.utc) - self.crawled_at
        return time_diff.total_seconds() < hours * 3600
    
    def calculate_price_per_sqm(self) -> Optional[float]:
        """Вычисляет цену за квадратный метр."""
        if self.price is None or self.area is None or self.area == 0:
            return None
            
        return self.price / self.area