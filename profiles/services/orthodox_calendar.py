"""
Сервис для работы с православным календарем

Поддерживает:
- Неподвижные праздники (фиксированные даты)
- Переходящие праздники (зависят от Пасхи)
- Посты (многодневные и однодневные)
- Дни памяти святых
- Седмицы (сплошные, мясопустная и т.д.)
"""

import os
import json
import logging
from datetime import datetime, timedelta, date
from functools import lru_cache
from typing import Dict, List, Optional, Tuple
from django.conf import settings

logger = logging.getLogger(__name__)


# ============================================================================
# КОНСТАНТЫ И УТИЛИТЫ
# ============================================================================

# Алгоритм Гаусса для вычисления Пасхи (Юлианский календарь)
def calculate_easter_julian(year: int) -> date:
    """
    Вычисление даты Пасхи по Юлианскому календарю
    (Православная Пасха)
    
    Args:
        year: Год для расчета
        
    Returns:
        date: Дата Пасхи
    """
    a = year % 19
    b = year % 4
    c = year % 7
    d = (19 * a + 15) % 30
    e = (2 * b + 4 * c + 6 * d + 6) % 7
    
    # Дата Пасхи по старому стилю
    day = 22 + d + e
    month = 3
    
    if day > 31:
        day = day - 31
        month = 4
    
    # Переводим в новый стиль (+13 дней для XX-XXI веков)
    easter_old_style = date(year, month, day)
    easter_new_style = easter_old_style + timedelta(days=13)
    
    return easter_new_style


# Кэшируем расчет Пасхи для оптимизации
@lru_cache(maxsize=100)
def get_easter_date(year: int) -> date:
    """Получить дату Пасхи с кэшированием"""
    return calculate_easter_julian(year)


# ============================================================================
# ОСНОВНОЙ СЕРВИС КАЛЕНДАРЯ
# ============================================================================

