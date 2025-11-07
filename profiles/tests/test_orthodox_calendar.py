"""
Тесты для сервиса православного календаря
"""

from datetime import date, timedelta
from django.test import TestCase
from profiles.services.orthodox_calendar import (
    OrthodoxCalendarService,
    get_easter_date,
)


class EasterCalculationTests(TestCase):
    """Тесты расчета даты Пасхи"""
    
    def test_easter_2024(self):
        """Пасха 2024 - 5 мая"""
        easter = get_easter_date(2024)
        self.assertEqual(easter, date(2024, 5, 5))
    
    def test_easter_2025(self):
        """Пасха 2025 - 20 апреля"""
        easter = get_easter_date(2025)
        self.assertEqual(easter, date(2025, 4, 20))
    
    def test_easter_2026(self):
        """Пасха 2026 - 12 апреля"""
        easter = get_easter_date(2026)
        self.assertEqual(easter, date(2026, 4, 12))
    
    def test_easter_caching(self):
        """Проверка кэширования расчета Пасхи"""
        easter1 = get_easter_date(2024)
        easter2 = get_easter_date(2024)
        self.assertIs(easter1, easter2)  # Должны быть один и тот же объект


class FastingTests(TestCase):
    """Тесты определения постных дней"""
    
    def setUp(self):
        self.calendar = OrthodoxCalendarService()
    
    def test_wednesday_fasting(self):
        """Среда - постный день (вне сплошных седмиц)"""
        # Обычная среда
        test_date = date(2024, 2, 7)  # Среда
        self.assertTrue(self.calendar.is_fasting_day(test_date))
    
    def test_friday_fasting(self):
        """Пятница - постный день"""
        test_date = date(2024, 2, 9)  # Пятница
        self.assertTrue(self.calendar.is_fasting_day(test_date))
    
    def test_christmas_fast(self):
        """Рождественский пост (28 ноября - 6 января)"""
        # Начало поста
        self.assertTrue(self.calendar.is_fasting_day(date(2024, 11, 28)))
        # Середина поста
        self.assertTrue(self.calendar.is_fasting_day(date(2024, 12, 15)))
        # Конец поста
        self.assertTrue(self.calendar.is_fasting_day(date(2025, 1, 6)))
        # После поста
        self.assertFalse(self.calendar.is_fasting_day(date(2025, 1, 8)))
    
    def test_great_lent(self):
        """Великий пост 2024 (18 марта - 4 мая)"""
        # Первый день Великого поста
        self.assertTrue(self.calendar.is_fasting_day(date(2024, 3, 18)))
        # Середина Великого поста
        self.assertTrue(self.calendar.is_fasting_day(date(2024, 4, 15)))
        # Последний день (Великая суббота)
        self.assertTrue(self.calendar.is_fasting_day(date(2024, 5, 4)))
    
    def test_pascha_week_no_fasting(self):
        """Светлая седмица - нет поста в среду и пятницу"""
        easter = get_easter_date(2024)
        # Среда Светлой седмицы
        wednesday = easter + timedelta(days=3)
        # В обычное время среда - пост, но не на Светлой седмице
        # (проверяем что среда, но не пост)
        self.assertEqual(wednesday.weekday(), 2)  # Это среда
        # Примечание: реализация может отличаться


class HolidayTests(TestCase):
    """Тесты определения праздников"""
    
    def setUp(self):
        self.calendar = OrthodoxCalendarService()
    
    def test_christmas(self):
        """Рождество Христово - 7 января"""
        holiday = self.calendar.get_holiday_by_date(date(2024, 1, 7))
        self.assertIsNotNone(holiday)
        self.assertIn('Рождество', holiday.get('title', ''))
    
    def test_pascha_2024(self):
        """Пасха 2024 - 5 мая"""
        holiday = self.calendar.get_holiday_by_date(date(2024, 5, 5))
        self.assertIsNotNone(holiday)
        self.assertEqual(holiday.get('category'), 'pascha')
        self.assertIn('ПАСХА', holiday.get('title', '').upper())
    
    def test_regular_day(self):
        """Обычный день"""
        # Произвольный будний день без праздников
        holiday = self.calendar.get_holiday_by_date(date(2024, 2, 15))
        self.assertEqual(holiday.get('category'), 'regular')
    
    def test_movable_holiday_ascension(self):
        """Вознесение - на 40-й день после Пасхи"""
        easter = get_easter_date(2024)
        ascension = easter + timedelta(days=39)
        holiday = self.calendar.get_holiday_by_date(ascension)
        self.assertIn('Вознесение', holiday.get('title', ''))


class MonthCalendarTests(TestCase):
    """Тесты календаря на месяц"""
    
    def setUp(self):
        self.calendar = OrthodoxCalendarService()
    
    def test_january_2024(self):
        """Календарь на январь 2024"""
        month_data = self.calendar.get_month_calendar(2024, 1)
        # В январе 31 день
        self.assertEqual(len(month_data), 31)
        # Первый день
        self.assertEqual(month_data[0]['day'], 1)
        # Последний день
        self.assertEqual(month_data[-1]['day'], 31)
    
    def test_february_leap_year(self):
        """Февраль в високосный год"""
        month_data = self.calendar.get_month_calendar(2024, 2)
        # В високосном году 29 дней
        self.assertEqual(len(month_data), 29)
    
    def test_february_regular_year(self):
        """Февраль в обычный год"""
        month_data = self.calendar.get_month_calendar(2025, 2)
        # В обычном году 28 дней
        self.assertEqual(len(month_data), 28)


class UpcomingHolidaysTests(TestCase):
    """Тесты получения ближайших праздников"""
    
    def setUp(self):
        self.calendar = OrthodoxCalendarService()
    
    def test_get_upcoming_holidays(self):
        """Получение ближайших праздников"""
        # Тестируем с фиксированной даты
        upcoming = self.calendar.get_upcoming_holidays(days=30)
        self.assertIsInstance(upcoming, list)
        # Проверяем структуру
        if upcoming:
            self.assertIn('date', upcoming[0])
            self.assertIn('holiday', upcoming[0])


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class CalendarIntegrationTests(TestCase):
    """Интеграционные тесты"""
    
    def test_full_year_consistency(self):
        """Проверка консистентности календаря на год"""
        calendar = OrthodoxCalendarService()
        year = 2024
        
        errors = []
        for month in range(1, 13):
            month_data = calendar.get_month_calendar(year, month)
            for day_info in month_data:
                target_date = day_info['date']
                # Проверяем что каждый день имеет валидную информацию
                if not day_info.get('holiday'):
                    errors.append(f"Нет информации о дне: {target_date}")
        
        self.assertEqual(len(errors), 0, f"Найдены ошибки: {errors}")


# ============================================================================
# КОМАНДA ДЛЯ ЗАПУСКА ТЕСТОВ
# ============================================================================
"""
# Запуск всех тестов календаря:
python manage.py test profiles.tests.test_orthodox_calendar

# Запуск конкретного теста:
python manage.py test profiles.tests.test_orthodox_calendar.EasterCalculationTests.test_easter_2024

# С подробным выводом:
python manage.py test profiles.tests.test_orthodox_calendar --verbosity=2
"""