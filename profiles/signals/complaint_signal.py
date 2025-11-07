from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from profiles.models import Complaint, Notification
from django.contrib.auth import get_user_model

User = get_user_model()
print("📦 complaint_signal.py загружен")


@receiver(pre_save, sender=Complaint)
def store_old_status(sender, instance, **kwargs):
    """Сохраняем старый статус перед изменением"""
    if instance.pk:
        try:
            old_instance = Complaint.objects.get(pk=instance.pk)
            instance._old_status = old_instance.status
        except Complaint.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


# ✅ ИСПРАВЛЕНО: ТОЛЬКО ОДИН receiver для post_save
@receiver(post_save, sender=Complaint)
def handle_complaint_change(sender, instance, created, **kwargs):
    """
    Единая функция для обработки создания и изменения жалобы
    Отправляет уведомление ОДИН раз при изменении статуса
    """
    print(f"\n📣 post_save сработал для жалобы #{instance.id}")
    print(f"   Created: {created}, Status: {instance.status}")
    
    # Проверка наличия автора жалобы
    if not instance.reporter:
        print("⚠️ Жалоба без автора — уведомление не отправлено")
        return
    
    # Подготовка сообщений для разных статусов
    status_messages = {
        Complaint.STATUS_NEW: {
            'message': f"Ваша жалоба на пользователя {instance.reported_user.first_name} взята на рассмотрение администрацией.",
            'emoji': '🆕'
        },
        Complaint.STATUS_IN_PROGRESS: {
            'message': f"Ваша жалоба на пользователя {instance.reported_user.first_name} находится в работе. Администрация проверяет информацию.",
            'emoji': '⏳'
        },
        Complaint.STATUS_RESOLVED: {
            'message': f"Ваша жалоба на пользователя {instance.reported_user.first_name} рассмотрена и разрешена. Приняты соответствующие меры. Спасибо за бдительность!",
            'emoji': '✅'
        }
    }
    
    # Определяем нужно ли отправлять уведомление
    should_send_notification = False
    
    if created:
        # При создании жалобы отправляем уведомление только если статус не "new"
        # (обычно жалобы создаются со статусом "new", уведомление придёт при смене на "in_progress")
        if instance.status != Complaint.STATUS_NEW:
            print(f"🆕 Жалоба создана со статусом: {instance.status}")
            should_send_notification = True
        else:
            print(f"🆕 Жалоба создана со статусом 'new' - уведомление пока не отправляем")
    else:
        # При изменении проверяем изменился ли статус
        if hasattr(instance, '_old_status') and instance._old_status and instance._old_status != instance.status:
            print(f"🔄 Статус изменился: {instance._old_status} → {instance.status}")
            should_send_notification = True
        else:
            print("ℹ️ Статус не изменился - уведомление не нужно")
    
    # Отправляем уведомление если нужно
    if should_send_notification:
        status_data = status_messages.get(instance.status)

        if status_data:
            message = status_data['message']
            emoji = status_data['emoji']
        else:
            # Fallback для неизвестных статусов
            message = f"Статус вашей жалобы на пользователя {instance.reported_user.username} изменён: {instance.get_status_display()}"
            emoji = '📝'
        
            from django.utils.timezone import now
            from datetime import timedelta

            # 💡 Защита от дублирования
            recent = Notification.objects.filter(
                recipient=instance.reporter,
                message=message,
                notification_type='COMPLAINT_STATUS',
                created_at__gte=now() - timedelta(minutes=5)
            ).exists()

            if recent:
                print("⚠️ Похожее уведомление уже было недавно — пропускаем")
                return
            # 💡 Защита от дублирования конец
            
        try:
            # ✅ Создаём уведомление БЕЗ sender
            notification = Notification.objects.create(
                recipient=instance.reporter,
                sender=None,  # БЕЗ sender - покажется иконка администрации
                message=message,
                notification_type='COMPLAINT_STATUS'
            )
            print(f"{emoji} ✅ Уведомление отправлено")
            print(f"   Notification ID: {notification.id}")
            print(f"   Получатель: {instance.reporter.username}")
            print(f"   Сообщение: {message[:60]}...")
            
        except Exception as e:
            print(f"❌ Ошибка при создании уведомления: {e}")
            import traceback
            print(traceback.format_exc())
    else:
        print("ℹ️ Уведомление не требуется")
    
    # Логирование в ComplaintLog (опционально)
    if not created and hasattr(instance, '_old_status') and instance._old_status and instance._old_status != instance.status:
        try:
            from profiles.models import ComplaintLog
            ComplaintLog.objects.create(
                complaint=instance,
                changed_by=None,  # Из сигнала не знаем кто изменил
                old_status=instance._old_status,
                new_status=instance.status,
                comment='Изменено через сигнал'
            )
            print("   📝 Запись в ComplaintLog создана")
        except Exception as e:
            print(f"   ⚠️ Не удалось создать ComplaintLog: {e}")

print("✅ Сигналы настроены (БЕЗ дублирования)")































