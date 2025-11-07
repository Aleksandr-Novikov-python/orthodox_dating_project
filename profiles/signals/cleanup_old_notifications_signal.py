import logging

from profiles.models import Notification


logger = logging.getLogger(__name__)

# ==============================================================================
# УТИЛИТЫ ДЛЯ УВЕДОМЛЕНИЙ
# ==============================================================================
def cleanup_old_notifications(days=30):
    """
    Утилита для очистки старых прочитанных уведомлений.
    Можно вызывать через Celery task или management command.
    """
    from datetime import timedelta
    from django.utils import timezone
    
    cutoff_date = timezone.now() - timedelta(days=days)
    
    deleted_count, _ = Notification.objects.filter(
        is_read=True,
        created_at__lt=cutoff_date
    ).delete()
    
    logger.info(f"Удалено старых уведомлений: {deleted_count}")
    return deleted_count