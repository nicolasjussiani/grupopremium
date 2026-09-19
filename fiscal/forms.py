from django import forms


class ImportacaoFolhaFiscalForm(forms.Form):
    competencia = forms.DateField(
        label='Competência',
        widget=forms.DateInput(attrs={'type': 'month'}),
        input_formats=['%Y-%m', '%Y-%m-%d'],
    )
    arquivo = forms.FileField(
        label='Planilha Fiscal (.xlsx)',
        help_text='Máximo de 10 MB. A planilha original ficará arquivada.',
    )

    def clean_arquivo(self):
        uploaded = self.cleaned_data['arquivo']
        if uploaded.size > 10 * 1024 * 1024:
            raise forms.ValidationError('A planilha excede o limite de 10 MB.')
        if not uploaded.name.lower().endswith('.xlsx'):
            raise forms.ValidationError('Envie uma planilha no formato .xlsx.')
        return uploaded

    def clean_competencia(self):
        value = self.cleaned_data['competencia']
        return value.replace(day=1)
