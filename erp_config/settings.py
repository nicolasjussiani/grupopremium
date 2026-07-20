"""
ERP Grupo PremiumBR - Settings
"""
from pathlib import Path
import os
import sys
import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Carrega .env explicitamente do diretório raiz do projeto
env_path = BASE_DIR / '.env'
env_local_path = BASE_DIR / '.env.local'
load_dotenv(dotenv_path=env_path)
load_dotenv(dotenv_path=env_local_path, override=True)

# Diagnóstico: mostra se DATABASE_URL foi encontrada
_db_url_found = os.environ.get('DATABASE_URL')
print(f'[ERP-DIAG] .env path: {env_path} (exists: {env_path.exists()})', file=sys.stderr)
print(f'[ERP-DIAG] DATABASE_URL found: {bool(_db_url_found)}', file=sys.stderr)
if _db_url_found:
    # Mostra só o host para não expor a senha
    print(f'[ERP-DIAG] DATABASE_URL host: ...{_db_url_found.split("@")[-1] if "@" in _db_url_found else "N/A"}', file=sys.stderr)

# ── Segurança ─────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-erp-ecopremium-2025-trip-eco-log-premium-key'
)
DEBUG = os.environ.get('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = ['*']

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
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'core.middleware.StatelessDemoMiddleware',
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
db_url = os.environ.get('DATABASE_URL')

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
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Fix for SQLite on Vercel (read-only filesystem except /tmp)
if DATABASES['default'].get('ENGINE') == 'django.db.backends.sqlite3':
    # dj_database_url might add ssl_require for sqlite which is invalid
    DATABASES['default'].pop('OPTIONS', None)
    
    is_serverless = os.environ.get('VERCEL') == '1' or os.environ.get('AWS_EXECUTION_ENV') is not None
    if is_serverless:
        import shutil
        source_db = BASE_DIR / 'db.sqlite3'
        tmp_db = '/tmp/db.sqlite3'
        try:
            if not os.path.exists(tmp_db) and os.path.exists(source_db):
                shutil.copy2(source_db, tmp_db)
            DATABASES['default']['NAME'] = tmp_db
        except Exception:
            pass

# Diagnóstico final do banco configurado
print(f'[ERP-DIAG] DB ENGINE: {DATABASES["default"]["ENGINE"]}', file=sys.stderr)
print(f'[ERP-DIAG] DB HOST: {DATABASES["default"].get("HOST", "N/A")}', file=sys.stderr)

# ── Supabase ──────────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_ANON_KEY = os.environ.get('SUPABASE_ANON_KEY', '')
SUPABASE_SERVICE_ROLE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
SUPABASE_PUBLISHABLE_KEY = os.environ.get('SUPABASE_PUBLISHABLE_KEY', '')

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ── Configuração Supabase Storage (S3) ────────────────────────────────────────
SUPABASE_S3_ENDPOINT_URL = os.environ.get('SUPABASE_S3_ENDPOINT_URL')
if SUPABASE_S3_ENDPOINT_URL:
    AWS_ACCESS_KEY_ID = os.environ.get('SUPABASE_S3_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.environ.get('SUPABASE_S3_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = os.environ.get('SUPABASE_S3_BUCKET_NAME', 'arquivos')
    AWS_S3_ENDPOINT_URL = SUPABASE_S3_ENDPOINT_URL
    AWS_S3_REGION_NAME = os.environ.get('SUPABASE_S3_REGION_NAME', 'sa-east-1')
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    AWS_S3_ADDRESSING_STYLE = 'path'
    AWS_S3_FILE_OVERWRITE = True
    AWS_DEFAULT_ACL = None
    
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

SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'

# ── Configurações de Proxy e CSRF para Vercel ─────────────────────────────────
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_TRUSTED_ORIGINS = [
    'https://*.vercel.app',
    'https://*.ecopremium.com.br',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]

