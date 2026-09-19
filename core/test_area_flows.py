from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.urls import resolve, reverse

from core.area_flows import FLOWS, ROUTE_FLOW_KEYS, flow_for_request


class AreaFlowMappingTests(TestCase):
    def test_all_routes_reference_existing_flows(self):
        self.assertTrue(ROUTE_FLOW_KEYS)
        self.assertTrue(set(ROUTE_FLOW_KEYS.values()).issubset(FLOWS))

    def test_resolves_flow_for_main_section(self):
        request = RequestFactory().get(reverse('painel_compras'))
        request.resolver_match = resolve(request.path)

        flow = flow_for_request(request)

        self.assertEqual(flow['title'], 'Compras e almoxarifado')
        self.assertGreaterEqual(len(flow['steps']), 4)


class AreaFlowRenderingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='fluxos_admin',
            email='fluxos@example.com',
            password='senha-teste',
        )
        self.client.force_login(self.user)

    def test_main_section_renders_matching_flow(self):
        response = self.client.get(reverse('lista_vagas'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Fluxo da área')
        self.assertContains(response, 'Recrutamento e seleção')
        self.assertContains(response, 'Encaminhar')

    def test_every_mapped_section_renders_its_flow(self):
        for route_name, flow_key in ROUTE_FLOW_KEYS.items():
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, FLOWS[flow_key]['title'])

    def test_detail_page_does_not_duplicate_area_flow(self):
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Fluxo da área')
