from django import forms

from compras.models import Material


class MaterialForm(forms.ModelForm):
    class Meta:
        model = Material
        exclude = ('codigo',)
        widgets = {'descricao': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
