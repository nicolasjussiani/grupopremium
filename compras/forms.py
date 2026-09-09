from django import forms

from compras.models import Material


class MaterialForm(forms.ModelForm):
    direct_upload_foto = forms.CharField(required=False, widget=forms.HiddenInput)
    remover_foto = forms.BooleanField(required=False, label='Remover foto atual')

    class Meta:
        model = Material
        exclude = ('codigo',)
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 3}),
            'foto': forms.FileInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, (forms.CheckboxInput, forms.HiddenInput)):
                field.widget.attrs['class'] = 'form-control'
        self.fields['foto'].widget.attrs.update({
            'accept': '.png,.jpg,.jpeg',
            'aria-describedby': 'foto-ajuda',
        })
