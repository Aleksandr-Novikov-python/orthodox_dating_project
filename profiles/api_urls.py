from django.urls import path
from . import views

app_name = 'api'

urlpatterns = [
    path('messages/<int:pk>/new/<str:last_timestamp>/', views.get_new_messages),
    path('messages/<int:pk>/delete/', views.delete_message_ajax),
    path('comment/<int:comment_id>/like/', views.like_comment),
    path('comment/<int:comment_id>/dislike/', views.dislike_comment),
]