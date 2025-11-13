import logging
from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.db import transaction
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from profiles.forms import UserRegistrationForm, UserProfileForm
from profiles.models import UserProfile, UserSession
from profiles.services.photo_validator import validate_registration_photo

logger = logging.getLogger(__name__)
User = get_user_model()


class RegistrationService:
    """Сервис для обработки регистрации пользователей"""
    
    @staticmethod
    def validate_photo(uploaded_photo, strict_mode=False):
        """
        Валидация загруженного фото
        
        Returns:
            tuple: (is_valid, errors, warnings)
            
        Raises:
            ImportError, AttributeError: критические ошибки в коде валидатора
        """
        if not uploaded_photo:
            return True, [], []
        
        try:
            is_valid, errors, warnings = validate_registration_photo(
                uploaded_photo, 
                strict_mode=strict_mode
            )
            return is_valid, errors, warnings
            
        except (OSError, IOError, ValueError, TypeError) as e:
            # Ожидаемые ошибки при обработке файлов:
            # - OSError/IOError: проблемы с чтением файла
            # - ValueError: невалидный формат изображения
            # - TypeError: неправильный тип данных
            logger.warning(
                f"Ошибка валидации фото (файл или формат): {str(e)}", 
                exc_info=True,
                extra={'error_type': type(e).__name__}
            )
            # В этих случаях можно разрешить регистрацию с предупреждением
            return True, [], [f"Не удалось проверить фото: {str(e)}"]
            
        except (ImportError, AttributeError, NameError) as e:
            # Критические ошибки в коде валидатора - НЕ перехватываем
            logger.critical(
                f"Критическая ошибка в коде валидатора: {str(e)}",
                exc_info=True,
                extra={'error_type': type(e).__name__}
            )
            raise  # Пробрасываем дальше для отображения 500 ошибки
    
    @staticmethod
    @transaction.atomic
    def create_user_with_profile(user_form, profile_form):
        """
        Создание пользователя и профиля в транзакции
        
        Returns:
            User: созданный пользователь
        """
        # Создаем пользователя
        new_user = user_form.save(commit=False)
        new_user.set_password(user_form.cleaned_data['password'])
        new_user.save()
        
        # Создаем профиль
        profile, created = UserProfile.objects.get_or_create(user=new_user)
        
        # Обновляем поля профиля
        for field, value in profile_form.cleaned_data.items():
            if value not in (None, ''):
                setattr(profile, field, value)
        profile.save()
        
        # Вычисляем хеш фото (опционально)
        uploaded_photo = profile_form.cleaned_data.get('photo')
        if uploaded_photo and hasattr(profile, 'photo_hash'):
            try:
                from profiles.services import calculate_photo_hash
                profile.photo_hash = calculate_photo_hash(uploaded_photo)
                profile.save(update_fields=['photo_hash'])
            except Exception as hash_error:
                logger.warning(
                    f"Не удалось вычислить хеш фото: {str(hash_error)}",
                    extra={'user_id': new_user.id}
                )
        
        logger.info(
            f"Успешная регистрация пользователя: {new_user.username}",
            extra={'user_id': new_user.id}
        )
        
        return new_user

def register(request):
    """
    Регистрация нового пользователя с комплексной проверкой фото
    """
    if request.method == 'POST':
        user_form = UserRegistrationForm(request.POST)
        profile_form = UserProfileForm(request.POST, request.FILES)
        
        if not (user_form.is_valid() and profile_form.is_valid()):
            # Показываем ошибки валидации форм
            _display_form_errors(request, user_form, profile_form)
            return _render_registration_page(request, user_form, profile_form)
        
        # Валидация фото из очищенных данных формы
        uploaded_photo = profile_form.cleaned_data.get('photo')
        is_valid, errors, warnings = RegistrationService.validate_photo(uploaded_photo)
        
        if not is_valid:
            for error in errors:
                messages.error(request, error)
            messages.error(
                request, 
                '❌ Регистрация отклонена. Исправьте проблемы с фотографией.'
            )
            return _render_registration_page(request, user_form, profile_form)
        
        # Показываем предупреждения
        for warning in warnings:
            messages.warning(request, warning)
        
        if uploaded_photo:
            messages.success(request, '✅ Фотография успешно проверена')
        
        # Создаем пользователя
        try:
            new_user = RegistrationService.create_user_with_profile(
                user_form, 
                profile_form
            )
            
            messages.success(
                request, 
                '🎉 Регистрация успешно завершена! Добро пожаловать!'
            )
            return redirect('login')
            
        except Exception as e:
            logger.error(
                f"Ошибка при создании аккаунта: {str(e)}",
                exc_info=True,
                extra={
                    'username': user_form.cleaned_data.get('username'),
                    'email': user_form.cleaned_data.get('email')
                }
            )
            messages.error(request, f'❌ Ошибка при создании аккаунта: {str(e)}')
    else:
        user_form = UserRegistrationForm()
        profile_form = UserProfileForm()
    
    return _render_registration_page(request, user_form, profile_form)

def _display_form_errors(request, user_form, profile_form):
    """Отображение ошибок валидации форм"""
    for form in [user_form, profile_form]:
        for field, errors in form.errors.items():
            for error in errors:
                field_label = (
                    form.fields[field].label 
                    if field in form.fields and hasattr(form.fields[field], 'label')
                    else field
                )
                messages.error(request, f'{field_label}: {error}')


def _render_registration_page(request, user_form, profile_form):
    """Рендер страницы регистрации с формами"""
    return render(request, 'profiles/register.html', {
        'user_form': user_form,
        'profile_form': profile_form
    })

class CustomLogoutView(View):
    """Выход пользователя с сохранением статистики"""
    
    def post(self, request):
        session_id = self._close_user_session(request.user)
        logout(request)
        return redirect(f"{reverse('profiles:logged_out')}?sid={session_id}")
    
    def _close_user_session(self, user):
        """Закрытие активной сессии пользователя"""
        try:
            session = UserSession.objects.filter(
                user=user,
                logout_time__isnull=True
            ).latest('login_time')
            
            session.logout_time = timezone.now()
            delta = session.logout_time - session.login_time
            session.duration_minutes = max(1, int(delta.total_seconds() // 60))
            session.save()
            
            logger.info(
                "Выход пользователя",
                extra={
                    'user_id': user.id,
                    'session_id': session.id,
                    'duration_minutes': session.duration_minutes
                }
            )
            
            return session.id
            
        except UserSession.DoesNotExist:
            logger.warning(
                "Нет активной сессии для пользователя",
                extra={'user_id': user.id}
            )
            return ''


class LoggedOutView(View):
    """Страница после выхода"""
    
    def get(self, request):
        session_id = request.GET.get('sid')
        session = self._get_session(session_id)
        
        return render(request, 'profiles/logged_out.html', {
            'session': session
        })
    
    def _get_session(self, session_id):
        """Получение сессии по ID"""
        if not session_id:
            return None
        
        try:
            session = UserSession.objects.get(id=session_id)
            logger.debug(f"Отображение статистики сессии: {session_id}")
            return session
        except UserSession.DoesNotExist:
            logger.warning(f"Сессия с ID {session_id} не найдена")
            return None

