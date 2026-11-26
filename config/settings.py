"""
Django settings for the Inventory Management API.

Not a single configuration value is hardcoded here: everything comes from
``.env`` through ``config.env`` (python-dotenv plus typed, fail-fast
accessors), which raises ``ImproperlyConfigured`` for any key that is missing
or unparsable. ``.env.example`` is the committed template to copy.
"""

from config import env

env.load()

BASE_DIR = env.BASE_DIR


# Core
# -----------------------------------------------------------------------------

SECRET_KEY = env.get('DJANGO_SECRET_KEY')

DEBUG = env.get_bool('DJANGO_DEBUG')

ALLOWED_HOSTS = env.get_list('DJANGO_ALLOWED_HOSTS')

CSRF_TRUSTED_ORIGINS = env.get_list('DJANGO_CSRF_TRUSTED_ORIGINS')


# Application definition
# -----------------------------------------------------------------------------

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'django_filters',
    'drf_spectacular',
    # Ships the Swagger UI / ReDoc assets so the docs need no CDN.
    'drf_spectacular_sidecar',
]

LOCAL_APPS = [
    'apps.common',
    'apps.companies',
    'apps.users',
    'apps.warehouses',
    'apps.products',
    'apps.transactions',
    'apps.reports',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'


# Database
# -----------------------------------------------------------------------------
# PostgreSQL is the target database. ``USE_SQLITE=1`` exists purely so the test
# suite can be executed on a machine without a running PostgreSQL instance.

if env.get_bool('USE_SQLITE'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': env.get('POSTGRES_DB'),
            'USER': env.get('POSTGRES_USER'),
            'PASSWORD': env.get('POSTGRES_PASSWORD'),
            'HOST': env.get('POSTGRES_HOST'),
            'PORT': env.get_int('POSTGRES_PORT'),
            'CONN_MAX_AGE': env.get_int('DB_CONN_MAX_AGE'),
            'ATOMIC_REQUESTS': False,
        }
    }

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Cache / Redis
# -----------------------------------------------------------------------------
# Redis backs three things: the report cache, the transaction rate limit
# counters and the session cache.

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': env.get('REDIS_URL'),
        'KEY_PREFIX': env.get('REDIS_KEY_PREFIX'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'IGNORE_EXCEPTIONS': False,
        },
    }
}

SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'
SESSION_CACHE_ALIAS = 'default'
SESSION_COOKIE_NAME = 'inventory_sessionid'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = env.get_bool('SESSION_COOKIE_SECURE')
CSRF_COOKIE_SECURE = env.get_bool('CSRF_COOKIE_SECURE')


# Authentication
# -----------------------------------------------------------------------------

AUTH_USER_MODEL = 'users.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

PASSWORD_RESET_TIMEOUT = env.get_int('PASSWORD_RESET_TIMEOUT')


# Django REST Framework
# -----------------------------------------------------------------------------

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'apps.common.permissions.IsCompanyEmployee',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'apps.common.pagination.PageNumberPagination',
    'PAGE_SIZE': env.get_int('API_PAGE_SIZE'),
    'DEFAULT_THROTTLE_CLASSES': [],
    'DEFAULT_THROTTLE_RATES': {
        # One employee may not create more than 50 transactions per minute.
        'transaction_create': env.get('TRANSACTION_THROTTLE_RATE'),
        'auth': env.get('AUTH_THROTTLE_RATE'),
    },
    'EXCEPTION_HANDLER': 'apps.common.exceptions.api_exception_handler',
    'TEST_REQUEST_DEFAULT_FORMAT': 'json',
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}


# OpenAPI / Swagger
# -----------------------------------------------------------------------------
# Schema at /api/schema/, Swagger UI at /api/docs/, ReDoc at /api/redoc/.

