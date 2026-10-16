# Aprovações de pagamentos e operações

Luiz autoriza pagamentos de colaboradores (salário, VT, ajuda de custo, distrato e demais tipos) e documentos financeiros classificados como **a pagar**, incluindo fornecedores. Thiago decide as demais solicitações da central: compras, manutenção e validação de lançamentos contábeis, por exemplo. A conferência de documentos e o checklist da equipe continuam como preparação do processo.

Autorizar um pagamento não registra sua quitação. A baixa exige autorização vigente para os mesmos dados; na folha, também exige comprovante. Alterações de valor, beneficiário, PIX, período, vencimento ou demais dados autorizados exigem nova decisão. Rejeições só são reenviadas por ação explícita. Recorrências futuras recebem autorização própria. Importações de comprovantes históricos já pagos não geram aprovações retroativas.

## Configuração necessária antes da ativação

Os logins confirmados já são os padrões da aplicação e constam no `.env.example`:

- `APROVADOR_PAGAMENTOS_USERNAME=admin@construipem.com.br`: Luiz.
- `APROVADOR_OPERACIONAL_USERNAME=thiago001`: Thiago.

As variáveis do ambiente podem substituir esses padrões. Caso tenham sido definidas com valor vazio durante a preparação, preencha-as com os logins acima; um valor explicitamente vazio continua bloqueando a finalidade correspondente. A aplicação não cria usuários automaticamente: as duas contas precisam existir e estar ativas no banco do ERP.

Os nomes visíveis não são usados para identificar usuários. Não existe substituição automática por CEO, administrador ou superusuário. Sem conta ativa configurada, a criação/decisão correspondente é bloqueada.

## Ativação e conferência

1. Confira se as contas acima existem e estão ativas; corrija variáveis antigas ou vazias que substituam os padrões.
2. Execute `python manage.py migrate` no ambiente correto.
3. Execute `python manage.py redistribuir_aprovacoes` para conferir os responsáveis e as quantidades sem gravar.
4. Execute `python manage.py redistribuir_aprovacoes --apply` para redistribuir pendências operacionais e criar as autorizações de pagamentos ainda pendentes.
5. Confira a central web e móvel com cada conta: Luiz recebe somente pagamentos e Thiago somente operações. Decisões concluídas mantêm responsável e histórico originais.

O comando pode ser repetido sem duplicar solicitações equivalentes. Ele não marca pagamentos como pagos nem aprova solicitações automaticamente.

## Notificações

As notificações internas de decisão seguem o responsável nominal. Para Telegram, configure separadamente `TELEGRAM_TOKEN_APROVACOES_PAGAMENTO` / `TELEGRAM_CHAT_ID_APROVACOES_PAGAMENTO` e `TELEGRAM_TOKEN_APROVACOES_OPERACIONAIS` / `TELEGRAM_CHAT_ID_APROVACOES_OPERACIONAIS`. Se um par não estiver configurado, esse canal não envia; não há alternativa pelo chat do CEO. Avisos informativos das equipes continuam independentes das convocações para decidir.
