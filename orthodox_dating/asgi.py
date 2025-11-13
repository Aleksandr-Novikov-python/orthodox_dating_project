import os
import django

# Сначала указываем настройки Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'orthodox_dating.settings')

# Затем запускаем инициализацию Django
django.setup()

# Импортируем остальное
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from orthodox_dating.safe_requests import patch_requests
import profiles.routing

patch_requests()

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            profiles.routing.websocket_urlpatterns
        )
    ),
})



