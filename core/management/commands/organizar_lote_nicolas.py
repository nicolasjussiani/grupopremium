from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from admissional.models import Colaborador, PagamentoColaborador
from core.models import ArquivoImportado, OrigemArquivoImportado


PASTA_LANCAMENTOS = 'COMPROVANTES PARA LANÇAMENTO'


REVISOES = {
    '01b8c192-a8b3-466c-a40b-60ab450417ed.jpg': ('documento_financeiro', 'servico_digital', 'financeiro', 'Pagamento de Facebook Serviços Online', '120.00', '2026-09-18', 'Facebook Serviços Online do Brasil'),
    '05045150-0a74-47f9-9b3e-2d459cebb5d2.jpg': ('documento_financeiro', 'freelancer_externo', 'financeiro', 'Pagamento de freelancer Recife', '650.00', '2026-09-17', 'Nicolas Robson da Silva'),
    '0a6883a2-f755-4820-95e1-6f0be2439703.jpg': ('documento_trabalhista', 'fgts', 'rh', 'Pagamento de FGTS à CEF Matriz', '1684.95', '2026-09-18', 'CEF Matriz'),
    '12ee4aad-c3cf-48ec-bb54-9ce87d7df644.jpg': ('reembolso', 'ressarcimento_cliente', 'financeiro', 'Recibo de ressarcimento ao cliente - página 1', '375.00', '2026-09-17', 'Cesar Daniel da Silva'),
    '14bbc3ed-a52e-45fa-86a4-d40ad69e6671.jpg': ('reembolso', 'material_operacional', 'financeiro', 'Reembolso de borrifadores da unidade Vamos Betim', '200.00', '2026-09-18', 'Thiago Costa Barbosa'),
    '3d7e6141-bb97-4529-9d7e-c3e588bd2344.jpg': ('documento_financeiro', 'servico_digital', 'financeiro', 'Pagamento de serviço OpenAI LLC', '493.44', '2026-09-19', 'FRANK'),
    '4e84af0b-13e9-4cb5-a004-e0a70610dda6.jpg': ('pagamento_colaborador', 'reembolso', 'rh', 'Reembolso de material operacional - álcool tira-cola', '64.00', '2026-09-10', 'Cristiano Aparecido Pena'),
    '703504cd-dce5-4b6d-9696-587915fe2771.jpg': ('reembolso', 'ressarcimento_cliente', 'financeiro', 'Recibo de ressarcimento ao cliente - página 2', '375.00', '2026-09-17', 'Cesar Daniel da Silva'),
    '79a1feb1-6c02-4893-8dec-8d3ad2caff18.jpg': ('documento_financeiro', 'combustivel', 'financeiro', 'Compra de diesel comum', '20.00', '2026-09-09', 'Albuquerque Pneus Ltda'),
    '83cb4f7a-5c06-4768-bf5f-e62cd3f9aba1.jpg': ('documento_financeiro', 'material_operacional', 'financeiro', 'Pagamento de material operacional', '130.00', '2026-09-18', 'Polibem'),
    '8725f0dd-eb65-4ece-8703-9e8ac81a5db7.jpg': ('documento_financeiro', 'transporte', 'financeiro', 'Corrida de aplicativo', '27.15', '2026-09-16', '99 Tecnologia Ltda'),
    '919a16e6-81a1-4e33-af65-303b0fd831d3.jpg': ('pagamento_colaborador', 'distrato', 'rh', 'Pagamento de verbas rescisórias', '1634.00', '2026-09-18', 'Andre Silva Ataide'),
    '9d70aa75-1428-479d-9cce-02f0d71c163e.jpg': ('documento_financeiro', 'diaria_externa', 'financeiro', 'Uma diária e meia - unidade Vamos SJP', '195.00', '2026-09-15', '68.741.298 Bianca Vitoria Rosa'),
    '9e9fa3fb-4e49-4352-87a5-fad04d0246fc.jpg': ('pagamento_colaborador', 'salario', 'rh', 'Adiantamento salarial a descontar', '100.00', '2026-09-18', 'Luis Carlos Antonio da Silva'),
    'a4459230-5ba3-4825-af19-146a899c0269.jpg': ('pagamento_colaborador', 'freelancer', 'rh', 'Pagamento de freelancer - unidade Vamos Recife', '130.00', '2026-09-16', 'Wallace Santos da Silva'),
    'a49ea2ac-b87b-43c8-b2da-05c3791d524f.jpg': ('reembolso', 'servicos', 'financeiro', 'Reembolso por serviços', '375.00', '2026-09-18', 'Cesar Daniel da Silva'),
    'a69b860f-56c4-4398-92b1-5ec472d17cf4.jpg': ('documento_financeiro', 'transporte', 'financeiro', 'Corrida de aplicativo', '29.40', '2026-09-16', '99 Tecnologia Ltda'),
    'b9ac16d4-f379-4964-9eed-4d478a2faf00.jpg': ('documento_financeiro', 'transporte', 'financeiro', 'Corrida de aplicativo', '22.86', '2026-09-18', 'Uber do Brasil Tecnologia Ltda'),
    'd491c504-469d-41a3-a486-a7e5894e6052.jpg': ('documento_financeiro', 'combustivel', 'financeiro', 'Compra de diesel comum', '20.00', '2026-09-09', 'Albuquerque Pneus Ltda'),
    'd4b382eb-2ced-459d-8cd9-83f80a7ea6b7.jpg': ('documento_financeiro', 'boleto', 'financeiro', 'Boleto de medicina e segurança do trabalho', '90.46', '2026-09-10', 'R J Medicina e Segurança no Trabalho'),
    'dbd1f2eb-21db-4334-b7f9-13fbfe1a32cd.jpg': ('pagamento_colaborador', 'reembolso', 'rh', 'Reembolso de materiais e transporte', '209.00', '2026-09-18', 'Brendon Gabriel Santos Oliveira'),
    'dc8e01cb-bf79-4b34-8694-1b20195eedc7.jpg': ('pedido', 'uniformes', 'compras', 'Pagamento de 75 camisas', '1240.00', '2026-09-18', 'Harley Ricardo Ribeiro'),
    'df6b50e7-7af0-4858-ae1c-471648478155.jpg': ('pagamento_colaborador', 'auxilio_telefonia', 'rh', 'Auxílio telefonia das bases', '690.00', '2026-09-18', 'Ursula Fidelis Tiago Sbragia'),
    'ea0fb750-8f67-4edd-aa5a-85f42c68dc79.jpg': ('pedido', 'materiais_lavagem', 'compras', 'Relação de produtos de lavagem', '1691.00', '2026-09-18', 'Fornecedor de produtos de lavagem'),
    'f50528c5-ff01-4665-8668-2fb80752019b.jpg': ('documento_financeiro', 'transporte', 'financeiro', 'Corrida de aplicativo', '116.30', '2026-09-17', '99 Tecnologia Ltda'),
    'f81b2eca-fc4a-4088-a086-9a69e596206f.jpg': ('documento_financeiro', 'locacao', 'financeiro', 'Pagamento de locação', '400.00', '2026-09-11', 'Minasloc Locações'),
    'WhatsApp Image 2026-09-19 at 09.54.28.jpeg': ('pagamento_colaborador', 'reembolso', 'rh', 'Reembolso de lanche para a equipe', '98.50', '2026-09-19', 'Ursula Fidelis Tiago Sbragia'),
}


