"""Configuração explícita de responsáveis para regressões dos fluxos antigos."""

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse


def configurar_aprovadores(testcase):
    configuracao = override_settings(
        APROVADOR_OPERACIONAL_USERNAME='ceo_premium',
        APROVADOR_PAGAMENTOS_USERNAME='luiz_teste',
    )
    configuracao.enable()
    testcase.addCleanup(configuracao.disable)
    get_user_model().objects.get_or_create(username='luiz_teste')


def autorizar_pagamento(testcase, pagamento):
    from core.payment_approvals import sincronizar_aprovacao_pagamento
    from django.test import Client

    aprovacao = sincronizar_aprovacao_pagamento(pagamento)
    cliente = Client()
    cliente.force_login(get_user_model().objects.get(username='luiz_teste'))
    resposta = cliente.post(reverse('aprovar_registro', args=[aprovacao.pk]))
    testcase.assertEqual(resposta.status_code, 302, resposta.content[:300])
    aprovacao.refresh_from_db()
    testcase.assertEqual(aprovacao.status, 'aprovado')
    return aprovacao
