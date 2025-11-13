# -*- coding: utf-8 -*-
import os
from pathlib import Path
from decouple import config
import dj_database_url
# from sentry_sdk.integrations.logging import LoggingIntegration
# from sentry_sdk.integrations.django import DjangoIntegration
# from sentry_sdk.integrations.celery import CeleryIntegration
# ==============================================================================
# БАЗОВЫЕ НАСТРОЙКИ
# ==============================================================================

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)

# ALLOWED_HOSTS из переменной окружения
ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='127.0.0.1,localhost'
).split(',')

# Добавляем PythonAnywhere хост если он есть
if 'ddoltann.pythonanywhere.com' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('ddoltann.pythonanywhere.com')


# ==============================================================================
# ПРИЛОЖЕНИЯ
# ==============================================================================

INSTALLED_APPS = [
    'channels',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'profiles.apps.ProfilesConfig',
    'crispy_forms',
    'crispy_bootstrap5',
    'django_q',
]

# ==============================================================================
# SILKY
# ==============================================================================
if DEBUG:
    INSTALLED_APPS += ['silk']

    SILKY_PYTHON_PROFILER = True
    SILKY_PYTHON_PROFILER_BINARY = False

    silk_path = BASE_DIR / 'silk_prof'
    silk_path.mkdir(parents=True, exist_ok=True)
    SILK_PROFILE_DIR = str(silk_path)

    SILKY_IGNORE_PATHS = [
        '/static/',
        '/media/',
        '/favicon.ico',
    ]

    SILKY_INTERCEPT_FUNC = lambda request: not (
        request.path.endswith('.js') or 
        request.path.endswith('.css') or
        request.path.endswith('.map') or
        request.path.startswith('/static/') or
        request.path.startswith('/media/')
    )

    SILKY_MAX_RECORDED_REQUESTS = 10000
    SILKY_MAX_RECORDED_REQUESTS_CHECK_PERCENT = 10
    SILKY_MIDDLEWARE_ENABLED = DEBUG
    SILKY_MAX_RESPONSE_BODY_SIZE = 1024 * 1024  # 1MB

Q_CLUSTER = {
    'name': 'orthodox',
    'workers': 4,
    'timeout': 60,
    'retry': 120,
    'queue_limit': 50,
    'bulk': 10,
    'orm': 'default',
    'log_level': 'INFO'  # или 'DEBUG' для отладки
}

Q_CLUSTER['redis'] = {
    'host': '127.0.0.1',
    'port': 6379,
    'db': 1,
}

CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_TRACK_STARTED = True  # Позволяет видеть статус STARTED
CELERY_TASK_TIME_LIMIT = 300      # Ограничение по времени (в секундах)
CELERY_TASK_SOFT_TIME_LIMIT = 270  # например, за 30 секунд до жёсткого


# ==============================================================================
# MIDDLEWARE
# ==============================================================================

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',

    # ✅ Ваш фильтр Silk
    'profiles.middlewares.silk_filter.SilkFilterMiddleware',
    # Твоя статистика
    'profiles.middlewares.middleware.SessionTrackingMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'profiles.middlewares.middleware.UpdateLastSeenMiddleware',
]
if DEBUG:
    try:
        idx = MIDDLEWARE.index('profiles.middlewares.silk_filter.SilkFilterMiddleware')
        if 'silk.middleware.SilkyMiddleware' not in MIDDLEWARE:
            MIDDLEWARE.insert(idx + 1, 'silk.middleware.SilkyMiddleware')
    except ValueError:
        # Если фильтр отсутствует — вставить Silk в начало или логировать
        MIDDLEWARE.insert(0, 'silk.middleware.SilkyMiddleware')

# ==============================================================================
# URL И TEMPLATES
# ==============================================================================

ROOT_URLCONF = 'orthodox_dating.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'profiles.context_processors.unread_notifications_count',
                'profiles.middlewares.middleware.online_users_processor'
            ],
        },
    },
]


# ==============================================================================
# WSGI/ASGI
# ==============================================================================

WSGI_APPLICATION = 'orthodox_dating.wsgi.application'
ASGI_APPLICATION = 'orthodox_dating.asgi.application'


# ==============================================================================
# CHANNELS И REDIS
# ==============================================================================

# Настройки для Channels с fallback
redis_url = config('REDIS_URL', default='redis://127.0.0.1:6379')

try:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [redis_url],
                'capacity': 1500,
                'expiry': 10,
            },
        },
    }
except Exception:
    # Fallback на InMemoryChannelLayer для разработки
    if DEBUG:
        CHANNEL_LAYERS = {
            'default': {
                'BACKEND': 'channels.layers.InMemoryChannelLayer'
            }
        }
    else:
        raise


# ==============================================================================
# БАЗА ДАННЫХ
# ==============================================================================

# Локально - SQLite, на сервере - PostgreSQL через DATABASE_URL
default_db_url = f'sqlite:///{BASE_DIR / "db.sqlite3"}'

try:
    DATABASES = {
        'default': dj_database_url.config(
            default=default_db_url,
            conn_max_age=600,
            conn_health_checks=True,  # Проверка здоровья соединения
        )
    }
except Exception as e:
    # Fallback на SQLite если что-то пошло не так
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
    if not DEBUG:
        print(f"Warning: Database configuration failed, using SQLite: {e}")


# ==============================================================================
# КЭШИРОВАНИЕ
# ==============================================================================

