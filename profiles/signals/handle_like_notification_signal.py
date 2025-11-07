import logging
from profiles.models import Like, Notification
from django.db import transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)

# ==============================================================================
# СИГНАЛЫ ДЛЯ СИМПАТИЙ
# ==============================================================================
@receiver(post_save, sender=Like)
def handle_like_notification(sender, instance, created, **kwargs):
    """
    Обработка уведомлений при создании симпатии.
    - Создаёт уведомление о новой симпатии (если её ещё нет)
    - Проверяет взаимность и создаёт уведомление о матче
    """
    if not created:
        return

    liker = instance.user_from
    liked = instance.user_to

    # Защита от лайка самому себе
    if liker == liked:
        logger.warning(f"Попытка лайкнуть самого себя: {liker.username}")
        return

    try:
        with transaction.atomic():
            # 🔍 Проверка на существующее уведомление о симпатии
            existing_like_notification = Notification.objects.filter(
                recipient=liked,
                sender=liker,
                notification_type='LIKE',
                message__contains='выразил'
            ).exists()

            if not existing_like_notification:
                Notification.objects.create(
                    recipient=liked,
                    sender=liker,
                    message=f"{liker.first_name or liker.username} выразил(а) вам симпатию!",
                    notification_type='LIKE'
                )
                logger.info(f"Создано уведомление о симпатии: {liker.username} → {liked.username}")
            else:
                logger.info(f"Уведомление о симпатии уже существует: {liker.username} → {liked.username}")

            # Проверка взаимности
            mutual_like_exists = Like.objects.filter(
                user_from=liked,
                user_to=liker
            ).exists()

            if mutual_like_exists:
                existing_match_notification = Notification.objects.filter(
                    recipient=liker,
                    sender=liked,
                    message__contains='взаимная симпатия'
                ).exists()

                if not existing_match_notification:
                    Notification.objects.create(
                        recipient=liker,
                        sender=liked,
                        message=f"🎉 У вас взаимная симпатия с {liked.first_name or liked.username}! Теперь вы можете общаться.",
                        notification_type='LIKE'
                    )
                    Notification.objects.create(
                        recipient=liked,
                        sender=liker,
                        message=f"🎉 У вас взаимная симпатия с {liker.first_name or liker.username}! Теперь вы можете общаться.",
                        notification_type='LIKE'
                    )
                    logger.info(f"Взаимная симпатия: {liker.username} ↔ {liked.username}")
                else:
                    logger.info(f"Уведомление о взаимной симпатии уже существует: {liker.username} ↔ {liked.username}")

    except Exception as e:
        logger.error(f"Ошибка при обработке симпатии от {liker.username} к {liked.username}: {e}")



@receiver(post_delete, sender=Like)
def handle_like_deletion(sender, instance, **kwargs):
    """
    Обработка удаления симпатии (опционально).
    Можно удалить связанные уведомления или оставить для истории.
    """
    try:
        # Удаляем только уведомления о новой симпатии (не о взаимности)
        Notification.objects.filter(
            recipient=instance.user_to,
            sender=instance.user_from,
            notification_type='LIKE',
            message__contains='выразил'
        ).delete()
        
        logger.info(f"Удалены уведомления о симпатии: {instance.user_from.username} → {instance.user_to.username}")
    
    except Exception as e:
        logger.error(f"Ошибка при удалении уведомлений о симпатии: {e}")