PAGAMENTOS = {
    '4e84af0b-13e9-4cb5-a004-e0a70610dda6.jpg': ('CRISTIANO APARECIDO PENA', 'reembolso'),
    '919a16e6-81a1-4e33-af65-303b0fd831d3.jpg': ('ANDRE SILVA ATAIDE', 'distrato'),
    '9e9fa3fb-4e49-4352-87a5-fad04d0246fc.jpg': ('LUIS CARLOS ANTONIO DA SILVA', 'salario'),
    'a4459230-5ba3-4825-af19-146a899c0269.jpg': ('WALLACE SANTOS DA SILVA', 'freelancer'),
    'dbd1f2eb-21db-4334-b7f9-13fbfe1a32cd.jpg': ('BRENDON GABRIEL SANTOS OLIVEIRA', 'reembolso'),
    'df6b50e7-7af0-4858-ae1c-471648478155.jpg': ('URSULA FIDELIS TIAGO SBRAGIA', 'auxilio_telefonia'),
    'WhatsApp Image 2026-09-19 at 09.54.28.jpeg': ('URSULA FIDELIS TIAGO SBRAGIA', 'reembolso'),
}


PDFS_FINANCEIROS = {
    'BOLETO DEMISSIONAL 10-09.pdf': ('documento_financeiro', 'boleto', 'financeiro', 'Boleto demissional - Piracicaba SST', '90.46', '2026-09-10', 'Piracicaba SST Ltda'),
    'FL-1346 - CT751 - JACQUELINE DA S.pdf': ('documento_financeiro', 'locacao', 'financeiro', 'Fatura de locação de container - contrato 751', '399.00', '2026-09-04', 'Serra Locação de Equipamentos Ltda'),
    'comprovante_picpay_pix_18-09-2026-12-17-17.pdf': ('documento_financeiro', 'comprovante', 'financeiro', 'Comprovante Pix', '929.50', '2026-09-18', 'Nicolas Robson da Silva'),
    'comprovante_picpay_pix_18-09-2026-15-06-07.pdf': ('documento_financeiro', 'comprovante', 'financeiro', 'Comprovante Pix', '1847.00', '2026-09-18', 'Nicolas Robson da Silva'),
    'comprovante_picpay_pix_18-09-2026-16-38-39.pdf': ('documento_financeiro', 'comprovante', 'financeiro', 'Comprovante Pix', '1691.00', '2026-09-18', 'Nicolas Robson da Silva'),
    'comprovante_picpay_pix_19-09-2026-09-44-59.pdf': ('documento_financeiro', 'comprovante', 'financeiro', 'Comprovante Pix', '2000.00', '2026-09-19', 'Uziel Nascimento de Carvalho'),
    'comprovante_picpay_pix_19-09-2026-09-51-30.pdf': ('documento_financeiro', 'comprovante', 'financeiro', 'Comprovante Pix', '55.00', '2026-09-19', 'Nicolas Giussani Vieira'),
    'GUIA DE FGTS DIA 18-09-2026.pdf': ('documento_trabalhista', 'fgts', 'rh', 'Guia do FGTS Digital', '1684.95', '2026-09-18', 'Caixa Econômica Federal'),
    'NF PREMIUMBR.pdf': ('nota_fiscal', 'nota_fiscal', 'fiscal', 'Nota fiscal de produtos automotivos nº 444', '1691.00', '2026-09-18', 'Deprimeira Produtos Automotivos Ltda'),
    'NF PREMIUMBR 2.pdf': ('nota_fiscal', 'nota_fiscal', 'fiscal', 'Nota fiscal de produtos automotivos nº 445', '62.00', '2026-09-18', 'Deprimeira Produtos Automotivos Ltda'),
    'PREMIUMBR 3078.pdf': ('nota_fiscal', 'nota_fiscal', 'fiscal', 'Nota fiscal de produtos automotivos nº 3078', '650.00', '2026-09-09', 'Aliança Auto Tintas Ltda'),
}