SPECTACULAR_SETTINGS = {
    'TITLE': 'Inventory Management API',
    'DESCRIPTION': (
        'REST API for warehouse stock management: products, warehouses and '
        'stock movements (IN / OUT / TRANSFER).\n\n'
        '**Stock is never stored.** Every balance and stock value is derived '
        'from the transaction ledger at read time, so the figures cannot drift '
        'away from the history.\n\n'
        '### Authentication\n'
        'Django sessions + cookies (no JWT). Register via '
        '`POST /api/auth/register/`, then `POST /api/auth/login/`. Unsafe '
        'requests made with a session cookie must carry the `X-CSRFToken` '
        'header; the login response returns the token and '
        '`GET /api/auth/csrf/` hands out a fresh one. The "Try it out" button '
        'below works once you are signed in, because the browser sends both '
        'cookies.\n\n'
        '### Multi-tenancy\n'
        'Every employee belongs to a company and only ever sees that '
        "company's warehouses, products and transactions.\n\n"
        '### Rate limiting\n'
        'Creating transactions is limited to 50 per employee per minute '
        '(counters in Redis); the credential endpoints allow 30 attempts per '
        'IP per minute.'
    ),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    # Self-hosted UI assets (drf_spectacular_sidecar) instead of a CDN.
    'SWAGGER_UI_DIST': 'SIDECAR',
    'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
    'REDOC_DIST': 'SIDECAR',
    'SCHEMA_PATH_PREFIX': '/api',
    'COMPONENT_SPLIT_REQUEST': True,
    'SORT_OPERATIONS': False,
    'ENUM_NAME_OVERRIDES': {
        'TransactionTypeEnum': 'apps.transactions.models.InventoryTransaction.TransactionType',
    },
    # Emitted into the page verbatim (drf-spectacular passes a string through
    # unchanged), which is what allows the interceptor below: it copies the
    # csrftoken cookie into the X-CSRFToken header, so "Try it out" works for
    # POST/PATCH/DELETE under session authentication.
    'SWAGGER_UI_SETTINGS': r"""{
        persistAuthorization: true,
        displayRequestDuration: true,
        filter: true,
        requestInterceptor: (request) => {
            const csrf = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
            if (csrf) {
                request.headers['X-CSRFToken'] = decodeURIComponent(csrf[1]);
            }
            return request;
        },
    }""",
    'TAGS': [
        {'name': 'auth', 'description': 'Registration, session login/logout, passwords'},
        {'name': 'employees', 'description': 'Colleagues of the signed-in employee'},
        {'name': 'companies', 'description': 'The company an employee belongs to'},
        {'name': 'warehouses', 'description': 'Warehouses and the stock they hold'},
        {'name': 'products', 'description': 'Catalogue, soft delete, calculated stock'},
        {'name': 'transactions', 'description': 'The append-only stock movement ledger'},
        {'name': 'reports', 'description': 'Aggregates, Redis cached report, CSV/JSON export'},
    ],
}


# Internationalization
# -----------------------------------------------------------------------------

LANGUAGE_CODE = 'en-us'
TIME_ZONE = env.get('TIME_ZONE')
USE_I18N = True
USE_TZ = True


# Static files
# -----------------------------------------------------------------------------

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'


# Email
# -----------------------------------------------------------------------------
# Configured through MAILERS (the EMAIL_* settings are deprecated as of this
# Django version). The SMTP credentials are only read when the SMTP backend is
# selected, so a console setup needs no mail server at all.

_mailer_backend = env.get('EMAIL_BACKEND')
_mailer = {'BACKEND': _mailer_backend}

if _mailer_backend.endswith('smtp.EmailBackend'):
    _mailer['OPTIONS'] = {
        'host': env.get('EMAIL_HOST'),
        'port': env.get_int('EMAIL_PORT'),
        'username': env.get('EMAIL_HOST_USER'),
        'password': env.get('EMAIL_HOST_PASSWORD'),
        'use_tls': env.get_bool('EMAIL_USE_TLS'),
    }

MAILERS = {'default': _mailer}

DEFAULT_FROM_EMAIL = env.get('DEFAULT_FROM_EMAIL')


# Project specific
# -----------------------------------------------------------------------------

# How long the (expensive) warehouse value report may stay in Redis. The entry
# is invalidated eagerly whenever stock moves, so this is only a safety net.
REPORT_CACHE_TTL = env.get_int('REPORT_CACHE_TTL')

# Template used to build the link sent in the password reset email.
PASSWORD_RESET_URL_TEMPLATE = env.get('PASSWORD_RESET_URL_TEMPLATE')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {'format': '[{levelname}] {name}: {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'simple'},
    },
    'root': {'handlers': ['console'], 'level': env.get('LOG_LEVEL')},
}
