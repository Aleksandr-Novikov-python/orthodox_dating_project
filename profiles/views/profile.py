import logging
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Prefetch
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from profiles.forms import (
    UserUpdateForm,
    ProfileUpdateForm,
    ProfileFilterForm,
    PhotoForm,
)
from profiles.models import UserProfile, Photo, UserSession, ViewedProfile
from profiles.services import verify_photo_originality, PhotoVerificationService
from profiles.views.mixins import is_staff_or_superuser

logger = logging.getLogger(__name__)
User = get_user_model()


class ProfileFilterService:
    """Сервис для фильтрации профилей"""
    
    @staticmethod
    def apply_filters(queryset, form_data):
        """
        Применить фильтры к queryset профилей
        
        Args:
            queryset: базовый QuerySet
            form_data: очищенные данные формы
            
        Returns:
            QuerySet: отфильтрованный набор
        """
        if not form_data:
            return queryset
        
        # Фильтр по полу
        if form_data.get('gender'):
            queryset = queryset.filter(gender=form_data['gender'])
        
        # Фильтр по городу
        if form_data.get('city'):
            queryset = queryset.filter(city__icontains=form_data['city'])
        
        # Фильтр по уровню воцерковления
        if form_data.get('churching_level'):
            queryset = queryset.filter(
                churching_level=form_data['churching_level']
            )
        
        # Фильтр по возрасту
        current_year = timezone.now().year
        
        if form_data.get('min_age'):
            queryset = queryset.filter(
                date_of_birth__year__lte=current_year - form_data['min_age']
            )
        
        if form_data.get('max_age'):
            queryset = queryset.filter(
                date_of_birth__year__gte=current_year - form_data['max_age']
            )
        
        return queryset


@login_required
def profile_list(request):
    """
    Список анкет с фильтрацией и пагинацией
    
    Оптимизировано:
    - Пагинация (20 профилей на страницу)
    - select_related для уменьшения запросов
    - Фильтрация через сервисный слой
    """
    # Базовый queryset с оптимизацией
    profiles = UserProfile.objects.select_related('user').exclude(
        Q(user=request.user) | 
        Q(user__is_staff=True) | 
        Q(user__is_superuser=True)
    ).only(
        'user__id',
        'user__username',
        'user__first_name',
        'photo',
        'city',
        'date_of_birth',
        'gender',
        'churching_level',
    )
    
    # Применение фильтров
    form = ProfileFilterForm(request.GET or None)
    if form.is_valid():
        profiles = ProfileFilterService.apply_filters(
            profiles, 
            form.cleaned_data
        )
    profiles = profiles.order_by('user__id')
    # Пагинация
    paginator = Paginator(profiles, 20)
    page_number = request.GET.get('page', 1)
    
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    
    logger.debug(
        f"Отображение страницы {page_obj.number} из {paginator.num_pages}",
        extra={
            'user_id': request.user.id,
            'total_profiles': paginator.count
        }
    )
    
    return render(request, 'profiles/profile_list.html', {
        'profiles': page_obj.object_list,  # Обратная совместимость
        'page_obj': page_obj,
        'form': form,
        'total_count': paginator.count,
    })


def profile_detail(request, pk):
    """
    Детальная информация о профиле с оптимизацией запросов
    
    Оптимизировано:
    - select_related + prefetch_related
    - Фиксация просмотра только 1 раз за сессию
    """
    other_user = get_object_or_404(
        User.objects.select_related('userprofile').prefetch_related(
            Prefetch(
                'userprofile__photos',
                queryset=Photo.objects.order_by('-uploaded_at')
            )
        ),
        pk=pk
    )
    
    # Запрет на просмотр профилей админов
    if is_staff_or_superuser(other_user):
        messages.error(request, 'Профиль недоступен.')
        return redirect('profiles:profile_list')
    
    # Фиксация просмотра анкеты
    if request.user.is_authenticated and request.user != other_user:
        _record_profile_view(request.user, other_user.userprofile)
    
    # Проверка взаимной симпатии
    mutual_like = False
    if request.user.is_authenticated:
        from profiles.services.user_service import UserService
        mutual_like = UserService.check_mutual_like(request.user, other_user)
    
    return render(request, 'profiles/profile_detail.html', {
        'profile': other_user.userprofile,
        'mutual_like': mutual_like,
        'photos': other_user.userprofile.photos.all()[:6],  # Первые 6 фото
    })


