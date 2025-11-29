
import uuid
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.text import slugify
from django.utils import timezone
from django.db.models.signals import post_save
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from datetime import date
from pytils.translit import slugify as pytils_slugify


# ==============================================================================
# ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ
# ==============================================================================
class UserProfile(models.Model):
    """Расширенный профиль пользователя для сайта знакомств"""

    GENDER_CHOICES = [
        ('Мужчина', 'Мужчина'),
        ('Женщина', 'Женщина')
    ]

    MARITAL_STATUS_CHOICES = [
        ('Не женат/Не замужем', 'Не женат/Не замужем'),
        ('Разведен(а)', 'Разведен(а)'),
        ('Вдовец/Вдова', 'Вдовец/Вдова')
    ]

    CHILDREN_CHOICES = [
        ('Нет', 'Нет'),
        ('Есть', 'Есть')
    ]

    CHURCHING_LEVEL_CHOICES = [
        ('Новоначальный', 'Новоначальный'),
        ('Воцерковленный', 'Воцерковленный')
    ]

    ATTITUDE_TO_FASTING_CHOICES = [
        ('Соблюдаю', 'Соблюдаю'),
        ('Не соблюдаю', 'Не соблюдаю')
    ]

    SACRAMENTS_CHOICES = [
        ('Регулярно', 'Регулярно'),
        ('Иногда', 'Иногда'),
        ('Редко', 'Редко')
    ]

    # Основная информация
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='userprofile'
    )
    patronymic = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Отчество"
    )
    date_of_birth = models.DateField(
        verbose_name="Дата рождения",
        null=True,
        blank=True,
        help_text="Формат: ГГГГ-ММ-ДД"
    )
    gender = models.CharField(
        max_length=10,
        choices=GENDER_CHOICES,
        verbose_name="Пол",
        blank=True,
        null=True
    )
    city = models.CharField(
        max_length=100,
        verbose_name="Город",
        blank=True,
        db_index=True
    )
    photo = models.ImageField(
        upload_to='profile_pics/%Y/%m/%d/',
        blank=True,
        null=True,
        default='default-avatar.png',
        verbose_name="Фотография профиля"
    )
    about_me = models.TextField(
        blank=True,
        verbose_name="О себе",
        max_length=2000,
        help_text="Максимум 2000 символов"
    )
    height = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name="Рост (см)",
        validators=[
            MinValueValidator(100, message="Минимальный рост 100 см"),
            MaxValueValidator(250, message="Максимальный рост 250 см")
        ]
    )

    # Семейное положение
    marital_status = models.CharField(
        max_length=50,
        choices=MARITAL_STATUS_CHOICES,
        verbose_name="Семейное положение",
        null=True,
        blank=True
    )
    children = models.CharField(
        max_length=50,
        choices=CHILDREN_CHOICES,
        verbose_name="Дети",
        null=True,
        blank=True
    )

    # Образование и работа
    education = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Образование"
    )
    occupation = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Профессия"
    )

    # Духовная жизнь
    churching_level = models.CharField(
        max_length=50,
        choices=CHURCHING_LEVEL_CHOICES,
        verbose_name="Степень воцерковленности",
        null=True,
        blank=True,
        db_index=True
    )
    attitude_to_fasting = models.CharField(
        max_length=50,
        choices=ATTITUDE_TO_FASTING_CHOICES,
        verbose_name="Отношение к постам",
        null=True,
        blank=True
    )
    sacraments = models.CharField(
        max_length=50,
        choices=SACRAMENTS_CHOICES,
        verbose_name="Участие в Таинствах",
        null=True,
        blank=True
    )
    favorite_saints = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Любимые святые"
    )
    spiritual_books = models.TextField(
        blank=True,
        verbose_name="Любимые духовные книги",
        max_length=1000
    )

    # Системные поля
    is_verified = models.BooleanField(
        default=False,
        verbose_name="Верифицирован",
        db_index=True
    )
    last_seen = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Последняя активность",
        db_index=True
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания профиля"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления профиля"
    )

    class Meta:
        verbose_name = "Профиль пользователя"
        verbose_name_plural = "Профили пользователей"
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['gender', 'city']),
        ]

    def __str__(self):
        return f'Профиль пользователя {self.user.username}'

    def clean(self):
        """Валидация модели"""
        super().clean()

        # Проверка даты рождения
        if self.date_of_birth:
            age = self.age
            if age is not None:
                if age < 18:
                    raise ValidationError({'date_of_birth': 'Минимальный возраст 18 лет'})
                if age > 100:
                    raise ValidationError({'date_of_birth': 'Проверьте правильность даты рождения'})

    def is_online(self):
        """Проверяет, был ли пользователь онлайн в последние 5 минут"""
        if self.last_seen:
            return (timezone.now() - self.last_seen) < timezone.timedelta(minutes=5)
        return False

    @property
    def age(self):
        """Вычисляет возраст пользователя"""
        if self.date_of_birth:
            today = date.today()
            return today.year - self.date_of_birth.year - (
                (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
            )
        return None

    def is_profile_complete(self):
        """Проверяет заполненность профиля"""
        required_fields = [
            self.date_of_birth,
            self.gender,
            self.city,
            self.about_me,
        ]
        return all(required_fields)
# ==============================================================================
# СИМПАТИИ
# ==============================================================================
class Like(models.Model):
    """Модель для хранения симпатий между пользователями"""

    user_from = models.ForeignKey(
        User,
        related_name='likes_sent',
        on_delete=models.CASCADE,
        verbose_name="От кого"
    )
    user_to = models.ForeignKey(
        User,
        related_name='likes_received',
        on_delete=models.CASCADE,
        verbose_name="Кому"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )

    class Meta:
        verbose_name = "Симпатия"
        verbose_name_plural = "Симпатии"
        constraints = [
            models.UniqueConstraint(
                fields=['user_from', 'user_to'],
                name='unique_like'
            ),
            models.CheckConstraint(
                check=~models.Q(user_from=models.F('user_to')),
                name='cannot_like_yourself'
            )
        ]
        indexes = [
            models.Index(fields=['user_from', 'user_to']),
            models.Index(fields=['user_to', 'created_at']),
        ]

    def __str__(self):
        return f'Симпатия от {self.user_from} к {self.user_to}'

    def clean(self):
        """Валидация: нельзя лайкать самого себя"""
        if self.user_from == self.user_to:
            raise ValidationError('Нельзя отправить симпатию самому себе')
# ==============================================================================
# СООБЩЕНИЯ
# ==============================================================================
class Message(models.Model):
    """Модель для личных сообщений между пользователями"""

    sender = models.ForeignKey(
        User,
        related_name='sent_messages',
        on_delete=models.CASCADE,
        verbose_name="Отправитель"
    )
    receiver = models.ForeignKey(
        User,
        related_name='received_messages',
        on_delete=models.CASCADE,
        verbose_name="Получатель"
    )
    content = models.TextField(
        verbose_name="Содержание",
        max_length=2000,
        blank=False,
        help_text="Максимум 2000 символов"
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Время отправки"
    )
    is_read = models.BooleanField(
        default=False,
        verbose_name="Прочитано",
        db_index=True
    )
    is_deleted_by_sender = models.BooleanField(
        default=False,
        verbose_name="Удалено отправителем"
    )
    is_deleted_by_receiver = models.BooleanField(
        default=False,
        verbose_name="Удалено получателем"
    )

    class Meta:
        ordering = ['timestamp']
        verbose_name = "Сообщение"
        verbose_name_plural = "Сообщения"
        indexes = [
            models.Index(fields=['sender', 'receiver', 'timestamp']),
            models.Index(fields=['receiver', 'is_read']),
        ]

    def __str__(self):
        sender = getattr(self.sender, 'username', 'Без отправителя')
        receiver = getattr(self.receiver, 'username', 'Без получателя')
        return f'Сообщение от {sender} к {receiver}'

    def clean(self):
        """Валидация сообщения"""
        errors = {}
        
        if self.sender and self.receiver and self.sender == self.receiver:
            errors['receiver'] = 'Нельзя отправить сообщение самому себе'
            
        if not self.content or not self.content.strip():
            errors['content'] = 'Сообщение не может быть пустым'
            
        if errors:
            raise ValidationError(errors)
# ==============================================================================
# ФОТОГРАФИИ
# ==============================================================================
class Photo(models.Model):
    """Дополнительные фотографии пользователя"""

    user_profile = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='photos',
        verbose_name="Профиль пользователя"
    )
    image = models.ImageField(
        upload_to='photos/%Y/%m/%d/',
        verbose_name="Фото"
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата загрузки"
    )
    image_hash = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        db_index=True,
        verbose_name="Хеш изображения",
        help_text="Perceptual hash для проверки на дубликаты"
    )

    class Meta:
        verbose_name = "Фотография"
        verbose_name_plural = "Фотографии"
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'Фото пользователя {self.user_profile.user.username}'
# ==============================================================================
# УВЕДОМЛЕНИЯ
# ==============================================================================
class Notification(models.Model):
    """Уведомления для пользователей"""

    NOTIFICATION_TYPES = [
        ('LIKE', 'Новая симпатия'),
        ('MESSAGE', 'Новое сообщение'),
        ('COMPLAINT_STATUS', 'Статус жалобы'),
        ('ADMIN', 'От администрации'),
        ('SYSTEM', 'Системное'),
    ]

    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name="Получатель"
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sent_notifications',
        verbose_name="Отправитель",
        null=True,
        blank=True
    )
    message = models.TextField(
        verbose_name="Сообщение",
        max_length=500
    )
    notification_type = models.CharField(
        max_length=20,
        choices=NOTIFICATION_TYPES,
        verbose_name="Тип уведомления",
        db_index=True
    )
    is_read = models.BooleanField(
        default=False,
        verbose_name="Прочитано",
        db_index=True
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name="Тип связанного объекта"
    )
    object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="ID связанного объекта"
    )
    target = GenericForeignKey('content_type', 'object_id')   

    class Meta:
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read', '-created_at']),
        ]

    def __str__(self):
        return f'Уведомление для {self.recipient.username} - {self.notification_type}'

    def get_sender_photo(self):
        """Получить URL фото отправителя с правильным fallback"""
        if self.sender:
            try:
                if hasattr(self.sender, 'userprofile') and self.sender.userprofile:
                    if self.sender.userprofile.photo:
                        if 'default-avatar' not in str(self.sender.userprofile.photo):
                            return self.sender.userprofile.photo.url
            except Exception:
                pass
        
        return '/static/img/default-avatar.png'
    
    def get_sender_name(self):
        """Получить имя отправителя"""
        if self.sender:
            full_name = f"{self.sender.first_name} {self.sender.last_name}".strip()
            return full_name or self.sender.username
            
        if self.notification_type == 'COMPLAINT_STATUS':
            return 'Администрация'
        elif self.notification_type == 'ADMIN':
            return 'Администрация сайта'
        elif self.notification_type == 'SYSTEM':
            return 'Система'
        
        return 'Уведомление'
    
    def has_sender_profile(self):
        """Проверка наличия профиля у отправителя"""
        if not self.sender:
            return False
        return hasattr(self.sender, 'userprofile') and self.sender.userprofile is not None

    @property
    def link(self):
        """Возвращает ссылку для перехода из уведомления"""
        if self.notification_type == 'LIKE' and self.sender:
            return reverse('profiles:profile_detail', kwargs={'pk': self.sender.pk})
        elif self.notification_type == 'MESSAGE' and self.sender:
            return reverse('profiles:conversation_detail', kwargs={'pk': self.sender.pk})
        return '#'
