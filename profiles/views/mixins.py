"""
Миксины для views приложения profiles
Содержат переиспользуемую логику для проверок и ограничений доступа
"""

import logging
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied

from profiles.models import Like, UserSession

logger = logging.getLogger(__name__)
User = get_user_model()


def is_staff_or_superuser(user):
    """Проверка, является ли пользователь админом"""
    return user.is_staff or user.is_superuser


class StaffProtectionMixin:
    """
    Запрещает взаимодействие с профилями администраторов
    
    Usage:
        class MyView(StaffProtectionMixin, View):
            staff_redirect_url = 'profiles:profile_list'
            
            def get_target_user(self):
                return get_object_or_404(User, pk=self.kwargs['pk'])
    """
    staff_redirect_url = 'profiles:profile_list'
    staff_error_message = 'Профиль недоступен.'
    
    def dispatch(self, request, *args, **kwargs):
        target = self.get_target_user()
        
        if is_staff_or_superuser(target):
            messages.error(request, self.staff_error_message)
            return redirect(self.staff_redirect_url)
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_target_user(self):
        """
        Переопределите этот метод для получения целевого пользователя
        """
        raise NotImplementedError(
            "Необходимо переопределить метод get_target_user()"
        )


class MutualLikeRequiredMixin:
    """
    Требует взаимной симпатии между пользователями
    
    Usage:
        class ConversationView(MutualLikeRequiredMixin, LoginRequiredMixin, View):
            def get_interlocutor(self):
                return get_object_or_404(User, pk=self.kwargs['pk'])
    """
    mutual_like_error_message = 'Можно писать только при взаимной симпатии.'
    mutual_like_redirect_pattern = 'profiles:profile_detail'
    
    def dispatch(self, request, *args, **kwargs):
        interlocutor = self.get_interlocutor()
        
        if not self.check_mutual_like(request.user, interlocutor):
            messages.error(request, self.mutual_like_error_message)
            return redirect(
                self.mutual_like_redirect_pattern, 
                pk=interlocutor.id
            )
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_interlocutor(self):
        """Переопределите для получения собеседника"""
        raise NotImplementedError(
            "Необходимо переопределить метод get_interlocutor()"
        )
    
    @staticmethod
    def check_mutual_like(user1, user2):
        """Проверка взаимной симпатии"""
        return (
            Like.objects.filter(user_from=user1, user_to=user2).exists() and
            Like.objects.filter(user_from=user2, user_to=user1).exists()
        )


class SessionStatsMixin:
    """
    Автоматическое обновление статистики сессии
    
    Usage:
        class LikeView(SessionStatsMixin, LoginRequiredMixin, View):
            session_stat_field = 'likes_given'
            
            def post(self, request, pk):
                # ... логика лайка
                self.update_session_stats(request.user)
    """
    session_stat_field = None  # Переопределите: 'likes_given', 'messages_sent' и т.д.
    
    def update_session_stats(self, user, increment=1):
        """
        Обновить статистику активной сессии
        
        Args:
            user: пользователь
            increment: на сколько увеличить счетчик (по умолчанию 1)
        """
        if not self.session_stat_field:
            logger.warning(
                "session_stat_field не определен для SessionStatsMixin"
            )
            return
        
        try:
            session = UserSession.objects.filter(
                user=user,
                logout_time__isnull=True
            ).latest('login_time')
            
            current_value = getattr(session, self.session_stat_field, 0)
            setattr(session, self.session_stat_field, current_value + increment)
            session.save(update_fields=[self.session_stat_field])
            
            logger.debug(
                f"Обновлена статистика: {self.session_stat_field} = "
                f"{current_value + increment}",
                extra={
                    'user_id': user.id,
                    'session_id': session.id
                }
            )
            
        except UserSession.DoesNotExist:
            logger.debug(
                f"Нет активной сессии для пользователя {user.id}",
                extra={'user_id': user.id}
            )


class AjaxRequiredMixin:
    """
    Требует, чтобы запрос был AJAX
    
    Usage:
        class MyAjaxView(AjaxRequiredMixin, View):
            pass
    """
    
    def dispatch(self, request, *args, **kwargs):
        if not self.is_ajax(request):
            raise PermissionDenied("Только AJAX запросы")
        
        return super().dispatch(request, *args, **kwargs)
    
    @staticmethod
    def is_ajax(request):
        """Проверка, является ли запрос AJAX"""
        return request.headers.get('x-requested-with') == 'XMLHttpRequest'


class SelfInteractionProtectionMixin:
    """
    Запрещает взаимодействие пользователя с самим собой
    
    Usage:
        class LikeView(SelfInteractionProtectionMixin, LoginRequiredMixin, View):
            self_interaction_error = 'Нельзя лайкать самого себя'
            
            def get_target_user(self):
                return get_object_or_404(User, pk=self.kwargs['pk'])
    """
    self_interaction_error = 'Недопустимое действие.'
    self_interaction_redirect = 'profiles:profile_list'
    
    def dispatch(self, request, *args, **kwargs):
        target = self.get_target_user()
        
        if target == request.user:
            messages.error(request, self.self_interaction_error)
            return redirect(self.self_interaction_redirect)
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_target_user(self):
        """Переопределите для получения целевого пользователя"""
        raise NotImplementedError(
            "Необходимо переопределить метод get_target_user()"
        )


class PaginationMixin:
    """
    Добавляет пагинацию к представлениям
    
    Usage:
        class ProfileListView(PaginationMixin, ListView):
            paginate_by = 20
    """
    paginate_by = 20
    page_kwarg = 'page'
    
    def get_paginate_by(self, queryset):
        """Получить количество элементов на странице"""
        return self.paginate_by
    
    def get_page_number(self, request):
        """Получить номер текущей страницы"""
        try:
            return int(request.GET.get(self.page_kwarg, 1))
        except (ValueError, TypeError):
            return 1


# ============================================================================
# ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ
# ============================================================================

"""
Пример 1: Просмотр профиля с защитой от админов

from django.views.generic import DetailView
from profiles.models import UserProfile

class ProfileDetailView(StaffProtectionMixin, DetailView):
    model = UserProfile
    template_name = 'profiles/profile_detail.html'
    
    def get_target_user(self):
        return self.get_object().user


Пример 2: Отправка лайка с несколькими защитами

from django.views import View

class AddLikeView(
    SelfInteractionProtectionMixin,
    StaffProtectionMixin,
    SessionStatsMixin,
    LoginRequiredMixin,
    View
):
    session_stat_field = 'likes_given'
    self_interaction_error = 'Нельзя лайкать самого себя.'
    staff_error_message = 'Нельзя отправить симпатию администратору.'
    
    def get_target_user(self):
        return get_object_or_404(User, pk=self.kwargs['pk'])
    
    def post(self, request, pk):
        target = self.get_target_user()
        
        # Создаем лайк
        like, created = Like.objects.get_or_create(
            user_from=request.user,
            user_to=target
        )
        
        if created:
            # Обновляем статистику
            self.update_session_stats(request.user)
            messages.success(request, 'Симпатия отправлена!')
        else:
            messages.info(request, 'Вы уже отправили симпатию.')
        
        return redirect('profiles:profile_detail', pk=pk)


Пример 3: Диалог с проверкой взаимных лайков

class ConversationDetailView(
    MutualLikeRequiredMixin,
    LoginRequiredMixin,
    View
):
    template_name = 'profiles/conversation_detail.html'
    
    def get_interlocutor(self):
        return get_object_or_404(User, pk=self.kwargs['pk'])
    
    def get(self, request, pk):
        interlocutor = self.get_interlocutor()
        # ... остальная логика
"""
