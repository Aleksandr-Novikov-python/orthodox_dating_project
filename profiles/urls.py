# -*- coding: utf-8 -*-
from django.urls import path

from profiles.views import CustomLogoutView
from . import views
from profiles.views import (
    OrthodoxCalendarView,
    CalendarAPIView,
    CalendarMonthView,
    LoggedOutView
)

app_name = 'profiles'

urlpatterns = [
    # ==============================================================================
    # ГЛАВНАЯ И РЕГИСТРАЦИЯ
    # ==============================================================================
    path('', views.home_page, name='home'),
    path('register/', views.register, name='register'),


    # ==============================================================================
    # ПРОФИЛИ
    # ==============================================================================
    path('profiles/', views.profile_list, name='profile_list'),
    path('profile/<int:pk>/', views.profile_detail, name='profile_detail'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('profile/photo/delete/<int:photo_id>/', views.delete_photo, name='delete_photo'),

    # ==============================================================================
    # СИМПАТИИ
    # ==============================================================================
    path('like/<int:pk>/', views.add_like, name='add_like'),
    path('likes-received/', views.likes_received_list, name='likes_received_list'),

    # ==============================================================================
    # СООБЩЕНИЯ
    # ==============================================================================
    path('inbox/', views.inbox, name='inbox'),
    path('conversation/<int:pk>/', views.conversation_detail, name='conversation_detail'),

    # AJAX endpoints для сообщений
    path('api/messages/<int:pk>/new/<str:last_timestamp>/',
         views.get_new_messages,
         name='get_new_messages'),
    path('api/messages/<int:pk>/delete/',
         views.delete_message_ajax,
         name='delete_message_ajax'),

    # ==============================================================================
    # УВЕДОМЛЕНИЯ
    # ==============================================================================
    path('notifications/', views.notification_list, name='notification_list'),
    path('notifications/mark-all-read/', views.mark_all_notifications_read, name='mark_all_notifications_read'),



    # ==============================================================================
    # БЛОГ
    # ==============================================================================
    path('blog/', views.post_list, name='post_list'),
    path('blog/post/<slug:slug>/', views.post_detail, name='post_detail'),

    # ==============================================================================
    # Православный календарь
    # ==============================================================================
     # Основной календарь
    path('calendar/', OrthodoxCalendarView.as_view(), name='calendar'),
    # API endpoint
    path('api/calendar/', CalendarAPIView.as_view(), name='calendar_api'),
    # Месячный вид
    path('calendar/month/', CalendarMonthView.as_view(), name='calendar_month'),

    # AJAX endpoints для комментариев
    path('api/comment/<int:comment_id>/like/',
         views.like_comment,
         name='like_comment'),
    path('api/comment/<int:comment_id>/dislike/',
         views.dislike_comment,
         name='dislike_comment'),

    # ==============================================================================
    # ЖАЛОБЫ
    # ==============================================================================
    path('complaint/<int:pk>/', views.submit_complaint, name='submit_complaint'),
    # ==============================================================================
    # СТАТИЧЕСКИЕ СТРАНИЦЫ
    # ==============================================================================
    path('page/<slug:slug>/', views.static_page_view, name='static_page'),

    # ==============================================================================
    # logout
    # ==============================================================================
     path('logout/', CustomLogoutView.as_view(), name='logout'),
     path('logged_out/', LoggedOutView.as_view(), name='logged_out'),

]


