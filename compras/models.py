"""ERP Grupo PremiumBR — Models do Módulo 5: Compras"""
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import models, transaction
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


class EquipamentoManutencao(models.Model):
    """Máquinas e ferramentas cadastradas para abrir solicitações de manutenção."""

    TIPOS = [
        ('maquina', 'Máquina'),
        ('ferramenta', 'Ferramenta'),
        ('equipamento', 'Equipamento'),
    ]

    nome = models.CharField(max_length=200, verbose_name='Nome')
    tipo = models.CharField(max_length=20, choices=TIPOS, default='equipamento')
    codigo = models.CharField(max_length=40, blank=True, verbose_name='Código / patrimônio')
    localizacao = models.CharField(max_length=150, blank=True, verbose_name='Unidade / localização')
    descricao = models.TextField(blank=True, verbose_name='Descrição')
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['nome']
        verbose_name = 'Equipamento de manutenção'
        verbose_name_plural = 'Equipamentos de manutenção'

    def __str__(self):
        return f'{self.nome} ({self.codigo})' if self.codigo else self.nome


class RequisicaoCompra(models.Model):
    """Agrupa vários materiais destinados à mesma unidade."""

    STATUS = [
        ('aguardando_adriana', 'Aguardando aprovação da Adriana'),
        ('aguardando_ceo', 'Aguardando aprovação do CEO'),
        ('aprovada', 'Aprovada'),
        ('pedido', 'Pedido'),
        ('rejeitada', 'Rejeitada'),
    ]

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
    documento = models.FileField(
        upload_to='compras/requisicoes/documentos/',
        null=True,
        blank=True,
        verbose_name='Documento Anexo'
    )
    comprovante_pagamento = models.FileField(
        upload_to='compras/requisicoes/comprovantes/',
        null=True,
        blank=True,
        verbose_name='Comprovante de Pagamento'
    )
    status = models.CharField(
        max_length=30, choices=STATUS, default='aguardando_adriana'
    )
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

    @property
    def status_entrega(self):
        if self.status not in {'aprovada', 'pedido'}:
            return 'Não se aplica' if self.status == 'rejeitada' else 'Aguardando aprovação'
        itens = [item for item in self.itens.all() if item.status != 'cancelado']
        entregues = sum(item.status == 'entregue' for item in itens)
        if itens and entregues == len(itens):
            return 'Entregue'
        return 'Entrega parcial' if entregues else 'Não entregue'

    @transaction.atomic
    def aprovar(self, usuario):
        """Após a decisão final, atende do estoque ou encaminha para compra."""
        if self.status != 'aguardando_ceo':
            raise ValidationError('A requisição não está aguardando a aprovação final.')
        itens = list(self.itens.select_related('material').select_for_update())
        materiais = {
            material.pk: material
            for material in Material.objects.select_for_update().filter(
                pk__in=[item.material_id for item in itens]
            )
        }
        for item in itens:
            material = materiais[item.material_id]
            if material.quantidade_estoque >= item.quantidade_solicitada:
                material.quantidade_estoque -= item.quantidade_solicitada
                material.save(update_fields=['quantidade_estoque', 'atualizado_em'])
                item.status = 'atendido_interno'
                item.atendida_por = usuario
            else:
                item.status = 'compra_externa'
            item.save(update_fields=['status', 'atendida_por', 'atualizado_em'])
        self.manutencoes.filter(status='pendente').update(status='aguardando_manutencao')
        self.status = 'aprovada'
        self.save(update_fields=['status', 'atualizado_em'])

    def rejeitar(self):
        if self.status not in {'aguardando_adriana', 'aguardando_ceo'}:
            raise ValidationError('A requisição não está aguardando aprovação.')
        self.itens.filter(status='pendente').update(status='cancelado')
        self.manutencoes.filter(status='pendente').update(status='cancelada')
        self.status = 'rejeitada'
        self.save(update_fields=['status', 'atualizado_em'])


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

    @property
    def status_entrega(self):
        if self.requisicao_id and self.requisicao.status not in {'aprovada', 'pedido'}:
            return 'Não se aplica' if self.requisicao.status == 'rejeitada' else 'Aguardando aprovação'
        if self.status == 'cancelado':
            return 'Não se aplica'
        if self.status == 'entregue':
            return 'Entregue'
        if self.status in {'atendido_interno', 'compra_externa', 'aguardando_entrega'}:
            return 'Não entregue'
        return 'Aguardando aprovação'

    @property
    def todos_pedidos(self):
        pedidos = {pedido.pk: pedido for pedido in self.pedidos.all()}
        for item in self.itens_pedido.all():
            pedidos[item.pedido_id] = item.pedido
        return sorted(pedidos.values(), key=lambda pedido: pedido.pk, reverse=True)

    @property
    def pode_confirmar_entrega(self):
        if self.requisicao_id and self.requisicao.status not in {'aprovada', 'pedido'}:
            return False
        if self.status == 'atendido_interno':
            return True
        return self.status == 'aguardando_entrega' and any(
            pedido.status in PedidoCompra.STATUS_APOS_APROVACAO
            for pedido in self.todos_pedidos
        )


