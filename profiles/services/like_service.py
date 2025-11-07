
from profiles.models import Like


def check_mutual_like(user1, user2):
    """Проверка взаимной симпатии между двумя пользователями"""
    return (
        Like.objects.filter(user_from=user1, user_to=user2).exists() and
        Like.objects.filter(user_from=user2, user_to=user1).exists()
    )