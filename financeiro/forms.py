from django import forms


class PagamentoDocumentoForm(forms.Form):
    situacao_pagamento = forms.ChoiceField(
        label='Situação do pagamento',
        choices=[('', 'Selecione...'), ('a_pagar', 'A pagar'), ('pago', 'Pago')],
        initial='a_pagar',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    data_pagamento = forms.DateField(
        label='Data do pagamento', required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
    )

    def clean(self):
        dados = super().clean()
        if dados.get('situacao_pagamento') == 'pago' and not dados.get('data_pagamento'):
            self.add_error('data_pagamento', 'Informe a data em que o pagamento foi realizado.')
        if dados.get('situacao_pagamento') == 'a_pagar':
            dados['data_pagamento'] = None
        return dados

    @classmethod
    def para_documento(cls, documento):
        return cls(initial={
            'situacao_pagamento': '' if documento.situacao_pagamento == 'nao_informado' else documento.situacao_pagamento,
            'data_pagamento': documento.data_pagamento,
        })