METADADOS_COMPLEMENTARES = {
    'BOLETO DEMISSIONAL 10-09.pdf': {
        'numero_documento': '0002614350',
        'data_emissao': '2026-09-02',
        'data_vencimento': '2026-09-10',
    },
    'FL-1346 - CT751 - JACQUELINE DA S.pdf': {
        'numero_documento': '1346',
        'contrato': '751',
        'data_emissao': '2026-09-04',
        'data_vencimento': '2026-10-04',
        'cliente': 'Jacqueline da Silva Moraes',
    },
    'GUIA DE FGTS DIA 18-09-2026.pdf': {
        'competencia': '09/2026',
        'data_emissao': '2026-09-11',
        'data_vencimento': '2026-09-18',
    },
    'NF PREMIUMBR.pdf': {'numero_documento': '444', 'data_emissao': '2026-09-18'},
    'NF PREMIUMBR 2.pdf': {'numero_documento': '445', 'data_emissao': '2026-09-18'},
    'PREMIUMBR 3078.pdf': {'numero_documento': '3078', 'data_emissao': '2026-09-09'},
}


def _origem(caminho):
    return OrigemArquivoImportado.objects.select_related('arquivo_importado').filter(
        caminho_relativo=caminho
    ).first()


def _atualizar_arquivo(arquivo, dados, *, manter_revisao=False):
    categoria, subcategoria, area, descricao, valor, data_documento, beneficiario = dados
    metadados = dict(arquivo.metadados or {})
    metadados.update({
        'descricao': descricao,
        'valor': valor.replace('.', ','),
        'data_pagamento': data_documento,
        'beneficiario': beneficiario,
        'revisado_visual_em': '2026-09-19',
    })
    arquivo.categoria = categoria
    arquivo.subcategoria = subcategoria
    arquivo.area = area
    arquivo.metadados = metadados
    if not manter_revisao:
        arquivo.status = 'arquivado'
        arquivo.motivo_revisao = ''
    arquivo.save(update_fields=[
        'categoria', 'subcategoria', 'area', 'metadados', 'status',
        'motivo_revisao', 'atualizado_em',
    ])


