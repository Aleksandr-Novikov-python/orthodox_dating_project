import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType

from profiles.models import Like, Message, Notification

logger = logging.getLogger(__name__)

# ==============================================================================
# СИГНАЛЫ ДЛЯ СООБЩЕНИЙ
# ==============================================================================
@receiver(post_save, sender=Message)
def handle_new_message_notification(sender, instance, created, **kwargs):
    """
    Создание уведомления при получении нового сообщения.
    Уведомление создаётся только если сообщение новое и не дублируется.
    """
    print(f"\n💬 post_save сработал для сообщения #{instance.id}")
    if not created:
        return

    sender_user = instance.sender
    receiver_user = instance.receiver

    # Защита от сообщений самому себе
    if sender_user == receiver_user:
        logger.warning(f"Попытка отправить сообщение самому себе: {sender_user.username}")
        return

    try:
        # Проверка взаимной симпатии
        mutual_like = (
            Like.objects.filter(user_from=sender_user, user_to=receiver_user).exists() and
            Like.objects.filter(user_from=receiver_user, user_to=sender_user).exists()
        )

        if not mutual_like:
            logger.warning(
                f"Попытка отправить сообщение без взаимной симпатии: "
                f"{sender_user.username} → {receiver_user.username}"
            )
            return

        # 🔍 Проверка на существующее уведомление о сообщении
        already_exists = Notification.objects.filter(
            recipient=receiver_user,
            sender=sender_user,
            notification_type='MESSAGE',
            object_id=instance.id,
            content_type=ContentType.objects.get_for_model(instance)
        ).exists()

        if already_exists:
            logger.info(f"⚠️ Уведомление уже существует для сообщения #{instance.id}")
            return

        # Создаём уведомление
        Notification.objects.create(
            recipient=receiver_user,
            sender=sender_user,
            message=f"Новое сообщение от {sender_user.first_name or sender_user.username}",
            notification_type='MESSAGE',
            content_type=ContentType.objects.get_for_model(instance),
            object_id=instance.id
        )

        logger.info(f"Создано уведомление о сообщении: {sender_user.username} → {receiver_user.username}")

    except Exception as e:
        logger.error(f"Ошибка при создании уведомления о сообщении: {e}")