class OrthodoxCalendarService:
    """
    Сервис для работы с православным календарем
    """
    
    def __init__(self):
        """Инициализация сервиса"""
        self.calendar_data = self._load_calendar_data()
        self._easter_cache = {}
    
    def _load_calendar_data(self) -> Dict:
        """
        Загрузка данных из JSON файла
        
        Returns:
            Dict: Данные календаря
        """
        json_path = os.path.join(settings.BASE_DIR, 'data', 'orthodox_calendar.json')
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info("Календарь успешно загружен")
                return data
        except FileNotFoundError:
            logger.error(f"Файл календаря не найден: {json_path}")
            return self._get_empty_calendar()
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON календаря: {e}")
            return self._get_empty_calendar()
        except Exception as e:
            logger.error(f"Неожиданная ошибка загрузки календаря: {e}", exc_info=True)
            return self._get_empty_calendar()
    
    @staticmethod
    def _get_empty_calendar() -> Dict:
        """Пустая структура календаря"""
        return {
            'holidays': [],
            'fasting_periods': [],
            'weekly_fasting': {},
            'non_fasting_weeks': [],
            'saint_days': {},
            'metadata': {}
        }
    
    # ========================================================================
    # РАБОТА С ПРАЗДНИКАМИ
    # ========================================================================
    
    def get_holiday_by_date(self, target_date: date) -> Optional[Dict]:
        """
        Получить информацию о празднике на конкретную дату
        
        Args:
            target_date: Дата для поиска
            
        Returns:
            Dict: Информация о празднике или None
        """
        date_str = target_date.strftime('%m-%d')
        
        # 1. Проверяем неподвижные праздники
        for holiday in self.calendar_data.get('holidays', []):
            if holiday.get('date') == date_str and not holiday.get('movable'):
                return self._enrich_holiday(holiday, target_date)
        
        # 2. Проверяем переходящие праздники
        movable_holiday = self._get_movable_holiday(target_date)
        if movable_holiday:
            return movable_holiday
        
        # 3. Проверяем дни святых
        saint_day = self.calendar_data.get('saint_days', {}).get(date_str)
        if saint_day:
            return self._create_saint_day(saint_day, target_date)
        
        # 4. Обычный день
        return self._create_regular_day(target_date)
    
    def _enrich_holiday(self, holiday: Dict, target_date: date) -> Dict:
        """
        Обогатить информацию о празднике дополнительными данными
        
        Args:
            holiday: Базовая информация о празднике
            target_date: Дата праздника
            
        Returns:
            Dict: Расширенная информация
        """
        return {
            **holiday,
            'fast': self.is_fasting_day(target_date),
            'week_info': self._get_week_info(target_date),
            'formatted_date': target_date.strftime('%d %B %Y'),
        }
    
    def _get_movable_holiday(self, target_date: date) -> Optional[Dict]:
        """
        Получить переходящий праздник для даты
        
        Args:
            target_date: Дата для проверки
            
        Returns:
            Dict: Информация о празднике или None
        """
        easter = get_easter_date(target_date.year)
        
        # Вычисляем смещение от Пасхи в днях
        delta = (target_date - easter).days
        
        # Карта переходящих праздников (смещение от Пасхи в днях)
        movable_holidays = {
            -63: {  # За 9 недель до Пасхи
                'title': 'Неделя о мытаре и фарисее',
                'type': 'Подготовительная к Великому посту',
                'category': 'preparatory',
            },
            -56: {
                'title': 'Неделя о блудном сыне',
                'type': 'Подготовительная к Великому посту',
                'category': 'preparatory',
            },
            -49: {
                'title': 'Неделя мясопустная',
                'type': 'Прощеное воскресенье',
                'category': 'preparatory',
            },
            -48: {
                'title': 'Начало Великого поста',
                'type': 'Чистый понедельник',
                'category': 'great_lent',
            },
            -7: {
                'title': 'Лазарева суббота',
                'type': 'Воскрешение Лазаря',
                'category': 'lent',
            },
            -1: {
                'title': 'Вход Господень в Иерусалим',
                'type': 'Вербное воскресенье',
                'category': 'major',
            },
            0: {
                'title': 'ПАСХА - ВОСКРЕСЕНИЕ ХРИСТОВО',
                'type': 'Праздник праздников',
                'category': 'pascha',
                'description': 'Светлое Христово Воскресение - главный праздник христианства',
            },
            39: {
                'title': 'Вознесение Господне',
                'type': 'Двунадесятый праздник',
                'category': 'major',
            },
            49: {
                'title': 'День Святой Троицы (Пятидесятница)',
                'type': 'Двунадесятый праздник',
                'category': 'major',
            },
            50: {
                'title': 'День Святого Духа',
                'type': 'Понедельник Святого Духа',
                'category': 'major',
            },
        }
        
        if delta in movable_holidays:
            holiday = movable_holidays[delta]
            return {
                **holiday,
                'movable': True,
                'easter_offset': delta,
                'fast': self.is_fasting_day(target_date),
                'formatted_date': target_date.strftime('%d %B %Y'),
            }
        
        return None
    
    def _create_saint_day(self, saint_name: str, target_date: date) -> Dict:
        """Создать запись для дня святого"""
        return {
            'title': saint_name,
            'type': 'День памяти святого',
            'category': 'saint',
            'fast': self.is_fasting_day(target_date),
            'description': f'В этот день Православная Церковь празднует память: {saint_name}',
            'liturgy': 'Литургия святителя Иоанна Златоуста',
        }
    
    def _create_regular_day(self, target_date: date) -> Dict:
        """Создать запись для обычного дня"""
        is_fast = self.is_fasting_day(target_date)
        
        return {
            'title': 'Обычный день',
            'type': 'Рядовой день',
            'category': 'regular',
            'fast': is_fast,
            'description': 'Обычный день церковного календаря. Совершаются повседневные богослужения.',
            'liturgy': 'Литургия святителя Иоанна Златоуста',
        }
    
    # ========================================================================
    # РАБОТА С ПОСТАМИ
    # ========================================================================
    
    def is_fasting_day(self, target_date: date) -> bool:
        """
        Проверить, является ли день постным
        
        Args:
            target_date: Дата для проверки
            
        Returns:
            bool: True если постный день
        """
        # 1. Многодневные посты
        if self._is_in_fasting_period(target_date):
            return True
        
        # 2. Однодневные посты (среда и пятница)
        if target_date.weekday() in [2, 4]:  # Среда (2) и пятница (4)
            if not self._is_in_non_fasting_week(target_date):
                return True
        
        # 3. Однодневные праздничные посты
        if self._is_single_day_fast(target_date):
            return True
        
        return False
    
    def _is_in_fasting_period(self, target_date: date) -> bool:
        """
        Проверить, находится ли дата в периоде многодневного поста
        
        Args:
            target_date: Дата для проверки
            
        Returns:
            bool: True если в посту
        """
        month, day = target_date.month, target_date.day
        
        # Неподвижные посты из JSON
        for period in self.calendar_data.get('fasting_periods', []):
            if period.get('start_variable'):
                # Переходящие посты обрабатываем отдельно
                continue
            
            start_date = period.get('start_date')
            end_date = period.get('end_date')
            
            if start_date and end_date:
                start_month, start_day = map(int, start_date.split('-'))
                end_month, end_day = map(int, end_date.split('-'))
                
                # Рождественский пост (переходит через Новый год)
                if start_month > end_month:
                    if (month == start_month and day >= start_day) or \
                       (month == end_month and day <= end_day) or \
                       (month > start_month or month < end_month):
                        return True
                # Обычные посты
                else:
                    if (start_month < month < end_month) or \
                       (month == start_month and day >= start_day) or \
                       (month == end_month and day <= end_day):
                        return True
        
        # Великий пост (переходящий)
        if self._is_great_lent(target_date):
            return True
        
        # Петров пост (переходящий)
        if self._is_apostles_fast(target_date):
            return True
        
        return False
    
    def _is_great_lent(self, target_date: date) -> bool:
        """Великий пост (48 дней до Пасхи)"""
        easter = get_easter_date(target_date.year)
        lent_start = easter - timedelta(days=48)
        lent_end = easter - timedelta(days=1)
        return lent_start <= target_date <= lent_end
    
    def _is_apostles_fast(self, target_date: date) -> bool:
        """
        Петров (Апостольский) пост
        От 8 дня после Троицы до 12 июля (нов. ст.)
        """
        easter = get_easter_date(target_date.year)
        trinity = easter + timedelta(days=49)  # Троица на 50-й день после Пасхи
        fast_start = trinity + timedelta(days=8)
        fast_end = date(target_date.year, 7, 12)
        
        return fast_start <= target_date <= fast_end
    
    def _is_in_non_fasting_week(self, target_date: date) -> bool:
        """
        Проверить, находится ли дата в сплошной седмице
        (когда пост в среду и пятницу отменяется)
        
        Args:
            target_date: Дата для проверки
            
        Returns:
            bool: True если в сплошной седмице
        """
        easter = get_easter_date(target_date.year)
        
        # Карта сплошных седмиц (относительно Пасхи)
        non_fasting_weeks = [
            # Святки (7 января - 18 января)
            (date(target_date.year, 1, 7), date(target_date.year, 1, 18)),
            
            # Мытаря и фарисея (за 3 недели до Великого поста)
            (easter - timedelta(days=70), easter - timedelta(days=64)),
            
            # Сырная (Масленица) (за 1 неделю до Великого поста)
            (easter - timedelta(days=56), easter - timedelta(days=50)),
            
            # Пасхальная (Светлая) (неделя после Пасхи)
            (easter, easter + timedelta(days=7)),
            
            # Троицкая (неделя после Троицы)
            (easter + timedelta(days=49), easter + timedelta(days=56)),
        ]
        
        for start, end in non_fasting_weeks:
            if start <= target_date <= end:
                return True
        
        return False
    
    def _is_single_day_fast(self, target_date: date) -> bool:
        """
        Однодневные праздничные посты:
        - Крещенский сочельник (18 января)
        - Усекновение главы Иоанна Предтечи (11 сентября)
        - Воздвижение Креста Господня (27 сентября)
        """
        single_day_fasts = [
            (1, 18),   # 18 января
            (9, 11),   # 11 сентября
            (9, 27),   # 27 сентября
        ]
        
        return (target_date.month, target_date.day) in single_day_fasts
    
    # ========================================================================
    # ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ
    # ========================================================================
    
    def _get_week_info(self, target_date: date) -> Optional[str]:
        """
        Получить информацию о церковной седмице
        
        Args:
            target_date: Дата для проверки
            
        Returns:
            str: Название седмицы или None
        """
        if target_date.weekday() != 6:  # Не воскресенье
            return None
        
        easter = get_easter_date(target_date.year)
        delta = (target_date - easter).days
        
        week_names = {
            -63: 'Неделя о мытаре и фарисее',
            -56: 'Неделя о блудном сыне',
            -49: 'Неделя мясопустная (Прощеное воскресенье)',
            -42: '1-я седмица Великого поста',
            -35: '2-я седмица Великого поста',
            -28: '3-я седмица Великого поста (Крестопоклонная)',
            -21: '4-я седмица Великого поста',
            -14: '5-я седмица Великого поста',
            -7: '6-я седмица Великого поста (Вход Господень в Иерусалим)',
            0: 'ПАСХА - ВОСКРЕСЕНИЕ ХРИСТОВО',
            7: 'Антипасха (Фомина неделя)',
            14: 'Неделя жен-мироносиц',
            21: 'Неделя о расслабленном',
            28: 'Неделя о самарянке',
            35: 'Неделя о слепом',
            42: 'Отдание Пасхи',
            49: 'День Святой Троицы (Пятидесятница)',
        }
        
        return week_names.get(delta)
    
    def get_upcoming_holidays(self, days: int = 7) -> List[Dict]:
        """
        Получить список ближайших значимых праздников
        
        Args:
            days: Количество дней для поиска
            
        Returns:
            List[Dict]: Список праздников
        """
        upcoming = []
        current_date = date.today()
        
        for i in range(days):
            check_date = current_date + timedelta(days=i)
            holiday = self.get_holiday_by_date(check_date)
            
            # Добавляем только значимые праздники
            if holiday and holiday.get('category') in ['pascha', 'great', 'major']:
                upcoming.append({
                    'date': check_date,
                    'holiday': holiday
                })
        
        return upcoming
    
    def get_month_calendar(self, year: int, month: int) -> List[Dict]:
        """
        Получить календарь на месяц
        
        Args:
            year: Год
            month: Месяц (1-12)
            
        Returns:
            List[Dict]: Список дней месяца с информацией
        """
        first_day = date(year, month, 1)
        
        if month == 12:
            last_day = date(year, month, 31)
        else:
            last_day = date(year, month + 1, 1) - timedelta(days=1)
        
        month_data = []
        current_day = first_day
        
        while current_day <= last_day:
            holiday = self.get_holiday_by_date(current_day)
            
            month_data.append({
                'date': current_day,
                'day': current_day.day,
                'weekday': current_day.weekday(),
                'holiday': holiday,
                'is_weekend': current_day.weekday() in [5, 6],
                'is_fast': self.is_fasting_day(current_day),
            })
            
            current_day += timedelta(days=1)
        
        return month_data


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

# Создаем единственный экземпляр сервиса
_calendar_service = None

def get_calendar_service() -> OrthodoxCalendarService:
    """
    Получить singleton экземпляр календарного сервиса
    
    Returns:
        OrthodoxCalendarService: Экземпляр сервиса
    """
    global _calendar_service
    if _calendar_service is None:
        _calendar_service = OrthodoxCalendarService()
        logger.info("Православный календарь инициализирован")
    return _calendar_service


# ============================================================================
# УДОБНЫЕ ФУНКЦИИ ДЛЯ ИСПОЛЬЗОВАНИЯ В ДРУГИХ ЧАСТЯХ ПРИЛОЖЕНИЯ
# ============================================================================

def get_today_holiday() -> Optional[Dict]:
    """Получить праздник текущего дня"""
    service = get_calendar_service()
    return service.get_holiday_by_date(date.today())


def is_fasting_today() -> bool:
    """Проверить, постный ли сегодня день"""
    service = get_calendar_service()
    return service.is_fasting_day(date.today())


def get_easter_date_for_year(year: int) -> date:
    """Получить дату Пасхи для года"""
    return get_easter_date(year)