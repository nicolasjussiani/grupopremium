from django import forms
from .models import DocumentoFinanceiro


class CancelamentoDocumentoForm(forms.Form):
    motivo = forms.CharField(
        label='Motivo do cancelamento', max_length=2000,
        error_messages={'required': 'Informe o motivo do cancelamento.'},
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3,
                                    'placeholder': 'Ex.: documento duplicado ou cadastrado por engano.'}),
    )


class PagamentoDocumentoForm(forms.Form):
    situacao_pagamento = forms.ChoiceField(
        label='Fluxo e situação',
        choices=[('', 'Selecione...'), ('nao_informado', 'A classificar'),
                 ('Saídas', [('a_pagar', 'A pagar'), ('pago', 'Pago')]),
                 ('Entradas', [('a_receber', 'A receber'), ('recebido', 'Recebido')])],
        initial='a_pagar',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    data_pagamento = forms.DateField(
        label='Data do pagamento / recebimento', required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
    )

    def clean(self):
        dados = super().clean()
        if dados.get('situacao_pagamento') in ('pago', 'recebido') and not dados.get('data_pagamento'):
            self.add_error('data_pagamento', 'Informe a data em que o pagamento ou recebimento foi realizado.')
        if dados.get('situacao_pagamento') in ('a_pagar', 'a_receber', 'nao_informado'):
            dados['data_pagamento'] = None
        return dados

    @classmethod
    def para_documento(cls, documento):
        return cls(initial={
            'situacao_pagamento': documento.situacao_pagamento,
            'data_pagamento': documento.data_pagamento,
        })


class DetalhamentoDocumentoForm(forms.ModelForm):
    class Meta:
        model = DocumentoFinanceiro
        fields = ('descricao', 'observacoes', 'centro_custo', 'unidade')
        widgets = {'observacoes': forms.Textarea(attrs={'rows': 5})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
