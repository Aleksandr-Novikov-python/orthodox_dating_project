"""
Пакет views для приложения profiles

Организация:
- auth.py: регистрация, вход, выход
- profile.py: просмотр и редактирование профилей
- messaging.py: личные сообщения
- social.py: лайки, жалобы
- blog.py: посты и комментарии
- calendar.py: православный календарь
- api.py: AJAX endpoints
- mixins.py: переиспользуемые компоненты
"""

# ============================================================================
# ИМПОРТЫ ДЛЯ ОБРАТНОЙ СОВМЕСТИМОСТИ
# ============================================================================

# Аутентификация
from .auth import (
    register,
    CustomLogoutView,
    LoggedOutView,
)

# Профили
from .profile import (
    profile_list,
    profile_detail,
    edit_profile,
    delete_photo,
)

# Сообщения
from .messaging import (
    inbox,
    conversation_detail,
    delete_message_ajax,
    get_new_messages,
)

# Социальные взаимодействия
from .social import (
    add_like,
    likes_received_list,
    submit_complaint,
)

# Блог
from .blog import (
    post_list,
    post_detail,
    like_comment,
    dislike_comment,
)

# Календарь
from .calendar import (
    OrthodoxCalendarView,
    CalendarMonthView,
    CalendarAPIView,
    get_today_holiday,
    is_fasting_today,
)

# Общие view
from .common import (
    home_page,
    static_page_view,
)

# Уведомления
from .notifications import (
    notification_list,
    mark_all_notifications_read,
)

# Миксины (для использования в других местах)
from .mixins import (
    StaffProtectionMixin,
    MutualLikeRequiredMixin,
    SessionStatsMixin,
    AjaxRequiredMixin,
    SelfInteractionProtectionMixin,
    PaginationMixin,
    is_staff_or_superuser,
)


__all__ = [
    # Auth
    'register',
    'CustomLogoutView',
    'LoggedOutView',
    
    # Profiles
    'profile_list',
    'profile_detail',
    'edit_profile',
    'delete_photo',
    
    # Messaging
    'inbox',
    'conversation_detail',
    'delete_message_ajax',
    'get_new_messages',
    
    # Social
    'add_like',
    'likes_received_list',
    'submit_complaint',
    
    # Blog
    'post_list',
    'post_detail',
    'like_comment',
    'dislike_comment',
    
    # Calendar
    'OrthodoxCalendarView',
    'CalendarMonthView',
    'CalendarAPIView',
    'get_today_holiday',
    'is_fasting_today',
    
    # Common
    'home_page',
    'static_page_view',
    
    # Notifications
    'notification_list',
    'mark_all_notifications_read',
    
    # Mixins
    'StaffProtectionMixin',
    'MutualLikeRequiredMixin',
    'SessionStatsMixin',
    'AjaxRequiredMixin',
    'SelfInteractionProtectionMixin',
    'PaginationMixin',
    'is_staff_or_superuser',
]
