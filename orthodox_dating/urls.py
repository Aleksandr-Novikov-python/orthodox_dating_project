
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from profiles.views import CustomLogoutView


from django.conf import settings
from pathlib import Path

if settings.DEBUG:
    profile_dir = Path(settings.SILK_PROFILE_DIR)
    print("Silk реально сохраняет профили в:", profile_dir)
# ==============================================================================
# ОСНОВНЫЕ URL
# ==============================================================================

urlpatterns = [
    # Админ-панель
    path('admin/', admin.site.urls),

    # ==============================================================================
    # АУТЕНТИФИКАЦИЯ
    # ==============================================================================

    # Вход/Выход
    path('login/',
         auth_views.LoginView.as_view(
             template_name='profiles/login.html',
             redirect_authenticated_user=True  # Редирект если уже залогинен
         ),
         name='login'),

    path('logout/', CustomLogoutView.as_view(), name='logout'),

    # Сброс пароля
    path('password-reset/',
         auth_views.PasswordResetView.as_view(
             template_name='profiles/password_reset_form.html',
             email_template_name='registration/password_reset_email.html',
             subject_template_name='registration/password_reset_subject.txt',
             success_url='/password-reset/done/'
         ),
         name='password_reset'),

    path('password-reset/done/',
         auth_views.PasswordResetDoneView.as_view(
             template_name='profiles/password_reset_done.html'
         ),
         name='password_reset_done'),

    path('password-reset-confirm/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(
             template_name='profiles/password_reset_confirm.html',
             success_url='/password-reset-complete/'
         ),
         name='password_reset_confirm'),

    path('password-reset-complete/',
         auth_views.PasswordResetCompleteView.as_view(
             template_name='profiles/password_reset_complete.html'
         ),
         name='password_reset_complete'),

    # Смена пароля (для залогиненных пользователей)
    path('password-change/',
         auth_views.PasswordChangeView.as_view(
             template_name='profiles/password_change_form.html',
             success_url='/password-change/done/'
         ),
         name='password_change'),

    path('password-change/done/',
         auth_views.PasswordChangeDoneView.as_view(
             template_name='profiles/password_change_done.html'
         ),
         name='password_change_done'),

    path('api', include('profiles.api_urls')),

    # ==============================================================================
    # ПРИЛОЖЕНИЕ PROFILES
    # ==============================================================================

    # Все остальные URL из приложения profiles
    path('', include('profiles.urls', namespace='profiles')),

]

# ==============================================================================
# МЕДИА ФАЙЛЫ (ТОЛЬКО В DEVELOPMENT)
# ==============================================================================

if settings.DEBUG:
    # Отдача медиа-файлов в режиме разработки
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += [path('silk/', include('silk.urls', namespace='silk'))]



# ==============================================================================
# ДОПОЛНИТЕЛЬНЫЕ НАСТРОЙКИ АДМИНКИ
# ==============================================================================

# Кастомизация админ-панели
admin.site.site_header = 'Администрирование Orthodox Dating'
admin.site.site_title = 'Orthodox Dating Admin'
admin.site.index_title = 'Панель управления'