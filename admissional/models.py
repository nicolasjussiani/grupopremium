"""ERP Grupo PremiumBR — Models do Módulo 2: Admissional"""
from django.db import models
from django.contrib.auth.models import User


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

    nome = models.CharField(max_length=200, verbose_name='Nome Completo')
    cpf = models.CharField(max_length=18, unique=True, verbose_name='CPF/CNPJ')
    rg = models.CharField(max_length=20, blank=True, verbose_name='RG')
    data_nascimento = models.DateField(null=True, blank=True, verbose_name='Data de Nascimento')
    email = models.EmailField(verbose_name='E-mail')
    telefone = models.CharField(max_length=20, verbose_name='Telefone')
    endereco = models.TextField(blank=True, verbose_name='Endereço')
    cargo = models.CharField(max_length=200, verbose_name='Cargo')
    setor = models.CharField(max_length=100, blank=True, verbose_name='Setor')
    unidade = models.CharField(max_length=100, verbose_name='Unidade')
    marca = models.CharField(max_length=20, choices=MARCAS, default='eco_premium', verbose_name='Marca')
    data_admissao = models.DateField(verbose_name='Data de Admissão')
    status = models.CharField(max_length=20, choices=STATUS, default='ativo')
    pis_pasep = models.CharField(max_length=20, blank=True, verbose_name='PIS/PASEP')
    ctps = models.CharField(max_length=30, blank=True, verbose_name='CTPS')
    salario = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Salário')
    
    # Anexos de documentos
    anexo_cpf = models.FileField(upload_to='colaboradores/docs/', null=True, blank=True, verbose_name='Anexo CPF/CNPJ')
    anexo_rg = models.FileField(upload_to='colaboradores/docs/', null=True, blank=True, verbose_name='Anexo RG')
    anexo_pis = models.FileField(upload_to='colaboradores/docs/', null=True, blank=True, verbose_name='Anexo PIS/PASEP')
    anexo_ctps = models.FileField(upload_to='colaboradores/docs/', null=True, blank=True, verbose_name='Anexo CTPS')
    anexo_titulo = models.FileField(upload_to='colaboradores/docs/', null=True, blank=True, verbose_name='Anexo Título de Eleitor')
    anexo_reservista = models.FileField(upload_to='colaboradores/docs/', null=True, blank=True, verbose_name='Anexo Reservista')
    
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Colaborador'
        verbose_name_plural = 'Colaboradores'
        ordering = ['nome']

    def __str__(self):
        return f"{self.nome} — {self.cargo} ({self.unidade})"


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
