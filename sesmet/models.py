"""ERP Grupo PremiumBR — Models do Módulo 4: SESMET / Segurança do Trabalho"""
from django.db import models
from django.contrib.auth.models import User
from admissional.models import Colaborador
from django.utils import timezone
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db import transaction
from uuid import uuid4


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


class EquipamentoProtecao(models.Model):
    codigo = models.CharField(max_length=20, unique=True, blank=True, verbose_name='Código interno')
    nome = models.CharField(max_length=150, verbose_name='Nome do EPI (ex: Luva de Raspa)')
    foto = models.ImageField(
        upload_to='epis/fotos/', null=True, blank=True,
        verbose_name='Foto do EPI',
    )
    numero_ca = models.CharField(max_length=20, blank=True, verbose_name='Número do CA')
    fabricante = models.CharField(max_length=150, blank=True)
    validade_ca = models.DateField(null=True, blank=True, verbose_name='Validade do CA')
    dias_durabilidade = models.PositiveIntegerField(default=90, verbose_name='Ciclo padrão (dias)')
    estoque_atual = models.IntegerField(default=0, verbose_name='Quantidade em Estoque')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Equipamento de Proteção'
        verbose_name_plural = 'Equipamentos de Proteção (Catálogo)'
        ordering = ['nome']
        constraints = [
            models.CheckConstraint(condition=models.Q(estoque_atual__gte=0), name='sesmet_estoque_epi_nao_negativo'),
        ]

    def __str__(self):
        return f"[{self.codigo}] {self.nome} (CA: {self.numero_ca})"

    def save(self, *args, **kwargs):
        gerar_codigo = self.pk is None and not self.codigo
        if gerar_codigo:
            self.codigo = f'TMP-{uuid4().hex[:16]}'
        super().save(*args, **kwargs)
        if gerar_codigo:
            self.codigo = f'EPI-{self.pk:06d}'
            type(self).objects.filter(pk=self.pk).update(codigo=self.codigo)

class RegistroEPI(models.Model):
    NIVEIS_ALERTA = [
        ('', 'Sem alerta'),
        ('proximo', 'Vencimento próximo'),
        ('urgente', 'Vencimento urgente'),
        ('vencido', 'Vencido'),
    ]
    TIPO_MOVIMENTACAO = [
        ('retirada', 'Retirada (Entrega)'),
        ('devolucao', 'Devolução'),
        ('descarte', 'Descarte / Perda'),
    ]

    colaborador = models.ForeignKey(Colaborador, on_delete=models.CASCADE, related_name='movimentacoes_epi')
    equipamento = models.ForeignKey(EquipamentoProtecao, on_delete=models.PROTECT, related_name='movimentacoes')
    tipo_movimentacao = models.CharField(max_length=20, choices=TIPO_MOVIMENTACAO, default='retirada')
    
    data_movimentacao = models.DateField(verbose_name='Data da Movimentação', default=timezone.now)
    quantidade = models.PositiveIntegerField(default=1)
    
    # Validade calculada no caso de 'retirada'
    data_validade = models.DateField(null=True, blank=True, verbose_name='Data de Vencimento Previsto')
    ciclo_ativo = models.BooleanField(default=True, db_index=True, verbose_name='Ciclo de 90 dias ativo')
    nivel_alerta = models.CharField(
        max_length=10,
        choices=NIVEIS_ALERTA,
        default='',
        blank=True,
        verbose_name='Último alerta enviado',
    )
    
    assinado = models.BooleanField(default=False, verbose_name='Colaborador Assinou?')
    assinatura_base64 = models.TextField(blank=True, null=True, verbose_name='Assinatura Digital')
    data_assinatura = models.DateTimeField(null=True, blank=True, verbose_name='Data da Assinatura')
    
    registrado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    obs = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Movimentação de EPI'
        verbose_name_plural = 'Movimentações de EPIs'
        ordering = ['-data_movimentacao', '-criado_em']
        constraints = [
            models.CheckConstraint(condition=models.Q(quantidade__gt=0), name='sesmet_quantidade_epi_positiva'),
        ]

    def __str__(self):
        return f"{self.get_tipo_movimentacao_display()} - {self.equipamento.nome} ({self.colaborador.nome})"

    def calcular_validade(self):
        if self.tipo_movimentacao == 'retirada':
            return self.data_movimentacao + timedelta(days=90)
        return None

    @property
    def dias_para_vencer(self):
        if not self.data_validade:
            return None
        return (self.data_validade - timezone.localdate()).days

    @property
    def esta_vencido(self):
        return self.dias_para_vencer is not None and self.dias_para_vencer < 0

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if not self.data_validade and self.tipo_movimentacao == 'retirada':
            self.data_validade = self.calcular_validade()

        if not is_new:
            original = type(self).objects.get(pk=self.pk)
            campos_estoque = ('equipamento_id', 'tipo_movimentacao', 'quantidade')
            if any(getattr(original, campo) != getattr(self, campo) for campo in campos_estoque):
                raise ValidationError(
                    'Equipamento, tipo e quantidade nao podem ser alterados apos a movimentacao.'
                )
            return super().save(*args, **kwargs)
        if self.quantidade <= 0:
            raise ValidationError('A quantidade deve ser maior que zero.')

        with transaction.atomic():
            equipamento = EquipamentoProtecao.objects.select_for_update().get(pk=self.equipamento_id)
            if self.tipo_movimentacao == 'retirada':
                if equipamento.estoque_atual < self.quantidade:
                    raise ValidationError('Estoque insuficiente para esta retirada.')
                type(self).objects.filter(
                    colaborador_id=self.colaborador_id,
                    equipamento_id=self.equipamento_id,
                    tipo_movimentacao='retirada',
                    ciclo_ativo=True,
                ).update(ciclo_ativo=False)
                equipamento.estoque_atual -= self.quantidade
            elif self.tipo_movimentacao == 'devolucao':
                equipamento.estoque_atual += self.quantidade
                type(self).objects.filter(
                    colaborador_id=self.colaborador_id,
                    equipamento_id=self.equipamento_id,
                    tipo_movimentacao='retirada',
                    ciclo_ativo=True,
                ).update(ciclo_ativo=False)
                self.ciclo_ativo = False
            else:
                self.ciclo_ativo = False
            super().save(*args, **kwargs)
            equipamento.save(update_fields=['estoque_atual', 'atualizado_em'])
            self.equipamento = equipamento



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
