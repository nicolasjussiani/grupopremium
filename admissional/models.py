"""ERP Grupo PremiumBR — Models do Módulo 2: Admissional"""
from decimal import Decimal

from django.db import models
from django.db.models import BooleanField, Case, Exists, OuterRef, Q, Value, When
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator


class ColaboradorQuerySet(models.QuerySet):
    CAMPOS_DOCUMENTAIS_ESSENCIAIS = ('anexo_cpf', 'anexo_rg', 'anexo_aso')

    def com_status_documental(self):
        """Anota a situação do checklist sem carregar ou abrir arquivos."""
        documentos = DocumentoColaborador.objects.filter(colaborador_id=OuterRef('pk'))
        queryset = self.annotate(
            tem_comprovante_endereco=Exists(
                documentos.filter(tipo='comprovante_endereco')
            ),
            tem_contrato_arquivo=Exists(documentos.filter(tipo='contrato')),
        )
        faltando = Q(tem_comprovante_endereco=False) | Q(tem_contrato_arquivo=False)
        for campo in self.CAMPOS_DOCUMENTAIS_ESSENCIAIS:
            faltando |= Q(**{f'{campo}__isnull': True}) | Q(**{campo: ''})
        return queryset.annotate(
            documentacao_incompleta=Case(
                When(faltando, then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        )

    def com_documentacao_incompleta(self):
        return self.com_status_documental().filter(documentacao_incompleta=True)

    def com_documentacao_completa(self):
        return self.com_status_documental().filter(documentacao_incompleta=False)

    def delete(self):
        """Desativa em massa sem remover pessoas ou seus relacionamentos."""
        quantidade = self.exclude(status='inativo').update(status='inativo')
        return quantidade, {self.model._meta.label: quantidade}


class Colaborador(models.Model):
    STATUS = [
        ('ativo', 'Ativo'),
        ('inativo', 'Inativo'),
        ('ferias', 'Em Férias'),
        ('afastado', 'Afastado'),
        ('desligado', 'Desligado'),
    ]
    MARCAS = [
        ('trip_premium', 'Trip Premium'),
        ('log_premium', 'Log Premium'),
        ('eco_premium', 'Eco Premium'),
    ]

    nome = models.CharField(max_length=200, blank=True, verbose_name='Nome Completo')
    cpf = models.CharField(max_length=18, unique=True, null=True, blank=True, verbose_name='CPF/CNPJ')
    rg = models.CharField(max_length=20, blank=True, verbose_name='RG')
    data_nascimento = models.DateField(null=True, blank=True, verbose_name='Data de Nascimento')
    email = models.EmailField(blank=True, verbose_name='E-mail')
    telefone = models.CharField(max_length=20, blank=True, verbose_name='Telefone')
    endereco = models.TextField(blank=True, verbose_name='Endereço')
    
    TIPO_CONTRATO = [
        ('clt', 'CLT'),
        ('pj', 'PJ'),
    ]
    tipo_contrato = models.CharField(max_length=10, choices=TIPO_CONTRATO, default='clt', verbose_name='Tipo de Contrato')

    cargo = models.CharField(max_length=200, blank=True, verbose_name='Cargo')
    setor = models.CharField(max_length=100, blank=True, verbose_name='Setor')
    unidade = models.CharField(max_length=100, blank=True, verbose_name='Unidade')
    contrato = models.CharField(max_length=200, blank=True, verbose_name='Contrato/Cliente')
    marca = models.CharField(max_length=20, choices=MARCAS, default='eco_premium', verbose_name='Marca')
    data_admissao = models.DateField(null=True, blank=True, verbose_name='Data de Admissão')
    status = models.CharField(max_length=20, choices=STATUS, default='ativo')
    pis_pasep = models.CharField(max_length=20, blank=True, verbose_name='PIS/PASEP')
    ctps = models.CharField(max_length=30, blank=True, verbose_name='CTPS')
    salario = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name='Salário',
    )
    vale_transporte_semanal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name='Vale-transporte semanal',
    )
    
    # Anexos de documentos
    anexo_cpf = models.FileField(upload_to='colaboradores/docs/', null=True, blank=True, verbose_name='Anexo CPF/CNPJ (Frente)')
    anexo_cpf_verso = models.FileField(upload_to='colaboradores/docs/', null=True, blank=True, verbose_name='Anexo CPF/CNPJ (Verso)')
    
    anexo_rg = models.FileField(upload_to='colaboradores/docs/', null=True, blank=True, verbose_name='Anexo RG (Frente)')
    anexo_rg_verso = models.FileField(upload_to='colaboradores/docs/', null=True, blank=True, verbose_name='Anexo RG (Verso)')
    
    anexo_pis = models.FileField(upload_to='colaboradores/docs/', null=True, blank=True, verbose_name='Anexo PIS/PASEP (Frente)')
    anexo_pis_verso = models.FileField(upload_to='colaboradores/docs/', null=True, blank=True, verbose_name='Anexo PIS/PASEP (Verso)')
    
    anexo_ctps = models.FileField(upload_to='colaboradores/docs/', null=True, blank=True, verbose_name='Anexo CTPS (Frente)')
    anexo_ctps_verso = models.FileField(upload_to='colaboradores/docs/', null=True, blank=True, verbose_name='Anexo CTPS (Verso)')
    
    anexo_titulo = models.FileField(upload_to='colaboradores/docs/', null=True, blank=True, verbose_name='Anexo Título de Eleitor (Frente)')
    anexo_titulo_verso = models.FileField(upload_to='colaboradores/docs/', null=True, blank=True, verbose_name='Anexo Título de Eleitor (Verso)')
    
    anexo_reservista = models.FileField(upload_to='colaboradores/docs/', null=True, blank=True, verbose_name='Anexo Reservista (Frente)')
    anexo_reservista_verso = models.FileField(upload_to='colaboradores/docs/', null=True, blank=True, verbose_name='Anexo Reservista (Verso)')
    
    anexo_aso = models.FileField(upload_to='colaboradores/docs/', null=True, blank=True, verbose_name='Anexo ASO (Atestado de Saúde Ocupacional)')
    
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    objects = ColaboradorQuerySet.as_manager()

    def delete(self, using=None, keep_parents=False):
        """Protege o historico: excluir um colaborador significa desativa-lo."""
        self.status = 'inativo'
        self.save(using=using, update_fields=['status'])
        return 1, {self._meta.label: 1}

    class Meta:
        verbose_name = 'Colaborador'
        verbose_name_plural = 'Colaboradores'
        ordering = ['nome']

    def __str__(self):
        return self.nome or f'Colaborador #{self.pk or "novo"}'


