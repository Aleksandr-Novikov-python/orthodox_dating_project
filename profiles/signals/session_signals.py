
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from django.utils.timezone import now
import logging

from profiles.models import UserSession  # или путь к модели, если она в другом приложении

logger = logging.getLogger(__name__)

# ==========================================
# СИГНАЛЫ ДЛЯ СТАТИСТИКИ
# ========================================== 
def get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


@receiver(user_logged_in)
def start_user_session(sender, request, user, **kwargs):
    ip = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    session_key = getattr(request.session, 'session_key', None)
    if not session_key:
        request.session.save()  # создаёт session_key, если его нет
        session_key = request.session.session_key   

    # Завершаем все незавершённые сессии (на всякий случай)
    UserSession.objects.filter(user=user, logout_time__isnull=True).update(logout_time=now())

    session = UserSession.objects.create(
        user=user,
        ip_address=ip,
        user_agent=user_agent,
        session_key=session_key
    )

    logger.info(
        f"🔐 Вход пользователя: {user.username} | IP: {ip} | UA: {user_agent} | Session ID: {session_key}"
    )


# @receiver(user_logged_out)
# def end_user_session_signal(sender, request, user, **kwargs):
#     session_key = getattr(request.session, 'session_key', None)

#     if not session_key:
#         logger.debug(f"🔍 Нет session_key в request.session при выходе пользователя: {user.username}")
#         return

#     try:
#         session = UserSession.objects.filter(
#             user=user,
#             session_key=session_key,
#             logout_time__isnull=True
#         ).first()

#         if session:
#             session.logout_time = now()
#             session.calculate_duration()
#             session.save()

#             logger.info(
#                 f"✅ Выход пользователя: {user.username} | Длительность: {session.duration_minutes} мин | Session ID: {session.session_key}"
#             )
#         else:
#             logger.debug(  # понижаем уровень до debug, чтобы не засорять warning'ами
#                 f"⚠️ Сессия не найдена или уже завершена: {user.username} | Session Key: {session_key}"
#             )

#         # Если функция делает что-то ещё (например, чистит кэш или токены)
#         end_user_session(session_key)

#     except Exception as e:
#         logger.exception(f"❌ Ошибка при завершении сессии пользователя {user.username}: {e}")




