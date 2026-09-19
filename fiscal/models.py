from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum


class FolhaFiscal(models.Model):
    STATUS = [
        ('importando', 'Importando'),
        ('revisao', 'Em revisão'),
        ('pronta', 'Pronta para processar'),
        ('processada', 'Processada'),
        ('erro', 'Erro'),
    ]

    competencia = models.DateField(db_index=True)
    titulo = models.CharField(max_length=200)
    versao = models.PositiveSmallIntegerField(default=1)
    arquivo_origem = models.ForeignKey(
        'core.ArquivoImportado',
        on_delete=models.PROTECT,
        related_name='folhas_fiscais',
    )
    hash_origem = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=20, choices=STATUS, default='importando', db_index=True)
    observacoes_importacao = models.TextField(blank=True)
    importado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='folhas_fiscais_importadas',
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-competencia', '-versao', '-pk']
        verbose_name = 'Folha fiscal'
        verbose_name_plural = 'Folhas fiscais'
        constraints = [
            models.UniqueConstraint(
                fields=['competencia', 'versao'],
                name='fiscal_folha_competencia_versao_unica',
            ),
        ]

    def __str__(self):
        return f'{self.titulo} - {self.competencia:%m/%Y}'

    @property
    def total_executado(self):
        return self.itens.aggregate(total=Sum('valor_executar'))['total'] or Decimal('0')

    @property
    def total_beneficios(self):
        return self.parcelas_beneficio.aggregate(total=Sum('valor'))['total'] or Decimal('0')


class ItemFolhaFiscal(models.Model):
    REGIMES = [
        ('clt', 'CLT'),
        ('pj', 'PJ'),
        ('freelancer', 'Freelancer fixo'),
        ('supervisor', 'Supervisor'),
        ('administrativo', 'Administrativo'),
        ('rescisao', 'Rescisão'),
    ]
    STATUS_FONTE = [
        ('pago', 'Pago na planilha'),
        ('pendente', 'Aguardando pagamento'),
        ('nao_informado', 'Não informado'),
    ]
    CONCILIACOES = [
        ('conciliado', 'Conciliado'),
        ('revisar', 'Revisar'),
    ]

    folha = models.ForeignKey(FolhaFiscal, on_delete=models.CASCADE, related_name='itens')
    colaborador = models.ForeignKey(
        'admissional.Colaborador',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='itens_fiscais',
    )
    pagamento = models.OneToOneField(
        'admissional.PagamentoColaborador',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='item_fiscal',
    )
    aba_origem = models.CharField(max_length=80)
    linha_origem = models.PositiveIntegerField()
    regime = models.CharField(max_length=20, choices=REGIMES, db_index=True)
    nome_fonte = models.CharField(max_length=200)
    cpf_cnpj_fonte = models.CharField(max_length=30, blank=True)
    pix = models.CharField(max_length=180, blank=True)
    banco = models.CharField(max_length=180, blank=True)
    cargo = models.CharField(max_length=180, blank=True)
    contrato = models.CharField(max_length=180, blank=True)
    unidade = models.CharField(max_length=180, blank=True)
    data_inicio = models.DateField(null=True, blank=True)
    data_termino = models.DateField(null=True, blank=True)
    salario_base = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    valor_dia = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    dias_trabalhados = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    bonificacao = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    faltas = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    descontos = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valor_executar = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    valor_planejado = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    data_pagamento_fonte = models.DateField(null=True, blank=True)
    status_fonte = models.CharField(max_length=20, choices=STATUS_FONTE, default='nao_informado')
    status_conciliacao = models.CharField(max_length=20, choices=CONCILIACOES, default='revisar')
    problemas = models.JSONField(default=list, blank=True)
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['aba_origem', 'linha_origem']
        verbose_name = 'Item da folha fiscal'
        verbose_name_plural = 'Itens da folha fiscal'
        constraints = [
            models.UniqueConstraint(
                fields=['folha', 'aba_origem', 'linha_origem'],
                name='fiscal_item_origem_unica',
            ),
        ]
        indexes = [
            models.Index(fields=['folha', 'status_conciliacao']),
            models.Index(fields=['regime', 'status_fonte']),
        ]

    def __str__(self):
        return f'{self.nome_fonte} ({self.aba_origem}:{self.linha_origem})'

    @property
    def valor_para_pagamento(self):
        if self.valor_executar is not None and self.valor_executar > 0:
            return self.valor_executar
        return self.valor_planejado


class BeneficioFiscal(models.Model):
    TIPOS = [
        ('vale_transporte', 'Vale-transporte'),
        ('ajuda_custo', 'Ajuda de custo'),
    ]

    folha = models.ForeignKey(FolhaFiscal, on_delete=models.CASCADE, related_name='beneficios')
    colaborador = models.ForeignKey(
        'admissional.Colaborador',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='beneficios_fiscais',
    )
    aba_origem = models.CharField(max_length=80)
    linha_origem = models.PositiveIntegerField()
    nome_fonte = models.CharField(max_length=200)
    pix = models.CharField(max_length=180, blank=True)
    base = models.CharField(max_length=180, blank=True)
    contrato = models.CharField(max_length=180, blank=True)
    tipo = models.CharField(max_length=30, choices=TIPOS, default='vale_transporte')
    valor_passagem_diaria = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status_fonte = models.CharField(
        max_length=20,
        choices=ItemFolhaFiscal.STATUS_FONTE,
        default='nao_informado',
    )
    status_conciliacao = models.CharField(
        max_length=20,
        choices=ItemFolhaFiscal.CONCILIACOES,
        default='revisar',
    )
    problemas = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['linha_origem']
        constraints = [
            models.UniqueConstraint(
                fields=['folha', 'aba_origem', 'linha_origem'],
                name='fiscal_beneficio_origem_unica',
            ),
        ]

    def __str__(self):
        return f'{self.nome_fonte} - {self.get_tipo_display()}'


class ParcelaBeneficioFiscal(models.Model):
    beneficio = models.ForeignKey(BeneficioFiscal, on_delete=models.CASCADE, related_name='parcelas')
    folha = models.ForeignKey(FolhaFiscal, on_delete=models.CASCADE, related_name='parcelas_beneficio')
    semana = models.PositiveSmallIntegerField()
    valor = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
    )
    pagamento = models.OneToOneField(
        'admissional.PagamentoColaborador',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='parcela_fiscal',
    )

    class Meta:
        ordering = ['beneficio__linha_origem', 'semana']
        constraints = [
            models.UniqueConstraint(
                fields=['beneficio', 'semana'],
                name='fiscal_beneficio_semana_unica',
            ),
            models.CheckConstraint(
                condition=models.Q(semana__gte=1, semana__lte=4),
                name='fiscal_semana_entre_1_e_4',
            ),
        ]

    def __str__(self):
        return f'{self.beneficio.nome_fonte} - semana {self.semana}'
