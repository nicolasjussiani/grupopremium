from django import forms

from compras.models import EquipamentoManutencao, Material


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


class EquipamentoManutencaoForm(forms.ModelForm):
    class Meta:
        model = EquipamentoManutencao
        fields = ('nome', 'tipo', 'codigo', 'localizacao', 'descricao', 'ativo')
        widgets = {'descricao': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        categorias_ativos = {'ferramentas', 'manutencao'}
        self.fields['categoria'].choices = [
            choice for choice in self.fields['categoria'].choices
            if choice[0] not in categorias_ativos
        ]
        if self.instance.pk and self.instance.categoria in categorias_ativos:
            valor = self.instance.categoria
            etiqueta = dict(Material.CATEGORIAS)[valor]
            self.fields['categoria'].choices = [(valor, etiqueta)] + list(
                self.fields['categoria'].choices
            )
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = 'form-control'
        self.fields['ativo'].label = 'Disponível para novas solicitações'
