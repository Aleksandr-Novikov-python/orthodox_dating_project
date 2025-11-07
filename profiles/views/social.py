from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

from profiles.forms import ComplaintForm
from profiles.models import Like, Notification, UserProfile, UserSession
from profiles.services.like_service import check_mutual_like
from profiles.views.mixins import is_staff_or_superuser
from profiles.views.auth import User

@login_required
def add_like(request, pk):
    """Отправка симпатии"""
    target = get_object_or_404(User, pk=pk)

    # Валидация
    if target == request.user:
        messages.error(request, 'Нельзя лайкать самого себя.')
        return redirect('profiles:profile_detail', pk=pk)

    if is_staff_or_superuser(target):
        messages.error(request, 'Нельзя отправить симпатию администратору.')
        return redirect('profiles:profile_list')

    # Создание лайка
    like, created = Like.objects.get_or_create(user_from=request.user, user_to=target)

    if created:
        # 📊 Обновление статистики
        try:
            session = UserSession.objects.filter(
                user=request.user,
                logout_time__isnull=True
            ).latest('login_time')
            session.likes_given += 1
            session.save()
        except UserSession.DoesNotExist:
            pass

        # Проверка взаимности и создание уведомления
        if check_mutual_like(request.user, target):
            messages.success(request, '🎉 Взаимная симпатия!')
        else:
            messages.success(request, 'Симпатия отправлена!')

        # Уведомление для получателя
        Notification.objects.create(
            recipient=target,
            sender=request.user,
            message=f'Вы понравились {request.user.first_name or request.user.username}!',
            notification_type='LIKE'
        )
    else:
        messages.info(request, 'Вы уже отправили симпатию этому пользователю.')

    return redirect('profiles:profile_detail', pk=pk)

@login_required
def likes_received_list(request):
    """Список полученных симпатий"""
    liker_ids = Like.objects.filter(user_to=request.user).values_list('user_from_id', flat=True)
    liker_profiles = UserProfile.objects.filter(
        user_id__in=liker_ids
    ).select_related('user')

    return render(request, 'profiles/likes_received_list.html', {
        'profiles': liker_profiles
    })

@login_required
def submit_complaint(request, pk):
    """Подача жалобы на пользователя"""
    reported_user = get_object_or_404(User, pk=pk)

    # Валидация
    if reported_user == request.user:
        messages.error(request, 'Нельзя пожаловаться на себя.')
        return redirect('profiles:profile_detail', pk=pk)

    if request.method == 'POST':
        form = ComplaintForm(request.POST)
        if form.is_valid():
            complaint = form.save(commit=False)
            complaint.reporter = request.user
            complaint.reported_user = reported_user
            complaint.save()

            messages.success(request, 'Жалоба отправлена.')
            return redirect('profiles:profile_detail', pk=pk)
    else:
        form = ComplaintForm()

    return render(request, 'profiles/submit_complaint.html', {
        'form': form,
        'reported_user': reported_user
    })