class DocumentoColaborador(models.Model):
    TIPOS = [
        ('comprovante_endereco', 'Comprovante de endereço'),
        ('ajuda_custo', 'Ajuda de custo semanal'),
        ('comprovante_servico', 'Comprovante de serviço'),
        ('contrato', 'Contrato'),
    ]

    colaborador = models.ForeignKey(
        Colaborador, on_delete=models.CASCADE, related_name='documentos_arquivo'
    )
    tipo = models.CharField(max_length=30, choices=TIPOS)
    arquivo = models.FileField(upload_to='colaboradores/documentos/')
    nome_original = models.CharField(max_length=255, blank=True)
    data_referencia = models.DateField(
        null=True, blank=True, verbose_name='Data de referência'
    )
    descricao = models.CharField(max_length=255, blank=True, verbose_name='Observação')
    enviado_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='documentos_colaboradores_enviados',
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Documento do colaborador'
        verbose_name_plural = 'Documentos dos colaboradores'
        ordering = ['-data_referencia', '-criado_em']
        indexes = [
            models.Index(fields=['colaborador', 'tipo', 'data_referencia']),
        ]

    def __str__(self):
        return f'{self.get_tipo_display()} - {self.colaborador.nome}'


class PagamentoColaborador(models.Model):
    TIPOS = [
        ('salario', 'Salário'),
        ('vale_transporte', 'Vale-transporte'),
    ]
    STATUS = [
        ('pendente', 'Pendente'),
        ('pago', 'Pago'),
    ]

    colaborador = models.ForeignKey(
        Colaborador,
        on_delete=models.PROTECT,
        related_name='pagamentos',
    )
    tipo = models.CharField(max_length=30, choices=TIPOS)
    competencia = models.DateField(verbose_name='Competência/período')
    valor = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    data_vencimento = models.DateField(verbose_name='Vencimento')
    status = models.CharField(max_length=10, choices=STATUS, default='pendente')
    data_pagamento = models.DateField(null=True, blank=True, verbose_name='Data do pagamento')
    observacao = models.TextField(blank=True, verbose_name='Observação')
    criado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pagamentos_colaboradores_criados',
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Pagamento de colaborador'
        verbose_name_plural = 'Pagamentos de colaboradores'
        ordering = ['-competencia', '-data_vencimento', '-pk']
        constraints = [
            models.UniqueConstraint(
                fields=['colaborador', 'tipo', 'competencia'],
                name='pagamento_unico_colaborador_tipo_competencia',
            ),
        ]
        indexes = [
            models.Index(fields=['status', 'data_vencimento']),
            models.Index(fields=['colaborador', 'competencia']),
        ]

    def __str__(self):
        return f'{self.get_tipo_display()} - {self.colaborador} - {self.competencia:%d/%m/%Y}'


