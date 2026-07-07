"""ERP Grupo PremiumBR — Models do Módulo 5: Compras"""
from django.db import models
from django.contrib.auth.models import User


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

    codigo = models.CharField(max_length=20, unique=True, verbose_name='Código')
    nome = models.CharField(max_length=200, verbose_name='Nome do Material')
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

    def __str__(self):
        return f"[{self.codigo}] {self.nome} — Estoque: {self.quantidade_estoque} {self.get_unidade_medida_display()}"

    def estoque_critico(self):
        return self.quantidade_estoque <= self.estoque_minimo


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

    def __str__(self):
        return f"Solicitação: {self.material.nome} x{self.quantidade_solicitada} — {self.get_status_display()}"


class PedidoCompra(models.Model):
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

    def __str__(self):
        return f"PC-{self.id:04d} | {self.solicitacao.material.nome} — {self.fornecedor}"
