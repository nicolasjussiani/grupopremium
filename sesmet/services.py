from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from core.models import Notificacao
from core.notifications import destinatarios_da_area
from sesmet.models import RegistroEPI


ORDEM_ALERTA = {'': 0, 'proximo': 1, 'urgente': 2, 'vencido': 3}


def _nivel_por_dias(dias):
    if dias < 0:
        return 'vencido'
    if dias <= 7:
        return 'urgente'
    if dias <= 15:
        return 'proximo'
    return ''


def sincronizar_alertas_epi():
    """Avança os alertas de ciclos ativos e notifica a equipe sem duplicidade."""
    hoje = timezone.localdate()
    limite = hoje + timezone.timedelta(days=15)
    alterados = defaultdict(list)
    with transaction.atomic():
        registros = list(
            RegistroEPI.objects.select_for_update().filter(
                tipo_movimentacao='retirada',
                ciclo_ativo=True,
                data_validade__lte=limite,
            ).select_related('colaborador', 'equipamento')
        )
        for registro in registros:
            dias = (registro.data_validade - hoje).days
            nivel = _nivel_por_dias(dias)
            if ORDEM_ALERTA[nivel] <= ORDEM_ALERTA.get(registro.nivel_alerta, 0):
                continue
            registro.nivel_alerta = nivel
            registro.save(update_fields=['nivel_alerta'])
            alterados[nivel].append(registro)

        if not alterados:
            return 0

        destinatarios = list(destinatarios_da_area('sesmet'))
        notificacoes = []
        configuracao = {
            'proximo': ('EPIs próximos do prazo de 90 dias', 'aviso'),
            'urgente': ('EPIs vencem em até 7 dias', 'aviso'),
            'vencido': ('EPIs com prazo de 90 dias vencido', 'erro'),
        }
        for nivel, itens in alterados.items():
            titulo, tipo = configuracao[nivel]
            exemplos = ', '.join(
                f'{item.colaborador.nome} ({item.equipamento.nome})'
                for item in itens[:3]
            )
            complemento = f' e mais {len(itens) - 3}' if len(itens) > 3 else ''
            mensagem = f'{len(itens)} ciclo(s) precisam de atenção: {exemplos}{complemento}.'
            for destinatario in destinatarios:
                notificacoes.append(Notificacao(
                    destinatario=destinatario,
                    tipo=tipo,
                    modulo='sesmet',
                    titulo=titulo,
                    mensagem=mensagem,
                    url_acao='/sesmet/',
                ))
        Notificacao.objects.bulk_create(notificacoes)
    return sum(len(itens) for itens in alterados.values())
