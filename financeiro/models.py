"""ERP Grupo PremiumBR — Models do Módulo 6: Financeiro / Fiscal"""
from django.db import models
from django.contrib.auth.models import User


class DocumentoFinanceiro(models.Model):
    TIPOS = [
        ('nota_fiscal', 'Nota Fiscal'),
        ('contrato', 'Contrato'),
        ('reembolso', 'Reembolso'),
        ('pagamento', 'Pagamento'),
        ('faturamento', 'Faturamento'),
        ('recibo', 'Recibo'),
        ('boleto', 'Boleto Bancário'),
    ]
    STATUS = [
        ('recebido', 'Recebido'),
        ('em_auditoria', 'Em Auditoria Interna'),
        ('informacoes_incorretas', 'Informações Incorretas'),
        ('aguardando_correcao', 'Aguardando Correção'),
        ('aprovado_lancamento', 'Aprovado para Lançamento'),
        ('lancado', 'Lançado no ERP'),
        ('arquivado', 'Arquivado'),
    ]

    tipo = models.CharField(max_length=20, choices=TIPOS, verbose_name='Tipo de Documento')
    numero_documento = models.CharField(max_length=50, verbose_name='Número do Documento')
    descricao = models.CharField(max_length=300, verbose_name='Descrição')
    valor = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Valor (R$)')
    centro_custo = models.CharField(max_length=100, verbose_name='Centro de Custo')
    unidade = models.CharField(max_length=100, verbose_name='Unidade')
    cnpj_emitente = models.CharField(max_length=18, blank=True, verbose_name='CNPJ do Emitente')
    razao_social_emitente = models.CharField(max_length=200, blank=True, verbose_name='Razão Social')
    contratos_vinculados = models.CharField(max_length=200, blank=True, verbose_name='Contratos Vinculados')
    data_emissao = models.DateField(verbose_name='Data de Emissão')
    data_vencimento = models.DateField(null=True, blank=True, verbose_name='Data de Vencimento')
    status = models.CharField(max_length=30, choices=STATUS, default='recebido')
    motivo_rejeicao = models.TextField(blank=True, verbose_name='Motivo da Rejeição')
    recebido_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='documentos_recebidos')
    arquivo_pdf = models.BinaryField(null=True, blank=True, editable=True, verbose_name='Nota Fiscal PDF (Legado DB)')
    arquivo = models.FileField(upload_to='notas_fiscais/', null=True, blank=True, verbose_name='Nota Fiscal PDF (Nuvem)')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Documento Financeiro'
        verbose_name_plural = 'Documentos Financeiros'
        ordering = ['-criado_em']

    def __str__(self):
        return f"[{self.get_tipo_display()}] {self.numero_documento} — R$ {self.valor} ({self.get_status_display()})"


class AuditoriaItem(models.Model):
    """Checklist de auditoria para cada documento financeiro"""
    ITENS_CHECKLIST = [
        ('valor_correto', 'Valor Correto'),
        ('centro_custo_ok', 'Centro de Custo Válido'),
        ('unidade_ok', 'Unidade Correta'),
        ('cnpj_valido', 'CNPJ Válido'),
        ('contrato_vinculado', 'Contrato Vinculado Correto'),
        ('data_valida', 'Data de Emissão Válida'),
    ]
    STATUS = [
        ('pendente', 'Pendente'),
        ('ok', 'Conferido — OK'),
        ('divergente', 'Divergente'),
    ]

    documento = models.ForeignKey(DocumentoFinanceiro, on_delete=models.CASCADE, related_name='auditoria')
    item = models.CharField(max_length=30, choices=ITENS_CHECKLIST)
    status = models.CharField(max_length=15, choices=STATUS, default='pendente')
    observacao = models.TextField(blank=True)
    verificado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name='itens_auditados')
    verificado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Item de Auditoria'
        verbose_name_plural = 'Itens de Auditoria'
        unique_together = ('documento', 'item')

    def __str__(self):
        return f"{self.get_item_display()} — {self.get_status_display()}"


class LancamentoERP(models.Model):
    TIPOS = [
        ('debito', 'Débito'),
        ('credito', 'Crédito'),
        ('provisao', 'Provisão'),
        ('estorno', 'Estorno'),
    ]
    STATUS = [
        ('rascunho', 'Rascunho'),
        ('em_validacao', 'Em Validação'),
        ('validado', 'Validado'),
        ('rejeitado', 'Rejeitado — Corrigir'),
        ('finalizado', 'Finalizado no ERP'),
    ]

    documento = models.ForeignKey(DocumentoFinanceiro, on_delete=models.CASCADE,
                                   related_name='lancamentos', verbose_name='Documento de Origem')
    descricao = models.CharField(max_length=300, verbose_name='Descrição do Lançamento')
    tipo = models.CharField(max_length=10, choices=TIPOS, verbose_name='Tipo')
    valor = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Valor (R$)')
    centro_custo = models.CharField(max_length=100, verbose_name='Centro de Custo')
    competencia = models.DateField(verbose_name='Mês de Competência')
    status = models.CharField(max_length=20, choices=STATUS, default='rascunho')
    lancado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='lancamentos_efetuados')
    validado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='lancamentos_validados')
    motivo_rejeicao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    finalizado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Lançamento ERP'
        verbose_name_plural = 'Lançamentos ERP'
        ordering = ['-criado_em']

    def __str__(self):
        return f"Lançamento {self.tipo.upper()} — R$ {self.valor} ({self.get_status_display()})"


class OrcamentoCentroCusto(models.Model):
    """Controle de Orçamento (Budget) e Metas de Redução de Custo por Centro de Custo"""
    centro_custo = models.CharField(max_length=100, verbose_name='Centro de Custo')
    competencia = models.DateField(verbose_name='Mês/Ano (Competência)')
    valor_orcado = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Valor Orçado (Budget)')
    meta_reducao_custo = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='Meta de Redução (%)', help_text='Ex: 5 para 5% de redução')
    
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Orçamento por Centro de Custo'
        verbose_name_plural = 'Orçamentos por Centro de Custo'
        ordering = ['-competencia']
        unique_together = ('centro_custo', 'competencia')

    def __str__(self):
        mes_ano = self.competencia.strftime('%m/%Y')
        return f"Budget {self.centro_custo} ({mes_ano}) — R$ {self.valor_orcado}"
