from django import forms
from .models import Colaborador

class ColaboradorForm(forms.ModelForm):
    class Meta:
        model = Colaborador
        fields = '__all__'
        widgets = {
            'data_nascimento': forms.DateInput(attrs={'type': 'date'}),
            'data_admissao': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
            
    def clean_anexo_aso(self):
        anexo_aso = self.cleaned_data.get('anexo_aso')
        if not self.instance.pk and not anexo_aso:
            raise forms.ValidationError('O ASO (Atestado de Saúde Ocupacional) é obrigatório para novos colaboradores.')
        return anexo_aso