class SolicitacaoManutencao(models.Model):
    STATUS = [
        ('pendente', 'Aguardando aprovação da RC'),
        ('aguardando_manutencao', 'Aguardando manutenção'),
        ('em_manutencao', 'Em manutenção'),
        ('concluida', 'Concluída'),
        ('cancelada', 'Cancelada'),
    ]

    requisicao = models.ForeignKey(
        RequisicaoCompra, on_delete=models.CASCADE, related_name='manutencoes'
    )
    equipamento = models.ForeignKey(
        EquipamentoManutencao, on_delete=models.PROTECT, related_name='solicitacoes'
    )
    problema = models.TextField(verbose_name='Manutenção necessária')
    status = models.CharField(max_length=30, choices=STATUS, default='pendente')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']
        verbose_name = 'Solicitação de manutenção'
        verbose_name_plural = 'Solicitações de manutenção'

    def __str__(self):
        return f'{self.equipamento} — {self.get_status_display()}'


class PedidoCompra(models.Model):
    CENTAVOS = Decimal('0.01')
    STATUS_APOS_APROVACAO = {
        'aprovado', 'pedido_emitido', 'aguardando_recebimento',
        'recebido_conferencia', 'entrada_estoque', 'concluido',
    }
    STATUS = [
        ('em_cotacao', 'Em Cotação'),
        ('aguardando_aprovacao', 'Aguardando Aprovação'),
        ('aprovado', 'Aprovado'),
        ('reprovado', 'Reprovado — Nova Cotação'),
        ('pedido_emitido', 'Pedido'),
        ('aguardando_recebimento', 'Aguardando Recebimento'),
        ('recebido_conferencia', 'Recebido — Em Conferência'),
        ('entrada_estoque', 'Entrada no Estoque'),
        ('concluido', 'Concluído'),
    ]

    solicitacao = models.ForeignKey(SolicitacaoMaterial, on_delete=models.CASCADE,
                                     null=True, blank=True,
                                     related_name='pedidos', verbose_name='Solicitação de Origem')
    requisicao = models.ForeignKey(
        RequisicaoCompra, on_delete=models.CASCADE, null=True, blank=True,
        related_name='pedidos', verbose_name='Requisição de Origem',
    )
    fornecedor = models.CharField(max_length=200, verbose_name='Fornecedor')
    cnpj_fornecedor = models.CharField(max_length=18, blank=True, verbose_name='CNPJ do Fornecedor')
    valor_unitario = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                        verbose_name='Valor Unitário')
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
            models.CheckConstraint(
                condition=(models.Q(solicitacao__isnull=False, requisicao__isnull=True, valor_unitario__isnull=False)
                           | models.Q(solicitacao__isnull=True, requisicao__isnull=False, valor_unitario__isnull=True)),
                name='compras_pedido_origem_valida',
            ),
            models.CheckConstraint(condition=models.Q(valor_unitario__gt=0), name='compras_valor_unitario_positivo'),
            models.CheckConstraint(condition=models.Q(valor_total__gt=0), name='compras_valor_total_positivo'),
            models.UniqueConstraint(
                fields=('solicitacao',),
                condition=~models.Q(status='reprovado'),
                name='compras_um_pedido_ativo_por_solicitacao',
            ),
        ]

    def __str__(self):
        origem = self.requisicao.numero if self.requisicao_id else self.solicitacao.material.nome
        return f"{self.numero_pedido or 'PC-NOVO'} | {origem} — {self.fornecedor}"

    @classmethod
    def para_solicitacao(cls, pk):
        return cls.objects.filter(
            models.Q(solicitacao_id=pk) | models.Q(
                pk__in=ItemPedidoCompra.objects.filter(solicitacao_id=pk).values('pedido_id')
            )
        )

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('detalhe_pedido', args=[self.pk])

    @property
    def solicitacoes_vinculadas(self):
        if self.solicitacao_id:
            return [self.solicitacao]
        return [item.solicitacao for item in self.itens.all()]

    @property
    def materiais_descricao(self):
        return ', '.join(sol.material.nome for sol in self.solicitacoes_vinculadas)

    def calcular_valor_total(self):
        """Calcula o total em centavos, mesmo para quantidades fracionadas."""
        if not self.solicitacao_id:
            if self.pk:
                itens = list(self.itens.all())
                if itens:
                    return sum((item.valor_total for item in itens), Decimal('0.00'))
            return self.valor_total
        if self.valor_unitario is None:
            return None
        quantidade = Decimal(str(self.solicitacao.quantidade_solicitada))
        return (Decimal(str(self.valor_unitario)) * quantidade).quantize(
            self.CENTAVOS, rounding=ROUND_HALF_UP
        )

    @property
    def status_entrega(self):
        if self.status == 'reprovado':
            return 'Não se aplica'
        if self.status not in self.STATUS_APOS_APROVACAO:
            return 'Aguardando aprovação'
        solicitacoes = self.solicitacoes_vinculadas
        entregues = sum(sol.status == 'entregue' for sol in solicitacoes)
        if solicitacoes and entregues == len(solicitacoes):
            return 'Entregue'
        return 'Entrega parcial' if entregues else 'Não entregue'

    def clean(self):
        super().clean()
        if self.valor_unitario is not None and self.valor_unitario <= 0:
            raise ValidationError({'valor_unitario': 'O valor unitário deve ser maior que zero.'})
        if self.solicitacao_id and ItemPedidoCompra.objects.filter(
            solicitacao_id=self.solicitacao_id, ativo=True,
        ).exists() and self.status != 'reprovado':
            raise ValidationError('Esta solicitação já possui um pedido de compra ativo.')
        total = self.calcular_valor_total()
        if total is not None:
            self.valor_total = total

    @transaction.atomic
    def aprovar(self, usuario):
        """Emite o pedido e mantém as solicitações sincronizadas."""
        if self.status != 'aguardando_aprovacao':
            raise ValidationError('Este pedido não está aguardando aprovação.')
        self.status = 'pedido_emitido'
        self.aprovado_por = usuario
        self.save(update_fields=['status', 'aprovado_por', 'atualizado_em'])
        SolicitacaoMaterial.objects.filter(pk__in=[sol.pk for sol in self.solicitacoes_vinculadas]).update(
            status='aguardando_entrega'
        )

    @transaction.atomic
    def reprovar(self, motivo=''):
        """Reabre as solicitações para permitir uma nova cotação."""
        if self.status != 'aguardando_aprovacao':
            raise ValidationError('Este pedido não está aguardando aprovação.')
        self.status = 'reprovado'
        self.obs = motivo or 'Reprovado — nova cotação necessária.'
        self.save(update_fields=['status', 'obs', 'atualizado_em'])
        SolicitacaoMaterial.objects.filter(pk__in=[sol.pk for sol in self.solicitacoes_vinculadas]).update(
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
        if self.requisicao_id:
            self.itens.update(ativo=self.status != 'reprovado')
        if gerar_numero:
            self.numero_pedido = f'PC-{self.pk:06d}'
            type(self).objects.filter(pk=self.pk).update(numero_pedido=self.numero_pedido)


class ItemPedidoCompra(models.Model):
    """Uma linha de um pedido que reúne os produtos selecionados da requisição."""

    pedido = models.ForeignKey(PedidoCompra, on_delete=models.CASCADE, related_name='itens')
    solicitacao = models.ForeignKey(
        SolicitacaoMaterial, on_delete=models.PROTECT, related_name='itens_pedido',
    )
    quantidade = models.DecimalField(max_digits=10, decimal_places=2)
    valor_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    valor_total = models.DecimalField(max_digits=12, decimal_places=2)
    ativo = models.BooleanField(default=True, editable=False)

    class Meta:
        ordering = ['pk']
        constraints = [
            models.UniqueConstraint(fields=['pedido', 'solicitacao'], name='compras_item_unico_no_pedido'),
            models.UniqueConstraint(fields=['solicitacao'], condition=models.Q(ativo=True),
                                    name='compras_um_item_pedido_ativo'),
            models.CheckConstraint(condition=models.Q(quantidade__gt=0), name='compras_item_pedido_qtd_positiva'),
            models.CheckConstraint(condition=models.Q(valor_unitario__gt=0), name='compras_item_pedido_preco_positivo'),
            models.CheckConstraint(condition=models.Q(valor_total__gt=0), name='compras_item_pedido_total_positivo'),
        ]

    def clean(self):
        super().clean()
        if self.pedido_id and self.solicitacao_id:
            if not self.pedido.requisicao_id or self.pedido.requisicao_id != self.solicitacao.requisicao_id:
                raise ValidationError('O produto deve pertencer à requisição deste pedido.')
            if self.ativo and self.solicitacao.pedidos.exclude(status='reprovado').exists():
                raise ValidationError('Esta solicitação já possui um pedido de compra ativo.')
        if self.valor_unitario is not None and self.quantidade is not None:
            self.valor_total = (Decimal(str(self.valor_unitario)) * Decimal(str(self.quantidade))).quantize(
                PedidoCompra.CENTAVOS, rounding=ROUND_HALF_UP,
            )

    def save(self, *args, **kwargs):
        self.valor_total = (Decimal(str(self.valor_unitario)) * Decimal(str(self.quantidade))).quantize(
            PedidoCompra.CENTAVOS, rounding=ROUND_HALF_UP,
        )
        self.ativo = self.pedido.status != 'reprovado'
        super().save(*args, **kwargs)