def _record_profile_view(viewer, viewed_profile):
    """
    Записать просмотр профиля (только 1 раз за сессию)
    
    Args:
        viewer: пользователь, просматривающий профиль
        viewed_profile: просматриваемый профиль
    """
    try:
        session = UserSession.objects.filter(
            user=viewer,
            logout_time__isnull=True
        ).latest('login_time')
        
        # Проверяем, был ли уже просмотр в этой сессии
        already_viewed = ViewedProfile.objects.filter(
            session=session,
            profile=viewed_profile
        ).exists()
        
        if not already_viewed:
            session.profiles_viewed += 1
            session.save(update_fields=['profiles_viewed'])
            ViewedProfile.objects.create(
                session=session, 
                profile=viewed_profile
            )
            
            logger.debug(
                f"Зафиксирован просмотр профиля {viewed_profile.user.username}",
                extra={
                    'viewer_id': viewer.id,
                    'viewed_profile_id': viewed_profile.id
                }
            )
    
    except UserSession.DoesNotExist:
        logger.debug("Нет активной сессии для фиксации просмотра")


@login_required
def edit_profile(request):
    """
    Редактирование профиля с проверкой дубликатов фото
    
    Улучшено:
    - Разделение логики обновления профиля и загрузки фото
    - Детальная проверка дубликатов
    - Улучшенная обработка ошибок
    """
    if request.method == 'POST':
        # Обновление основной информации профиля
        if 'update_profile' in request.POST:
            return _handle_profile_update(request)
        
        # Загрузка новой фотографии
        elif 'upload_photo' in request.POST:
            return _handle_photo_upload(request)
    
    # GET запрос - отображение форм
    user_form = UserUpdateForm(instance=request.user)
    profile_form = ProfileUpdateForm(instance=request.user.userprofile)
    photo_form = PhotoForm()
    
    return render(request, 'profiles/edit_profile.html', {
        'user_form': user_form,
        'profile_form': profile_form,
        'photo_form': photo_form,
        'user_photos': request.user.userprofile.photos.all().order_by('-uploaded_at')
    })


def _handle_profile_update(request):
    """Обработка обновления информации профиля"""
    user_form = UserUpdateForm(request.POST, instance=request.user)
    profile_form = ProfileUpdateForm(
        request.POST,
        request.FILES,
        instance=request.user.userprofile
    )
    
    if user_form.is_valid() and profile_form.is_valid():
        user_form.save()
        profile_form.save()
        messages.success(request, 'Ваш профиль успешно обновлён!')
        logger.info(
            "Профиль обновлен",
            extra={'user_id': request.user.id}
        )
    else:
        for form in [user_form, profile_form]:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    
    return redirect('profiles:edit_profile')


def _handle_photo_upload(request):
    """Обработка загрузки новой фотографии"""
    photo_form = PhotoForm(request.POST, request.FILES)
    
    if not photo_form.is_valid():
        messages.error(request, 'Ошибка в форме загрузки фото.')
        return redirect('profiles:edit_profile')
    
    # ✅ Получаем из cleaned_data после валидации
    uploaded_file = photo_form.cleaned_data.get('image')
    if not uploaded_file:
        messages.error(request, 'Файл не был загружен.')
        return redirect('profiles:edit_profile')
    
    try:
        # Проверяем оригинальность
        is_original, photo_hash, similar_photos = verify_photo_originality(
            image=uploaded_file,
            user_profile=request.user.userprofile
        )
        
        if not is_original:
            # Показываем информацию о дубликатах
            msg = PhotoVerificationService.get_verification_message(
                is_original, 
                similar_photos
            )
            messages.warning(request, msg)
            
            for photo, score in similar_photos[:3]:
                messages.info(
                    request,
                    f"📸 Похожее фото загружено: "
                    f"{photo.uploaded_at.strftime('%d.%m.%Y в %H:%M')}"
                )
            
            # Запрещаем дубликат
            messages.error(
                request, 
                '❌ Загрузка отменена: фото уже есть в вашем профиле.'
            )
            
            logger.info(
                "Попытка загрузки дубликата фото",
                extra={
                    'user_id': request.user.id,
                    'similar_count': len(similar_photos)
                }
            )
            
            return redirect('profiles:edit_profile')
        
        # Сохраняем фото с хешем
        photo = photo_form.save(commit=False)
        photo.user_profile = request.user.userprofile
        photo.image_hash = photo_hash
        photo.save()
        
        logger.info(
            "Фото успешно загружено",
            extra={
                'user_id': request.user.id,
                'photo_id': photo.id
            }
        )
        
        messages.success(request, '✅ Фотография успешно добавлена!')
        
    except (OSError, IOError) as e:
        # Проблемы с файловой системой/чтением файла
        logger.error(
            f"Ошибка I/O при загрузке фото: {str(e)}",
            exc_info=True,
            extra={
                'user_id': request.user.id,
                'filename': uploaded_file.name,
                'error_type': type(e).__name__
            }
        )
        messages.error(request, 'Ошибка при чтении файла. Попробуйте другой файл.')
        
    except ValueError as e:
        # Невалидный формат изображения
        logger.warning(
            f"Невалидный формат изображения: {str(e)}",
            extra={
                'user_id': request.user.id,
                'filename': uploaded_file.name
            }
        )
        messages.error(request, f'Невалидный формат изображения: {str(e)}')
        
    except (ImportError, AttributeError) as e:
        # Критические ошибки в коде - не перехватываем
        logger.critical(
            f"Критическая ошибка при загрузке фото: {str(e)}",
            exc_info=True,
            extra={
                'user_id': request.user.id,
                'error_type': type(e).__name__
            }
        )
        # Пробрасываем для показа 500 ошибки
        raise
    
    return redirect('profiles:edit_profile')