# ==============================================================================
# БЛОГ
# ==============================================================================
class Post(models.Model):
    """Статьи блога"""

    STATUS_CHOICES = [
        ('draft', 'Черновик'),
        ('published', 'Опубликовано'),
    ]

    title = models.CharField(
        max_length=200,
        verbose_name="Заголовок"
    )
    slug = models.SlugField(
        max_length=200,
        unique=True,
        verbose_name="URL",
        help_text="Автоматически генерируется из заголовка"
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='blog_posts',
        verbose_name="Автор"
    )
    content = models.TextField(
        verbose_name="Содержание"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name="Статус",
        db_index=True
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Статья"
        verbose_name_plural = "Статьи"
        indexes = [
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        """Возвращает канонический URL для статьи"""
        return reverse('profiles:post_detail', args=[self.slug])

    def save(self, *args, **kwargs):
        """При сохранении автоматически создает slug из заголовка"""
        if not self.slug:
            try:
                self.slug = pytils_slugify(self.title)
            except Exception:
                self.slug = slugify(self.title)
        super().save(*args, **kwargs)
# ==============================================================================
# КОММЕНТАРИИ
# ==============================================================================
class Comment(models.Model):
    """Комментарии к статьям"""

    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='comments',
        verbose_name="Статья"
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='post_comments',
        verbose_name="Автор"
    )
    body = models.TextField(
        verbose_name="Текст комментария",
        max_length=1000,
        help_text="Максимум 1000 символов"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )
    active = models.BooleanField(
        default=False,
        verbose_name="Одобрен",
        db_index=True
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies',
        verbose_name="Родительский комментарий"
    )
    likes = models.ManyToManyField(
        User,
        related_name='comment_likes',
        blank=True,
        verbose_name="Лайки"
    )
    dislikes = models.ManyToManyField(
        User,
        related_name='comment_dislikes',
        blank=True,
        verbose_name="Дизлайки"
    )

    class Meta:
        ordering = ['created_at']
        verbose_name = "Комментарий"
        verbose_name_plural = "Комментарии"
        indexes = [
            models.Index(fields=['post', 'active', 'created_at']),
            models.Index(fields=['parent', 'active']),
        ]

    def __str__(self):
        return f"Комментарий от {self.author} к статье '{self.post}'"

    def total_likes(self):
        """Количество лайков"""
        return self.likes.count()

    def total_dislikes(self):
        """Количество дизлайков"""
        return self.dislikes.count()

    @property
    def visible_replies(self):
        """Возвращает только активные ответы"""
        return self.replies.filter(active=True).exclude(author__is_superuser=True)
# ==============================================================================
# ЖАЛОБЫ
# ==============================================================================
class Complaint(models.Model):
    """Жалобы пользователей друг на друга"""
    
    STATUS_NEW = 'new'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_RESOLVED = 'resolved'

    REASON_CHOICES = [
        ('spam', 'Спам или реклама'),
        ('inappropriate_content', 'Неприемлемый контент (фото, текст)'),
        ('scam', 'Мошенничество или обман'),
        ('insult', 'Оскорбления или грубое поведение'),
        ('other', 'Другое'),
    ]

    STATUS_CHOICES = [
        (STATUS_NEW, 'Взята на рассмотрение'),
        (STATUS_IN_PROGRESS, 'Рассматривается'),
        (STATUS_RESOLVED, 'Разрешённый конфликт (Отдельно вы получите сообщение-отчет о жалобе)'),
    ]

    reporter = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='filed_complaints',
        verbose_name="Подавший жалобу"
    )
    reported_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='complaints_against',
        verbose_name="Пользователь, на которого жалуются"
    )
    reason = models.CharField(
        max_length=50,
        choices=REASON_CHOICES,
        verbose_name="Причина"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Подробное описание",
        max_length=1000
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата подачи"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_NEW,
        verbose_name="Статус",
        db_index=True
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Жалоба"
        verbose_name_plural = "Жалобы"
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['reported_user', 'status']),
        ]

    def __str__(self):
        reporter_name = self.reporter.username if self.reporter else 'Удалённый пользователь'
        return f"Жалоба от {reporter_name} на {self.reported_user} (Статус: {self.get_status_display()})"


