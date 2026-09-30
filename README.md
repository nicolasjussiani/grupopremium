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

## Consulta de entregas

O perfil **Entregas — somente consulta** entra diretamente em `/entregas/`.
Exibe materiais de RCs com status `aprovada`, agrupados e filtráveis por unidade,
com quantidade, unidade de medida e situação do item. Itens cancelados não aparecem.
A situação de compra externa continua visível: aprovação não comprova disponibilidade
física para entrega. Valores, justificativas e anexos não são exibidos.

Após publicar, execute `python manage.py migrate`. Em **Usuários > Novo**, cadastre
Eric com usuário e senha e selecione esse perfil; o e-mail pode ficar vazio.
Não marque acessos adicionais. O perfil bloqueia os demais módulos, APIs e alterações,
mesmo quando a conta possui grupos antigos. A conta não é criada pela migração.

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
- Dominios de deploy da Vercel sao adicionados automaticamente a
  `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS`; dominios personalizados adicionais
  devem ser informados nessas variaveis.
- A ausencia de `DATABASE_URL` em Vercel/serverless impede a inicializacao.
- O armazenamento S3 e obrigatorio em Vercel/serverless.
- Os arquivos dos formularios sao enviados pelo navegador diretamente ao
  Supabase Storage por URL S3 temporaria. O PostgreSQL guarda somente a
  referencia do objeto; isso evita o limite de 4,5 MB das Functions da Vercel.
- O limite da aplicacao para upload direto e 50 MB por arquivo.

## Folha salarial e VT antecipado

Na Folha de Pagamento, **Calcular salários do mês** abre a revisão por colaborador.
Informe salário mensal, dias do período antes das faltas (até 30), gratificação integral,
faltas a descontar, outros descontos/adiantamentos e vencimento. O servidor calcula:
`salário / 30 × (dias do período − faltas) + gratificação − outros descontos`.
Arredonda somente o resultado. O quadro mostra as datas das faltas da presença e
permite editar os números do cálculo sem reescrever a lista de presença. Repetir o
salvamento atualiza o salário pendente; salários pagos ficam somente para consulta.

O VT/ajuda semanal passa a antecipar a semana que começa na segunda selecionada.
Informe jornada (normalmente 5 ou 6 dias), dias previstos e faltas anteriores já pagas
a descontar. É possível corrigir o valor diário do desconto quando a tarifa anterior
for diferente e lançar outros descontos. Sem preenchimento, a diária do desconto é
calculada como valor semanal dividido pela jornada. Novos admitidos até o domingo
da semana aparecem mesmo sem presença anterior. Dias sem registro não viram falta.
A sugestão de faltas a descontar só é automática quando há antecipação paga da semana
anterior; para os demais casos, confira e informe os dias manualmente.

A programação salva a base semanal e os parâmetros por semana. Ler as telas não
altera pagamentos anteriores. Pagamentos já realizados preservam o cálculo salvo;
a próxima antecipação exige nova revisão. Lançamentos antigos continuam com seus
valores e cálculo histórico. Totais sem valor positivo são recusados para revisão.
Execute `python manage.py migrate` antes de publicar para aplicar
`0028_calculo_salario_vt_antecipado`.

## PWA de aprovacoes no iPhone

- Acesse `/mobile/` com um superusuario ou membro dos grupos `Admin_Global` ou
  `Diretoria_Final`.
- No Safari do iPhone, use **Compartilhar > Adicionar a Tela de Inicio**.
- O aplicativo instalado abre somente a central de notificacoes, aprovacoes,
  detalhes dos processos e historico de decisoes.
- O botao **Ativar alertas** habilita avisos enquanto a PWA estiver ativa. Para
  alertas em segundo plano sera necessario configurar Web Push/VAPID em uma
  etapa posterior.
- Paginas e dados autenticados nao sao armazenados para uso offline.
- Na Vercel, cada salvamento aceita no maximo 4 MB somando os novos anexos;
  documentos adicionais devem ser enviados em etapas.
- Migrações devem ser executadas pelo processo de deploy, nunca por uma rota HTTP.
- Aprovadores devem pertencer aos grupos criados por `criar_grupos`.
- O grupo `Diretoria_Final` substitui verificacoes baseadas em nome de usuario.
- O seed exige `DEBUG=True`, `ALLOW_DEMO_SEED=True` e uma senha em
  `SEED_DEFAULT_PASSWORD`.

## Credenciais historicamente expostas

Antes de qualquer novo deploy, rotacione as credenciais de Supabase/PostgreSQL,
S3, Gemini e Telegram. Remover valores do arquivo atual nao invalida segredos que
ja foram publicados no historico Git.
