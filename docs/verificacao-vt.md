# Verificação da interface e do fluxo de VT

Data: 26/09/2026. Revisão local sobre a versão `47e86ac`, com base e pessoas fictícias. Nenhum pagamento real foi alterado.

## Resultado

91 testes automatizados passaram. A inspeção no navegador cobriu a programação semanal, a folha, a visão de benefícios, o histórico, o formulário de pagamento e o relatório, com telas de computador e de celular (390 e 320 pixels). Não foram observados erros de console nas telas verificadas nem rolagem horizontal da página nos tamanhos de celular; tabelas mantêm sua própria rolagem.

## Problemas corrigidos

| Problema | Correção e evidência |
| --- | --- |
| Datas preenchidas pelo sistema apareciam vazias nos campos de pagamento. | Formato compatível com campos de data. Verificados início, fim, vencimento e data de pagamento na criação/edição. |
| O formulário consultava presenças da competência do pagamento, enquanto a programação usava a semana anterior. | VT e ajuda de custo usam a segunda ao domingo anteriores. Um cenário com três presenças foi conferido no navegador. Ausência de registro continua diferente de zero presenças. |
| Busca e filtros desapareciam ao salvar uma decisão. | Estado da lista mantido por tela e semana; busca, benefício, situação e página persistem na sessão do navegador. |
| Toda a equipe aparecia de uma vez. | Exibição de seis pessoas por página, com busca sobre toda a lista e contagem dos resultados. Sem JavaScript, os registros continuam acessíveis. |
| Edições poderiam ser perdidas ao sair da tela. | Indicação de alteração não salva e aviso do navegador ao sair com decisões pendentes de gravação. |
| Uma confirmação conflitante podia gerar erro 500. | Bloqueio explicado na tela, preservando o lançamento pendente e sem vincular o comprovante. Reproduzido em teste antes da correção. |
| Confirmar o pagamento levava à folha geral, perdendo a semana de origem. | Retorno à programação ou à folha de origem, com consulta preservada. Destinos externos são rejeitados. |
| O histórico exibia somente o primeiro comprovante. | Todos os comprovantes vinculados ficam disponíveis com seus nomes. |
| O botão de tema não mudava a aparência. | Removida a chamada duplicada; tema claro/escuro e legibilidade de indicadores conferidos. |
| Resumo e erros do formulário eram removidos automaticamente. | Avisos relevantes permanecem visíveis durante a edição. |

## Fluxos confirmados

- CLT recebe VT; PJ recebe ajuda de custo, conforme o cadastro.
- A semana pode ser revisada sem quitar a anterior. Apenas abrir a programação não cria pagamentos.
- Pagar cria ou atualiza o lançamento pendente; repetir a decisão não duplica o lançamento.
- Não precisa cancela o pendente sem apagar o histórico e não impede a revisão de outras semanas.
- Valor vazio, zero, negativo ou inválido para pagar é rejeitado.
- Colaboradores indisponíveis e datas inválidas são bloqueados pelos controles existentes.
- Pagamentos confirmados ficam protegidos na programação.
- Comprovante obrigatório, vínculo ao pagamento, validação de token e prevenção de reutilização em outro pagamento foram exercitados pelos testes.
- Permissões de leitura/escrita, autenticação e proteção CSRF foram verificadas.
- Na interface, salvar valores e confirmar um pagamento fictício com comprovante já vinculado atualizaram os totais e retornaram à semana de origem.
- Busca com acentos, filtros combinados, lista vazia e troca de página foram conferidos no navegador.
- Integração com folha, relatório e rotinas fiscais foi exercitada nos testes.

## Limites da verificação

O envio real de um novo arquivo ao armazenamento de produção e a concorrência no PostgreSQL publicado não foram exercitados nesta revisão. Os testes usaram armazenamento e banco locais de teste. A confirmação pelo navegador usou um comprovante fictício previamente vinculado.

A regra existente normaliza a data de baixa de benefícios para a segunda-feira e bloqueia dois pagamentos do mesmo benefício para a mesma pessoa nessa semana de baixa, mesmo que sejam de competências diferentes. Essa regra foi preservada; agora o conflito apresenta uma mensagem compreensível.

As correções estão no projeto local, sem publicação desta revisão.

## Testes executados

```text
python manage.py test admissional.test_programacao_vt admissional.test_comprovantes_pagamento admissional.test_historico_vt admissional.test_pagamentos_colaboradores admissional.test_relatorio_folha fiscal.tests core.test_full_site --noinput

Ran 91 tests
OK
System check identified no issues (0 silenced).
```
