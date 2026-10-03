from django.db import migrations


def proteger_ips_no_postgres(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        # Os IPs são consultados pelo backend Django, não pela API pública.
        schema_editor.execute('ALTER TABLE core_ipusuario ENABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [('core', '0018_ipusuario')]
    operations = [migrations.RunPython(proteger_ips_no_postgres, migrations.RunPython.noop)]
