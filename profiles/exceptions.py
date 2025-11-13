# ==============================================================================
# 1. CUSTOM EXCEPTIONS (profiles/exceptions.py)
# ==============================================================================

class ProfileException(Exception):
    """Base exception for profile-related errors"""
    default_message = "Произошла ошибка профиля"
    
    def __init__(self, message=None):
        self.message = message or self.default_message
        super().__init__(self.message)


class ProfileNotVerifiedException(ProfileException):
    default_message = "Профиль не верифицирован"


class ProfileIncompleteException(ProfileException):
    default_message = "Заполните все обязательные поля профиля"


class MatchingException(Exception):
    """Base exception for matching/sympathy errors"""
    default_message = "Ошибка при обработке симпатии"


class AlreadyLikedException(MatchingException):
    default_message = "Вы уже отправили симпатию этому пользователю"


class MessageException(Exception):
    """Base exception for messaging errors"""
    default_message = "Ошибка при отправке сообщения"


class NoMutualMatchException(MessageException):
    default_message = "Общение доступно только после взаимной симпатии"


# ==============================================================================
# 2. ERROR HANDLER MIDDLEWARE (profiles/middleware.py)
# ==============================================================================

import logging
from profile import Profile
from re import Match
from django.http import JsonResponse
from django.shortcuts import render
from django.conf import settings

from profiles.models import Like, Message

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware:
    """Centralized error handling middleware"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        return self.get_response(request)
    
    def process_exception(self, request, exception):
        """Handle exceptions globally"""
        
        # Log the error
        logger.error(
            f"Error: {exception.__class__.__name__}: {str(exception)}",
            exc_info=True,
            extra={'request': request}
        )
        
        # For AJAX requests, return JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': str(exception),
                'error_type': exception.__class__.__name__
            }, status=400)
        
        # For known exceptions, show user-friendly error page
        if isinstance(exception, (ProfileException, MatchingException, MessageException)):
            return render(request, 'profiles/error.html', {
                'error_message': str(exception),
                'error_type': 'user_error'
            }, status=400)
        
        # For unexpected errors, show generic error in production
        if not settings.DEBUG:
            return render(request, 'profiles/error.html', {
                'error_message': 'Произошла неожиданная ошибка. Пожалуйста, попробуйте позже.',
                'error_type': 'server_error'
            }, status=500)
        
        # In debug mode, let Django handle it
        return None


# ==============================================================================
# 3. VIEW DECORATORS (profiles/decorators.py)
# ==============================================================================

from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def profile_required(view_func):
    """Ensure user has a complete profile"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Пожалуйста, войдите в систему')
            return redirect('login')
        
        profile = getattr(request.user, 'profile', None)
        if not profile:
            messages.error(request, 'Создайте профиль для продолжения')
            return redirect('profiles:register')
        
        if not profile.is_complete():
            messages.warning(request, 'Заполните все обязательные поля профиля')
            return redirect('profiles:edit_profile')
        
        return view_func(request, *args, **kwargs)
    return wrapper


def verified_profile_required(view_func):
    """Ensure user's profile is verified"""
    @wraps(view_func)
    @profile_required
    def wrapper(request, *args, **kwargs):
        if not request.user.profile.is_verified:
            messages.warning(request, 'Ваш профиль ожидает верификации')
            return redirect('profiles:profile_detail', pk=request.user.profile.pk)
        
        return view_func(request, *args, **kwargs)
    return wrapper


def ajax_error_handler(view_func):
    """Handle errors in AJAX views"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except (ProfileException, MatchingException, MessageException) as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
        except Exception as e:
            logger.error(f"AJAX error: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Произошла ошибка. Попробуйте позже.'
            }, status=500)
    return wrapper


# ==============================================================================
# 4. EXAMPLE VIEWS WITH ERROR HANDLING (profiles/views.py)
# ==============================================================================

from django.views.generic import ListView, DetailView
from django.contrib.auth.decorators import login_required
from django.db import transaction


@login_required
@profile_required
def send_like(request, profile_id):
    """Send a like/sympathy to another profile"""
    try:
        target_profile = Profile.objects.get(id=profile_id)
        user_profile = request.user.profile
        
        # Validate business rules
        if target_profile == user_profile:
            raise MatchingException("Нельзя отправить симпатию самому себе")
        
        if Like.objects.filter(from_profile=user_profile, to_profile=target_profile).exists():
            raise AlreadyLikedException()
        
        # Create like atomically
        with transaction.atomic():
            like = Like.objects.create(
                from_profile=user_profile,
                to_profile=target_profile
            )
            
            # Check for mutual match
            mutual = Like.objects.filter(
                from_profile=target_profile,
                to_profile=user_profile
            ).exists()
            
            if mutual:
                Match.objects.get_or_create(
                    profile1=user_profile,
                    profile2=target_profile
                )
                messages.success(request, '🎉 Взаимная симпатия! Теперь вы можете общаться')
            else:
                messages.success(request, 'Симпатия отправлена')
        
        return JsonResponse({'success': True, 'mutual': mutual})
        
    except Profile.DoesNotExist:
        logger.warning(f"Profile {profile_id} not found for like")
        return JsonResponse({
            'success': False,
            'error': 'Профиль не найден'
        }, status=404)
    except (MatchingException, AlreadyLikedException) as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)
    except Exception as e:
        logger.error(f"Error sending like: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Не удалось отправить симпатию'
        }, status=500)


@login_required
@ajax_error_handler
def send_message(request, profile_id):
    """Send a message (requires mutual match)"""
    if request.method != 'POST':
        raise MessageException("Метод не разрешен")
    
    target_profile = Profile.objects.get(id=profile_id)
    user_profile = request.user.profile
    
    # Check mutual match
    if not Match.objects.filter(
        profile1__in=[user_profile, target_profile],
        profile2__in=[user_profile, target_profile]
    ).exists():
        raise NoMutualMatchException()
    
    content = request.POST.get('message', '').strip()
    if not content:
        raise MessageException("Сообщение не может быть пустым")
    
    if len(content) > 1000:
        raise MessageException("Сообщение слишком длинное (макс. 1000 символов)")
    
    message = Message.objects.create(
        sender=user_profile,
        recipient=target_profile,
        content=content
    )
    
    return JsonResponse({
        'success': True,
        'message_id': message.id
    })


# ==============================================================================
# 5. FORM ERROR HANDLING (profiles/forms.py)
# ==============================================================================

from django import forms


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['name', 'age', 'city', 'about', 'photo']
        error_messages = {
            'name': {
                'required': 'Имя обязательно для заполнения',
                'max_length': 'Имя слишком длинное'
            },
            'age': {
                'required': 'Укажите ваш возраст',
                'invalid': 'Укажите корректный возраст',
                'min_value': 'Минимальный возраст 18 лет',
                'max_value': 'Максимальный возраст 100 лет'
            }
        }
    
    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo:
            if photo.size > 5 * 1024 * 1024:  # 5MB
                raise forms.ValidationError('Файл слишком большой (макс. 5MB)')
            
            if not photo.content_type.startswith('image/'):
                raise forms.ValidationError('Загрузите изображение')
        
        return photo
    
    def clean(self):
        cleaned_data = super().clean()
        # Cross-field validation
        return cleaned_data

