# -*- coding: utf-8 -*-
import logging
from django.contrib import admin, messages as django_messages
from django.urls import reverse
from django.utils.html import format_html
from django.db.models import Exists, OuterRef, Q, Count
from django.db import transaction

from profiles.services.photo_verification import PhotoVerificationService, calculate_photo_hash, verify_photo_originality
from .models import (
    Comment, Complaint, Post, StaticPage, TelegramUser, UserProfile,
    Photo, Like, Message, Notification, UserSession, UserActivity, ComplaintLog
)
logger = logging.getLogger(__name__)

# ==============================================================================
# БАЗОВЫЕ МИКСИНЫ ДЛЯ ПЕРЕИСПОЛЬЗОВАНИЯ
# ==============================================================================

class ReadOnlyTimestampsMixin:
    """Миксин для readonly полей с датами"""
    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj:
            timestamp_fields = ['created_at', 'updated_at', 'timestamp']
            for field in timestamp_fields:
                if hasattr(obj, field) and field not in readonly:
                    readonly.append(field)
        return readonly


class ShortTextDisplayMixin:
    """Миксин для сокращения длинных текстов"""
    @staticmethod
    def truncate_text(text, max_length=50):
        if not text:
            return "-"
        return text[:max_length] + '...' if len(text) > max_length else text

# ==============================================================================
# ИНЛАЙНЫ
# ==============================================================================
class PhotoInline(admin.TabularInline):
    model = Photo
    extra = 1
    readonly_fields = ('uploaded_at', 'preview', 'hash_status')
    fields = ('image', 'preview', 'image_hash', 'hash_status', 'uploaded_at')
    can_delete = True

    def preview(self, obj):
        """Безопасное отображение превью с обработкой ошибок"""
        if not obj.pk or not obj.image:
            return "-"
        if not hasattr(obj.image, 'url'):
            return format_html('<span style="color: red;">❌ Файл не найден</span>')
        try:
            return format_html(
                '<img src="{}" style="max-height: 100px; border-radius: 4px;" alt="Фото" />',
                obj.image.url
            )
        except Exception as e:
            return format_html('<span style="color: red;">❌ Ошибка: {}</span>', str(e)[:50])
    preview.short_description = "Превью"

    def hash_status(self, obj):
        """Показать статус хеша"""
        if obj.image_hash:
            return format_html('<span style="color: green;">✅</span>')
        return format_html('<span style="color: red;">❌</span>')
    hash_status.short_description = "Хеш"

