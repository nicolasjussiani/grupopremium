from django import forms
from .models import Colaborador
from core.validators import validate_document_upload

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
        self.fields['email'].required = True
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'

    def clean(self):
        cleaned_data = super().clean()
        for name, upload in cleaned_data.items():
            if name.startswith('anexo_') and upload and hasattr(upload, 'content_type'):
                validate_document_upload(upload)
        return cleaned_data
