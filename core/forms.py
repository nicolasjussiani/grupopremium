from django import forms
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import transaction

from core.models import PerfilUsuario


PROFILE_GROUPS = {
    'admin': ('Admin_Global',),
    'rh': ('Recrutamento_RH', 'Admissional_RH'),
    'financeiro': ('Financeiro_Operador',),
    'sesmet': ('SESMET_Tecnico',),
    'compras': ('Compras_Almoxarife',),
    'estoque_compras': ('Estoque_EPI_Compras',),
}
MANAGED_GROUPS = {name for names in PROFILE_GROUPS.values() for name in names}


class UsuarioERPForm(forms.Form):
    username = forms.CharField(
        label='Usuario',
        max_length=150,
        validators=[RegexValidator(r'^[\w.@+-]+$', 'Use apenas letras, numeros e . @ + - _')],
    )
    first_name = forms.CharField(label='Nome', max_length=150)
    last_name = forms.CharField(label='Sobrenome', max_length=150)
    email = forms.EmailField(label='E-mail', required=False)
    telefone = forms.CharField(max_length=20, required=False)
    perfil = forms.ChoiceField(label='Perfil de acesso', choices=PerfilUsuario.PERFIS)
    acesso_epi = forms.BooleanField(
        label='Acesso adicional a EPI / SESMET', required=False
    )
    acesso_financeiro = forms.BooleanField(
        label='Acesso adicional ao Financeiro', required=False
    )
    marca = forms.ChoiceField(choices=PerfilUsuario.MARCAS)
    unidade = forms.CharField(max_length=100, initial='Matriz')
    is_active = forms.BooleanField(label='Usuario ativo', required=False, initial=True)
    password1 = forms.CharField(label='Senha temporaria', widget=forms.PasswordInput, required=False)
    password2 = forms.CharField(label='Confirmar senha', widget=forms.PasswordInput, required=False)

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
        if instance:
            perfil = getattr(instance, 'perfil', None)
            self.initial.update({
                'username': instance.username,
                'first_name': instance.first_name,
                'last_name': instance.last_name,
                'email': instance.email,
                'is_active': instance.is_active,
                'telefone': getattr(perfil, 'telefone', ''),
                'perfil': getattr(perfil, 'perfil', 'operacional'),
                'marca': getattr(perfil, 'marca', 'eco_premium'),
                'unidade': getattr(perfil, 'unidade', 'Matriz'),
                'acesso_epi': instance.groups.filter(
                    name='SESMET_Tecnico'
                ).exists(),
                'acesso_financeiro': instance.groups.filter(
                    name='Financeiro_Operador'
                ).exists(),
            })

    def clean_username(self):
        username = self.cleaned_data['username'].strip().lower()
        query = User.objects.filter(username__iexact=username)
        if self.instance:
            query = query.exclude(pk=self.instance.pk)
        if query.exists():
            raise ValidationError('Este nome de usuario ja esta em uso.')
        return username

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get('password1', '')
        password2 = cleaned.get('password2', '')
        if not self.instance and not password1:
            self.add_error('password1', 'Informe uma senha temporaria.')
        if password1 and len(password1) < 10:
            self.add_error('password1', 'A senha deve ter pelo menos 10 caracteres.')
        if password1 != password2:
            self.add_error('password2', 'As senhas nao conferem.')
        return cleaned

    @transaction.atomic
    def save(self):
        data = self.cleaned_data
        user = self.instance or User()
        user.username = data['username']
        user.first_name = data['first_name'].strip()
        user.last_name = data['last_name'].strip()
        user.email = data['email'].strip()
        user.is_active = data['is_active']
        if data['password1']:
            user.set_password(data['password1'])
        user.save()

        perfil, _ = PerfilUsuario.objects.update_or_create(
            usuario=user,
            defaults={
                'perfil': data['perfil'],
                'marca': data['marca'],
                'unidade': data['unidade'].strip(),
                'telefone': data['telefone'].strip(),
            },
        )
        perfil.avatar_iniciais = ''
        perfil.save(update_fields=['avatar_iniciais'])

        user.groups.remove(*Group.objects.filter(name__in=MANAGED_GROUPS))
        user.groups.add(*Group.objects.filter(name__in=PROFILE_GROUPS.get(data['perfil'], ())))
        if data.get('acesso_epi'):
            user.groups.add(*Group.objects.filter(name='SESMET_Tecnico'))
        if data.get('acesso_financeiro'):
            user.groups.add(*Group.objects.filter(name='Financeiro_Operador'))
        return user
