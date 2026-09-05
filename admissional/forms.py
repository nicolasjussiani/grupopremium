from django import forms
from .models import Colaborador
from core.validators import MAX_REQUEST_UPLOAD_SIZE, validate_document_upload

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
        for name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'
            if name.startswith('anexo_'):
                field.widget.attrs['accept'] = '.pdf,.png,.jpg,.jpeg'

    def clean(self):
        cleaned_data = super().clean()
        uploads = [
            upload
            for name, upload in self.files.items()
            if name.startswith('anexo_') and upload
        ]
        if sum(upload.size for upload in uploads) > MAX_REQUEST_UPLOAD_SIZE:
            raise forms.ValidationError(
                'Os novos anexos ultrapassam 4 MB no total. '
                'Salve os documentos em etapas menores.'
            )
        for name, upload in cleaned_data.items():
            if name.startswith('anexo_') and upload and hasattr(upload, 'content_type'):
                validate_document_upload(upload)
        return cleaned_data
