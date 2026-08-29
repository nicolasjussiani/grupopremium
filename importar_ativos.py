"""
Script de importação: ATIVOS_TRATADOS.csv → Model Colaborador
Uso: python importar_ativos.py
"""
import os
import sys
import csv
import unicodedata
import django
from datetime import datetime

# ── Setup Django ────────────────────────────────────────────────────────────
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp_config.settings')
django.setup()

from admissional.models import Colaborador  # noqa: E402


def normalize_key(k: str) -> str:
    """Remove acentos e normaliza key de header CSV para comparação."""
    return unicodedata.normalize('NFKD', k).encode('ascii', 'ignore').decode('ascii').upper().strip()


CSV_DATE_COL_INDEX = 10  # Coluna ADMISSÃO é a 11ª (índice 10)

CSV_PATH = os.path.join(os.path.dirname(__file__), 'admissional', 'Dados', 'ATIVOS_TRATADOS.csv')

# Formatos de data aceitos no CSV (americano e brasileiro)
DATE_FORMATS = [
    '%m/%d/%Y',   # 8/30/2026
    '%d/%m/%Y',   # 21/10/2025
]


def parse_date(raw: str):
    """Tenta parsear a data em vários formatos. Retorna None se inválida."""
    raw = raw.strip().replace('//', '/')  # corrige dupla barra
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    print(f"    WARNING: Data inválida ignorada: '{raw}'")
    return None


def map_tipo_contrato(clt_col: str) -> str:
    """Mapeia coluna CLT do CSV → choices do model ('clt' / 'pj')."""
    val = clt_col.strip().upper()
    if val in ('SIM', 'CLT'):
        return 'clt'
    return 'pj'  # PJ, NÃO, vazio → pj


def run():
    print("=" * 60)
    print("  Importação: ATIVOS_TRATADOS.csv -> Colaborador")
    print("=" * 60)

    inseridos = 0
    atualizados = 0
    ignorados = 0
    erros = []

    with open(CSV_PATH, encoding='latin-1', newline='') as f:
        reader = csv.DictReader(f)

        for i, row in enumerate(reader, start=2):  # linha 2 = 1ª linha de dados
            nome = row.get('COLABORADOR', '').strip()

            # Linha de total ou vazia — ignorar
            if not nome or nome.upper() == 'TOTAL':
                print(f"  Linha {i}: ignorada ('{nome}')")
                ignorados += 1
                continue

            cpf = row.get('CPF', '').strip()
            cargo = row.get('CARGO', '').strip()
            contrato = row.get('CONTRATO', '').strip()
            unidade = row.get('UNIDADE', '').strip()
            tipo_contrato = map_tipo_contrato(row.get('CLT', ''))

            # Busca a coluna de data pelo índice posicional (coluna 11, idx=10)
            # pois o nome 'ADMISSÃO' fica corrompido com encoding latin-1
            row_values = list(row.values())
            admissao_val = row_values[CSV_DATE_COL_INDEX] if len(row_values) > CSV_DATE_COL_INDEX else ''
            data_admissao = parse_date(admissao_val)

            salario_raw = row.get('SALARIO', '').strip()
            try:
                salario = float(salario_raw) if salario_raw else None
            except ValueError:
                salario = None

            if not cpf:
                print(f"  Linha {i}: CPF vazio -> ignorado ({nome})")
                ignorados += 1
                erros.append(f"Linha {i} - CPF vazio: {nome}")
                continue

            if data_admissao is None:
                print(f"  Linha {i}: data inválida -> ignorado ({nome})")
                ignorados += 1
                erros.append(f"Linha {i} - Data inválida: {nome}")
                continue

            defaults = dict(
                nome=nome,
                cargo=cargo,
                setor='Operacional',
                contrato=contrato,
                unidade=unidade,
                tipo_contrato=tipo_contrato,
                data_admissao=data_admissao,
                salario=salario,
                email='',
                telefone='',
                status='ativo',
            )

            try:
                obj, created = Colaborador.objects.update_or_create(
                    cpf=cpf,
                    defaults=defaults,
                )
                if created:
                    print(f"  OK Inserido:   {nome} ({cpf})")
                    inseridos += 1
                else:
                    print(f"  ** Atualizado: {nome} ({cpf})")
                    atualizados += 1

            except Exception as e:
                msg = f"Linha {i} - ERRO ao salvar {nome} ({cpf}): {e}"
                print(f"  ERRO: {msg}")
                erros.append(msg)
                ignorados += 1

    print()
    print("=" * 60)
    print(f"  Inseridos:   {inseridos}")
    print(f"  Atualizados: {atualizados}")
    print(f"  Ignorados:   {ignorados}")
    if erros:
        print(f"\n  Erros ({len(erros)}):")
        for e in erros:
            print(f"    - {e}")
    print("=" * 60)


if __name__ == '__main__':
    run()
