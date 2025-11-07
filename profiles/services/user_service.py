from django.db.models import Max
from profiles.models import Like, Message, UserSession

class UserService:
    @staticmethod
    def check_mutual_like(user1, user2):
        """Проверка взаимной симпатии"""
        return (
            Like.objects.filter(user_from=user1, user_to=user2).exists() and
            Like.objects.filter(user_from=user2, user_to=user1).exists()
        )

    @staticmethod
    def get_user_conversations(user):
        """Получить список собеседников"""
        sent_to = Message.objects.filter(
            sender=user,
            is_deleted_by_sender=False
        ).values_list('receiver_id', flat=True)

        received_from = Message.objects.filter(
            receiver=user,
            is_deleted_by_receiver=False
        ).values_list('sender_id', flat=True)

        interlocutor_ids = set(sent_to) | set(received_from)

        from django.contrib.auth import get_user_model
        User = get_user_model()

        return User.objects.filter(
            id__in=interlocutor_ids
        ).select_related('userprofile').annotate(
            last_message_time=Max('sent_messages__timestamp')
        ).order_by('-last_message_time')

    @staticmethod
    def update_session_stats(user, **kwargs):
        """Обновить статистику сессии"""
        try:
            session = UserSession.objects.filter(
                user=user,
                logout_time__isnull=True
            ).latest('login_time')

            for field, increment in kwargs.items():
                current = getattr(session, field, 0)
                setattr(session, field, current + increment)

            session.save(update_fields=list(kwargs.keys()))

        except UserSession.DoesNotExist:
            pass