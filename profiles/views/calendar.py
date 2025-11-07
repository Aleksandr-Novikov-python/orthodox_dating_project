import logging
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from datetime import datetime, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse

from profiles.services.orthodox_calendar import get_calendar_service

logger = logging.getLogger(__name__)

# ========================================================
#     Праваславный календарь
# ========================================================
class OrthodoxCalendarView(View):
    """
    Просмотр православного календаря на конкретную дату
    """
    
    @method_decorator(cache_page(60 * 60 * 24))  # Кэш на 24 часа
    def get(self, request):
        """Отображение календаря"""
        try:
            # Получаем сервис календаря
            calendar = get_calendar_service()
            
            # Парсим дату из параметра или используем текущую
            date_param = request.GET.get('date')
            if date_param:
                try:
                    selected_date = datetime.strptime(date_param, '%Y-%m-%d').date()
                except ValueError:
                    logger.warning(f"Некорректный формат даты: {date_param}")
                    selected_date = datetime.now().date()
            else:
                selected_date = datetime.now().date()
            
            # Получаем информацию о празднике
            holiday = calendar.get_holiday_by_date(selected_date)
            
            # Дополнительная информация
            context = {
                'holiday': holiday,
                'selected_date': selected_date,
                'selected_date_formatted': selected_date.strftime('%d %B %Y'),
                'is_sunday': selected_date.weekday() == 6,
                'is_fasting': calendar.is_fasting_day(selected_date),
                'upcoming_holidays': calendar.get_upcoming_holidays(days=7),
            }
            
            logger.debug(f"Календарь для даты {selected_date}: {holiday.get('title', 'Неизвестно')}")
            
            return render(request, 'profiles/calendar.html', context)
            
        except Exception as e:
            logger.error(f"Ошибка отображения календаря: {e}", exc_info=True)
            return render(request, 'profiles/calendar_error.html', {
                'error': 'Не удалось загрузить календарь'
            })
        
class CalendarMonthView(View):
    """
    Просмотр календаря на месяц
    """
    
    @method_decorator(cache_page(60 * 60 * 24))  # Кэш на 24 часа
    def get(self, request):
        """Отображение календаря на месяц"""
        try:
            calendar = get_calendar_service()
            
            # Парсим дату
            date_param = request.GET.get('date')
            if date_param:
                try:
                    selected_date = datetime.strptime(date_param, '%Y-%m-%d').date()
                except ValueError:
                    selected_date = datetime.now().date()
            else:
                selected_date = datetime.now().date()
            
            # Получаем данные на месяц
            month_data = calendar.get_month_calendar(
                selected_date.year,
                selected_date.month
            )
            
            # Навигация по месяцам
            first_day = selected_date.replace(day=1)
            prev_month = first_day - timedelta(days=1)
            
            if selected_date.month == 12:
                next_month = selected_date.replace(year=selected_date.year + 1, month=1, day=1)
            else:
                next_month = selected_date.replace(month=selected_date.month + 1, day=1)
            
            context = {
                'month_data': month_data,
                'selected_month': selected_date.strftime('%B %Y'),
                'selected_date': selected_date,
                'prev_month': prev_month,
                'next_month': next_month,
            }
            
            logger.debug(f"Календарь на месяц: {selected_date.strftime('%B %Y')}")
            
            return render(request, 'profiles/calendar_month.html', context)
            
        except Exception as e:
            logger.error(f"Ошибка отображения месячного календаря: {e}", exc_info=True)
            return render(request, 'profiles/calendar_error.html', {
                'error': 'Не удалось загрузить календарь на месяц'
            })
        
# ============================================================================
# API VIEWS (для AJAX запросов)
# ============================================================================
class CalendarAPIView(View):
    """
    API для получения данных календаря в формате JSON
    """
    
    def get(self, request):
        """Получить данные о конкретной дате"""
        try:
            date_param = request.GET.get('date')
            
            if not date_param:
                return JsonResponse({
                    'success': False,
                    'error': 'Параметр date обязателен'
                }, status=400)
            
            try:
                target_date = datetime.strptime(date_param, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({
                    'success': False,
                    'error': 'Неверный формат даты. Используйте YYYY-MM-DD'
                }, status=400)
            
            # Получаем данные
            calendar = get_calendar_service()
            holiday = calendar.get_holiday_by_date(target_date)
            
            # Преобразуем в JSON-сериализуемый формат
            response_data = {
                'success': True,
                'date': date_param,
                'holiday': {
                    'title': holiday.get('title'),
                    'type': holiday.get('type'),
                    'category': holiday.get('category'),
                    'description': holiday.get('description'),
                    'fast': holiday.get('fast'),
                },
                'is_fasting': calendar.is_fasting_day(target_date),
                'is_weekend': target_date.weekday() in [5, 6],
            }
            
            logger.debug(f"API запрос для даты {date_param}")
            
            return JsonResponse(response_data)
            
        except Exception as e:
            logger.error(f"Ошибка API календаря: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Внутренняя ошибка сервера'
            }, status=500)
        
# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ИСПОЛЬЗОВАНИЯ В ШАБЛОНАХ
# ============================================================================
def get_today_holiday():
    """
    Получить праздник текущего дня
    Можно использовать в других views или шаблонах
    """
    from profiles.services.orthodox_calendar import get_today_holiday as _get_today
    return _get_today()


def is_fasting_today():
    """
    Проверить, постный ли сегодня день
    Можно использовать в других views или шаблонах
    """
    from profiles.services.orthodox_calendar import is_fasting_today as _is_fasting
    return _is_fasting()