def _vincular_pagamento(arquivo, colaborador, tipo, valor, data_pagamento, usuario, descricao):
    existente = PagamentoColaborador.objects.filter(
        colaborador=colaborador,
        valor=valor,
        data_pagamento=data_pagamento,
    ).order_by('pk').first()
    if existente:
        pagamento = existente
        criado = False
    else:
        mensal = tipo in {
            'salario', 'salario_beneficios', 'prestacao_servico',
            'freelancer', 'distrato', 'auxilio_telefonia',
        }
        competencia = data_pagamento.replace(day=1) if mensal else data_pagamento
        competencia_fim = (
            competencia.replace(day=monthrange(competencia.year, competencia.month)[1])
            if mensal else data_pagamento
        )
        pagamento = PagamentoColaborador(
            colaborador=colaborador,
            tipo=tipo,
            competencia=competencia,
            competencia_fim=competencia_fim,
            valor=valor,
            data_vencimento=data_pagamento,
            status='pago',
            data_pagamento=data_pagamento,
            recorrente=False,
            observacao=f'{descricao}. Conferido no lote NICOLAS SISTEMA.',
            identificador_transacao=f'lote-nicolas:{arquivo.sha256}',
            criado_por=usuario,
        )
        pagamento.full_clean()
        pagamento.save()
        criado = True
    arquivo.categoria = 'pagamento_colaborador'
    arquivo.subcategoria = tipo
    arquivo.area = 'rh'
    arquivo.content_type = ContentType.objects.get_for_model(pagamento)
    arquivo.object_id = pagamento.pk
    arquivo.status = 'vinculado'
    arquivo.motivo_revisao = ''
    arquivo.save(update_fields=[
        'categoria', 'subcategoria', 'area', 'content_type', 'object_id',
        'status', 'motivo_revisao', 'atualizado_em',
    ])
    return criado


