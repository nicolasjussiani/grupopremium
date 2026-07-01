# Dicionário com Vídeos de Treinamento e Avaliação (5 Questões) para cada EPI
# URL alterada para usar o mesmo vídeo em todos os EPIs: https://www.youtube.com/watch?v=5zW2cSsMXQc

VIDEOS_EPI = {
    'luva': {
        'url': 'https://www.youtube.com/embed/1aks7R6QXV0',
        'duracao_segundos': 300, # 5 minutos
        'questoes': [
            {'id': 'q1', 'pergunta': '1. Qual a principal regra ao retirar luvas contaminadas?', 'opcoes': [{'id': 'a', 'texto': 'Puxar pelas pontas dos dedos com a boca'}, {'id': 'b', 'texto': 'Puxar do punho virando do avesso para não tocar na parte externa'}, {'id': 'c', 'texto': 'Lavar com água e sabão antes de tirar'}], 'resposta_correta': 'b'},
            {'id': 'q2', 'pergunta': '2. Quando as luvas devem ser descartadas?', 'opcoes': [{'id': 'a', 'texto': 'Apenas quando rasgarem completamente'}, {'id': 'b', 'texto': 'A cada 30 minutos de uso'}, {'id': 'c', 'texto': 'Quando apresentarem furos, desgastes severos ou excesso de contaminação'}], 'resposta_correta': 'c'},
            {'id': 'q3', 'pergunta': '3. Posso usar as mesmas luvas para qualquer atividade?', 'opcoes': [{'id': 'a', 'texto': 'Sim, a luva protege contra tudo'}, {'id': 'b', 'texto': 'Não, cada tipo de luva é específico para o risco (químico, corte, etc.)'}, {'id': 'c', 'texto': 'Apenas se eu usar duas juntas'}], 'resposta_correta': 'b'},
            {'id': 'q4', 'pergunta': '4. Como devo guardar minhas luvas ao final do expediente?', 'opcoes': [{'id': 'a', 'texto': 'Amasar e guardar no bolso'}, {'id': 'b', 'texto': 'Deixar jogadas na bancada'}, {'id': 'c', 'texto': 'Limpar conforme instrução e guardar em local seco e arejado'}], 'resposta_correta': 'c'},
            {'id': 'q5', 'pergunta': '5. O que fazer se a luva ficar úmida de suor?', 'opcoes': [{'id': 'a', 'texto': 'Cortar a ponta para ventilar'}, {'id': 'b', 'texto': 'Alternar o par ou retirar nos descansos para arejar as mãos'}, {'id': 'c', 'texto': 'Continuar usando até encharcar'}], 'resposta_correta': 'b'}
        ]
    },
    'calcado': {
        'url': 'https://www.youtube.com/embed/1aks7R6QXV0',
        'duracao_segundos': 300,
        'questoes': [
            {'id': 'q1', 'pergunta': '1. Qual o cuidado principal com o calçado de segurança?', 'opcoes': [{'id': 'a', 'texto': 'Deixar secar ao sol intenso'}, {'id': 'b', 'texto': 'Limpar com pano úmido e secar à sombra'}, {'id': 'c', 'texto': 'Lavar na máquina semanalmente'}], 'resposta_correta': 'b'},
            {'id': 'q2', 'pergunta': '2. O uso de meias é obrigatório?', 'opcoes': [{'id': 'a', 'texto': 'Sim, de algodão para absorver suor e evitar fungos'}, {'id': 'b', 'texto': 'Não, usar sem meia é melhor'}, {'id': 'c', 'texto': 'Só no inverno'}], 'resposta_correta': 'a'},
            {'id': 'q3', 'pergunta': '3. Se a biqueira sofrer um forte impacto, o que fazer?', 'opcoes': [{'id': 'a', 'texto': 'Desamassar com martelo'}, {'id': 'b', 'texto': 'Solicitar substituição imediata'}, {'id': 'c', 'texto': 'Continuar usando'}], 'resposta_correta': 'b'},
            {'id': 'q4', 'pergunta': '4. Por que não se deve pisar no calcanhar para tirar a bota?', 'opcoes': [{'id': 'a', 'texto': 'Porque deforma o contraforte e reduz a vida útil'}, {'id': 'b', 'texto': 'Porque suja a sola'}, {'id': 'c', 'texto': 'Pode pisar sem problema'}], 'resposta_correta': 'a'},
            {'id': 'q5', 'pergunta': '5. Quando o calçado deve ser trocado?', 'opcoes': [{'id': 'a', 'texto': 'Quando furar a sola de vez'}, {'id': 'b', 'texto': 'Todo ano não importa o estado'}, {'id': 'c', 'texto': 'Ao notar o solado muito gasto/liso ou couro danificado'}], 'resposta_correta': 'c'}
        ]
    },
    'protetor_auricular': {
        'url': 'https://www.youtube.com/embed/1aks7R6QXV0',
        'duracao_segundos': 300,
        'questoes': [
            {'id': 'q1', 'pergunta': '1. Como colocar corretamente o protetor plug?', 'opcoes': [{'id': 'a', 'texto': 'Apenas empurrar'}, {'id': 'b', 'texto': 'Puxar a orelha para cima e para trás antes de inserir'}, {'id': 'c', 'texto': 'Umedecer com água'}], 'resposta_correta': 'b'},
            {'id': 'q2', 'pergunta': '2. Como deve ser feita a higienização diária do plug?', 'opcoes': [{'id': 'a', 'texto': 'Com água limpa e sabão neutro'}, {'id': 'b', 'texto': 'Com álcool 70%'}, {'id': 'c', 'texto': 'Não precisa higienizar'}], 'resposta_correta': 'a'},
            {'id': 'q3', 'pergunta': '3. Posso compartilhar meu protetor auricular com colega?', 'opcoes': [{'id': 'a', 'texto': 'Sim, se lavar'}, {'id': 'b', 'texto': 'Não, é de uso estritamente pessoal'}, {'id': 'c', 'texto': 'Sim, em emergências'}], 'resposta_correta': 'b'},
            {'id': 'q4', 'pergunta': '4. O que indica a necessidade de troca do plug de silicone?', 'opcoes': [{'id': 'a', 'texto': 'Quando endurece ou perde flexibilidade'}, {'id': 'b', 'texto': 'Apenas quando rasga'}, {'id': 'c', 'texto': 'A cada 3 anos'}], 'resposta_correta': 'a'},
            {'id': 'q5', 'pergunta': '5. Protetor tipo concha (abafador) precisa de manutenção?', 'opcoes': [{'id': 'a', 'texto': 'Não'}, {'id': 'b', 'texto': 'Sim, troca das almofadas periodicamente'}, {'id': 'c', 'texto': 'Lavar as espumas na máquina'}], 'resposta_correta': 'b'}
        ]
    },
    'respirador_p2': {
        'url': 'https://www.youtube.com/embed/1aks7R6QXV0',
        'duracao_segundos': 300,
        'questoes': [
            {'id': 'q1', 'pergunta': '1. O que compromete a vedação do respirador P2?', 'opcoes': [{'id': 'a', 'texto': 'Barba volumosa ou falhas na pele'}, {'id': 'b', 'texto': 'Cor da máscara'}, {'id': 'c', 'texto': 'Tempo seco'}], 'resposta_correta': 'a'},
            {'id': 'q2', 'pergunta': '2. Posso lavar a máscara descartável P2?', 'opcoes': [{'id': 'a', 'texto': 'Sim, com sabão neutro'}, {'id': 'b', 'texto': 'Não, a umidade destrói a manta filtrante'}, {'id': 'c', 'texto': 'Apenas com álcool em spray'}], 'resposta_correta': 'b'},
            {'id': 'q3', 'pergunta': '3. Como ajustar a haste metálica do nariz?', 'opcoes': [{'id': 'a', 'texto': 'Apertar forte com uma mão formando um V'}, {'id': 'b', 'texto': 'Moldar suavemente com as duas mãos seguindo o formato do nariz'}, {'id': 'c', 'texto': 'Não precisa ajustar'}], 'resposta_correta': 'b'},
            {'id': 'q4', 'pergunta': '4. Quando sei que a máscara já saturou?', 'opcoes': [{'id': 'a', 'texto': 'Quando fica muito leve'}, {'id': 'b', 'texto': 'Quando começo a sentir dificuldade crescente para respirar'}, {'id': 'c', 'texto': 'Quando a tinta sai'}], 'resposta_correta': 'b'},
            {'id': 'q5', 'pergunta': '5. Se remover a máscara para falar, devo pendurá-la no pescoço?', 'opcoes': [{'id': 'a', 'texto': 'Sim, é mais prático'}, {'id': 'b', 'texto': 'Não, o pescoço contamina o interior do respirador'}, {'id': 'c', 'texto': 'Pode, desde que seja rápido'}], 'resposta_correta': 'b'}
        ]
    },
    'oculos': {
        'url': 'https://www.youtube.com/embed/1aks7R6QXV0',
        'duracao_segundos': 300,
        'questoes': [
            {'id': 'q1', 'pergunta': '1. Qual a melhor forma de limpar os óculos?', 'opcoes': [{'id': 'a', 'texto': 'Com a camisa do uniforme'}, {'id': 'b', 'texto': 'Com água, sabão neutro e secar suavemente com papel toalha limpo'}, {'id': 'c', 'texto': 'Esfregar no jeans'}], 'resposta_correta': 'b'},
            {'id': 'q2', 'pergunta': '2. Como guardar os óculos ao parar o trabalho?', 'opcoes': [{'id': 'a', 'texto': 'Colocar na cabeça tipo tiara'}, {'id': 'b', 'texto': 'Jogar na caixa de ferramentas solto'}, {'id': 'c', 'texto': 'Guardar em estojo ou local protegido, com lentes viradas para cima'}], 'resposta_correta': 'c'},
            {'id': 'q3', 'pergunta': '3. Se as lentes ficarem muito riscadas, o que fazer?', 'opcoes': [{'id': 'a', 'texto': 'Lixar com polidor'}, {'id': 'b', 'texto': 'Pedir a substituição do EPI'}, {'id': 'c', 'texto': 'Continuar usando ignorando os riscos'}], 'resposta_correta': 'b'},
            {'id': 'q4', 'pergunta': '4. Os óculos de sobrepor servem para quê?', 'opcoes': [{'id': 'a', 'texto': 'Ficar mais estiloso'}, {'id': 'b', 'texto': 'Serem usados por cima do óculos de grau do colaborador'}, {'id': 'c', 'texto': 'Ter dupla camada de lente apenas'}], 'resposta_correta': 'b'},
            {'id': 'q5', 'pergunta': '5. Por que usar cordinha de segurança?', 'opcoes': [{'id': 'a', 'texto': 'Evita a queda e risco das lentes quando tirados do rosto'}, {'id': 'b', 'texto': 'É apenas enfeite'}, {'id': 'c', 'texto': 'Ajuda a apertar no rosto'}], 'resposta_correta': 'a'}
        ]
    },
    'uniforme': {
        'url': 'https://www.youtube.com/embed/1aks7R6QXV0',
        'duracao_segundos': 300,
        'questoes': [
            {'id': 'q1', 'pergunta': '1. O uniforme pode sofrer reparos pelo próprio usuário?', 'opcoes': [{'id': 'a', 'texto': 'Não, furos e rasgos comprometem a proteção e exigem troca'}, {'id': 'b', 'texto': 'Sim, pode costurar com qualquer linha'}, {'id': 'c', 'texto': 'Pode colocar fita adesiva'}], 'resposta_correta': 'a'},
            {'id': 'q2', 'pergunta': '2. Uniformes antichama aceitam cloro na lavagem?', 'opcoes': [{'id': 'a', 'texto': 'Sim'}, {'id': 'b', 'texto': 'Não, o cloro destrói as propriedades antichama do tecido'}, {'id': 'c', 'texto': 'Só se tiver mancha forte'}], 'resposta_correta': 'b'},
            {'id': 'q3', 'pergunta': '3. Qual a atitude correta sobre uso do uniforme fora da empresa?', 'opcoes': [{'id': 'a', 'texto': 'Evitar o uso em ambientes de lazer ou bares após o trabalho'}, {'id': 'b', 'texto': 'Não tem restrição, é roupa normal'}, {'id': 'c', 'texto': 'Deve ser usado até nos fins de semana'}], 'resposta_correta': 'a'},
            {'id': 'q4', 'pergunta': '4. Mangas compridas do uniforme de proteção devem ficar:', 'opcoes': [{'id': 'a', 'texto': 'Dobradinhas até o cotovelo para não sentir calor'}, {'id': 'b', 'texto': 'Completamente abaixadas protegendo os braços inteiros'}, {'id': 'c', 'texto': 'Removidas na tesoura'}], 'resposta_correta': 'b'},
            {'id': 'q5', 'pergunta': '5. Quando deve ser lavado o uniforme contaminado com óleos fortes?', 'opcoes': [{'id': 'a', 'texto': 'Junto com a roupa da família em casa'}, {'id': 'b', 'texto': 'De forma separada ou, dependendo do risco, lavado por empresa especializada'}, {'id': 'c', 'texto': 'Lavar só com água pura'}], 'resposta_correta': 'b'}
        ]
    },
    'capacete': {
        'url': 'https://www.youtube.com/embed/1aks7R6QXV0',
        'duracao_segundos': 300,
        'questoes': [
            {'id': 'q1', 'pergunta': '1. O que deve ser regulado no capacete antes do uso?', 'opcoes': [{'id': 'a', 'texto': 'Apenas a cor'}, {'id': 'b', 'texto': 'A suspensão interna (carneira) para não ficar folgado nem apertado'}, {'id': 'c', 'texto': 'O tamanho da aba'}], 'resposta_correta': 'b'},
            {'id': 'q2', 'pergunta': '2. A jugular (fita de queixo) serve para:', 'opcoes': [{'id': 'a', 'texto': 'Ajudar a manter o capacete fixo na cabeça em caso de ventos ou movimentos bruscos'}, {'id': 'b', 'texto': 'Absorver suor'}, {'id': 'c', 'texto': 'Pendurar o capacete'}], 'resposta_correta': 'a'},
            {'id': 'q3', 'pergunta': '3. Posso colar adesivos ou pintar o capacete?', 'opcoes': [{'id': 'a', 'texto': 'Sim, à vontade'}, {'id': 'b', 'texto': 'Não, os solventes das colas/tintas enfraquecem a estrutura plástica do casco'}, {'id': 'c', 'texto': 'Só se for adesivo pequeno'}], 'resposta_correta': 'b'},
            {'id': 'q4', 'pergunta': '4. O que fazer se o capacete sofrer um impacto forte, mas não rachar?', 'opcoes': [{'id': 'a', 'texto': 'Continuar usando normalmente'}, {'id': 'b', 'texto': 'Substituí-lo mesmo assim, pois o plástico pode ter microfissuras e perder resistência'}, {'id': 'c', 'texto': 'Dar um polimento'}], 'resposta_correta': 'b'},
            {'id': 'q5', 'pergunta': '5. Como é a limpeza do capacete?', 'opcoes': [{'id': 'a', 'texto': 'Lavar a carneira com água e sabão e o casco com pano úmido'}, {'id': 'b', 'texto': 'Esfregar com thinner'}, {'id': 'c', 'texto': 'Não se deve limpar para não tirar a resina plástica'}], 'resposta_correta': 'a'}
        ]
    },
    'cinto_seguranca': {
        'url': 'https://www.youtube.com/embed/1aks7R6QXV0',
        'duracao_segundos': 300,
        'questoes': [
            {'id': 'q1', 'pergunta': '1. Onde o talabarte do cinto de segurança deve ser conectado?', 'opcoes': [{'id': 'a', 'texto': 'Em pontos de ancoragem dimensionados acima da linha da cintura'}, {'id': 'b', 'texto': 'Em encanamentos plásticos frágeis'}, {'id': 'c', 'texto': 'Na perna da escada portátil'}], 'resposta_correta': 'a'},
            {'id': 'q2', 'pergunta': '2. A partir de que altura é obrigatório o uso do cinto tipo para-quedista?', 'opcoes': [{'id': 'a', 'texto': 'A partir de 1 metro'}, {'id': 'b', 'texto': 'A partir de 2 metros'}, {'id': 'c', 'texto': 'A partir de 5 metros'}], 'resposta_correta': 'b'},
            {'id': 'q3', 'pergunta': '3. O que verificar antes de vestir o cinto?', 'opcoes': [{'id': 'a', 'texto': 'Se a cor está bonita'}, {'id': 'b', 'texto': 'Costuras, fivelas e se há desgastes/cortes nas fitas sintéticas'}, {'id': 'c', 'texto': 'Se o logotipo ainda aparece'}], 'resposta_correta': 'b'},
            {'id': 'q4', 'pergunta': '4. Qual a função do absorvedor de energia (ABS)?', 'opcoes': [{'id': 'a', 'texto': 'Esticar mais o cabo'}, {'id': 'b', 'texto': 'Reduzir o impacto físico (força de frenagem) no corpo durante a retenção de uma queda'}, {'id': 'c', 'texto': 'Facilitar a subida na escada'}], 'resposta_correta': 'b'},
            {'id': 'q5', 'pergunta': '5. Como devo manter as fitas do cinto ajustadas ao corpo?', 'opcoes': [{'id': 'a', 'texto': 'Justas o suficiente que uma mão plana passe apertado entre a fita e o corpo'}, {'id': 'b', 'texto': 'Totalmente folgadas para não apertar'}, {'id': 'c', 'texto': 'Apertadas a ponto de cortar a circulação sanguínea'}], 'resposta_correta': 'a'}
        ]
    },
    'avental': {
        'url': 'https://www.youtube.com/embed/1aks7R6QXV0',
        'duracao_segundos': 300,
        'questoes': [
            {'id': 'q1', 'pergunta': '1. Após o uso do avental impermeável, qual o procedimento?', 'opcoes': [{'id': 'a', 'texto': 'Lavar e secar bem antes de guardar'}, {'id': 'b', 'texto': 'Dobrar ainda molhado e guardar no armário'}, {'id': 'c', 'texto': 'Limpar na própria roupa'}], 'resposta_correta': 'a'},
            {'id': 'q2', 'pergunta': '2. Como o avental de PVC deve ser inspecionado?', 'opcoes': [{'id': 'a', 'texto': 'Ignorando os furinhos'}, {'id': 'b', 'texto': 'Colocando contra a luz para ver se existem microfuros ou ressecamentos'}, {'id': 'c', 'texto': 'Só inspecionar quando rasgar metade'}], 'resposta_correta': 'b'},
            {'id': 'q3', 'pergunta': '3. Como ajustar o avental no corpo?', 'opcoes': [{'id': 'a', 'texto': 'Deixar solto arrastando'}, {'id': 'b', 'texto': 'Amarrar as tiras nas costas de forma firme, cobrindo o tórax e abdômen até os joelhos'}, {'id': 'c', 'texto': 'Amarrar apenas no pescoço deixando a cintura solta'}], 'resposta_correta': 'b'},
            {'id': 'q4', 'pergunta': '4. Posso usar um avental rasgado se remendar com fita?', 'opcoes': [{'id': 'a', 'texto': 'Sim, a fita veda bem produtos químicos'}, {'id': 'b', 'texto': 'Não, a fita não garante a proteção original e pode causar acidentes'}, {'id': 'c', 'texto': 'Só temporariamente por algumas semanas'}], 'resposta_correta': 'b'},
            {'id': 'q5', 'pergunta': '5. Onde não se deve deixar o avental de PVC/raspa guardado?', 'opcoes': [{'id': 'a', 'texto': 'Em locais frescos e secos'}, {'id': 'b', 'texto': 'Sob luz solar direta e umidade contínua, pois deterioram o material'}, {'id': 'c', 'texto': 'Em cabides arejados'}], 'resposta_correta': 'b'}
        ]
    },
}