@login_required
def delete_photo(request, photo_id):
    """
    Удаление фотографии с проверкой владельца
    """
    photo = get_object_or_404(
        Photo, 
        id=photo_id, 
        user_profile=request.user.userprofile
    )
    
    if request.method == 'POST':
        photo_filename = photo.image.name if photo.image else 'unknown'
        photo.delete()
        
        logger.info(
            f"Фотография удалена: {photo_filename}",
            extra={
                'user_id': request.user.id,
                'photo_id': photo_id
            }
        )
        
        messages.success(request, 'Фотография удалена.')
    
    return redirect('profiles:edit_profile')

# import logging
# from django.contrib.auth.decorators import login_required
# from django.contrib import messages
# from django.shortcuts import render, redirect, get_object_or_404
# from django.utils import timezone
# from django.db.models import Q

# from profiles.forms import PhotoForm, ProfileFilterForm, ProfileUpdateForm, UserUpdateForm
# from profiles.models import Photo, UserProfile, UserSession, ViewedProfile
# from profiles.services.photo_verification import PhotoVerificationService, verify_photo_originality
# from profiles.services.like_service import check_mutual_like
# from profiles.views.mixins import is_staff_or_superuser
# from profiles.views.auth import User


# logger = logging.getLogger(__name__)


# @login_required
# def edit_profile(request):
#     """Редактирование профиля"""
#     if request.method == 'POST':
#         if 'update_profile' in request.POST:
#             user_form = UserUpdateForm(request.POST, instance=request.user)
#             profile_form = ProfileUpdateForm(
#                 request.POST,
#                 request.FILES,
#                 instance=request.user.userprofile
#             )

#             if user_form.is_valid() and profile_form.is_valid():
#                 user_form.save()
#                 profile_form.save()
#                 messages.success(request, 'Ваш профиль успешно обновлён!')
#                 return redirect('profiles:edit_profile')

#         # ✅ ЗАГРУЗКА ФОТОГРАФИИ С ПРОВЕРКОЙ ДУБЛИКАТОВ
#         elif 'upload_photo' in request.POST:
#             photo_form = PhotoForm(request.POST, request.FILES)

#             if photo_form.is_valid():
#                 uploaded_file = request.FILES.get('image')
#                 if uploaded_file:
#                     try:
#                         # ✅ ПРОВЕРЯЕМ ОРИГИНАЛЬНОСТЬ
#                         is_original, photo_hash, similar_photos = verify_photo_originality(
#                             image=uploaded_file,
#                             user_profile=request.user.userprofile
#                         )
                        
#                         if not is_original:
#                             msg = PhotoVerificationService.get_verification_message(
#                                 is_original, 
#                                 similar_photos
#                             )
#                             messages.warning(request, msg)
                            
#                             for photo, score in similar_photos[:3]:
#                                 messages.info(
#                                     request,
#                                     f"📸 Похожее фото загружено: {photo.uploaded_at.strftime('%d.%m.%Y в %H:%M')}"
#                                 )
                            
#                             # ВАРИАНТ 1: Запретить дубликат (рекомендую)
#                             messages.error(request, '❌ Загрузка отменена: фото уже есть в вашем профиле.')
                            
