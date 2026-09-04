# ERP Grupo PremiumBR

ERP interno desenvolvido em Django para recrutamento, admissao, administrativo,
SESMET, compras, financeiro e manutencao.

## Requisitos

- Python 3.11 ou 3.12
- PostgreSQL em producao; SQLite e suportado somente para desenvolvimento local
- Bucket S3/Supabase Storage para anexos em producao

## Instalacao local

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Gere uma chave e substitua SECRET_KEY no .env:
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
python manage.py migrate
python manage.py criar_grupos
python manage.py runserver
```

Substitua `SECRET_KEY` no `.env` pelo valor gerado. Em desenvolvimento,
`DEBUG=True` usa SQLite e armazenamento local. Em producao, use `DEBUG=False`,
configure PostgreSQL, hosts/origens HTTPS e armazenamento S3. Nunca reutilize
valores presentes no historico antigo do repositorio.

## Validacao

```powershell
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
python manage.py test
```

Os testes usam SQLite em memoria e armazenamento em memoria; nao acessam o banco
ou o bucket configurado nos arquivos `.env`.

## Seguranca e operacao

- `SECRET_KEY` deve ser aleatoria e ter pelo menos 50 caracteres.
- `DATABASE_URL` e obrigatoria sempre que `DEBUG=False`.
- `ALLOWED_HOSTS` nao aceita `*` em producao.
- A ausencia de `DATABASE_URL` em Vercel/serverless impede a inicializacao.
- O armazenamento S3 e obrigatorio em Vercel/serverless.
- Migrações devem ser executadas pelo processo de deploy, nunca por uma rota HTTP.
- Aprovadores devem pertencer aos grupos criados por `criar_grupos`.
- O grupo `Diretoria_Final` substitui verificacoes baseadas em nome de usuario.
- O seed exige `DEBUG=True`, `ALLOW_DEMO_SEED=True` e uma senha em
  `SEED_DEFAULT_PASSWORD`.

## Credenciais historicamente expostas

Antes de qualquer novo deploy, rotacione as credenciais de Supabase/PostgreSQL,
S3, Gemini e Telegram. Remover valores do arquivo atual nao invalida segredos que
ja foram publicados no historico Git.
