"""ERP Grupo PremiumBR — Models do Módulo 3: Administrativo"""
from django.db import models
from django.contrib.auth.models import User


class DemandaAdministrativa(models.Model):
    TIPOS = [
        ('controle_documental', 'Controle Documental'),
        ('contratos', 'Contratos'),
        ('fornecedores', 'Fornecedores'),
        ('reembolsos', 'Reembolsos'),
        ('pagamentos', 'Pagamentos'),
        ('relatorios', 'Relatórios'),
        ('agendas_reunioes', 'Agendas e Reuniões'),
        ('apoio_operacional', 'Apoio Operacional'),
    ]
    STATUS = [
        ('recebida', 'Recebida'),
        ('em_triagem', 'Em Triagem'),
        ('informacoes_incompletas', 'Informações Incompletas'),
        ('em_execucao', 'Em Execução'),
        ('aguardando_ajuste', 'Aguardando Ajuste'),
        ('arquivada', 'Arquivada / Concluída'),
    ]
    PRIORIDADES = [
        ('baixa', 'Baixa'),
        ('media', 'Média'),
        ('alta', 'Alta'),
        ('urgente', 'Urgente'),
    ]

    tipo = models.CharField(max_length=30, choices=TIPOS, verbose_name='Tipo de Demanda')
    titulo = models.CharField(max_length=200, verbose_name='Título')
    descricao = models.TextField(verbose_name='Descrição Detalhada')
    requisitante = models.CharField(max_length=200, verbose_name='Requisitante')
    requisitante_usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                              related_name='demandas_solicitadas')
    responsavel = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='demandas_responsavel', verbose_name='Responsável')
    prioridade = models.CharField(max_length=10, choices=PRIORIDADES, default='media')
    status = models.CharField(max_length=30, choices=STATUS, default='recebida')
    motivo_rejeicao = models.TextField(blank=True, verbose_name='Motivo de Rejeição/Ajuste')
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    concluido_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Demanda Administrativa'
        verbose_name_plural = 'Demandas Administrativas'
        ordering = ['-criado_em']

    def __str__(self):
        return f"[{self.get_tipo_display()}] {self.titulo} — {self.get_status_display()}"

    def get_prioridade_color(self):
        cores = {
            'baixa': 'success',
            'media': 'info',
            'alta': 'warning',
            'urgente': 'danger',
        }
        return cores.get(self.prioridade, 'secondary')
