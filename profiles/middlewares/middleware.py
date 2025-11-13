# -*- coding: utf-8 -*-
import logging
from django.utils import timezone
from django.core.cache import cache
from django.db import DatabaseError
from datetime import timedelta
from profiles.models import UserProfile
from profiles.models import UserSession

from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class UpdateLastSeenMiddleware:
    """
    Middleware для обновления времени последней активности пользователя.
    
    Оптимизирован с использованием кэша:
    - Обновляет БД только раз в 5 минут
    - Пропускает статические файлы и медиа
    - Обрабатывает ошибки БД
    - Не блокирует запрос при проблемах с БД
    """
    
    # Настройки
    UPDATE_INTERVAL = 300  # 5 минут в секундах
    CACHE_PREFIX = 'last_seen_'
    CACHE_TIMEOUT = 300  # 5 минут
    
    # Пути которые нужно пропускать
    SKIP_PATHS = (
        '/static/',
        '/media/',
        '/favicon.ico',
        '/robots.txt',
        '/admin/jsi18n/',
    )
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Обрабатываем запрос
        response = self.get_response(request)
        
        # Обновляем активность после обработки запроса
        self._update_last_seen(request)
        
        return response

    def _should_skip(self, request):
        """Проверка нужно ли пропустить этот запрос"""
        # Пропускаем если пользователь не авторизован
        if not request.user.is_authenticated:
            return True
        
        # Пропускаем статику, медиа и другие служебные пути
        path = request.path
        if any(path.startswith(skip_path) for skip_path in self.SKIP_PATHS):
            return True
        
        # Пропускаем AJAX запросы к определённым эндпоинтам
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # Можно добавить исключения для определённых AJAX путей
            if any(endpoint in path for endpoint in ['/api/messages/', '/api/notifications/']):
                return True
        
        return False

    def _update_last_seen(self, request):
        """Обновление времени последней активности с использованием кэша"""
        if self._should_skip(request):
            return
        
        user_id = request.user.id
        cache_key = f'{self.CACHE_PREFIX}{user_id}'
        
        # Проверяем кэш
        last_update = cache.get(cache_key)
        now = timezone.now()
        
        # Если обновляли недавно - пропускаем
        if last_update:
            time_since_update = (now - last_update).total_seconds()
            if time_since_update < self.UPDATE_INTERVAL:
                return
        
        # Обновляем БД
        try:
            # Используем update() для эффективности
            # select_for_update() предотвращает race conditions
            updated = UserProfile.objects.filter(
                user_id=user_id
            ).update(last_seen=now)
            
            # Если профиль не найден - логируем предупреждение
            if updated == 0:
                logger.warning(f'Profile not found for user {request.user.username} (ID: {user_id})')
            else:
                # Обновляем кэш только если обновление успешно
                cache.set(cache_key, now, self.CACHE_TIMEOUT)
                
        except DatabaseError as e:
            # Не блокируем запрос при проблемах с БД
            logger.error(f'Database error updating last_seen for user {user_id}: {e}')
        except Exception as e:
            # Ловим любые другие ошибки
            logger.error(f'Unexpected error updating last_seen for user {user_id}: {e}')


class OnlineUsersMiddleware:
    """
    Опциональный middleware для отслеживания онлайн пользователей.
    Хранит список активных пользователей в кэше.
    """
    
    ONLINE_THRESHOLD = 300  # 5 минут
    CACHE_KEY = 'online_users'
    CACHE_TIMEOUT = 60  # Обновляем список каждую минуту
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        if request.user.is_authenticated:
            self._update_online_users(request.user.id)
        
        return response

    def _update_online_users(self, user_id):
        """Добавление пользователя в список онлайн"""
        try:
            online_users = cache.get(self.CACHE_KEY, set())
            online_users.add(user_id)
            cache.set(self.CACHE_KEY, online_users, self.CACHE_TIMEOUT)
        except Exception as e:
            logger.error(f'Error updating online users: {e}')

    @classmethod
    def get_online_users_count(cls):
        """Получение количества онлайн пользователей"""
        try:
            online_users = cache.get(cls.CACHE_KEY, set())
            return len(online_users)
        except Exception:
            return 0


class RequestLoggingMiddleware:
    """
    Опциональный middleware для логирования медленных запросов.
    Помогает найти узкие места в производительности.
    """
    
    SLOW_REQUEST_THRESHOLD = 1.0  # секунды
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        import time
        start_time = time.time()
        
        response = self.get_response(request)
        
        duration = time.time() - start_time
        
        # Логируем медленные запросы
        if duration > self.SLOW_REQUEST_THRESHOLD:
            logger.warning(
                f'Slow request: {request.method} {request.path} '
                f'took {duration:.2f}s '
                f'(user: {request.user.username if request.user.is_authenticated else "anonymous"})'
            )
        
        return response


# ==============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================================================

def get_online_users():
    """
    Получить QuerySet онлайн пользователей.
    Используется в шаблонах или views.
    """
    from datetime import timedelta
    threshold = timezone.now() - timedelta(minutes=5)
    return UserProfile.objects.filter(
        last_seen__gte=threshold
    ).select_related('user')


def get_online_users_count():
    """
    Быстрое получение количества онлайн пользователей из кэша.
    """
    return OnlineUsersMiddleware.get_online_users_count()


# ==============================================================================
# CONTEXT PROCESSOR (добавить в settings.py)
# ==============================================================================

def online_users_processor(request):
    """
    Context processor для отображения онлайн пользователей в шаблонах.
    
    Добавьте в settings.py:
    TEMPLATES = [{
        'OPTIONS': {
            'context_processors': [
                ...
                'profiles.middlewares.middleware.online_users_processor',
            ],
        },
    }]
    """
    return {
        'online_users_count': get_online_users_count(),
    }

# ==========================================
# MIDDLEWARE ДЛЯ СТАТИСТИКИ
# ========================================== 

class SessionTrackingMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if request.user.is_authenticated:
            try:
                session = UserSession.objects.filter(user=request.user, logout_time__isnull=True).latest('login_time')
                request.user_session = session
            except UserSession.DoesNotExist:
                request.user_session = None