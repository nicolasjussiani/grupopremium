import os
import django
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp_config.settings')
django.setup()

from django.contrib.auth.models import User
from manutencao.models import Ativo, RegistroManutencao
from core.models import AprovacaoRegistro
from django.contrib.contenttypes.models import ContentType

def inject_and_test():
    print("Iniciando injeção de dados de Manutenção...")

    # Pega um usuário (solicitante) e um aprovador (super admin)
    solicitante = User.objects.filter(is_superuser=False).first()
    if not solicitante:
        solicitante = User.objects.first()
        
    aprovador = User.objects.filter(is_superuser=True).first()
    if not aprovador:
        aprovador = User.objects.first()

    # 1. Criar um Ativo
    ativo, created = Ativo.objects.get_or_create(
        numero_patrimonio='PAT-12345',
        defaults={
            'nome': 'Empilhadeira Yale 2.5T',
            'descricao': 'Equipamento do setor logístico',
            'unidade_atual': 'Galpão 01',
            'status': 'ativo',
            'valor_aquisicao': 120000.00
        }
    )
    if created:
        print(f"Ativo '{ativo.nome}' criado com sucesso!")
    else:
        print(f"Ativo '{ativo.nome}' já existe.")

    # 2. Mudar status para manutenção e registrar o chamado
    ativo.status = 'manutencao'
    ativo.save()

    manutencao = RegistroManutencao.objects.create(
        ativo=ativo,
        unidade_origem=ativo.unidade_atual,
        motivo='Vazamento de óleo hidráulico no mastro principal.',
        data_inicio=timezone.now().date(),
        status='aguardando_aprovacao',
        fornecedor_servico='Mecânica Pesada XYZ (Orçamento R$ 4.500)',
        obs='O equipamento parou durante o turno da noite. Compras já fez 3 orçamentos.',
        registrado_por=solicitante
    )
    print(f"Registro de Manutenção para '{ativo.nome}' criado!")

    # 3. Criar o registro de Aprovação associado
    aprovacao = AprovacaoRegistro.objects.create(
        content_type=ContentType.objects.get_for_model(manutencao),
        object_id=manutencao.id,
        modulo='manutencao',
        nivel=2,
        titulo=f"Manutenção: {ativo.nome} ({manutencao.unidade_origem})",
        descricao=f"Motivo: {manutencao.motivo}",
        solicitado_por=solicitante,
        status='pendente'
    )
    print("Registro de aprovação pendente criado no módulo 'manutencao'.")

    # 4. Simular a Aprovação do Registro (Teste de fluxo)
    print("Testando fluxo: Aprovando a solicitação...")
    aprovacao.status = 'aprovado'
    aprovacao.aprovado_por = aprovador
    aprovacao.decidido_em = timezone.now()
    aprovacao.comentario = 'Aprovado. O conserto é essencial para a operação.'
    aprovacao.save()

    # Chamar o callback manualmente (simulando a view aprovar_registro)
    from core.views_aprovacao import _executar_callback_aprovacao
    _executar_callback_aprovacao(aprovacao, 'aprovado', aprovador)

    manutencao.refresh_from_db()
    if manutencao.status == 'aberta':
        print(f"SUCESSO! O status da manutenção mudou automaticamente para '{manutencao.status}'!")
    else:
        print(f"ERRO! O status esperado era 'aberta', mas ficou '{manutencao.status}'.")

if __name__ == '__main__':
    inject_and_test()
