from django.db import migrations


def desativar_bloqueio_ip(apps, schema_editor):
    ControleAcessoIP = apps.get_model('core', 'ControleAcessoIP')
    ControleAcessoIP.objects.using(schema_editor.connection.alias).update(ativo=False)


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0020_controle_acesso_ip'),
    ]

    operations = [
        migrations.RunPython(desativar_bloqueio_ip, migrations.RunPython.noop),
    ]
