"""ERP Grupo PremiumBR — Models do Módulo 5: Compras"""
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.auth.models import User
from uuid import uuid4


class Material(models.Model):
    CATEGORIAS = [
        ('consumo', 'Material de Consumo'),
        ('limpeza', 'Material de Limpeza'),
        ('escritorio', 'Material de Escritório'),
        ('ferramentas', 'Ferramentas'),
        ('epi', 'EPI / Segurança'),
        ('informatica', 'Informática'),
        ('manutencao', 'Manutenção'),
        ('outros', 'Outros'),
    ]
    UNIDADES = [
        ('un', 'Unidade'),
        ('cx', 'Caixa'),
        ('pc', 'Pacote'),
        ('kg', 'Quilograma'),
        ('lt', 'Litro'),
        ('mt', 'Metro'),
        ('pr', 'Par'),
        ('rl', 'Rolo'),
    ]

    codigo = models.CharField(max_length=20, unique=True, blank=True, verbose_name='Código')
    nome = models.CharField(max_length=200, verbose_name='Nome do Material')
    foto = models.ImageField(
        upload_to='materiais/fotos/', null=True, blank=True,
        verbose_name='Foto do material',
    )
    descricao = models.TextField(blank=True, verbose_name='Descrição')
    categoria = models.CharField(max_length=20, choices=CATEGORIAS, default='consumo')
    unidade_medida = models.CharField(max_length=5, choices=UNIDADES, default='un')
    quantidade_estoque = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                              verbose_name='Qtd. em Estoque')
    estoque_minimo = models.DecimalField(max_digits=10, decimal_places=2, default=5,
                                          verbose_name='Estoque Mínimo')
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                          verbose_name='Preço Unitário')
    fornecedor_preferencial = models.CharField(max_length=200, blank=True, verbose_name='Fornecedor Preferencial')
    localizacao = models.CharField(max_length=100, blank=True, verbose_name='Localização no Almoxarifado')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Material'
        verbose_name_plural = 'Materiais'
        ordering = ['nome']
        constraints = [
            models.CheckConstraint(condition=models.Q(quantidade_estoque__gte=0), name='compras_estoque_nao_negativo'),
            models.CheckConstraint(condition=models.Q(estoque_minimo__gte=0), name='compras_estoque_minimo_nao_negativo'),
        ]

    def __str__(self):
        return f"[{self.codigo}] {self.nome} — Estoque: {self.quantidade_estoque} {self.get_unidade_medida_display()}"

    def save(self, *args, **kwargs):
        gerar_codigo = self.pk is None and not self.codigo
        if gerar_codigo:
            self.codigo = f'TMP-{uuid4().hex[:16]}'
        super().save(*args, **kwargs)
        if gerar_codigo:
            self.codigo = f'MAT-{self.pk:06d}'
            type(self).objects.filter(pk=self.pk).update(codigo=self.codigo)

    def estoque_critico(self):
        return self.quantidade_estoque <= self.estoque_minimo


class RequisicaoCompra(models.Model):
    """Agrupa vários materiais destinados à mesma unidade."""

    solicitante = models.CharField(max_length=200, verbose_name='Solicitante')
    solicitante_usuario = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requisicoes_compra',
    )
    unidade_destino = models.CharField(max_length=100, verbose_name='Unidade de Destino')
    justificativa = models.TextField(verbose_name='Justificativa')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Requisição de Compra'
        verbose_name_plural = 'Requisições de Compra'
        ordering = ['-criado_em']

    def __str__(self):
        return f'{self.numero} - {self.unidade_destino}'

    @property
    def numero(self):
        return f'REQ-{self.pk:06d}' if self.pk else 'REQ-NOVA'


class SolicitacaoMaterial(models.Model):
    STATUS = [
        ('pendente', 'Pendente'),
        ('em_analise', 'Em Análise de Estoque'),
        ('atendido_interno', 'Atendido pelo Estoque'),
        ('compra_externa', 'Encaminhado para Compra Externa'),
        ('aguardando_entrega', 'Aguardando Entrega'),
        ('entregue', 'Entregue'),
        ('cancelado', 'Cancelado'),
    ]

    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name='solicitacoes',
                                  verbose_name='Material')
    requisicao = models.ForeignKey(
        RequisicaoCompra,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='itens',
        verbose_name='Requisição agrupada',
    )
    quantidade_solicitada = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Quantidade')
    solicitante = models.CharField(max_length=200, verbose_name='Solicitante')
    solicitante_usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                             related_name='solicitacoes_material')
    unidade_destino = models.CharField(max_length=100, verbose_name='Unidade de Destino')
    justificativa = models.TextField(verbose_name='Justificativa')
    status = models.CharField(max_length=20, choices=STATUS, default='pendente')
    atendida_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='solicitacoes_atendidas')
    obs = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Solicitação de Material'
        verbose_name_plural = 'Solicitações de Material'
        ordering = ['-criado_em']
        constraints = [
            models.CheckConstraint(condition=models.Q(quantidade_solicitada__gt=0), name='compras_quantidade_solicitada_positiva'),
        ]

    def __str__(self):
        return f"Solicitação: {self.material.nome} x{self.quantidade_solicitada} — {self.get_status_display()}"

    def save(self, *args, **kwargs):
        if self.requisicao_id:
            self.unidade_destino = self.requisicao.unidade_destino
            self.justificativa = self.requisicao.justificativa
            self.solicitante = self.requisicao.solicitante
            self.solicitante_usuario = self.requisicao.solicitante_usuario
            if kwargs.get('update_fields') is not None:
                kwargs['update_fields'] = set(kwargs['update_fields']) | {
                    'unidade_destino', 'justificativa', 'solicitante',
                    'solicitante_usuario',
                }
        super().save(*args, **kwargs)

    @property
    def numero(self):
        return f'SOL-{self.pk:06d}' if self.pk else 'SOL-NOVO'