# Используем Redis для кэша если доступен, иначе локальная память
if not DEBUG and redis_url:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': redis_url,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            },
            'KEY_PREFIX': 'orthodox_dating',
            'TIMEOUT': 300,  # 5 минут по умолчанию
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-snowflake',
        }
    }



# ==============================================================================
# ВАЛИДАЦИЯ ПАРОЛЕЙ
# ==============================================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# ==============================================================================
# ИНТЕРНАЦИОНАЛИЗАЦИЯ
# ==============================================================================

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Kyiv'
USE_I18N = True
USE_TZ = True


# ==============================================================================
# СТАТИЧЕСКИЕ ФАЙЛЫ
# ==============================================================================

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Хранилище для статики с компрессией
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# Дополнительные папки со статикой (только если существуют)
static_dir = BASE_DIR / 'static'
if static_dir.exists():
    STATICFILES_DIRS = [static_dir]
else:
    STATICFILES_DIRS = []


# ==============================================================================
# МЕДИА ФАЙЛЫ
# ==============================================================================

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Создаём папку media если её нет
MEDIA_ROOT.mkdir(exist_ok=True)


# ==============================================================================
# ФОРМЫ
# ==============================================================================

CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK = 'bootstrap5'


# ==============================================================================
# АУТЕНТИФИКАЦИЯ
# ==============================================================================

LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'
LOGIN_URL = 'login'

# Время жизни сессии (2 недели)
SESSION_COOKIE_AGE = 1209600
SESSION_SAVE_EVERY_REQUEST = True


# ==============================================================================
# EMAIL
# ==============================================================================

if DEBUG:
    # В режиме разработки выводим email в консоль
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    # Для продакшена - настройки SMTP
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
    EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
    EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
    EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
    EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
    DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default=EMAIL_HOST_USER)

# ==============================================================================
# ЛОГИРОВАНИЕ
# ==============================================================================

# Создаем директорию для логов если её нет
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

# ✅ PRODUCTION-READY НАСТРОЙКА ЛОГИРОВАНИЯ
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,

    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {name} {module}.{funcName}:{lineno} | {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            'format': '[{levelname}] {asctime} | {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(asctime)s %(name)s %(levelname)s %(message)s',
        },
    },

    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },

    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
            'filters': ['require_debug_true'],
        },
        'silk_errors': {
            'level': 'ERROR',  # ✅ Только ошибки, не WARNING
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/silk.log',
            'maxBytes': 1024 * 1024 * 10,  # 10 MB
            'backupCount': 3,
        },
        'file_all': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'django_all.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
        'file_errors': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'django_errors.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 10,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
        'file_security': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'security.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 10,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
            'filters': ['require_debug_false'],
            'formatter': 'verbose',
        },
    },

    'loggers': {
        'django': {
            'handlers': ['console', 'file_all', 'file_errors'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['file_errors', 'mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['file_security', 'mail_admins'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django_q': {
            'handlers': ['console', 'file_all', 'file_errors'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'profiles': {
            'handlers': ['console', 'file_all', 'file_errors'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console', 'file_all', 'file_errors'],
            'level': 'INFO',
            'propagate': False,
        },
        'redis': {
            'handlers': ['console', 'file_all', 'file_errors'],
            'level': 'WARNING',
            'propagate': False,
        },
        'photo_signals': {
            'handlers': ['console', 'file_all', 'file_errors'],
            'level': 'INFO',
            'propagate': False,
        },
        'silk': {
            'handlers': ['silk_errors'],
            'level': 'ERROR',  # Было: 'WARNING'
            'propagate': False,
        },
        'silk.model_factory': {
            'handlers': ['silk_errors'],
            'level': 'ERROR',  # ✅ Игнорируем WARNING
            'propagate': False,
        },       
        'root': {
            'handlers': ['console', 'file_all', 'file_errors'],
            'level': 'INFO',
        },
    },
}

# ✅ ДОПОЛНИТЕЛЬНЫЕ НАСТРОЙКИ ДЛЯ PRODUCTION

# Email для отправки ошибок админам
ADMINS = [
    ('Admin Name', 'admin@example.com'),
]

MANAGERS = ADMINS

# Server email для отправки ошибок
SERVER_EMAIL = 'noreply@yoursite.com'
EMAIL_SUBJECT_PREFIX = '[Django]'
# ==============================================================================
# НАСТРОЙКИ БЕЗОПАСНОСТИ (PRODUCTION)
# ==============================================================================

if not DEBUG:
    # Cookies
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_HTTPONLY = True

    # HTTPS
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

    # HSTS
    SECURE_HSTS_SECONDS = 31536000  # 1 год
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # Защита от XSS и других атак
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'

    # Допустимые хосты для CSRF
    CSRF_TRUSTED_ORIGINS = [
        'https://ddoltann.pythonanywhere.com',
        # Добавьте другие домены если нужно
    ]

else:
    # Разработка - отключаем некоторые проверки
    SECURE_SSL_REDIRECT = False


# ==============================================================================
# РАЗНОЕ
# ==============================================================================

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Ограничение размера загружаемых файлов (5MB)
DATA_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB

# Timeout для запросов
CONN_MAX_AGE = 600


# ==============================================================================
# SETTINGS ДЛЯ РАЗРАБОТКИ
# ==============================================================================

if DEBUG:
    # Дополнительные настройки для удобства разработки
    INTERNAL_IPS = [
        '127.0.0.1',
        'localhost',
    ]

    # Можно добавить django-debug-toolbar если нужно
    # INSTALLED_APPS += ['debug_toolbar']
    # MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']