class Admissao(models.Model):
    STATUS = [
        ('aguardando_documentos', 'Aguardando Documentos'),
        ('documentos_em_analise', 'Documentos em Análise'),
        ('documentos_pendentes', 'Documentos Pendentes'),
        ('cadastro_sistema', 'Cadastro no Sistema'),
        ('contrato_gerado', 'Contrato Gerado'),
        ('integracao', 'Em Integração'),
        ('epis_entregues', 'EPIs Entregues'),
        ('liberado', 'Liberado para Unidade'),
        ('concluido', 'Concluído'),
    ]

    candidato_nome = models.CharField(max_length=200, verbose_name='Nome do Candidato')
    candidato_email = models.EmailField(verbose_name='E-mail do Candidato')
    candidato_telefone = models.CharField(max_length=20, blank=True)
    vaga_nome = models.CharField(max_length=200, verbose_name='Vaga')
    unidade_destino = models.CharField(max_length=100, verbose_name='Unidade de Destino')
    colaborador = models.OneToOneField(Colaborador, on_delete=models.SET_NULL,
                                        null=True, blank=True, related_name='admissao')
    status = models.CharField(max_length=30, choices=STATUS, default='aguardando_documentos')
    responsavel_rh = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name='admissoes_responsavel')
    observacoes = models.TextField(blank=True)
    tem_filhos_menores_14 = models.BooleanField(default=False, verbose_name='Tem filhos menores de 14 anos?')
    data_inicio = models.DateField(null=True, blank=True, verbose_name='Data de Início na Empresa')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    concluido_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Processo Admissional'
        verbose_name_plural = 'Processos Admissionais'
        ordering = ['-criado_em']

    def __str__(self):
        return f"Admissão: {self.candidato_nome} → {self.vaga_nome}"

    def percentual_conclusao(self):
        docs = self.documentos.all()
        if not docs.exists():
            return 0
        aprovados = docs.filter(status='aprovado').count()
        return int((aprovados / docs.count()) * 100)


class DocumentoAdmissional(models.Model):
    TIPOS = [
        ('rg', 'RG'),
        ('cpf', 'CPF'),
        ('ctps', 'Carteira de Trabalho (CTPS)'),
        ('pis', 'PIS/PASEP'),
        ('comprovante_residencia', 'Comprovante de Residência'),
        ('certidao_nascimento', 'Certidão de Nascimento'),
        ('certidao_casamento', 'Certidão de Casamento'),
        ('diploma', 'Diploma/Certificado Escolar'),
        ('foto_3x4', 'Foto 3x4'),
        ('atestado_saude', 'Atestado de Saúde Ocupacional (ASO)'),
        ('dados_bancarios', 'Dados Bancários'),
        ('antecedentes', 'Certidão de Antecedentes Criminais'),
        ('titulo_eleitor', 'Título de Eleitor'),
        ('reservista', 'Certificado de Reservista'),
        ('carteira_vacinacao', 'Carteira de Vacinação dos Filhos'),
    ]
    STATUS = [
        ('pendente', 'Pendente'),
        ('aguardando_analise', 'Aguardando Análise'),
        ('aprovado', 'Aprovado'),
        ('rejeitado', 'Rejeitado — Solicitar Correção'),
    ]

    admissao = models.ForeignKey(Admissao, on_delete=models.CASCADE, related_name='documentos')
    tipo = models.CharField(max_length=30, choices=TIPOS)
    status = models.CharField(max_length=20, choices=STATUS, default='pendente')
    observacao = models.TextField(blank=True, verbose_name='Observação')
    enviado_em = models.DateTimeField(auto_now_add=True)
    arquivo = models.BinaryField(null=True, blank=True, editable=True, verbose_name='Arquivo do Documento (Legado DB)')
    arquivo_nuvem = models.FileField(upload_to='documentos_admissional/', null=True, blank=True, verbose_name='Arquivo do Documento (Nuvem)')
    arquivo_nome = models.CharField(max_length=255, null=True, blank=True, verbose_name='Nome do Arquivo')
    arquivo_mimetype = models.CharField(max_length=100, null=True, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Documento Admissional'
        verbose_name_plural = 'Documentos Admissionais'
        unique_together = ('admissao', 'tipo')

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.get_status_display()}"


class PresencaDiaria(models.Model):
    STATUS_CHOICES = [
        ('presente', 'Presente'),
        ('falta', 'Falta'),
        ('atestado', 'Atestado/Licença'),
        ('folga', 'Folga'),
    ]

    colaborador = models.ForeignKey(Colaborador, on_delete=models.CASCADE, related_name='presencas')
    data = models.DateField(verbose_name='Data')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='presente')
    observacao = models.TextField(blank=True, verbose_name='Observação')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Presença Diária'
        verbose_name_plural = 'Controle de Presenças'
        unique_together = ('colaborador', 'data')
        ordering = ['-data', 'colaborador__nome']

    def __str__(self):
        return f"{self.colaborador.nome} - {self.data} ({self.get_status_display()})"