class PedidoCompra(models.Model):
    CENTAVOS = Decimal('0.01')
    STATUS = [
        ('em_cotacao', 'Em Cotação'),
        ('aguardando_aprovacao', 'Aguardando Aprovação'),
        ('aprovado', 'Aprovado'),
        ('reprovado', 'Reprovado — Nova Cotação'),
        ('pedido_emitido', 'Pedido Emitido ao Fornecedor'),
        ('aguardando_recebimento', 'Aguardando Recebimento'),
        ('recebido_conferencia', 'Recebido — Em Conferência'),
        ('entrada_estoque', 'Entrada no Estoque'),
        ('concluido', 'Concluído'),
    ]

    solicitacao = models.ForeignKey(SolicitacaoMaterial, on_delete=models.CASCADE,
                                     related_name='pedidos', verbose_name='Solicitação de Origem')
    fornecedor = models.CharField(max_length=200, verbose_name='Fornecedor')
    cnpj_fornecedor = models.CharField(max_length=18, blank=True, verbose_name='CNPJ do Fornecedor')
    valor_unitario = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Valor Unitário')
    valor_total = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Valor Total')
    prazo_entrega = models.DateField(null=True, blank=True, verbose_name='Prazo de Entrega')
    status = models.CharField(max_length=30, choices=STATUS, default='em_cotacao')
    aprovado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='pedidos_aprovados')
    numero_pedido = models.CharField(max_length=30, blank=True, verbose_name='Número do Pedido')
    nota_fiscal = models.CharField(max_length=30, blank=True, verbose_name='Nota Fiscal')
    obs = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Pedido de Compra'
        verbose_name_plural = 'Pedidos de Compra'
        ordering = ['-criado_em']
        constraints = [
            models.CheckConstraint(condition=models.Q(valor_unitario__gt=0), name='compras_valor_unitario_positivo'),
            models.CheckConstraint(condition=models.Q(valor_total__gt=0), name='compras_valor_total_positivo'),
            models.UniqueConstraint(
                fields=('solicitacao',),
                condition=~models.Q(status='reprovado'),
                name='compras_um_pedido_ativo_por_solicitacao',
            ),
        ]

    def __str__(self):
        return f"{self.numero_pedido or 'PC-NOVO'} | {self.solicitacao.material.nome} — {self.fornecedor}"

    def calcular_valor_total(self):
        """Calcula o total em centavos, mesmo para quantidades fracionadas."""
        if self.valor_unitario is None or not self.solicitacao_id:
            return None
        quantidade = Decimal(str(self.solicitacao.quantidade_solicitada))
        return (Decimal(str(self.valor_unitario)) * quantidade).quantize(
            self.CENTAVOS, rounding=ROUND_HALF_UP
        )

    def clean(self):
        super().clean()
        if self.valor_unitario is not None and self.valor_unitario <= 0:
            raise ValidationError({'valor_unitario': 'O valor unitário deve ser maior que zero.'})
        total = self.calcular_valor_total()
        if total is not None:
            self.valor_total = total

    def aprovar(self, usuario):
        """Emite o pedido e mantém a solicitação sincronizada."""
        if self.status != 'aguardando_aprovacao':
            raise ValidationError('Este pedido não está aguardando aprovação.')
        self.status = 'pedido_emitido'
        self.aprovado_por = usuario
        self.save(update_fields=['status', 'aprovado_por', 'atualizado_em'])
        SolicitacaoMaterial.objects.filter(pk=self.solicitacao_id).update(
            status='aguardando_entrega'
        )

    def reprovar(self, motivo=''):
        """Reabre a solicitação para permitir uma nova cotação."""
        if self.status != 'aguardando_aprovacao':
            raise ValidationError('Este pedido não está aguardando aprovação.')
        self.status = 'reprovado'
        self.obs = motivo or 'Reprovado — nova cotação necessária.'
        self.save(update_fields=['status', 'obs', 'atualizado_em'])
        SolicitacaoMaterial.objects.filter(pk=self.solicitacao_id).update(
            status='compra_externa'
        )

    def save(self, *args, **kwargs):
        gerar_numero = self.pk is None and not self.numero_pedido
        total = self.calcular_valor_total()
        if total is not None:
            self.valor_total = total
            if kwargs.get('update_fields') is not None:
                kwargs['update_fields'] = set(kwargs['update_fields']) | {'valor_total'}
        super().save(*args, **kwargs)
        if gerar_numero:
            self.numero_pedido = f'PC-{self.pk:06d}'
            type(self).objects.filter(pk=self.pk).update(numero_pedido=self.numero_pedido)
