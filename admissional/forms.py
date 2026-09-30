from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from .models import (
    Colaborador, PagamentoColaborador, TIPOS_PAGAMENTO_SEMANAIS,
    periodo_semanal,
)
from core.validators import MAX_REQUEST_UPLOAD_SIZE, validate_document_upload

class ColaboradorForm(forms.ModelForm):
    DIRECT_UPLOAD_FIELDS = (
        'anexo_cpf', 'anexo_cpf_verso',
        'anexo_rg', 'anexo_rg_verso',
        'anexo_titulo', 'anexo_titulo_verso',
        'anexo_reservista', 'anexo_reservista_verso',
        'anexo_aso',
    )

    class Meta:
        model = Colaborador
        exclude = (
            'pis_pasep', 'ctps',
            'anexo_pis', 'anexo_pis_verso',
            'anexo_ctps', 'anexo_ctps_verso',
        )
        widgets = {
            'data_nascimento': forms.DateInput(attrs={'type': 'date'}),
            'chave_pix': forms.TextInput(attrs={
                'autocomplete': 'off',
                'placeholder': 'CPF, CNPJ, e-mail, telefone ou chave aleatória',
            }),
            'data_admissao': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'data_desligamento': forms.DateInput(
                format='%Y-%m-%d', attrs={'type': 'date'},
            ),
            'salario': forms.TextInput(attrs={
                'inputmode': 'decimal', 'placeholder': 'Ex.: 2000,00',
            }),
            'vale_transporte_semanal': forms.TextInput(attrs={
                'inputmode': 'decimal', 'placeholder': 'Ex.: 80,00',
            }),
            'ajuda_custo_semanal': forms.TextInput(attrs={
                'inputmode': 'decimal', 'placeholder': 'Ex.: 80,00',
            }),
        }

    def __init__(self, *args, **kwargs):
        self.require_document = kwargs.pop('require_document', False)
        super().__init__(*args, **kwargs)
        # Mantem a referencia do arquivo que ja chegou ao Supabase quando
        # outro campo do formulario precisa ser corrigido.
        for name in self.DIRECT_UPLOAD_FIELDS:
            self.fields[f'direct_upload_{name}'] = forms.CharField(
                required=False,
                max_length=2048,
                widget=forms.HiddenInput(),
            )
        for name, field in self.fields.items():
            # Os demais dados podem ser completados depois; a data de inicio
            # e obrigatoria em novos cadastros (definida abaixo).
            if not name.startswith('anexo_') and not name.startswith('direct_upload_'):
                field.required = False
            field.widget.attrs['class'] = 'form-control'
            if name.startswith('anexo_'):
                field.widget.attrs['accept'] = '.pdf,.png,.jpg,.jpeg'
        data_admissao = self.fields['data_admissao']
        data_admissao.required = self.instance._state.adding
        data_admissao.label = 'Data de início / admissão'
        data_admissao.error_messages['required'] = 'Informe a data de início do colaborador.'
        data_admissao.help_text = 'Informe a data em que a pessoa iniciou na empresa.'
        self.fields['salario'].help_text = 'Informe o salário mensal do colaborador.'
        self.fields['vale_transporte_semanal'].help_text = (
            'Informe o valor total pago por semana (apenas CLT).'
        )
        self.fields['ajuda_custo_semanal'].help_text = (
            'Informe o valor total pago por semana (apenas PJ).'
        )
        for name in ('salario', 'vale_transporte_semanal', 'ajuda_custo_semanal'):
            self.fields[name].localize = True
            self.fields[name].widget.is_localized = True

    def clean(self):
        cleaned_data = super().clean()
        cleaned_data['cpf'] = cleaned_data.get('cpf') or None
        for name, default in (
            ('tipo_contrato', 'clt'),
            ('categoria_trabalho', 'fixo'),
            ('marca', 'eco_premium'),
            ('status', 'ativo'),
        ):
            cleaned_data[name] = (
                cleaned_data.get(name) or getattr(self.instance, name, None) or default
            )

        tipo_contrato = cleaned_data['tipo_contrato']
        status = cleaned_data['status']
        if (
            status in Colaborador.STATUS_SEM_PAGAMENTO
            and not cleaned_data.get('data_desligamento')
        ):
            self.add_error(
                'data_desligamento',
                'Informe a data de desligamento do colaborador.',
            )
        vale_transporte = cleaned_data.get('vale_transporte_semanal') or 0
        ajuda_custo = cleaned_data.get('ajuda_custo_semanal') or 0
        if tipo_contrato == 'pj' and vale_transporte > 0:
            self.add_error(
                'vale_transporte_semanal',
                'Vale-transporte deve ser usado somente para colaboradores CLT.',
            )
        if tipo_contrato == 'clt' and ajuda_custo > 0:
            self.add_error(
                'ajuda_custo_semanal',
                'Ajuda de custo deve ser usada somente para colaboradores PJ.',
            )

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
        has_local_upload = bool(uploads)
        has_direct_upload = any(
            str(self.data.get(f'direct_upload_{name}', '')).strip()
            for name in self.DIRECT_UPLOAD_FIELDS
        )
        has_existing_document = bool(
            self.instance.pk
            and any(getattr(self.instance, name, None) for name in self.DIRECT_UPLOAD_FIELDS)
        )
        if self.require_document and not (
            has_local_upload or has_direct_upload or has_existing_document
        ):
            self.add_error(
                None,
                'Envie pelo menos um documento para cadastrar o colaborador.'
            )
        return cleaned_data


