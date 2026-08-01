from django.db.models.signals import post_save
from django.dispatch import receiver
from core.models import AprovacaoRegistro
from core.telegram_utils import enviar_mensagem_telegram

@receiver(post_save, sender=AprovacaoRegistro)
def notificar_nova_aprovacao_telegram(sender, instance, created, **kwargs):
    """
    Se uma nova aprovação for criada com status 'pendente', envia um aviso para o CEO.
    """
    if created and instance.status == 'pendente':
        solicitante_nome = instance.solicitado_por.get_full_name() or instance.solicitado_por.username if instance.solicitado_por else "Sistema"
        
        mensagem = (
            f"🚨 <b>Novo Pedido de Aprovação!</b>\n\n"
            f"<b>Módulo:</b> {instance.get_modulo_display()}\n"
            f"<b>Solicitante:</b> {solicitante_nome}\n"
            f"<b>Título:</b> {instance.titulo}\n"
            f"<b>Descrição:</b> {instance.descricao}\n\n"
            f"👉 <a href='https://erp.grupopremiumbr.com.br/aprovacoes/'>Acessar ERP para Aprovar</a>"
        )
        
        enviar_mensagem_telegram(instance.modulo, mensagem)
