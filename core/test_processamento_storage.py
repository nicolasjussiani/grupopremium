from django.test import SimpleTestCase

from core.services.processamento_storage import extrair_documento


class ExtracaoLocalStorageTests(SimpleTestCase):
    def test_extrai_nfse_xml_com_data_valor_e_numero(self):
        conteudo = b'''<?xml version="1.0" encoding="utf-8"?>
        <NFSe><infNFSe><nNFSe>487</nNFSe><dhEmi>2026-09-02T18:42:13-03:00</dhEmi>
        <emit><CNPJ>32991343000151</CNPJ><xNome>PREMIUMBR LTDA</xNome></emit>
        <xLocPrestacao>Americana</xLocPrestacao><xDescServ>Lavagem completa</xDescServ>
        <vLiq>7772.00</vLiq></infNFSe></NFSe>'''

        texto, dados, metodo = extrair_documento(
            conteudo, 'nfse.xml', 'text/xml', usar_ocr=False
        )

        self.assertEqual(metodo, 'xml_estruturado')
        self.assertIn('Lavagem completa', texto)
        self.assertEqual(dados['numero_documento'], '487')
        self.assertEqual(dados['valor'], '7772,00')
        self.assertEqual(dados['data_emissao'], '2026-09-02')
        self.assertEqual(dados['cnpj_emitente'], '32991343000151')
        self.assertEqual(dados['unidade'], 'Americana')

    def test_extrai_comprovante_textual_docx(self):
        import io
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as pacote:
            pacote.writestr(
                'word/document.xml',
                '<document><p><t>Favorecido JOAO SILVA</t></p>'
                '<p><t>Valor R$ 150,00</t></p>'
                '<p><t>01/09/2026</t></p></document>',
            )

        texto, dados, metodo = extrair_documento(
            buffer.getvalue(), 'comprovante.docx',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            usar_ocr=False,
        )

        self.assertEqual(metodo, 'docx_texto')
        self.assertIn('JOAO SILVA', texto)
        self.assertEqual(dados['beneficiario'], 'JOAO SILVA')
        self.assertEqual(dados['valor'], '150,00')
        self.assertEqual(dados['data_pagamento'], '2026-09-01')
