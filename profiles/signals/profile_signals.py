import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

from profiles.models import UserProfile
from django.contrib.auth import get_user_model

User = get_user_model()

logger = logging.getLogger(__name__)

# ==============================================================================
# СИГНАЛЫ ДЛЯ ПРОФИЛЯ
# ==============================================================================
@receiver(post_save, sender=User)
def handle_user_profile(sender, instance, created, **kwargs):
    """
    Создаёт профиль при регистрации пользователя и сохраняет его при обновлении.
    Без дублирования, с защитой от IntegrityError.
    """
    try:
        profile, just_created = UserProfile.objects.get_or_create(user=instance)
        profile.save()
        if created and just_created:
            logger.info(f"Профиль создан для нового пользователя: {instance.username}")
        elif created and not just_created:
            logger.warning(f"Профиль уже существовал при создании пользователя: {instance.username}")
        elif not created:
            logger.info(f"Профиль сохранён при обновлении пользователя: {instance.username}")
    except Exception as e:
        logger.error(f"Ошибка при обработке профиля пользователя {instance.username}: {e}")
