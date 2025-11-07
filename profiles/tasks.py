from celery import shared_task
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.storage import default_storage
from profiles.models import Photo, Notification
from profiles.services.photo_verification import calculate_photo_hash, PhotoVerificationService
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from PIL import Image
import logging

logger = logging.getLogger(__name__)

@shared_task(name='profiles.tasks.process_uploaded_photo')
def process_uploaded_photo(photo_id):
    """
    Асинхронная обработка загруженного фото:
    1. Вычисление хеша
    2. Проверка на дубликаты
    3. Уведомление админа при необходимости
    
    ✅ Работает с локальным хранилищем И облачными (S3, GCS и т.д.)
    """
    try:
        photo = Photo.objects.select_related('user_profile__user').get(pk=photo_id)
    except ObjectDoesNotExist:
        logger.error(f"❌ Фото #{photo_id} не найдено")
        return {'status': 'error', 'message': 'Photo not found'}
    
    # Проверяем файл
    if not photo.image:
        logger.warning(f"⚠️ У фото #{photo_id} нет файла")
        return {'status': 'error', 'message': 'No image file'}
    
    result = {'photo_id': photo_id, 'status': 'success'}
    
    # ✅ ИСПРАВЛЕНО: Работаем с файловым объектом, а не с path
    try:
        # Открываем файл через Django storage (работает с любым бэкендом)
        with photo.image.open('rb') as image_file:
            image_data = image_file.read()
        
        # Проверяем что файл не пустой
        if not image_data:
            logger.warning(f"⚠️ Пустой файл для фото #{photo_id}")
            raise process_uploaded_photo.retry(exc=ValueError(f"Empty file for photo #{photo_id}"))
        
    except FileNotFoundError:
        logger.warning(f"⚠️ Файл не найден для фото #{photo_id}")
        # Повторяем попытку
        raise process_uploaded_photo.retry(exc=FileNotFoundError(f"File not found for photo #{photo_id}"))
    except Exception as e:
        logger.error(f"❌ Ошибка чтения файла для фото #{photo_id}: {e}")
        return {'status': 'error', 'message': f'File read error: {str(e)}'}
    
    # Шаг 1: Вычисляем хеш если его нет
    if not photo.image_hash:
        try:
            # ✅ ИСПРАВЛЕНО: передаем байты вместо пути
            photo_hash = calculate_photo_hash(image_data)
            
            # Обновляем БД напрямую (быстрее и не вызывает сигнал)
            Photo.objects.filter(pk=photo_id).update(image_hash=photo_hash)
            
            logger.info(f"✅ Хеш вычислен для фото #{photo_id}: {photo_hash[:8]}...")
            result['hash'] = photo_hash[:8]
            result['hash_calculated'] = True
            
            # Обновляем локальный объект
            photo.image_hash = photo_hash
            
        except Exception as e:
            logger.error(f"❌ Ошибка вычисления хеша для фото #{photo_id}: {e}")
            result['status'] = 'partial_error'
            result['error'] = str(e)
            return result
    else:
        result['hash_calculated'] = False
    
    # Шаг 2: Проверяем на дубликаты
    if photo.image_hash:
        try:
            similar = PhotoVerificationService.find_similar_photos(
                photo_hash=photo.image_hash,
                user_profile=photo.user_profile,
                exclude_photo_id=photo.id
            )
            
            result['duplicates_found'] = len(similar)
            
            if similar:
                logger.warning(
                    f"⚠️ Фото #{photo_id} пользователя {photo.user_profile.user.username} "
                    f"имеет {len(similar)} дубликат(ов)"
                )
                
                # ✅ ИСПРАВЛЕНО: передаем только ID фото и дубликатов
                similar_photo_ids = [photo.id for photo, score in similar]
                notify_admins_about_duplicate.apply_async(
                    args=[photo_id, similar_photo_ids]
                )
                result['admins_notified'] = True
            else:
                logger.info(f"✅ Фото #{photo_id} уникально")
                result['admins_notified'] = False
                
        except Exception as e:
            logger.error(f"❌ Ошибка проверки дубликатов для фото #{photo_id}: {e}")
            result['status'] = 'partial_error'
            result['duplicate_check_error'] = str(e)
    
    return result


@shared_task(name='profiles.tasks.notify_admins_about_duplicate')
def notify_admins_about_duplicate(photo_id, similar_photo_ids):
    """
    Отправляет уведомления админам о дубликате
    
    Args:
        photo_id: ID загруженного фото
        similar_photo_ids: список ID похожих фото
    
    ✅ ОПТИМИЗИРОВАНО: использует bulk_create для одного запроса в БД
    """
    try:
        # Загружаем объекты из БД по ID
        photo = Photo.objects.select_related('user_profile__user').get(pk=photo_id)
        admins = User.objects.filter(is_superuser=True, is_active=True)
        
        if not admins.exists():
            logger.warning("⚠️ Нет активных администраторов для уведомления")
            return {'status': 'no_admins'}
        
        message = (
            f"Пользователь {photo.user_profile.user.username} "
            f"загрузил фото #{photo.pk}, которое имеет {len(similar_photo_ids)} дубликат(ов). "
            f"Требуется проверка."
        )

        photo_ct = ContentType.objects.get_for_model(Photo)
        existing_admin_ids = Notification.objects.filter(
            content_type=photo_ct,
            object_id=photo.id,
            notification_type='ADMIN'
        ).values_list('recipient_id', flat=True)

        admins_to_notify = admins.exclude(id__in=existing_admin_ids)

        # ✅ ОПТИМИЗАЦИЯ: создаем список уведомлений
        notifications = [
            Notification(
                recipient=admin,
                sender=None,
                message=message,
                notification_type='ADMIN',
                content_type=photo_ct,
                object_id=photo.id
            )
            for admin in admins_to_notify
        ]
        
        # ✅ Одним запросом создаем все уведомления
        created_notifications = Notification.objects.bulk_create(notifications)
        notifications_count = len(created_notifications)
        
        logger.info(f"📧 Уведомления о дубликате отправлены {notifications_count} админам (bulk_create)")
        
        return {
            'status': 'success',
            'notifications_sent': notifications_count
        }
        
    except Photo.DoesNotExist:
        logger.error(f"❌ Фото #{photo_id} не найдено")
        return {'status': 'error', 'error': 'Photo not found'}
    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомления админам: {e}")
        return {'status': 'error', 'error': str(e)}
    

@shared_task(name='profiles.tasks.test_task')
def test_task():
    logger.info("✅ Test task executed")
    return "Test task completed"










