import json
import os
from functools import wraps
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from profiles.models import TelegramUser

# Получаем ключ из настроек или переменных окружения
API_SECRET_KEY = os.getenv('API_SECRET_KEY', 'your_very_secret_key_here_change_this')

def require_api_key(view_func):
    """Декоратор для проверки Bearer токена"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        auth_header = request.headers.get('Authorization')

        if not auth_header or not auth_header.startswith('Bearer '):
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        token = auth_header.replace('Bearer ', '')

        if token != API_SECRET_KEY:
            return JsonResponse({'error': 'Invalid API key'}, status=401)

        return view_func(request, *args, **kwargs)
    return _wrapped_view

@csrf_exempt
@require_http_methods(["POST"])
@require_api_key
def check_user(request):
    """Проверка регистрации пользователя"""
    try:
        data = json.loads(request.body)
        telegram_id = data.get('telegram_id')

        if not telegram_id:
            return JsonResponse({'error': 'telegram_id required'}, status=400)

        # Проверка в БД через Django ORM
        is_registered = TelegramUser.objects.filter(telegram_id=telegram_id).exists()

        # Если нужно вернуть данные пользователя при наличии
        user_data = None
        if is_registered:
            user = TelegramUser.objects.get(telegram_id=telegram_id)
            user_data = {
                'first_name': user.first_name,
                'username': user.username
            }

        return JsonResponse({
            'is_registered': is_registered,
            'telegram_id': telegram_id,
            'user_data': user_data
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
@require_api_key
def register_user(request):
    """Регистрация нового пользователя"""
    try:
        data = json.loads(request.body)

        telegram_id = data.get('telegram_id')
        email = data.get('email')
        phone = data.get('phone')

        if not all([telegram_id, email, phone]):
            return JsonResponse({'error': 'Missing required fields'}, status=400)

        # Проверка на дубликаты
        if TelegramUser.objects.filter(telegram_id=telegram_id).exists():
            return JsonResponse({'message': 'User already exists', 'field': 'telegram_id'}, status=409)

        if TelegramUser.objects.filter(email=email).exists():
            return JsonResponse({'message': 'Email already taken', 'field': 'email'}, status=409)

        # Создание пользователя
        user = TelegramUser.objects.create(
            telegram_id=telegram_id,
            username=data.get('username'),
            first_name=data.get('first_name'),
            email=email,
            phone=phone
        )

        return JsonResponse({
            'success': True,
            'message': 'User registered successfully',
            'telegram_id': user.telegram_id
        }, status=201)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["GET"])
@require_api_key
def get_user(request, telegram_id):
    """Получение информации о пользователе"""
    user = get_object_or_404(TelegramUser, telegram_id=telegram_id)

    return JsonResponse({
        'telegram_id': user.telegram_id,
        'username': user.username,
        'first_name': user.first_name,
        'email': user.email,
        'phone': user.phone,
        'created_at': user.created_at
    })