class PagamentoColaboradorForm(forms.ModelForm):
    class Meta:
        model = PagamentoColaborador
        fields = (
            'colaborador', 'tipo', 'competencia', 'competencia_fim', 'valor',
            'dias_trabalhados', 'salario_base', 'gratificacao', 'faltas', 'outros_descontos', 'valor_diaria', 'chave_pix', 'data_vencimento', 'status',
            'data_pagamento', 'recorrente', 'observacao',
        )
        widgets = {
            'competencia': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'competencia_fim': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'valor': forms.TextInput(attrs={
                'inputmode': 'decimal', 'placeholder': 'Ex.: 2000,00',
            }),
            'dias_trabalhados': forms.NumberInput(attrs={
                'inputmode': 'decimal', 'min': '0.01', 'step': '0.01',
                'placeholder': 'Ex.: 7',
            }),
            'valor_diaria': forms.TextInput(attrs={
                'inputmode': 'decimal', 'placeholder': 'Ex.: 150,00',
            }),
            'chave_pix': forms.TextInput(attrs={
                'autocomplete': 'off', 'placeholder': 'CPF, CNPJ, e-mail, telefone ou chave aleatória',
            }),
            'data_vencimento': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'data_pagamento': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'observacao': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dados_pagos = None
        if self.instance.pk and self.instance.status == 'pago':
            self._dados_pagos = {
                campo: getattr(self.instance, campo)
                for campo in self.Meta.fields if campo not in ('observacao', 'recorrente')
            }
        self.fields['colaborador'].queryset = Colaborador.objects.exclude(
            status__in=['inativo', 'desligado']
        )
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
        self.fields['recorrente'].widget.attrs['class'] = 'form-check-input'
        self.fields['valor'].required = False
        self.fields['valor'].localize = True
        self.fields['valor'].widget.is_localized = True
        self.fields['valor_diaria'].localize = True
        self.fields['valor_diaria'].widget.is_localized = True
        for name in ('salario_base', 'gratificacao', 'faltas', 'outros_descontos'):
            self.fields[name].localize = True
            self.fields[name].widget = forms.TextInput(attrs={'class': 'form-control', 'inputmode': 'decimal'})
            self.fields[name].widget.is_localized = True
        self.fields['salario_base'].help_text = 'Salário mensal ÷ 30. Deixe vazio somente para manter um lançamento manual antigo.'
        self.fields['dias_trabalhados'].help_text = 'Salário: dias do período antes de descontar faltas (até 30). Não desconte a mesma falta neste campo e novamente em Faltas.'
        self.fields['gratificacao'].help_text = 'Valor integral, sem proporcionalidade.'


    def clean(self):
        cleaned_data = super().clean()
        if self.instance.pk and self.instance.status == 'pago' and self.instance.tipo == 'salario':
            for name in ('salario_base', 'gratificacao', 'faltas', 'outros_descontos', 'dias_trabalhados', 'valor', 'tipo', 'competencia', 'competencia_fim', 'colaborador', 'status', 'data_vencimento'):
                enviado = cleaned_data.get(name)
                atual = getattr(self.instance, name)
                if name in ('gratificacao', 'faltas', 'outros_descontos'):
                    enviado = enviado or Decimal('0')
                if enviado != atual:
                    self.add_error(name, 'Salário já pago: o cálculo salvo não pode ser alterado.')
        colaborador = cleaned_data.get('colaborador')
        tipo = cleaned_data.get('tipo')
        valor = cleaned_data.get('valor')
        dias_trabalhados = cleaned_data.get('dias_trabalhados')
        valor_diaria = cleaned_data.get('valor_diaria')
        for name in ('gratificacao', 'faltas', 'outros_descontos'):
            cleaned_data[name] = cleaned_data.get(name) or Decimal('0')
        if tipo == 'salario' and cleaned_data.get('salario_base') is not None:
            from .calculo_folha import calcular_salario
            try:
                cleaned_data['valor'] = calcular_salario(
                    cleaned_data['salario_base'], dias_trabalhados,
                    cleaned_data['faltas'], cleaned_data['gratificacao'], cleaned_data['outros_descontos'],
                )
                cleaned_data['valor_diaria'] = None
            except ValidationError as exc:
                self.add_error(None, exc)
        elif tipo == 'freelancer':
            if bool(dias_trabalhados) != bool(valor_diaria):
                if not dias_trabalhados:
                    self.add_error('dias_trabalhados', 'Informe os dias trabalhados.')
                if not valor_diaria:
                    self.add_error('valor_diaria', 'Informe o valor da diária.')
            elif dias_trabalhados and valor_diaria:
                cleaned_data['valor'] = (dias_trabalhados * valor_diaria).quantize(
                    Decimal('0.01')
                )
            elif not self.instance.pk:
                self.add_error(
                    'dias_trabalhados',
                    'Freelancer deve ser pago pelos dias efetivamente trabalhados.',
                )
                self.add_error('valor_diaria', 'Informe o valor da diária do freelancer.')
        elif not valor:
            self.add_error('valor', 'Informe o valor do pagamento.')
        if colaborador and tipo == 'vale_transporte' and colaborador.tipo_contrato != 'clt':
            self.add_error(
                'tipo',
                'Vale-transporte deve ser cadastrado somente para colaboradores CLT.',
            )
        if colaborador and tipo == 'ajuda_custo' and colaborador.tipo_contrato != 'pj':
            self.add_error(
                'tipo',
                'Ajuda de custo deve ser cadastrada somente para colaboradores PJ.',
            )
        status = cleaned_data.get('status')
        data_pagamento = cleaned_data.get('data_pagamento')
        if status == 'pago' and not data_pagamento:
            self.add_error(
                'data_pagamento',
                'Informe a data em que o pagamento foi realizado.',
            )
        competencia = cleaned_data.get('competencia')
        competencia_fim = cleaned_data.get('competencia_fim')
        if tipo in TIPOS_PAGAMENTO_SEMANAIS and competencia:
            segunda, domingo = periodo_semanal(competencia)
            cleaned_data['competencia'] = segunda
            cleaned_data['competencia_fim'] = domingo
            cleaned_data['data_vencimento'] = segunda
            if data_pagamento and status == 'pago':
                cleaned_data['data_pagamento'] = periodo_semanal(data_pagamento)[0]
            competencia = segunda
            competencia_fim = domingo
        if competencia and not competencia_fim and self._dados_pagos is None:
            cleaned_data['competencia_fim'] = competencia
        if competencia and competencia_fim and competencia_fim < competencia:
            self.add_error(
                'competencia_fim',
                'O fim da competência não pode ser anterior ao início.',
            )
        cleaned_data['recorrente'] = tipo in TIPOS_PAGAMENTO_SEMANAIS
        if status != 'pago':
            cleaned_data['data_pagamento'] = None
        if self._dados_pagos is not None and any(
            cleaned_data.get(campo) != original
            for campo, original in self._dados_pagos.items()
        ):
            raise forms.ValidationError(
                'Pagamento já realizado não pode ter seus dados financeiros alterados. '
                'Nesta tela, acrescente apenas observações ou comprovantes.'
            )
        return cleaned_data
