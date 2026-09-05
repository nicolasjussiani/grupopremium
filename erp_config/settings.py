"""
ERP Grupo PremiumBR - Settings
"""
from pathlib import Path
import os
import sys
from urllib.parse import urlsplit

import dj_database_url
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
RUNNING_TESTS = 'test' in sys.argv

# Carrega .env explicitamente do diretório raiz do projeto
env_path = BASE_DIR / '.env'
env_local_path = BASE_DIR / '.env.local'
if not RUNNING_TESTS:
    load_dotenv(dotenv_path=env_path)
    load_dotenv(dotenv_path=env_local_path, override=False)

# ── Segurança ─────────────────────────────────────────────────────────────────
DEBUG = os.environ.get('DEBUG', 'False').lower() in {'1', 'true', 'yes'}
SECRET_KEY = os.environ.get('SECRET_KEY')
if RUNNING_TESTS:
    DEBUG = True
    SECRET_KEY = 'django-insecure-test-only'
if not RUNNING_TESTS and (
    not SECRET_KEY
    or SECRET_KEY == 'change-me'
    or SECRET_KEY.startswith('replace-')
    or len(SECRET_KEY) < 50
):
    raise ImproperlyConfigured('SECRET_KEY deve ser exclusiva e ter pelo menos 50 caracteres.')

def _hostname_from_value(value):
    """Return only the hostname from a hostname or URL environment value."""
    value = (value or '').strip()
    if not value:
        return None
    parsed = urlsplit(value if '://' in value else f'//{value}')
    return parsed.hostname


VERCEL_HOSTS = []
for variable_name in (
    'VERCEL_URL',
    'VERCEL_BRANCH_URL',
    'VERCEL_PROJECT_PRODUCTION_URL',
    'APP_URL',
    'PUBLIC_URL',
):
    hostname = _hostname_from_value(os.environ.get(variable_name))
    if hostname and hostname not in VERCEL_HOSTS:
        VERCEL_HOSTS.append(hostname)

# Dominio canonico atual. Mantemos a origem explicita porque as variaveis
# automaticas da Vercel podem nao ser expostas ao runtime em alguns projetos.
CANONICAL_HOSTS = ('teste-eight-tau-53.vercel.app',)
for hostname in CANONICAL_HOSTS:
    if hostname not in VERCEL_HOSTS:
        VERCEL_HOSTS.append(hostname)

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
    if host.strip()
]
for hostname in VERCEL_HOSTS:
    if hostname not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(hostname)
if not DEBUG and '*' in ALLOWED_HOSTS:
    raise ImproperlyConfigured('ALLOWED_HOSTS nao pode conter curinga em producao.')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'storages',
    # Apps ERP Grupo PremiumBR
    'core',
    'recrutamento',
    'admissional',
    'administrativo',
    'sesmet',
    'compras',
    'financeiro',
    'manutencao',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'core.middleware.AcessoModuloMiddleware',
    'core.middleware.AuditLogMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'erp_config.urls'

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
            ],
        },
    },
]

WSGI_APPLICATION = 'erp_config.wsgi.application'

# ── Banco de Dados ────────────────────────────────────────────────────────────
# Em produção (Vercel), usa DATABASE_URL → Supabase PostgreSQL
# Em desenvolvimento local, usa SQLite como fallback
db_url = None if RUNNING_TESTS else os.environ.get('DATABASE_URL')
is_serverless = os.environ.get('VERCEL') == '1' or os.environ.get('AWS_EXECUTION_ENV') is not None

if not db_url and not DEBUG:
    raise ImproperlyConfigured('DATABASE_URL e obrigatoria quando DEBUG=False.')

if db_url:
    DATABASES = {
        'default': dj_database_url.config(
            default=db_url,
            conn_max_age=0,
            ssl_require=True,
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:' if RUNNING_TESTS else BASE_DIR / 'db.sqlite3',
        }
    }

# Fix for SQLite on Vercel (read-only filesystem except /tmp)
if DATABASES['default'].get('ENGINE') == 'django.db.backends.sqlite3':
    # dj_database_url might add ssl_require for sqlite which is invalid
    DATABASES['default'].pop('OPTIONS', None)
    

# ── Supabase ──────────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_ANON_KEY = os.environ.get('SUPABASE_ANON_KEY', '')
SUPABASE_SERVICE_ROLE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
SUPABASE_PUBLISHABLE_KEY = os.environ.get('SUPABASE_PUBLISHABLE_KEY', '')

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ── Configuração Supabase Storage (S3) ────────────────────────────────────────
SUPABASE_S3_ENDPOINT_URL = os.environ.get('SUPABASE_S3_ENDPOINT_URL')
if is_serverless and not RUNNING_TESTS and not SUPABASE_S3_ENDPOINT_URL:
    raise ImproperlyConfigured('O armazenamento S3 e obrigatorio em ambiente serverless.')
if RUNNING_TESTS:
    STORAGES = {
        'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }
elif SUPABASE_S3_ENDPOINT_URL:
    AWS_ACCESS_KEY_ID = os.environ.get('SUPABASE_S3_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.environ.get('SUPABASE_S3_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = os.environ.get('SUPABASE_S3_BUCKET_NAME', 'arquivos')
    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY or not AWS_STORAGE_BUCKET_NAME:
        raise ImproperlyConfigured('As credenciais e o bucket S3 devem ser configurados em conjunto.')
    AWS_S3_ENDPOINT_URL = SUPABASE_S3_ENDPOINT_URL
    AWS_S3_REGION_NAME = os.environ.get('SUPABASE_S3_REGION_NAME', 'sa-east-1')
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    AWS_S3_ADDRESSING_STYLE = 'path'
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = True
    AWS_QUERYSTRING_EXPIRE = 300
    
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
        },
    }
else:
    # Fallback local
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
        },
    }

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

AUTH_USER_MODEL = 'auth.User'


# ── Configurações de Proxy e CSRF para Vercel ─────────────────────────────────
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        'CSRF_TRUSTED_ORIGINS',
        'http://localhost:8000,http://127.0.0.1:8000',
    ).split(',')
    if origin.strip()
]
CSRF_FAILURE_VIEW = 'core.views.csrf_failure_view'
for hostname in VERCEL_HOSTS:
    origin = f'https://{hostname}'
    if origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(origin)

SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = 'Lax'
SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', str(not DEBUG)).lower() in {'1', 'true', 'yes'}
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
X_FRAME_OPTIONS = 'DENY'

DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

