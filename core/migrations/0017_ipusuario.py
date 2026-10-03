from ipaddress import ip_address

from django.conf import settings
from django.db import migrations, models
from django.db.models import Min, Max
import django.db.models.deletion


def importar_ips_auditoria(apps, schema_editor):
    database = schema_editor.connection.alias
    Log = apps.get_model('core', 'LogAtividade')
    IP = apps.get_model('core', 'IPUsuario')
    registros = Log.objects.using(database).filter(
        usuario__isnull=False, ip_address__isnull=False,
    ).order_by().values('usuario_id', 'ip_address').annotate(
        primeiro=Min('criado_em'), ultimo=Max('criado_em'),
    )
    for registro in registros.iterator():
        try:
            address = ip_address(registro['ip_address'])
            if address.version == 6 and address.ipv4_mapped:
                address = address.ipv4_mapped
            # Endereços internos do proxy não servem para a lista da Vercel.
            if not address.is_global:
                continue
        except ValueError:
            continue
        ip, created = IP.objects.using(database).get_or_create(
            usuario_id=registro['usuario_id'], ip_address=str(address),
            defaults={
                'primeiro_acesso': registro['primeiro'],
                'ultimo_acesso': registro['ultimo'],
                'confirmado': False,
            },
        )
        if not created:
            IP.objects.using(database).filter(pk=ip.pk).update(
                primeiro_acesso=min(ip.primeiro_acesso, registro['primeiro']),
                ultimo_acesso=max(ip.ultimo_acesso, registro['ultimo']),
            )


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0016_perfil_entregas_consulta'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='IPUsuario',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ip_address', models.GenericIPAddressField()),
                ('primeiro_acesso', models.DateTimeField()),
                ('ultimo_acesso', models.DateTimeField()),
                ('confirmado', models.BooleanField(default=False)),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ips_acesso', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-ultimo_acesso', 'ip_address'],
                'constraints': [models.UniqueConstraint(fields=('usuario', 'ip_address'), name='core_usuario_ip_unico')],
            },
        ),
        migrations.RunPython(importar_ips_auditoria, migrations.RunPython.noop),
    ]
