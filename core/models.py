"""ERP Grupo PremiumBR — Models do Core (Perfil de Usuário + Aprovações)"""
from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class PerfilUsuario(models.Model):
    PERFIS = [
        ('admin', 'Administrador'),
        ('gestor', 'Gestor'),
        ('rh', 'RH / Departamento Pessoal'),
        ('financeiro', 'Financeiro / Fiscal'),
        ('sesmet', 'SESMET / Segurança do Trabalho'),
        ('compras', 'Compras / Almoxarifado'),
        ('operacional', 'Operacional'),
    ]
    MARCAS = [
        ('eco_premium', 'Eco Premium'),
        ('trip_premium', 'Trip Premium'),
        ('log_premium', 'Log Premium'),
        ('matriz', 'Matriz Grupo PremiumBR'),
    ]

    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    perfil = models.CharField(max_length=20, choices=PERFIS, default='operacional')
    marca = models.CharField(max_length=20, choices=MARCAS, default='eco_premium')
    unidade = models.CharField(max_length=100, default='Matriz')
    telefone = models.CharField(max_length=20, blank=True)
    avatar_iniciais = models.CharField(max_length=3, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Perfil de Usuário'
        verbose_name_plural = 'Perfis de Usuários'

    def __str__(self):
        return f"{self.usuario.get_full_name()} ({self.get_perfil_display()})"

    def save(self, *args, **kwargs):
        if not self.avatar_iniciais:
            nome = self.usuario.get_full_name() or self.usuario.username
            partes = nome.split()
            if len(partes) >= 2:
                self.avatar_iniciais = (partes[0][0] + partes[1][0]).upper()
            else:
                self.avatar_iniciais = nome[:2].upper()
        super().save(*args, **kwargs)


class Notificacao(models.Model):
    TIPOS = [
        ('info', 'Informação'),
        ('sucesso', 'Sucesso'),
        ('aviso', 'Aviso'),
        ('erro', 'Erro'),
        ('gateway', 'Gateway de Processo'),
    ]
    MODULOS = [
        ('recrutamento', 'Recrutamento'),
        ('admissional', 'Admissional'),
        ('administrativo', 'Administrativo'),
        ('sesmet', 'SESMET'),
        ('compras', 'Compras'),
        ('financeiro', 'Financeiro'),
        ('sistema', 'Sistema'),
    ]

    destinatario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notificacoes')
    tipo = models.CharField(max_length=20, choices=TIPOS, default='info')
    modulo = models.CharField(max_length=20, choices=MODULOS, default='sistema')
    titulo = models.CharField(max_length=200)
    mensagem = models.TextField()
    lida = models.BooleanField(default=False)
    url_acao = models.CharField(max_length=200, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Notificação'
        verbose_name_plural = 'Notificações'
        ordering = ['-criado_em']

    def __str__(self):
        return f"[{self.get_tipo_display()}] {self.titulo}"


# ──────────────────────────────────────────────────────────────────────────────
# LINHA DE APROVAÇÃO GENÉRICA
# Pode ser usada por qualquer model do sistema via GenericForeignKey.
# ──────────────────────────────────────────────────────────────────────────────

class AprovacaoRegistro(models.Model):
    """Linha de aprovação genérica para qualquer objeto do ERP."""

    STATUS = [
        ('pendente', 'Pendente'),
        ('aprovado', 'Aprovado'),
        ('rejeitado', 'Rejeitado'),
        ('cancelado', 'Cancelado'),
    ]
    NIVEL = [
        (1, 'Nível 1 — Gestor / Área'),
        (2, 'Nível 2 — Diretoria'),
    ]
    MODULOS = [
        ('recrutamento', 'Recrutamento'),
        ('admissional', 'Admissional'),
        ('administrativo', 'Administrativo'),
        ('sesmet', 'SESMET'),
        ('compras', 'Compras'),
        ('financeiro', 'Financeiro'),
    ]

    # Objeto referenciado (qualquer model)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name='Tipo de Objeto',
    )
    object_id = models.PositiveBigIntegerField(verbose_name='ID do Objeto')
    objeto = GenericForeignKey('content_type', 'object_id')

    # Dados da aprovação
    modulo = models.CharField(max_length=20, choices=MODULOS, default='sistema', verbose_name='Módulo')
    nivel = models.IntegerField(choices=NIVEL, default=1, verbose_name='Nível de Aprovação')
    status = models.CharField(max_length=20, choices=STATUS, default='pendente')

    titulo = models.CharField(max_length=255, verbose_name='Título da Solicitação')
    descricao = models.TextField(blank=True, verbose_name='Descrição / Contexto')
    comentario = models.TextField(blank=True, verbose_name='Comentário do Aprovador')
    motivo_rejeicao = models.TextField(blank=True, verbose_name='Motivo da Rejeição')

    # Usuários envolvidos
    solicitado_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='aprovacoes_solicitadas', verbose_name='Solicitado por'
    )
    aprovado_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='aprovacoes_decididas', verbose_name='Decidido por'
    )

    # Timestamps
    criado_em = models.DateTimeField(auto_now_add=True)
    decidido_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Aprovação'
        verbose_name_plural = 'Aprovações'
        ordering = ['-criado_em']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['status']),
            models.Index(fields=['modulo', 'status']),
        ]

    def __str__(self):
        return f"[{self.get_modulo_display()}] {self.titulo} — {self.get_status_display()}"

    def esta_pendente(self):
        return self.status == 'pendente'

    @classmethod
    def criar_para(cls, objeto, titulo, descricao='', modulo='sistema', nivel=1, solicitado_por=None):
        """Helper para criar uma aprovação para qualquer objeto."""
        ct = ContentType.objects.get_for_model(objeto)
        return cls.objects.create(
            content_type=ct,
            object_id=objeto.pk,
            titulo=titulo,
            descricao=descricao,
            modulo=modulo,
            nivel=nivel,
            solicitado_por=solicitado_por,
        )


class LogAtividade(models.Model):
    """Log geral de todas as ações de escrita (POST) no sistema para auditoria do CEO."""
    
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='logs_atividade')
    acao = models.CharField(max_length=255)
    modulo = models.CharField(max_length=100, default='sistema')
    url = models.CharField(max_length=500, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    detalhes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Log de Atividade'
        verbose_name_plural = 'Logs de Atividades'
        ordering = ['-criado_em']

    def __str__(self):
        nome = self.usuario.username if self.usuario else 'Sistema'
        return f"[{self.modulo}] {nome} - {self.acao} em {self.criado_em.strftime('%d/%m/%Y %H:%M')}"