def get_video_info(tipo_epi):
    """Retorna os dados do vídeo baseado no EPI. Fallback seguro."""
    return VIDEOS_EPI.get(tipo_epi, {
        'url': 'https://www.youtube.com/embed/1aks7R6QXV0',
        'duracao_segundos': 300,
        'questoes': [
            {'id': 'q1', 'pergunta': '1. Compreendeu as instruções de uso?', 'opcoes': [{'id': 'a', 'texto': 'Sim'}, {'id': 'b', 'texto': 'Não'}], 'resposta_correta': 'a'},
            {'id': 'q2', 'pergunta': '2. Vai higienizar o equipamento corretamente?', 'opcoes': [{'id': 'a', 'texto': 'Sim'}, {'id': 'b', 'texto': 'Não'}], 'resposta_correta': 'a'},
            {'id': 'q3', 'pergunta': '3. Entendeu os riscos em caso de não utilização?', 'opcoes': [{'id': 'a', 'texto': 'Sim'}, {'id': 'b', 'texto': 'Não'}], 'resposta_correta': 'a'},
            {'id': 'q4', 'pergunta': '4. Comprometer-se a inspecionar o EPI antes do uso?', 'opcoes': [{'id': 'a', 'texto': 'Sim'}, {'id': 'b', 'texto': 'Não'}], 'resposta_correta': 'a'},
            {'id': 'q5', 'pergunta': '5. Compromete-se a não alterar o formato original do EPI?', 'opcoes': [{'id': 'a', 'texto': 'Sim'}, {'id': 'b', 'texto': 'Não'}], 'resposta_correta': 'a'},
        ]
    })