class ComplaintLog(models.Model):
    """Лог изменений статусов жалоб"""
    
    complaint = models.ForeignKey(
        Complaint,
        on_delete=models.CASCADE,
        related_name='logs',
        verbose_name="Жалоба"
    )
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="Кто изменил"
    )
    old_status = models.CharField(
        max_length=20,
        verbose_name="Старый статус"
    )
    new_status = models.CharField(
        max_length=20,
        verbose_name="Новый статус"
    )
    changed_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата изменения"
    )
    comment = models.TextField(
        blank=True,
        verbose_name="Комментарий"
    )

    class Meta:
        ordering = ['-changed_at']
        verbose_name = "Лог жалобы"
        verbose_name_plural = "Логи жалоб"

    def __str__(self):
        changer = self.changed_by.username if self.changed_by else 'Система'
        return f"{changer} изменил статус {self.old_status} → {self.new_status}"
# ==============================================================================
# СТАТИЧЕСКИЕ СТРАНИЦЫ
# ==============================================================================
class StaticPage(models.Model):
    """Статические страницы сайта"""

    title = models.CharField(
        max_length=200,
        verbose_name="Заголовок"
    )
    slug = models.SlugField(
        max_length=200,
        unique=True,
        verbose_name="URL",
        help_text="Короткое имя для URL (например, 'rules')"
    )
    content = models.TextField(
        verbose_name="Содержание",
        help_text="Используйте HTML-теги для форматирования."
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )

    class Meta:
        verbose_name = "Статическая страница"
        verbose_name_plural = "Статические страницы"
        ordering = ['title']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        """Возвращает URL для страницы"""
        return reverse('profiles:static_page', args=[self.slug])
