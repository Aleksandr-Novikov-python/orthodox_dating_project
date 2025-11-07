from django.db.models.signals import post_save
from django.dispatch import receiver
from profiles.models import Photo
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Photo)
def schedule_photo_processing(sender, instance, created, **kwargs):
    """
    Легковесный сигнал: просто ставит задачу в очередь
    """
    # Защита от рекурсии
    if kwargs.get('update_fields') and 'image_hash' in kwargs['update_fields']:
        return
    
    # Проверяем что есть файл
    if not instance.image:
        return
    
    # Ставим задачу в очередь
    from profiles.tasks import process_uploaded_photo
    
    try:
        # ✅ ИСПРАВЛЕНО: передаем только ID (сериализуемый тип)
        process_uploaded_photo.apply_async(
            args=[instance.pk],
            countdown=2
        )
        logger.info(f"📤 Задача обработки фото #{instance.pk} поставлена в очередь")
    except Exception as e:
        logger.error(f"❌ Ошибка постановки задачи для фото #{instance.pk}: {e}")



