class Command(BaseCommand):
    help = 'Organiza e concilia o lote revisado da pasta NICOLAS SISTEMA.'

    def add_arguments(self, parser):
        parser.add_argument('--usuario', default='ceo_premium')

    @transaction.atomic
    def handle(self, *args, **options):
        usuario = User.objects.filter(username=options['usuario']).first()
        if not usuario:
            raise CommandError(f'Usuário não encontrado: {options["usuario"]}')
        atualizados = pagamentos_criados = pagamentos_reutilizados = 0

        dados_todos = dict(REVISOES)
        dados_todos.update(PDFS_FINANCEIROS)
        for nome, dados in dados_todos.items():
            origem = _origem(f'{PASTA_LANCAMENTOS}\\{nome}')
            if not origem and nome == 'comprovante_picpay_pix_18-09-2026-12-17-17.pdf':
                origem = _origem(f'{PASTA_LANCAMENTOS}\\{nome[:-4]} (1).pdf')
            if not origem:
                raise CommandError(f'Origem do lote não encontrada: {nome}')
            arquivo = origem.arquivo_importado
            _atualizar_arquivo(arquivo, dados)
            if nome in METADADOS_COMPLEMENTARES:
                arquivo.metadados = {
                    **(arquivo.metadados or {}),
                    **METADADOS_COMPLEMENTARES[nome],
                }
                arquivo.save(update_fields=['metadados', 'atualizado_em'])
            atualizados += 1
            if nome in PAGAMENTOS:
                nome_colaborador, tipo = PAGAMENTOS[nome]
                colaborador = Colaborador.objects.filter(nome__iexact=nome_colaborador).first()
                if not colaborador:
                    raise CommandError(f'Colaborador não encontrado: {nome_colaborador}')
                criado = _vincular_pagamento(
                    arquivo,
                    colaborador,
                    tipo,
                    Decimal(dados[4]),
                    date.fromisoformat(dados[5]),
                    usuario,
                    dados[3],
                )
                pagamentos_criados += int(criado)
                pagamentos_reutilizados += int(not criado)

        # As imagens de recarga não exibem o nome do colaborador. Guardamos
        # valor e data, mas mantemos a pendência de identificação humana.
        origens_aux = OrigemArquivoImportado.objects.select_related('arquivo_importado').filter(
            caminho_relativo__startswith='AUXILIO TELEFONIA\\SETEMBRO\\WhatsApp Image'
        )
        vistos = set()
        for origem in origens_aux:
            arquivo = origem.arquivo_importado
            if arquivo.pk in vistos:
                continue
            vistos.add(arquivo.pk)
            if '14.40.38' in origem.caminho_relativo:
                dados = (
                    'pagamento_colaborador', 'auxilio_telefonia', 'rh',
                    'Auxílio telefonia', '39.00', '2026-09-18',
                    'Lucas Henrique Reginaldo Santana',
                )
                _atualizar_arquivo(arquivo, dados)
                colaborador = Colaborador.objects.get(pk=17)
                criado = _vincular_pagamento(
                    arquivo, colaborador, 'auxilio_telefonia', Decimal('39.00'),
                    date(2026, 9, 18), usuario, 'Auxílio telefonia',
                )
                pagamentos_criados += int(criado)
                pagamentos_reutilizados += int(not criado)
            else:
                dados = (
                    'pagamento_colaborador', 'auxilio_telefonia', 'rh',
                    'Recarga de telefonia', '30.00', '2026-09-18',
                    'Colaborador a identificar',
                )
                _atualizar_arquivo(arquivo, dados, manter_revisao=True)
                arquivo.motivo_revisao = 'Colaborador da recarga ainda não identificado.'
                arquivo.save(update_fields=['motivo_revisao', 'atualizado_em'])
            atualizados += 1

        self.stdout.write(self.style.SUCCESS(
            f'Lote organizado: {atualizados} arquivos revisados, '
            f'{pagamentos_criados} pagamentos criados e '
            f'{pagamentos_reutilizados} pagamentos existentes reutilizados.'
        ))
