from django import forms

from recrutamento.models import HistoricoVaga, Vaga


class VagaEdicaoForm(forms.ModelForm):
    motivo_alteracao = forms.ChoiceField(
        label='Motivo da alteração',
        choices=[('', 'Selecione...'), *HistoricoVaga.MOTIVOS],
    )
    justificativa_alteracao = forms.CharField(
        label='Descreva o motivo',
        widget=forms.Textarea(attrs={'rows': 3}),
        min_length=5,
    )

    class Meta:
        model = Vaga
        fields = [
            'nome_vaga', 'quantidade_colaboradores', 'cidade', 'unidade',
            'perfil_desejado', 'atividades', 'horario_trabalho',
            'tipo_contratacao', 'valor_salario', 'previsao_inicio',
            'exige_experiencia', 'descricao_experiencia',
            'motivo_solicitacao', 'gestor_responsavel', 'status',
            'observacoes',
        ]
        widgets = {
            'perfil_desejado': forms.Textarea(attrs={'rows': 3}),
            'atividades': forms.Textarea(attrs={'rows': 3}),
            'motivo_solicitacao': forms.Textarea(attrs={'rows': 3}),
            'observacoes': forms.Textarea(attrs={'rows': 3}),
            'previsao_inicio': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'

    def clean_justificativa_alteracao(self):
        return self.cleaned_data['justificativa_alteracao'].strip()
