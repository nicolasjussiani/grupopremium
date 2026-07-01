"""
ERP Grupo Premium — Management Command: criar_grupos

Cria todos os grupos de privilégio por área e configura permissões.
Execute com: python manage.py criar_grupos

Grupos criados:
  - Recrutamento_Gestor
  - Recrutamento_RH
  - Admissional_RH
  - Administrativo_Gestor
  - Administrativo_Operador
  - SESMET_Tecnico
  - SESMET_Gestor
  - Compras_Solicitante
  - Compras_Almoxarife
  - Compras_Aprovador
  - Financeiro_Operador
  - Financeiro_Auditor
  - Financeiro_Aprovador
  - Admin_Global
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.apps import apps


class Command(BaseCommand):
    help = 'Cria os grupos de privilégio por área do ERP Grupo Premium'

    # Definição dos grupos e seus modelos com permissões
    # Formato: 'NomeGrupo': { 'app.Model': ['add', 'change', 'view', 'delete'] }
    GRUPOS = {
        # ── RECRUTAMENTO ──────────────────────────────────────────────────────
        'Recrutamento_Gestor': {
            'recrutamento.Vaga':      ['add', 'change', 'view', 'delete'],
            'recrutamento.Candidato': ['add', 'change', 'view', 'delete'],
            'core.AprovacaoRegistro': ['view'],
        },
        'Recrutamento_RH': {
            'recrutamento.Vaga':      ['add', 'change', 'view'],
            'recrutamento.Candidato': ['add', 'change', 'view'],
            'core.AprovacaoRegistro': ['add', 'view'],
        },

        # ── ADMISSIONAL ───────────────────────────────────────────────────────
        'Admissional_RH': {
            'admissional.Colaborador':          ['add', 'change', 'view'],
            'admissional.Admissao':             ['add', 'change', 'view'],
            'admissional.DocumentoAdmissional': ['add', 'change', 'view', 'delete'],
            'core.AprovacaoRegistro':            ['add', 'view'],
        },

        # ── ADMINISTRATIVO ────────────────────────────────────────────────────
        'Administrativo_Gestor': {
            'administrativo.DemandaAdministrativa': ['add', 'change', 'view', 'delete'],
            'core.AprovacaoRegistro':               ['view'],
        },
        'Administrativo_Operador': {
            'administrativo.DemandaAdministrativa': ['add', 'change', 'view'],
            'core.AprovacaoRegistro':               ['add', 'view'],
        },

        # ── SESMET ────────────────────────────────────────────────────────────
        'SESMET_Tecnico': {
            'sesmet.IntegracaoSeguranca': ['add', 'change', 'view'],
            'sesmet.OrdemServico':        ['add', 'change', 'view'],
            'sesmet.RegistroEPI':         ['add', 'change', 'view'],
            'core.AprovacaoRegistro':     ['add', 'view'],
        },
        'SESMET_Gestor': {
            'sesmet.IntegracaoSeguranca': ['add', 'change', 'view', 'delete'],
            'sesmet.OrdemServico':        ['add', 'change', 'view', 'delete'],
            'sesmet.RegistroEPI':         ['add', 'change', 'view', 'delete'],
            'core.AprovacaoRegistro':     ['view'],
        },

        # ── COMPRAS ───────────────────────────────────────────────────────────
        'Compras_Solicitante': {
            'compras.Material':            ['view'],
            'compras.SolicitacaoMaterial': ['add', 'change', 'view'],
            'core.AprovacaoRegistro':      ['add', 'view'],
        },
        'Compras_Almoxarife': {
            'compras.Material':            ['add', 'change', 'view'],
            'compras.SolicitacaoMaterial': ['add', 'change', 'view'],
            'compras.PedidoCompra':        ['view'],
            'core.AprovacaoRegistro':      ['add', 'view'],
        },
        'Compras_Aprovador': {
            'compras.Material':            ['add', 'change', 'view', 'delete'],
            'compras.SolicitacaoMaterial': ['add', 'change', 'view'],
            'compras.PedidoCompra':        ['add', 'change', 'view'],
            'core.AprovacaoRegistro':      ['view'],
        },

        # ── FINANCEIRO ────────────────────────────────────────────────────────
        'Financeiro_Operador': {
            'financeiro.DocumentoFinanceiro': ['add', 'change', 'view'],
            'financeiro.LancamentoERP':       ['add', 'change', 'view'],
            'core.AprovacaoRegistro':         ['add', 'view'],
        },
        'Financeiro_Auditor': {
            'financeiro.DocumentoFinanceiro': ['change', 'view'],
            'financeiro.AuditoriaItem':       ['add', 'change', 'view'],
            'financeiro.LancamentoERP':       ['view'],
            'core.AprovacaoRegistro':         ['add', 'view'],
        },
        'Financeiro_Aprovador': {
            'financeiro.DocumentoFinanceiro': ['add', 'change', 'view'],
            'financeiro.AuditoriaItem':       ['add', 'change', 'view', 'delete'],
            'financeiro.LancamentoERP':       ['add', 'change', 'view'],
            'core.AprovacaoRegistro':         ['view'],
        },

        # ── ADMIN GLOBAL ──────────────────────────────────────────────────────
        'Admin_Global': {
            'recrutamento.Vaga':                    ['add', 'change', 'view', 'delete'],
            'recrutamento.Candidato':               ['add', 'change', 'view', 'delete'],
            'admissional.Colaborador':              ['add', 'change', 'view', 'delete'],
            'admissional.Admissao':                 ['add', 'change', 'view', 'delete'],
            'admissional.DocumentoAdmissional':     ['add', 'change', 'view', 'delete'],
            'administrativo.DemandaAdministrativa': ['add', 'change', 'view', 'delete'],
            'sesmet.IntegracaoSeguranca':            ['add', 'change', 'view', 'delete'],
            'sesmet.OrdemServico':                  ['add', 'change', 'view', 'delete'],
            'sesmet.RegistroEPI':                   ['add', 'change', 'view', 'delete'],
            'compras.Material':                     ['add', 'change', 'view', 'delete'],
            'compras.SolicitacaoMaterial':          ['add', 'change', 'view', 'delete'],
            'compras.PedidoCompra':                 ['add', 'change', 'view', 'delete'],
            'financeiro.DocumentoFinanceiro':       ['add', 'change', 'view', 'delete'],
            'financeiro.AuditoriaItem':             ['add', 'change', 'view', 'delete'],
            'financeiro.LancamentoERP':             ['add', 'change', 'view', 'delete'],
            'core.AprovacaoRegistro':               ['add', 'change', 'view', 'delete'],
            'core.PerfilUsuario':                   ['add', 'change', 'view', 'delete'],
            'core.Notificacao':                     ['add', 'change', 'view', 'delete'],
        },
    }

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('\n[ERP] ERP Grupo Premium -- Criacao de Grupos de Privilegio\n'))
        criados = 0
        atualizados = 0

        for nome_grupo, modelos_perms in self.GRUPOS.items():
            grupo, created = Group.objects.get_or_create(name=nome_grupo)
            if created:
                criados += 1
                self.stdout.write(f'  [OK] Grupo criado: {nome_grupo}')
            else:
                atualizados += 1
                self.stdout.write(f'  [~]  Grupo atualizado: {nome_grupo}')
                grupo.permissions.clear()

            perms_adicionadas = 0
            for app_model, acoes in modelos_perms.items():
                app_label, model_name = app_model.split('.')
                try:
                    model_class = apps.get_model(app_label, model_name)
                    ct = ContentType.objects.get_for_model(model_class)
                    for acao in acoes:
                        codename = f'{acao}_{model_name.lower()}'
                        try:
                            perm = Permission.objects.get(content_type=ct, codename=codename)
                            grupo.permissions.add(perm)
                            perms_adicionadas += 1
                        except Permission.DoesNotExist:
                            self.stdout.write(
                                self.style.WARNING(f'     [!] Permissao nao encontrada: {codename}')
                            )
                except LookupError:
                    self.stdout.write(
                        self.style.WARNING(f'     [!] Model nao encontrado: {app_model}')
                    )

            self.stdout.write(f'     -> {perms_adicionadas} permissao(oes) configurada(s)')

        self.stdout.write('\n' + self.style.SUCCESS(
            f'[V] Concluido! {criados} grupo(s) criado(s), {atualizados} atualizado(s).\n'
            f'    Total de grupos ativos: {Group.objects.count()}\n'
        ))
        self.stdout.write(self.style.NOTICE(
            '[i] Dica: Atribua usuarios aos grupos via Django Admin ou:\n'
            '    python manage.py shell -c "from django.contrib.auth.models import User, Group; '
            'u = User.objects.get(username=\'SEU_USER\'); '
            'g = Group.objects.get(name=\'Admin_Global\'); u.groups.add(g)"\n'
        ))
