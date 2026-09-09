import base64

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from compras.models import Material
from core.models import PerfilUsuario
from sesmet.models import EquipamentoProtecao


PNG_1X1 = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
)


class InventoryPhotoAndHelpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='admin-fotos', password='senha-forte-123', email='admin@example.com'
        )
        PerfilUsuario.objects.create(usuario=self.user, perfil='admin')
        self.client.force_login(self.user)

    def _photo(self, name='item.png'):
        return SimpleUploadedFile(name, PNG_1X1, content_type='image/png')

    def test_cadastra_material_com_foto_e_codigo_automatico(self):
        response = self.client.post(reverse('novo_material'), {
            'nome': 'Parafusadeira',
            'foto': self._photo('parafusadeira.png'),
            'descricao': 'Equipamento de teste',
            'categoria': 'ferramentas',
            'unidade_medida': 'un',
            'quantidade_estoque': '2',
            'estoque_minimo': '1',
            'preco_unitario': '100.00',
            'fornecedor_preferencial': '',
            'localizacao': 'Prateleira A',
        })
        self.assertRedirects(response, reverse('lista_materiais'))
        material = Material.objects.get(nome='Parafusadeira')
        self.assertTrue(material.codigo.startswith('MAT-'))
        self.assertTrue(material.foto.name.startswith(f'compras/materiais/{material.pk}/foto/'))

    def test_cadastra_epi_com_foto_e_codigo_automatico(self):
        response = self.client.post(reverse('novo_equipamento'), {
            'nome': 'Capacete com jugular',
            'foto': self._photo('capacete.png'),
            'numero_ca': '12345',
            'fabricante': 'Fabricante teste',
            'validade_ca': '',
            'dias_durabilidade': '90',
            'estoque_atual': '8',
        })
        self.assertRedirects(response, reverse('catalogo_equipamentos'))
        equipamento = EquipamentoProtecao.objects.get(nome='Capacete com jugular')
        self.assertTrue(equipamento.codigo.startswith('EPI-'))
        self.assertTrue(equipamento.foto.name.startswith(f'sesmet/epis/{equipamento.pk}/foto/'))

    def test_ajuda_exige_login_e_aparece_no_menu(self):
        response = self.client.get(reverse('ajuda'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Central de Ajuda')
        self.assertContains(response, 'Instalar no celular')

        self.client.logout()
        response = self.client.get(reverse('ajuda'))
        self.assertEqual(response.status_code, 302)