# ==============================================================================
# MОДЕЛИ ДЛЯ СТАТИСТИКИ
# ==============================================================================
class UserSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    login_time = models.DateTimeField(auto_now_add=True)
    logout_time = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    profiles_viewed = models.IntegerField(default=0)
    likes_given = models.IntegerField(default=0)
    messages_sent = models.IntegerField(default=0)
    messages_received = models.IntegerField(default=0)
    session_key = models.CharField(max_length=100, blank=True)
    duration_minutes = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-login_time']
        verbose_name = 'Сеанс пользователя'
        verbose_name_plural = 'Сеансы пользователей'

    def __str__(self):
        return f"{self.user.username} — {self.login_time.strftime('%d.%m.%Y %H:%M')}"

    def calculate_duration(self):
        if self.logout_time:
            delta = self.logout_time - self.login_time
            self.duration_minutes = int(delta.total_seconds() / 60)
            return self.duration_minutes
        return 0

    def get_duration_display(self):
        if not self.duration_minutes:
            return "—"
        hours = self.duration_minutes // 60
        minutes = self.duration_minutes % 60
        return f"{hours}ч {minutes}мин" if hours else f"{minutes}мин"


class UserActivity(models.Model):
    ACTION_CHOICES = [
        ('view_profile', 'Просмотр профиля'),
        ('like', 'Лайк'),
        ('message', 'Сообщение'),
        ('search', 'Поиск'),
        ('edit_profile', 'Редактирование профиля'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    session = models.ForeignKey(UserSession, on_delete=models.CASCADE, related_name='activities', null=True)
    action_type = models.CharField(max_length=50, choices=ACTION_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)
    target_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='received_activities')

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Активность пользователя'
        verbose_name_plural = 'Активности пользователей'

class ViewedProfile(models.Model):
    session = models.ForeignKey(UserSession, on_delete=models.CASCADE)
    profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)

