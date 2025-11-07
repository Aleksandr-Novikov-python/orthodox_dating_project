from django.db.models.signals import post_save
from django.dispatch import receiver


# Сигнал для автоматического создания профиля
from profiles.models import UserProfile
from profiles.views.auth import User

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Автоматически создаёт профиль при создании пользователя"""
    if created:
        # Проверяем что профиль ещё не создан
        if not hasattr(instance, 'userprofile'):
            UserProfile.objects.create(user=instance)
            print(f"✅ Профиль создан для пользователя: {instance.username}")


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Сохраняет профиль при сохранении пользователя"""
    if hasattr(instance, 'userprofile'):
        instance.userprofile.save()
