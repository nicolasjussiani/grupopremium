from django.db import models
from django.contrib.auth.models import User

class Ativo(models.Model):
    STATUS = [
        ('ativo', 'Ativo / Em Uso'),
        ('manutencao', 'Em Manutenção'),
        ('inativo', 'Baixado / Inativo'),
    ]

    numero_patrimonio = models.CharField(max_length=50, unique=True, verbose_name='Número de Patrimônio')
    nome = models.CharField(max_length=200, verbose_name='Nome do Equipamento/Ativo')
    descricao = models.TextField(blank=True, verbose_name='Descrição / Especificações')
    unidade_atual = models.CharField(max_length=100, verbose_name='Unidade Atual')
    status = models.CharField(max_length=20, choices=STATUS, default='ativo', verbose_name='Status')
    data_aquisicao = models.DateField(null=True, blank=True, verbose_name='Data de Aquisição')
    valor_aquisicao = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Valor de Aquisição')
    foto = models.ImageField(upload_to='equipamentos/', null=True, blank=True, verbose_name='Foto do Equipamento')
    
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Ativo (Patrimônio)'
        verbose_name_plural = 'Ativos (Patrimônio)'
        ordering = ['nome']

    def __str__(self):
        return f"[{self.numero_patrimonio}] {self.nome} - {self.unidade_atual}"

class RegistroManutencao(models.Model):
    STATUS = [
        ('aguardando_aprovacao', 'Aguardando Aprovação (CEO)'),
        ('aberta', 'Aberta / Em Análise'),
        ('andamento', 'Em Andamento (Conserto)'),
        ('concluida', 'Concluída'),
        ('cancelada', 'Cancelada'),
    ]

    ativo = models.ForeignKey(Ativo, on_delete=models.CASCADE, related_name='manutencoes', verbose_name='Equipamento')
    unidade_origem = models.CharField(max_length=100, verbose_name='Unidade de Origem (Onde estava)')
    motivo = models.TextField(verbose_name='Motivo da Manutenção / Defeito')
    data_inicio = models.DateField(verbose_name='Data de Início')
    data_conclusao = models.DateField(null=True, blank=True, verbose_name='Data de Conclusão')
    status = models.CharField(max_length=20, choices=STATUS, default='aberta', verbose_name='Status da Manutenção')
    custo_reparo = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Custo do Reparo (R$)')
    fornecedor_servico = models.CharField(max_length=200, blank=True, verbose_name='Fornecedor / Técnico')
    obs = models.TextField(blank=True, verbose_name='Observações / Laudo Técnico')
    foto_equipamento = models.ImageField(upload_to='manutencao/', null=True, blank=True, verbose_name='Foto do Equipamento')
    registrado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Registro de Manutenção'
        verbose_name_plural = 'Registros de Manutenção'
        ordering = ['-data_inicio']

    def __str__(self):
        return f"Manutenção: {self.ativo.nome} ({self.get_status_display()})"
