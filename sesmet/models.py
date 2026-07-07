"""ERP Grupo PremiumBR — Models do Módulo 4: SESMET / Segurança do Trabalho"""
from django.db import models
from django.contrib.auth.models import User
from admissional.models import Colaborador
from django.utils import timezone
from datetime import timedelta


class IntegracaoSeguranca(models.Model):
    colaborador = models.OneToOneField(Colaborador, on_delete=models.CASCADE,
                                        related_name='integracao_seguranca')
    data_integracao = models.DateField(verbose_name='Data da Integração')
    apresentador = models.CharField(max_length=200, verbose_name='Apresentador SESMET')
    missao_visao_valores = models.BooleanField(default=False, verbose_name='Missão, Visão e Valores')
    normas_seguranca = models.BooleanField(default=False, verbose_name='Normas de Segurança')
    uso_epis = models.BooleanField(default=False, verbose_name='Uso e Cuidados com EPIs')
    procedimentos_emergencia = models.BooleanField(default=False, verbose_name='Procedimentos de Emergência')
    concluida = models.BooleanField(default=False, verbose_name='Integração Concluída')
    obs = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Integração de Segurança'
        verbose_name_plural = 'Integrações de Segurança'

    def __str__(self):
        return f"Integração: {self.colaborador.nome} ({self.data_integracao})"


class RegistroEPI(models.Model):
    TIPOS_EPI = [
        ('luva', 'Luva'),
        ('calcado', 'Calçado de Segurança'),
        ('protetor_auricular', 'Protetor Auricular'),
        ('respirador_p2', 'Respirador P2'),
        ('oculos', 'Óculos de Proteção'),
        ('uniforme', 'Uniforme'),
        ('capacete', 'Capacete'),
        ('cinto_seguranca', 'Cinto de Segurança'),
        ('avental', 'Avental de Proteção'),
    ]
    STATUS = [
        ('ativo', 'Ativo / Em Uso'),
        ('vencido', 'Vencido — Substituição Necessária'),
        ('substituido', 'Substituído'),
        ('perdido', 'Perdido / Danificado'),
    ]
    MOTIVOS_SUBSTITUICAO = [
        ('vencimento', 'Vencimento da Validade'),
        ('dano', 'Dano / Desgaste'),
        ('perda', 'Perda'),
        ('troca_cargo', 'Troca de Cargo/Função'),
        ('inicial', 'Entrega Inicial'),
    ]

    # Periodicidades em dias por tipo de EPI
    PERIODICIDADE = {
        'luva': 30,
        'calcado': 365,
        'protetor_auricular': 90,
        'respirador_p2': 3,
        'oculos': None,   # Avaliação
        'uniforme': None,  # Necessidade
        'capacete': 730,
        'cinto_seguranca': 365,
        'avental': 180,
    }

    colaborador = models.ForeignKey(Colaborador, on_delete=models.CASCADE, related_name='epis')
    tipo_epi = models.CharField(max_length=30, choices=TIPOS_EPI, verbose_name='Tipo de EPI')
    data_entrega = models.DateField(verbose_name='Data de Entrega')
    quantidade = models.PositiveIntegerField(default=1)
    numero_ca = models.CharField(max_length=20, blank=True, verbose_name='Número CA')
    data_validade = models.DateField(null=True, blank=True, verbose_name='Data de Validade/Substituição')
    status = models.CharField(max_length=20, choices=STATUS, default='ativo')
    motivo_substituicao = models.CharField(max_length=20, choices=MOTIVOS_SUBSTITUICAO,
                                            default='inicial', verbose_name='Motivo')
    assinado = models.BooleanField(default=False, verbose_name='Colaborador Assinou?')
    assinatura_base64 = models.TextField(blank=True, null=True, verbose_name='Assinatura Digital')
    data_assinatura = models.DateTimeField(null=True, blank=True, verbose_name='Data da Assinatura')
    registrado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name='epis_registrados')
    obs = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Registro de EPI'
        verbose_name_plural = 'Registros de EPIs'
        ordering = ['-data_entrega']

    def __str__(self):
        return f"{self.colaborador.nome} — {self.get_tipo_epi_display()} ({self.data_entrega})"

    def calcular_validade(self):
        """Calcula data de validade com base na periodicidade do tipo de EPI"""
        dias = self.PERIODICIDADE.get(self.tipo_epi)
        if dias:
            return self.data_entrega + timedelta(days=dias)
        return None

    def esta_vencido(self):
        if self.data_validade:
            return timezone.now().date() > self.data_validade
        return False

    def dias_para_vencer(self):
        if self.data_validade:
            delta = self.data_validade - timezone.now().date()
            return delta.days
        return None

    def save(self, *args, **kwargs):
        if not self.data_validade:
            self.data_validade = self.calcular_validade()
        if self.data_validade and timezone.now().date() > self.data_validade:
            self.status = 'vencido'
        super().save(*args, **kwargs)


class OrdemServico(models.Model):
    colaborador = models.ForeignKey(Colaborador, on_delete=models.CASCADE, related_name='ordens_servico')
    numero = models.CharField(max_length=20, unique=True, verbose_name='Número da OS')
    descricao_riscos = models.TextField(verbose_name='Descrição dos Riscos')
    medidas_preventivas = models.TextField(verbose_name='Medidas Preventivas')
    epis_obrigatorios = models.TextField(verbose_name='EPIs Obrigatórios')
    data_emissao = models.DateField(verbose_name='Data de Emissão')
    assinado = models.BooleanField(default=False, verbose_name='Colaborador Assinou?')
    data_assinatura = models.DateField(null=True, blank=True)
    emitido_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='os_emitidas')
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Ordem de Serviço'
        verbose_name_plural = 'Ordens de Serviço'
        ordering = ['-data_emissao']

    def __str__(self):
        return f"OS {self.numero} — {self.colaborador.nome}"
