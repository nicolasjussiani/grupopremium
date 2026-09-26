"""ERP Grupo PremiumBR — Models do Módulo 2: Admissional"""
from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.db.models import BooleanField, Case, Exists, OuterRef, Q, Value, When
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.contrib.contenttypes.fields import GenericRelation
from django.utils import timezone


TIPOS_PAGAMENTO_CANCELAVEIS_NA_DESATIVACAO = {
    'salario',
    'salario_beneficios',
    'vale_transporte',
    'ajuda_custo',
    'prestacao_servico',
    'freelancer',
}

TIPOS_PAGAMENTO_SEMANAIS = {'vale_transporte', 'ajuda_custo'}


def periodo_semanal(data_referencia):
    """Retorna a segunda e o domingo da semana da data informada."""
    segunda = data_referencia - timedelta(days=data_referencia.weekday())
    return segunda, segunda + timedelta(days=6)


def cancelar_pagamentos_futuros(colaborador_ids):
    """Retira da folha os pagamentos futuros gerados para pessoas desativadas."""
    hoje = timezone.localdate()
    return PagamentoColaborador.objects.filter(
        colaborador_id__in=colaborador_ids,
        status='pendente',
        tipo__in=TIPOS_PAGAMENTO_CANCELAVEIS_NA_DESATIVACAO,
    ).filter(
        Q(data_vencimento__gte=hoje)
        | Q(tipo__in=TIPOS_PAGAMENTO_SEMANAIS, competencia_fim__gte=hoje)
    ).update(status='cancelado', recorrente=False)


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
        colaboradores = self.exclude(status='inativo')
        ids = list(colaboradores.values_list('pk', flat=True))
        quantidade = colaboradores.update(status='inativo')
        if ids:
            cancelar_pagamentos_futuros(ids)
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
    CATEGORIAS_TRABALHO = [
        ('fixo', 'Colaborador fixo'),
        ('freelancer', 'Freelancer'),
    ]
    categoria_trabalho = models.CharField(
        max_length=15,
        choices=CATEGORIAS_TRABALHO,
        default='fixo',
        db_index=True,
        verbose_name='Categoria de trabalho',
    )

    cargo = models.CharField(max_length=200, blank=True, verbose_name='Cargo')
    setor = models.CharField(max_length=100, blank=True, verbose_name='Setor')
    unidade = models.CharField(max_length=100, blank=True, verbose_name='Unidade')
    contrato = models.CharField(max_length=200, blank=True, verbose_name='Contrato/Cliente')
    marca = models.CharField(max_length=20, choices=MARCAS, default='eco_premium', verbose_name='Marca')
    data_admissao = models.DateField(null=True, blank=True, verbose_name='Data de Admissão')
    data_desligamento = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name='Data de Desligamento',
    )
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
    ajuda_custo_semanal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name='Ajuda de custo semanal',
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

    STATUS_SEM_PAGAMENTO = {'inativo', 'desligado'}

    def save(self, *args, **kwargs):
        status_anterior = None
        if self.pk:
            status_anterior = type(self).objects.filter(pk=self.pk).values_list(
                'status', flat=True
            ).first()
        super().save(*args, **kwargs)
        if (
            self.status in self.STATUS_SEM_PAGAMENTO
            and status_anterior not in self.STATUS_SEM_PAGAMENTO
        ):
            cancelar_pagamentos_futuros([self.pk])

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

    def clean(self):
        super().clean()
        if self.status in self.STATUS_SEM_PAGAMENTO and not self.data_desligamento:
            raise ValidationError({
                'data_desligamento':
                    'Informe a data de desligamento do colaborador.'
            })
        if (
            self.data_admissao
            and self.data_desligamento
            and self.data_desligamento < self.data_admissao
        ):
            raise ValidationError({
                'data_desligamento':
                    'A data de desligamento não pode ser anterior à admissão.'
            })
        if self.tipo_contrato == 'pj' and (self.vale_transporte_semanal or 0) > 0:
            raise ValidationError({
                'vale_transporte_semanal':
                    'Vale-transporte deve ser usado somente para colaboradores CLT.'
            })
        if self.tipo_contrato == 'clt' and (self.ajuda_custo_semanal or 0) > 0:
            raise ValidationError({
                'ajuda_custo_semanal':
                    'Ajuda de custo deve ser usada somente para colaboradores PJ.'
            })


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
        ('ajuda_custo', 'Ajuda de custo'),
        ('auxilio_telefonia', 'Auxílio telefonia'),
        ('salario_beneficios', 'Salário e benefícios'),
        ('prestacao_servico', 'Prestação de serviços'),
        ('freelancer', 'Freelancer'),
        ('distrato', 'Distrato'),
        ('reembolso', 'Reembolso'),
    ]
    STATUS = [
        ('pendente', 'Pendente'),
        ('pago', 'Pago'),
        ('cancelado', 'Cancelado / retirado da folha'),
    ]

    colaborador = models.ForeignKey(
        Colaborador,
        on_delete=models.PROTECT,
        related_name='pagamentos',
    )
    tipo = models.CharField(max_length=30, choices=TIPOS)
    competencia = models.DateField(verbose_name='Início da competência')
    competencia_fim = models.DateField(
        null=True,
        blank=True,
        verbose_name='Fim da competência',
    )
    valor = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    dias_trabalhados = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='Dias trabalhados',
        help_text='Obrigatório para freelancer: quantidade de dias efetivamente trabalhados.',
    )
    valor_diaria = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='Valor da diária',
        help_text='Obrigatório para freelancer. O total será dias trabalhados × diária.',
    )
    chave_pix = models.CharField(
        max_length=180,
        blank=True,
        verbose_name='Chave PIX',
        help_text='Chave utilizada para este pagamento.',
    )
    data_vencimento = models.DateField(verbose_name='Vencimento')
    status = models.CharField(max_length=10, choices=STATUS, default='pendente')
    data_pagamento = models.DateField(null=True, blank=True, verbose_name='Data do pagamento')
    observacao = models.TextField(blank=True, verbose_name='Observação')
    recorrente = models.BooleanField(
        default=False,
        verbose_name='Repetir semanalmente',
        help_text='Cria a próxima semana automaticamente quando este pagamento for marcado como pago.',
    )
    identificador_transacao = models.CharField(
        max_length=160,
        unique=True,
        null=True,
        blank=True,
        verbose_name='Identificador da transação',
    )
    criado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pagamentos_colaboradores_criados',
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    arquivos_importados = GenericRelation(
        'core.ArquivoImportado', related_query_name='pagamento_colaborador'
    )

    class Meta:
        verbose_name = 'Pagamento de colaborador'
        verbose_name_plural = 'Pagamentos de colaboradores'
        ordering = ['-competencia', '-data_vencimento', '-pk']
        indexes = [
            models.Index(fields=['status', 'data_vencimento']),
            models.Index(fields=['colaborador', 'competencia']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    'colaborador', 'tipo', 'competencia',
                    'data_vencimento', 'valor',
                ],
                condition=~Q(status='cancelado'),
                name='admissional_pagamento_ativo_sem_duplicidade',
            ),
            models.UniqueConstraint(
                fields=['colaborador', 'tipo', 'data_vencimento'],
                condition=(
                    ~Q(status='cancelado')
                    & Q(tipo__in=[
                        'salario', 'vale_transporte', 'ajuda_custo',
                        'freelancer', 'prestacao_servico',
                    ])
                ),
                name='admissional_um_tipo_por_vencimento',
            ),
            models.UniqueConstraint(
                fields=['colaborador', 'tipo', 'data_pagamento'],
                condition=(
                    Q(status='pago', data_pagamento__isnull=False)
                    & Q(tipo__in=[
                        'salario', 'vale_transporte', 'ajuda_custo',
                        'freelancer', 'prestacao_servico',
                    ])
                ),
                name='admissional_um_tipo_pago_por_dia',
            ),
            models.UniqueConstraint(
                fields=['colaborador', 'tipo', 'competencia', 'valor'],
                condition=(
                    ~Q(status='cancelado')
                    & Q(tipo__in=[
                        'salario', 'vale_transporte', 'ajuda_custo',
                        'freelancer', 'prestacao_servico',
                    ])
                ),
                name='admissional_um_valor_por_competencia',
            ),
            models.UniqueConstraint(
                fields=['colaborador', 'competencia'],
                condition=Q(tipo='salario') & ~Q(status='cancelado'),
                name='admissional_um_salario_por_competencia',
            ),
        ]

    def __str__(self):
        return f'{self.get_tipo_display()} - {self.colaborador} - {self.competencia:%d/%m/%Y}'

    def normalizar_datas_semanais(self):
        if self.tipo not in TIPOS_PAGAMENTO_SEMANAIS:
            return
        referencia = self.competencia or self.data_vencimento or self.data_pagamento
        if referencia:
            segunda, domingo = periodo_semanal(referencia)
            self.competencia = segunda
            self.competencia_fim = domingo
            self.data_vencimento = segunda
        if self.data_pagamento:
            self.data_pagamento = periodo_semanal(self.data_pagamento)[0]
        self.recorrente = self.status != 'cancelado'

    def save(self, *args, **kwargs):
        self.normalizar_datas_semanais()
        update_fields = kwargs.get('update_fields')
        if update_fields is not None and self.tipo in TIPOS_PAGAMENTO_SEMANAIS:
            kwargs['update_fields'] = set(update_fields) | {
                'competencia', 'competencia_fim', 'data_vencimento',
                'data_pagamento', 'recorrente',
            }
        return super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        self.normalizar_datas_semanais()
        if self.competencia_fim and self.competencia and self.competencia_fim < self.competencia:
            raise ValidationError({
                'competencia_fim': 'O fim da competência não pode ser anterior ao início.'
            })
        if self.recorrente and self.tipo not in {'vale_transporte', 'ajuda_custo'}:
            raise ValidationError({
                'recorrente': 'A recorrência semanal é permitida apenas para VT ou ajuda de custo.'
            })
        if bool(self.dias_trabalhados) != bool(self.valor_diaria):
            raise ValidationError({
                'dias_trabalhados': 'Informe os dias trabalhados e o valor da diária juntos.',
                'valor_diaria': 'Informe os dias trabalhados e o valor da diária juntos.',
            })
        if not self.colaborador_id:
            return
        if (
            self.status != 'cancelado'
            and self.competencia
            and self.data_vencimento
            and self.valor is not None
            and type(self).objects.exclude(pk=self.pk).exclude(status='cancelado').filter(
                colaborador_id=self.colaborador_id,
                tipo=self.tipo,
                competencia=self.competencia,
                data_vencimento=self.data_vencimento,
                valor=self.valor,
            ).exists()
        ):
            raise ValidationError(
                'Já existe um lançamento igual para esta pessoa, data, tipo e valor.'
            )
        if (
            self.colaborador.status in Colaborador.STATUS_SEM_PAGAMENTO
            and self.status not in {'pago', 'cancelado'}
            and self.tipo != 'distrato'
        ):
            raise ValidationError({
                'colaborador': (
                    'Não é possível criar pagamentos regulares pendentes para '
                    'um colaborador inativo.'
                )
            })
        tipo_contrato = self.colaborador.tipo_contrato
        if self.tipo == 'vale_transporte' and tipo_contrato != 'clt':
            raise ValidationError({
                'tipo': 'Vale-transporte deve ser cadastrado somente para colaboradores CLT.'
            })
        if self.tipo == 'ajuda_custo' and tipo_contrato != 'pj':
            raise ValidationError({
                'tipo': 'Ajuda de custo deve ser cadastrada somente para colaboradores PJ.'
            })

    @property
    def fim_competencia(self):
        return self.competencia_fim or self.competencia

    def criar_proxima_recorrencia(self, usuario=None):
        """Gera uma única parcela da semana seguinte, sem duplicar registros."""
        if (
            self.colaborador.status in Colaborador.STATUS_SEM_PAGAMENTO
            or not self.recorrente
            or self.status != 'pago'
            or self.tipo not in {
            'vale_transporte', 'ajuda_custo',
            }
        ):
            return None, False
        proximo_inicio = self.competencia + timedelta(days=7)
        # Valores proporcionais precisam de uma nova revisão das presenças.
        if ProgramacaoVT.objects.filter(
            colaborador_id=self.colaborador_id, segunda=self.competencia,
            valor_semana_completa__isnull=False,
        ).exists():
            return None, False
        if ProgramacaoVT.objects.filter(
            colaborador_id=self.colaborador_id, segunda=proximo_inicio, pagar=False,
        ).exists():
            return None, False
        existente = PagamentoColaborador.objects.filter(
            colaborador=self.colaborador,
            tipo=self.tipo,
            competencia=proximo_inicio,
        ).first()
        if existente:
            return existente, False
        duracao = self.fim_competencia - self.competencia
        proximo = PagamentoColaborador(
            colaborador=self.colaborador,
            tipo=self.tipo,
            competencia=proximo_inicio,
            competencia_fim=proximo_inicio + duracao,
            valor=self.valor,
            data_vencimento=self.data_vencimento + timedelta(days=7),
            status='pendente',
            recorrente=True,
            observacao=f'Recorrência automática do pagamento #{self.pk}.',
            criado_por=usuario or self.criado_por,
        )
        proximo.full_clean()
        proximo.save()
        return proximo, True


class ProgramacaoVT(models.Model):
    colaborador = models.ForeignKey(Colaborador, on_delete=models.PROTECT)
    segunda = models.DateField(db_index=True)
    pagar = models.BooleanField()
    valor_semana_completa = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    dias_presentes = models.PositiveSmallIntegerField(null=True, blank=True)
    atualizado_por = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=['colaborador', 'segunda'], name='vt_decisao_por_semana',
        )]


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
        ('indefinido', 'Não definido'),
        ('presente', 'Presente'),
        ('falta', 'Falta'),
        ('atestado', 'Atestado/Licença'),
        ('folga', 'Folga'),
    ]

    colaborador = models.ForeignKey(Colaborador, on_delete=models.CASCADE, related_name='presencas')
    data = models.DateField(verbose_name='Data')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='indefinido')
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