# ==============================================================================
# ADMIN ДЛЯ PHOTO
# ==============================================================================
@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ('id', 'photo_preview', 'user_link', 'uploaded_at', 'hash_display', 'duplicate_check')
    list_filter = ('uploaded_at',)
    search_fields = ('user_profile__user__username', 'user_profile__user__email')
    readonly_fields = ('uploaded_at', 'photo_large', 'image_hash', 'duplicates_info')

    actions = ['verify_photos', 'calculate_hashes', 'delete_duplicates']

    fieldsets = (
        ('📸 Фотография', {
            'fields': ('user_profile', 'image', 'photo_large')
        }),
        ('🔍 Проверка на дубликаты', {
            'fields': ('image_hash', 'duplicates_info'),
            'classes': ('collapse',)
        }),
        ('📅 Информация', {
            'fields': ('uploaded_at',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user_profile__user')

    @admin.display(description='Превью')
    def photo_preview(self, obj):
        if obj.image:
            try:
                return format_html(
                    '<img src="{}" width="50" height="50" style="object-fit: cover; border-radius: 4px;" />',
                    obj.image.url
                )
            except Exception:
                return '❌'
        return '❌'

    @admin.display(description='Пользователь')
    def user_link(self, obj):
        if obj.user_profile and obj.user_profile.user:
            return format_html(
                '<a href="/admin/auth/user/{}/change/">👤 {}</a>',
                obj.user_profile.user.id,
                obj.user_profile.user.username
            )
        return '❓'

    @admin.display(description='Хеш')
    def hash_display(self, obj):
        if obj.image_hash:
            return format_html(
                '<span style="color: green;">✅ {}</span>',
                obj.image_hash[:8] + '...'
            )
        return format_html('<span style="color: red;">❌ Нет</span>')

    @admin.display(description='Дубликаты')
    def duplicate_check(self, obj):
        if not obj.image_hash:
            return format_html('<span style="color: gray;">⚠️ Нет хеша</span>')

        try:
            similar = PhotoVerificationService.find_similar_photos(
                photo_hash=obj.image_hash,
                user_profile=obj.user_profile,
                exclude_photo_id=obj.id
            )

            if similar:
                return format_html(
                    '<span style="color: red; font-weight: bold;">❌ {}</span>',
                    len(similar)
                )
            return format_html('<span style="color: green;">✅ OK</span>')
        except Exception:
            return format_html('<span style="color: orange;">⚠️</span>')

    def photo_large(self, obj):
        """Большое превью"""
        if obj.image:
            try:
                return format_html(
                    '<img src="{}" style="max-width: 400px; border-radius: 8px;" />',
                    obj.image.url
                )
            except Exception:
                return '❌'
        return '❌'
    photo_large.short_description = 'Превью'

    def duplicates_info(self, obj):
        """Информация о дубликатах"""
        if not obj.image_hash:
            return '⚠️ Хеш не вычислен'

        try:
            similar = PhotoVerificationService.find_similar_photos(
                photo_hash=obj.image_hash,
                user_profile=obj.user_profile,
                exclude_photo_id=obj.id
            )

            if not similar:
                return format_html('<p style="color: green;">✅ Дубликатов нет</p>')

            html = f'<p style="color: red;">❌ Найдено дубликатов: {len(similar)}</p><ul>'
            for photo, score in similar[:5]:
                html += f'<li><a href="/admin/profiles/photo/{photo.id}/change/" target="_blank">Фото #{photo.id}</a> (похожесть: {score}/20, загружено {photo.uploaded_at.strftime("%d.%m.%Y")})</li>'
            html += '</ul>'
            return format_html(html)
        except Exception as e:
            return format_html(f'<p style="color: red;">Ошибка: {e}</p>')
    duplicates_info.short_description = 'Дубликаты'

    # ✅ ИСПРАВЛЕННЫЕ ДЕЙСТВИЯ (работают с облачными хранилищами)
    
    @admin.action(description='🔍 Проверить на дубликаты')
    def verify_photos(self, request, queryset):
        """
        Проверяет фото на дубликаты
        ✅ Работает с локальным и облачным хранилищем
        """
        checked = 0
        duplicates = 0
        errors = 0

        for photo in queryset.select_related('user_profile'):
            try:
                if not photo.image:
                    continue

                # ✅ ИСПРАВЛЕНО: читаем файл через storage API
                try:
                    with photo.image.open('rb') as image_file:
                        image_data = image_file.read()
                except Exception as e:
                    logger.error(f"Ошибка чтения файла для фото #{photo.id}: {e}")
                    errors += 1
                    continue

                # Проверяем оригинальность
                is_original, photo_hash, similar = verify_photo_originality(
                    image_input=image_data,  # ✅ Передаем bytes вместо пути
                    user_profile=photo.user_profile,
                    exclude_photo_id=photo.id
                )

                # Сохраняем хеш если его не было
                if not photo.image_hash:
                    photo.image_hash = photo_hash
                    photo.save(update_fields=['image_hash'])

                checked += 1
                if not is_original:
                    duplicates += 1
                    
            except Exception as e:
                logger.error(f"Ошибка проверки фото #{photo.id}: {e}")
                errors += 1

        message = f'✅ Проверено: {checked} | ❌ С дубликатами: {duplicates}'
        if errors > 0:
            message += f' | ⚠️ Ошибок: {errors}'
            
        self.message_user(
            request,
            message,
            django_messages.SUCCESS if errors == 0 else django_messages.WARNING
        )

    @admin.action(description='🔢 Вычислить хеши')
    def calculate_hashes(self, request, queryset):
        """
        Вычисляет хеши для фото
        ✅ Работает с локальным и облачным хранилищем
        """
        calculated = 0
        errors = 0
        
        for photo in queryset.filter(image_hash__isnull=True):
            try:
                if not photo.image:
                    continue
                
                # ✅ ИСПРАВЛЕНО: читаем файл через storage API
                try:
                    with photo.image.open('rb') as image_file:
                        image_data = image_file.read()
                except Exception as e:
                    logger.error(f"Ошибка чтения файла для фото #{photo.id}: {e}")
                    errors += 1
                    continue
                
                # Вычисляем хеш
                photo_hash = calculate_photo_hash(image_data)  # ✅ Передаем bytes
                photo.image_hash = photo_hash
                photo.save(update_fields=['image_hash'])
                calculated += 1
                
            except Exception as e:
                logger.error(f"Ошибка вычисления хеша для фото #{photo.id}: {e}")
                errors += 1

        message = f'✅ Вычислено хешей: {calculated}'
        if errors > 0:
            message += f' | ⚠️ Ошибок: {errors}'
            
        self.message_user(
            request,
            message,
            django_messages.SUCCESS if errors == 0 else django_messages.WARNING
        )

    @admin.action(description='🗑️ УДАЛИТЬ дубликаты')
    def delete_duplicates(self, request, queryset):
        """
        Удаляет дубликаты фото (оставляет самое старое)
        """
        if not request.user.is_superuser:
            self.message_user(
                request, 
                '⛔ Только суперпользователь может удалять дубликаты', 
                django_messages.ERROR
            )
            return

        deleted = 0
        hash_groups = {}

        # Группируем по хешам
        for photo in queryset.select_related('user_profile'):
            if photo.image_hash:
                if photo.image_hash not in hash_groups:
                    hash_groups[photo.image_hash] = []
                hash_groups[photo.image_hash].append(photo)

        # Удаляем дубликаты в транзакции
        try:
            with transaction.atomic():
                for photos in hash_groups.values():
                    if len(photos) > 1:
                        # Сортируем по дате (оставляем самое старое)
                        photos.sort(key=lambda p: p.uploaded_at)
                        # Удаляем все кроме первого
                        photo_ids = [p.id for p in photos[1:]]
                        Photo.objects.filter(id__in=photo_ids).delete()
                        deleted += len(photo_ids)

            self.message_user(
                request,
                f'✅ Удалено дубликатов: {deleted}',
                django_messages.SUCCESS if deleted > 0 else django_messages.INFO
            )
        except Exception as e:
            logger.error(f"Ошибка при удалении дубликатов: {e}")
            self.message_user(
                request,
                f'❌ Ошибка при удалении: {str(e)}',
                django_messages.ERROR
            )
# ==============================================================================
# ДЕЙСТВИЯ
# ==============================================================================
@admin.action(description='✅ Верифицировать выбранные анкеты')
def make_verified(modeladmin, request, queryset):
    """Массовая верификация с подтверждением"""
    if not request.user.is_superuser:
        modeladmin.message_user(
            request,
            'Только суперпользователи могут верифицировать анкеты',
            django_messages.ERROR
        )
        return

    updated = queryset.filter(is_verified=False).update(is_verified=True)
    if updated:
        modeladmin.message_user(
            request,
            f'Верифицировано анкет: {updated}',
            django_messages.SUCCESS
        )
    else:
        modeladmin.message_user(
            request,
            'Все выбранные анкеты уже верифицированы',
            django_messages.INFO
        )
# ==============================================================================
# АДМИНКИ МОДЕЛЕЙ
# ==============================================================================
@admin.register(UserProfile)
class UserProfileAdmin(ReadOnlyTimestampsMixin, admin.ModelAdmin):
    list_display = ('user', 'get_full_name', 'city', 'gender', 'age', 'is_verified', 'photo_count', 'created_at')
    list_display_links = ('user',)
    list_filter = ('is_verified', 'gender', 'city', 'churching_level', 'created_at')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'city', 'about_me')
    actions = [make_verified]
    inlines = [PhotoInline]
    save_on_top = True
    date_hierarchy = 'created_at'
    list_per_page = 50

    fieldsets = (
        ('👤 Пользователь', {'fields': ('user', 'is_verified', 'last_seen')}),
        ('📋 Основная информация', {
            'fields': ('patronymic', 'date_of_birth', 'gender', 'city', 'photo', 'about_me', 'height')
        }),
        ('💍 Семейное положение', {
            'fields': ('marital_status', 'children', 'education', 'occupation')
        }),
        ('⛪ Духовная жизнь', {
            'fields': ('churching_level', 'attitude_to_fasting', 'sacraments', 'favorite_saints', 'spiritual_books')
        }),
        ('📅 Даты', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('user').annotate(photos_count=Count('photos', distinct=True))

    @admin.display(description='Полное имя', ordering='user__first_name')
    def get_full_name(self, obj):
        if obj.user.first_name and obj.user.last_name:
            return f"{obj.user.first_name} {obj.user.last_name}"
        return obj.user.username

    @admin.display(description='Фото', ordering='photos_count')
    def photo_count(self, obj):
        count = getattr(obj, 'photos_count', 0)
        if count > 0:
            return format_html('<span style="color: #28a745;">📷 {}</span>', count)
        return format_html('<span style="color: #6c757d;">-</span>')

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

@admin.register(Post)
class PostAdmin(ReadOnlyTimestampsMixin, admin.ModelAdmin):
    list_display = ('title', 'author', 'status', 'created_at')
    list_display_links = ('title',)
    list_filter = ('status', 'created_at')
    search_fields = ('title', 'content', 'author__username')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'
    save_on_top = True

    fieldsets = (
        ('📝 Содержание', {'fields': ('title', 'slug', 'content', 'author', 'status')}),
        ('📅 Даты (только для просмотра)', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('author').annotate(
            active_comments_count=Count('comments', filter=Q(comments__active=True), distinct=True)
        )

    @admin.display(description='Комментарии', ordering='active_comments_count')
    def comment_count(self, obj):
        count = getattr(obj, 'active_comments_count', 0)
        if count > 0:
            return format_html('<span style="color: #007bff;">💬 {}</span>', count)
        return format_html('<span style="color: #6c757d;">-</span>')


@admin.register(Comment)
class CommentAdmin(ReadOnlyTimestampsMixin, ShortTextDisplayMixin, admin.ModelAdmin):
    list_display = ('get_author_name', 'get_short_body', 'post', 'active', 'is_reply', 'created_at')
    list_display_links = ('get_short_body',)
    list_filter = ('active', 'created_at')
    search_fields = ('author__username', 'body', 'post__title')
    actions = ['approve_comments', 'reject_comments']
    date_hierarchy = 'created_at'
    save_on_top = True
    list_per_page = 100

    fieldsets = (
        ('💬 Комментарий', {'fields': ('author', 'post', 'body', 'parent')}),
        ('⚙️ Модерация', {'fields': ('active',)}),
        ('📅 Даты', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('author', 'post', 'parent').prefetch_related('likes', 'dislikes')

    @admin.display(description='Автор', ordering='author__username')
    def get_author_name(self, obj):
        return obj.author.username if obj.author else '👤 Аноним'

    @admin.display(description='Текст')
    def get_short_body(self, obj):
        return self.truncate_text(obj.body, 60)

    @admin.display(description='Ответ?', boolean=True)
    def is_reply(self, obj):
        return bool(obj.parent)

    @admin.action(description='✅ Одобрить комментарии')
    def approve_comments(self, request, queryset):
        updated = queryset.filter(active=False).update(active=True)
        msg = f'Одобрено комментариев: {updated}' if updated else 'Нет комментариев для одобрения'
        level = django_messages.SUCCESS if updated else django_messages.INFO
        self.message_user(request, msg, level)

    @admin.action(description='❌ Отклонить комментарии')
    def reject_comments(self, request, queryset):
        updated = queryset.filter(active=True).update(active=False)
        msg = f'Отклонено комментариев: {updated}' if updated else 'Нет комментариев для отклонения'
        level = django_messages.WARNING if updated else django_messages.INFO
        self.message_user(request, msg, level)


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ('get_reporter', 'get_reported', 'reason', 'status_colored', 'created_at')
    list_filter = ('status', 'reason', 'created_at')
    search_fields = ('reporter__username', 'reported_user__username', 'description')

    # ✅ УБРАЛИ list_editable - теперь изменяем только через форму редактирования
    # list_editable = ('status',)  # <-- ЭТО ВЫЗЫВАЛО ДВОЙНОЕ СРАБАТЫВАНИЕ

    actions = ['mark_as_resolved', 'mark_as_in_progress', 'mark_as_new']
    date_hierarchy = 'created_at'
    save_on_top = True
    list_per_page = 50

    fieldsets = (
        ('🚨 Информация о жалобе', {
            'fields': ('reporter', 'reported_user', 'reason', 'description')
        }),
        ('⚙️ Статус и модерация', {
            'fields': ('status',),
            'description': 'Измените статус и нажмите "Сохранить" - пользователь автоматически получит уведомление через сигнал'
        }),
        ('📅 Системная информация', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('reporter', 'reported_user')

    @admin.display(description='От кого', ordering='reporter__username')
    def get_reporter(self, obj):
        if obj.reporter:
            return format_html(
                '<a href="/admin/auth/user/{}/change/" style="color: #007bff;">👤 {}</a>',
                obj.reporter.id,
                obj.reporter.username
            )
        return '❓ Удален'

    @admin.display(description='На кого', ordering='reported_user__username')
    def get_reported(self, obj):
        if obj.reported_user:
            return format_html(
                '<a href="/admin/auth/user/{}/change/" style="color: #dc3545;">🎯 {}</a>',
                obj.reported_user.id,
                obj.reported_user.username
            )
        return '❓ Удален'

    @admin.display(description='Статус', ordering='status')
    def status_colored(self, obj):
        """Цветное отображение статуса"""
        colors = {
            'new': '#ffc107',
            'in_progress': '#17a2b8',
            'resolved': '#28a745',
        }

        icons = {
            'new': '🆕',
            'in_progress': '⏳',
            'resolved': '✅',
        }

        color = colors.get(obj.status, '#6c757d')
        icon = icons.get(obj.status, '❓')

        return format_html(
            '<span style="background: {}; color: white; padding: 4px 12px; border-radius: 12px; font-weight: bold; white-space: nowrap;">{} {}</span>',
            color,
            icon,
            obj.get_status_display()
        )

    # ✅ УБРАЛИ ВСЮ ЛОГИКУ ОТПРАВКИ УВЕДОМЛЕНИЙ
    # Теперь уведомления отправляются ТОЛЬКО через сигнал в final_complaint_signal.py

    def save_model(self, request, obj, form, change):
        """Простое сохранение БЕЗ отправки уведомлений"""
        # Сохраняем старый статус для логирования
        old_status = None
        if change and obj.pk:
            try:
                old_complaint = Complaint.objects.get(pk=obj.pk)
                old_status = old_complaint.status
            except Complaint.DoesNotExist:
                pass

        # Сохраняем (сигнал сам отправит уведомление)
        super().save_model(request, obj, form, change)

        # Только логируем изменение
        if change and old_status and old_status != obj.status:
            try:
                ComplaintLog.objects.create(
                    complaint=obj,
                    changed_by=request.user,
                    old_status=old_status,
                    new_status=obj.status,
                    comment=f'Статус изменен через админ-панель: {old_status} → {obj.status}'
                )

                # Информируем админа что уведомление будет отправлено сигналом
                self.message_user(
                    request,
                    format_html(
                        '✅ Статус изменён. Уведомление автоматически отправлено пользователю <strong>{}</strong>',
                        obj.reporter.username if obj.reporter else 'Удалён'
                    ),
                    django_messages.SUCCESS
                )
            except Exception as e:
                print(f"Ошибка логирования: {e}")

    # ✅ МАССОВЫЕ ДЕЙСТВИЯ - тоже БЕЗ отправки (отправит сигнал)

    @admin.action(description='✅ Отметить "Разрешён" (resolved)')
    def mark_as_resolved(self, request, queryset):
        """Массово отметить жалобы как решенные"""
        count = 0
        for complaint in queryset.exclude(status=Complaint.STATUS_RESOLVED):
            old_status = complaint.status
            complaint.status = Complaint.STATUS_RESOLVED
            complaint.save()  # Сигнал сам отправит уведомление

            # Только логируем
            try:
                ComplaintLog.objects.create(
                    complaint=complaint,
                    changed_by=request.user,
                    old_status=old_status,
                    new_status=Complaint.STATUS_RESOLVED,
                    comment='Массовое изменение через действие админки'
                )
            except:
                pass

            count += 1

        if count > 0:
            self.message_user(
                request,
                f'✅ Отмечено как "Решена": {count} жалоб. Уведомления отправлены автоматически.',
                django_messages.SUCCESS
            )

    @admin.action(description='⏳ Отметить "В работе" (in_progress)')
    def mark_as_in_progress(self, request, queryset):
        """Массово отметить жалобы как в работе"""
        count = 0
        for complaint in queryset.exclude(status=Complaint.STATUS_IN_PROGRESS):
            old_status = complaint.status
            complaint.status = Complaint.STATUS_IN_PROGRESS
            complaint.save()

            try:
                ComplaintLog.objects.create(
                    complaint=complaint,
                    changed_by=request.user,
                    old_status=old_status,
                    new_status=Complaint.STATUS_IN_PROGRESS,
                    comment='Массовое изменение через действие админки'
                )
            except:
                pass

            count += 1

        if count > 0:
            self.message_user(
                request,
                f'⏳ Отмечено как "В работе": {count} жалоб. Уведомления отправлены автоматически.',
                django_messages.INFO
            )

    @admin.action(description='🔄 Вернуть в "Новая" (new)')
    def mark_as_new(self, request, queryset):
        """Массово вернуть жалобы в статус новых"""
        count = 0
        for complaint in queryset.exclude(status=Complaint.STATUS_NEW):
            old_status = complaint.status
            complaint.status = Complaint.STATUS_NEW
            complaint.save()

            try:
                ComplaintLog.objects.create(
                    complaint=complaint,
                    changed_by=request.user,
                    old_status=old_status,
                    new_status=Complaint.STATUS_NEW,
                    comment='Массовое изменение через действие админки'
                )
            except:
                pass

            count += 1

        if count > 0:
            self.message_user(
                request,
                f'🔄 Возвращено в "Новые": {count} жалоб. Уведомления отправлены автоматически.',
                django_messages.INFO
            )

    def has_delete_permission(self, request, obj=None):
        """Только суперюзер может удалять жалобы"""
        return request.user.is_superuser

    def has_add_permission(self, request):
        """Запретить создание жалоб через админку"""
        return False


@admin.register(ComplaintLog)
class ComplaintLogAdmin(admin.ModelAdmin):
    list_display = ('complaint', 'changed_by', 'old_status', 'new_status', 'changed_at')
    list_filter = ('old_status', 'new_status', 'changed_by', 'changed_at')
    search_fields = ('complaint__description', 'changed_by__username', 'comment')
    date_hierarchy = 'changed_at'
    readonly_fields = ('complaint', 'changed_by', 'old_status', 'new_status', 'changed_at', 'comment')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(StaticPage)
class StaticPageAdmin(ReadOnlyTimestampsMixin, admin.ModelAdmin):
    list_display = ('title', 'slug', 'updated_at')
    search_fields = ('title', 'content')
    prepopulated_fields = {'slug': ('title',)}
    save_on_top = True


@admin.register(Like)
class LikeAdmin(ReadOnlyTimestampsMixin, admin.ModelAdmin):
    list_display = ('user_from', 'user_to', 'is_mutual', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user_from__username', 'user_to__username')
    date_hierarchy = 'created_at'
    save_on_top = True
    list_per_page = 100

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related('user_from', 'user_to')
        mutual_like = Like.objects.filter(user_from=OuterRef('user_to'), user_to=OuterRef('user_from'))
        return qs.annotate(has_mutual=Exists(mutual_like))

    @admin.display(description='Взаимная?', boolean=True)
    def is_mutual(self, obj):
        return getattr(obj, 'has_mutual', False)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Message)
class MessageAdmin(ReadOnlyTimestampsMixin, ShortTextDisplayMixin, admin.ModelAdmin):
    list_display = ('sender', 'receiver', 'get_short_content', 'is_read', 'timestamp')
    list_filter = ('is_read', 'timestamp')
    search_fields = ('sender__username', 'receiver__username', 'content')
    date_hierarchy = 'timestamp'
    save_on_top = True
    list_per_page = 100

    fieldsets = (
        ('👥 Участники', {'fields': ('sender', 'receiver')}),
        ('💬 Содержание', {'fields': ('content', 'is_read', 'timestamp')}),
        ('🗑️ Удаление', {
            'fields': ('is_deleted_by_sender', 'is_deleted_by_receiver'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('sender', 'receiver')

    @admin.display(description='Сообщение')
    def get_short_content(self, obj):
        return self.truncate_text(obj.content, 50)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
    
    def get_absolute_url(self):
        return reverse('profiles:conversation_detail', kwargs={'pk': self.sender.pk})



@admin.register(Notification)
class NotificationAdmin(ReadOnlyTimestampsMixin, ShortTextDisplayMixin, admin.ModelAdmin):
    list_display = ('recipient', 'sender', 'get_short_message', 'notification_type', 'is_read', 'created_at')
    list_filter = ('is_read', 'notification_type', 'created_at')
    search_fields = ('recipient__username', 'sender__username', 'message')
    actions = ['mark_as_read', 'mark_as_unread', 'delete_old_notifications']
    date_hierarchy = 'created_at'
    save_on_top = True
    list_per_page = 100

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('recipient', 'sender')

    @admin.display(description='Уведомление')
    def get_short_message(self, obj):
        return self.truncate_text(obj.message, 60)

    @admin.action(description='✅ Отметить прочитанными')
    def mark_as_read(self, request, queryset):
        updated = queryset.filter(is_read=False).update(is_read=True)
        self.message_user(request, f'Отмечено прочитанными: {updated}', django_messages.SUCCESS)

    @admin.action(description='📭 Отметить непрочитанными')
    def mark_as_unread(self, request, queryset):
        updated = queryset.filter(is_read=True).update(is_read=False)
        self.message_user(request, f'Отмечено непрочитанными: {updated}', django_messages.INFO)

    @admin.action(description='🗑️ Удалить старые (>30 дней)')
    def delete_old_notifications(self, request, queryset):
        from django.utils import timezone
        from datetime import timedelta
        cutoff_date = timezone.now() - timedelta(days=30)
        deleted, _ = queryset.filter(created_at__lt=cutoff_date).delete()
        msg = f'Удалено старых уведомлений: {deleted}' if deleted else 'Нет старых уведомлений'
        level = django_messages.WARNING if deleted else django_messages.INFO
        self.message_user(request, msg, level)

    def linked_object(self, obj):
        if obj.target:
            return format_html('<a href="{}">{}</a>', obj.target.get_absolute_url(), str(obj.target))
        return "-"
    linked_object.short_description = "Связанный объект"


# ==============================================================================
# ADMIN ДЛЯ СТАТИСТИКИ
# ==============================================================================

@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'login_time', 'logout_time', 'duration_minutes')
    readonly_fields = [f.name for f in UserSession._meta.fields]


@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ('user', 'action_type', 'timestamp', 'target_user')
    readonly_fields = [f.name for f in UserActivity._meta.fields]

from django.contrib import admin
from django.utils.html import format_html
from .models import SessionLog

@admin.register(SessionLog)
class SessionLogAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "action_badge",
        "status_badge",
        "timestamp",
        "duration_display",
        "session_key",
    )
    list_filter = ("status", "action", "timestamp")
    search_fields = ("user__username", "session_key", "extra_info")
    ordering = ("-timestamp",)

    def status_badge(self, obj):
        colors = {
            "completed": "green",
            "no_active_session": "orange",
            "error": "red",
        }
        color = colors.get(obj.status, "gray")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, dict(SessionLog.STATUS_CHOICES).get(obj.status, obj.status)
        )
    status_badge.short_description = "Статус"

    def action_badge(self, obj):
        labels = dict(SessionLog.ACTION_CHOICES)
        return format_html(
            '<span style="color: #555;">{}</span>',
            labels.get(obj.action, obj.action)
        )
    action_badge.short_description = "Действие"

    def duration_display(self, obj):
        if obj.duration:
            total_seconds = int(obj.duration.total_seconds())
            minutes, seconds = divmod(total_seconds, 60)
            return f"{minutes} мин {seconds} сек"
        return "-"
    duration_display.short_description = "Длительность"


    
# ==============================================================================
# НАСТРОЙКА АДМИН-ПАНЕЛИ
# ==============================================================================

admin.site.site_header = "🏛️ Администрирование сайта знакомств"
admin.site.site_title = "Админ-панель"
admin.site.index_title = "Управление сайтом"
admin.site.empty_value_display = '(не указано)'
