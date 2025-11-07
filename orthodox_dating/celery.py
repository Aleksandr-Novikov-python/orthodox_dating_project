from celery import Celery
import os

from orthodox_dating.safe_requests import patch_requests
patch_requests()


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'orthodox_dating.settings')

app = Celery('orthodox_dating')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# ✅ Настройки сериализации
app.conf.update(
    task_serializer='json',  # только JSON (сериализуемые типы)
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # Оптимизация для обработки изображений
    task_soft_time_limit=300,
    task_time_limit=360,
    worker_prefetch_multiplier=1,
    
    # ✅ Настройки для производительности
    task_acks_late=True,  # Подтверждаем задачу после выполнения
    worker_max_tasks_per_child=1000,  # Перезапуск после 1000 задач
    task_reject_on_worker_lost=True,  # Возвращаем задачу в очередь при сбое
)


# ✅ Приоритеты задач (опционально)
app.conf.task_routes = {
    'profiles.tasks.process_uploaded_photo': {'queue': 'photos', 'priority': 5},
    'profiles.tasks.notify_admins_about_duplicate': {'queue': 'notifications', 'priority': 3},
}