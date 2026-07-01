"""ERP Grupo Premium — Models do Módulo 1: Recrutamento e Seleção"""
from django.db import models
from django.contrib.auth.models import User


class Vaga(models.Model):
    STATUS_CHOICES = [
        ('aguardando_aprovacao', 'Aguardando Aprovação'),
        ('informacoes_incompletas', 'Informações Incompletas'),
        ('em_selecao', 'Em Seleção'),
        ('aguardando_entrevista', 'Aguardando Entrevista Final'),
        ('preenchida', 'Vaga Preenchida'),
        ('cancelada', 'Cancelada'),
    ]
    TIPO_CONTRATACAO = [
        ('clt', 'CLT'),
        ('pj', 'Pessoa Jurídica'),
        ('temporario', 'Temporário'),
        ('estagio', 'Estágio'),
        ('autonomo', 'Autônomo'),
    ]

    nome_vaga = models.CharField(max_length=200, verbose_name='Nome da Vaga')
    quantidade_colaboradores = models.PositiveIntegerField(verbose_name='Quantidade de Colaboradores')
    cidade = models.CharField(max_length=100, verbose_name='Cidade')
    unidade = models.CharField(max_length=100, verbose_name='Unidade')
    perfil_desejado = models.TextField(verbose_name='Perfil Desejado')
    atividades = models.TextField(verbose_name='Atividades da Função')
    horario_trabalho = models.CharField(max_length=100, verbose_name='Horário de Trabalho')
    tipo_contratacao = models.CharField(max_length=20, choices=TIPO_CONTRATACAO, verbose_name='Tipo de Contratação')
    valor_salario = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Valor/Salário')
    previsao_inicio = models.DateField(verbose_name='Previsão de Início')
    exige_experiencia = models.BooleanField(default=False, verbose_name='Exige Experiência?')
    descricao_experiencia = models.TextField(blank=True, verbose_name='Descrição da Experiência Necessária')
    motivo_solicitacao = models.TextField(verbose_name='Motivo da Solicitação')
    gestor_responsavel = models.CharField(max_length=200, verbose_name='Nome do Gestor Responsável')
    gestor_usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name='vagas_abertas', verbose_name='Usuário Gestor')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='aguardando_aprovacao')
    observacoes = models.TextField(blank=True, verbose_name='Observações')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Vaga'
        verbose_name_plural = 'Vagas'
        ordering = ['-criado_em']

    def __str__(self):
        return f"{self.nome_vaga} - {self.unidade} ({self.get_status_display()})"

    def get_status_color(self):
        cores = {
            'aguardando_aprovacao': 'warning',
            'informacoes_incompletas': 'danger',
            'em_selecao': 'info',
            'aguardando_entrevista': 'primary',
            'preenchida': 'success',
            'cancelada': 'secondary',
        }
        return cores.get(self.status, 'secondary')


class Candidato(models.Model):
    ETAPAS = [
        ('triagem', 'Triagem / Seleção'),
        ('avaliacao_dp', 'Avaliação DP / Comportamental'),
        ('entrevista_final', 'Entrevista Final com Gestor'),
        ('aprovado', 'Aprovado'),
        ('reprovado', 'Reprovado'),
        ('desistente', 'Desistente'),
    ]

    vaga = models.ForeignKey(Vaga, on_delete=models.CASCADE, related_name='candidatos')
    nome = models.CharField(max_length=200, verbose_name='Nome Completo')
    email = models.EmailField(verbose_name='E-mail')
    telefone = models.CharField(max_length=20, verbose_name='Telefone')
    cidade = models.CharField(max_length=100, blank=True, verbose_name='Cidade')
    cpf = models.CharField(max_length=14, blank=True, verbose_name='CPF')
    etapa_atual = models.CharField(max_length=20, choices=ETAPAS, default='triagem')
    aprovado = models.BooleanField(null=True, blank=True, verbose_name='Aprovado?')
    curriculum_obs = models.TextField(blank=True, verbose_name='Observações do Currículo')
    avaliacao_comportamental = models.TextField(blank=True, verbose_name='Avaliação Comportamental')
    resultado_entrevista = models.TextField(blank=True, verbose_name='Resultado da Entrevista Final')
    avaliado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='candidatos_avaliados')
    encaminhado_admissao = models.BooleanField(default=False, verbose_name='Encaminhado para Admissão?')
    arquivo_pdf = models.BinaryField(null=True, blank=True, editable=True, verbose_name='Currículo PDF (Legado DB)')
    arquivo = models.FileField(upload_to='curriculos/', null=True, blank=True, verbose_name='Currículo PDF (Nuvem)')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Candidato'
        verbose_name_plural = 'Candidatos'
        ordering = ['-criado_em']

    def __str__(self):
        return f"{self.nome} → {self.vaga.nome_vaga} ({self.get_etapa_atual_display()})"


class Talento(models.Model):
    nome = models.CharField(max_length=200, verbose_name='Nome Completo')
    email = models.EmailField(verbose_name='E-mail', unique=True)
    telefone = models.CharField(max_length=20, verbose_name='Telefone')
    cidade = models.CharField(max_length=100, blank=True, verbose_name='Cidade')
    cpf = models.CharField(max_length=14, blank=True, verbose_name='CPF')
    curriculo_texto = models.TextField(blank=True, verbose_name='Texto Extraído do Currículo')
    arquivo_pdf = models.BinaryField(null=True, blank=True, editable=True, verbose_name='Currículo PDF (Legado DB)')
    arquivo = models.FileField(upload_to='curriculos/', null=True, blank=True, verbose_name='Currículo PDF (Nuvem)')
    ultima_vaga = models.ForeignKey(Vaga, on_delete=models.SET_NULL, null=True, blank=True, related_name='talentos_aplicados', verbose_name='Última Vaga Aplicada')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Talento'
        verbose_name_plural = 'Banco de Talentos'
        ordering = ['-criado_em']

    def __str__(self):
        return f"{self.nome} ({self.cidade})"