#                             logger.info(
#                                 f"Попытка загрузки дубликата фото",
#                                 extra={
#                                     'user_id': request.user.id,
#                                     'similar_count': len(similar_photos)
#                                 }
#                             )
                            
#                             return redirect('profiles:edit_profile')
                        
#                         # Сохраняем фото с хешем
#                         photo = photo_form.save(commit=False)
#                         photo.user_profile = request.user.userprofile
#                         photo.image_hash = photo_hash
#                         photo.save()
                        
#                         logger.info(
#                             f"Фото успешно загружено",
#                             extra={
#                                 'user_id': request.user.id,
#                                 'photo_id': photo.id
#                             }
#                         )
                        
#                         messages.success(request, '✅ Фотография успешно добавлена!')
                        
#                     except Exception as e:
#                         # ✅ ИСПРАВЛЕНО: Подробное логирование
#                         logger.error(
#                             f"Ошибка при загрузке фото: {str(e)}",
#                             exc_info=True,
#                             extra={
#                                 'user_id': request.user.id,
#                                 'filename': uploaded_file.name if uploaded_file else 'unknown'
#                             }
#                         )
                        
#                         messages.error(request, f'Ошибка при проверке фото: {str(e)}')
#                 else:
#                     messages.error(request, 'Файл не был загружен.')
                
#                 return redirect('profiles:edit_profile')
#     else:
#         user_form = UserUpdateForm(instance=request.user)
#         profile_form = ProfileUpdateForm(instance=request.user.userprofile)
#         photo_form = PhotoForm()

#     return render(request, 'profiles/edit_profile.html', {
#         'user_form': user_form,
#         'profile_form': profile_form,
#         'photo_form': photo_form,
#         'user_photos': request.user.userprofile.photos.all()
#     })

# @login_required
# def profile_list(request):
#     """Список анкет с фильтрацией"""
#     # Базовый queryset с оптимизацией
#     profiles = UserProfile.objects.select_related('user').exclude(
#         Q(user=request.user) | Q(user__is_staff=True) | Q(user__is_superuser=True)
#     )

#     # Применение фильтров
#     form = ProfileFilterForm(request.GET or None)
#     if form.is_valid():
#         cd = form.cleaned_data

#         if cd.get('gender'):
#             profiles = profiles.filter(gender=cd['gender'])

#         if cd.get('city'):
#             profiles = profiles.filter(city__icontains=cd['city'])

#         if cd.get('churching_level'):
#             profiles = profiles.filter(churching_level=cd['churching_level'])

#         # Фильтрация по возрасту
#         current_year = timezone.now().year
#         if cd.get('min_age'):
#             profiles = profiles.filter(date_of_birth__year__lte=current_year - cd['min_age'])

#         if cd.get('max_age'):
#             profiles = profiles.filter(date_of_birth__year__gte=current_year - cd['max_age'])

#     return render(request, 'profiles/profile_list.html', {
#         'profiles': profiles,
#         'form': form
#     })

# def profile_detail(request, pk):
#     """Детальная информация о профиле"""
#     other_user = get_object_or_404(
#         User.objects.select_related('userprofile').prefetch_related('userprofile__photos'),
#         pk=pk
#     )

#     # Запрет на просмотр профилей админов
#     if is_staff_or_superuser(other_user):
#         messages.error(request, 'Профиль недоступен.')
#         return redirect('profiles:profile_list')

#     # Фиксация просмотра анкеты (только один раз за сессию)
#     if request.user.is_authenticated and request.user != other_user:
#         try:
#             session = UserSession.objects.filter(
#                 user=request.user,
#                 logout_time__isnull=True
#             ).latest('login_time')

#             already_viewed = ViewedProfile.objects.filter(
#                 session=session,
#                 profile=other_user.userprofile
#             ).exists()

#             if not already_viewed:
#                 session.profiles_viewed += 1
#                 session.save()
#                 ViewedProfile.objects.create(session=session, profile=other_user.userprofile)

#         except UserSession.DoesNotExist:
#             pass

#     # Проверка взаимной симпатии
#     mutual_like = check_mutual_like(request.user, other_user)

#     return render(request, 'profiles/profile_detail.html', {
#         'profile': other_user.userprofile,
#         'mutual_like': mutual_like
#     })

# @login_required
# def delete_photo(request, photo_id):
#     """Удаление фотографии"""
#     photo = get_object_or_404(Photo, id=photo_id, user_profile=request.user.userprofile)

#     if request.method == 'POST':
#         photo.delete()
#         messages.success(request, 'Фотография удалена.')

#     return redirect('profiles:edit_profile')