class SessionLog(models.Model):
    """Лог завершения пользовательских сессий"""

    STATUS_CHOICES = [
        ('completed', 'Завершена'),
        ('no_active_session', 'Нет активной сессии'),
        ('error', 'Ошибка'),
    ]

    ACTION_CHOICES = [
        ('logout', 'Выход'),
        ('timeout', 'Таймаут'),
        ('manual', 'Ручное завершение'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name="Пользователь"
    )
    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
        default='logout',
        verbose_name="Действие"
    )
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default='completed',
        verbose_name="Статус"
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Время события"
    )
    session_key = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Ключ сессии"
    )
    duration = models.DurationField(
        blank=True,
        null=True,
        verbose_name="Длительность"
    )
    extra_info = models.TextField(
        blank=True,
        null=True,
        verbose_name="Доп. информация"
    )

    class Meta:
        verbose_name = "Лог сессии"
        verbose_name_plural = "Логи сессий"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'status', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.user.username} | {self.action} | {self.status} | {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"

#==========================================================================
#  Проверка пользователя для чат-Групы
#==========================================================================
class TelegramUser(models.Model):
    telegram_id = models.BigIntegerField(
        unique=True,
        verbose_name="ID Telegram",
        db_index=True
    )
    username = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Username"
    )
    first_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Имя"
    )
    email = models.EmailField(
        unique=True,
        verbose_name="Email"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата регистрации"
    )

    class Meta:
        verbose_name = "Пользователь Telegram"
        verbose_name_plural = "Пользователи Telegram"

    def __str__(self):
        return f"{self.email} ({self.telegram_id})"


