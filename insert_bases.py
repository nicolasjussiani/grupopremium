from core.models import Unidade

bases = [
    ("MOV-001", "Piracicaba"),
    ("MOV-002", "Sorocaba"),
    ("MOV-003", "Limeira"),
    ("MOV-004", "Indaiatuba"),
    ("MOV-005", "Bauru"),
    ("MOV-006", "Ribeirão Preto"),
    ("MOV-007", "São Carlos"),
    ("MOV-008", "São José do Rio Preto"),
    ("MOV-009", "Sorocaba Dom Aguirre"),
    ("MOV-010", "Praia Grande"),
    ("MOV-011", "Rio Claro"),
    ("MOV-012", "Goiânia RIO VERDE"),
    ("MOV-013", "Londrina")
]

for codigo, nome in bases:
    unidade, created = Unidade.objects.get_or_create(
        codigo=codigo,
        defaults={'nome': nome}
    )
    if created:
        print(f"Base criada: {codigo} - {nome}")
    else:
        # Se já existir, atualiza o nome
        unidade.nome = nome
        unidade.save()
        print(f"Base atualizada: {codigo} - {nome}")

print("Importação concluída.")
