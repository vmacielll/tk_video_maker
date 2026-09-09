#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Biblioteca de temas prontos: frases + legenda + palavras-chave de fundo.

Cada tema tem:
    busca    -> palavras-chave (em inglês) pra buscar o fundo no Pexels
    frases   -> as 7 frases do vídeo (~15s)
    legenda  -> a descrição pronta pro TikTok
"""

TEMAS = {
    "lei da atracao": {
        "busca": "golden light sunrise hope",
        "cor": "#d4af37",
        "frases": [
            "Se você achou esse vídeo, as coisas vão dar certo pra você",
            "O que é seu já está vindo até você",
            "Confia no tempo — tudo acontece na hora certa",
            "Você está exatamente onde deveria estar",
            "O universo está trabalhando a seu favor agora",
            "Comenta EU ACEITO se você acredita",
            "E me segue para mais mensagens assim",
        ],
        "legenda": "Comenta EU ACEITO se você acredita 🙏 e me segue para mais mensagens de positividade ✨\n\n#leidaatracao #positividade #manifestacao #vaidarcerto #gratidao #espiritualidade",
    },
    "gratidao": {
        "busca": "warm sunlight nature",
        "cor": "#7fc98a",
        "frases": [
            "Pare o que está fazendo e sinta gratidão agora",
            "A gratidão atrai mais coisas boas",
            "O que você agradece, o universo multiplica",
            "Agradeça pelo que já tem, e mais vai chegar",
            "Sua vida já é mais rica do que você percebe",
            "Comenta EU ACEITO se você é grato",
            "Me segue para mais lembretes assim",
        ],
        "legenda": "O que você tem pra agradecer hoje? 🙏\nComenta EU ACEITO e me segue para mais lembretes de gratidão ✨\n\n#gratidao #leidaatracao #positividade #gratidaodiaria #espiritualidade #manifestacao",
    },
    "prosperidade": {
        "busca": "golden bokeh sparkle abundance",
        "cor": "#e6b83a",
        "frases": [
            "O dinheiro está vindo até você",
            "Pare de bloquear a abundância com medo",
            "Você merece viver com tranquilidade financeira",
            "Abra espaço na mente para receber",
            "A prosperidade é seu direito natural",
            "Comenta EU ACEITO se você recebe",
            "Me segue para mais mensagens de abundância",
        ],
        "legenda": "A abundância já está a caminho 💰\nComenta EU ACEITO se você recebe e me segue para mais mensagens de prosperidade ✨\n\n#prosperidade #abundancia #leidaatracao #dinheiro #manifestacao #espiritualidade",
    },
    "amor proprio": {
        "busca": "pink flowers soft dreamy",
        "cor": "#e58fb0",
        "frases": [
            "Você não precisa da aprovação de ninguém",
            "Você é suficiente exatamente como é",
            "Pare de se comparar com os outros",
            "O amor que você procura começa em você",
            "Cuide de você como cuida de quem ama",
            "Comenta EU ACEITO se vai se amar mais",
            "Me segue para mais lembretes assim",
        ],
        "legenda": "Você é suficiente, exatamente como é 💜\nComenta EU ACEITO se vai se amar mais e me segue para mais lembretes ✨\n\n#amorproprio #autoestima #leidaatracao #autocuidado #espiritualidade #positividade",
    },
    "confianca no tempo": {
        "busca": "calm sunset horizon",
        "cor": "#7fb3d5",
        "frases": [
            "Tudo tem o tempo certo",
            "O que é seu não vai passar de você",
            "A pressa só gera ansiedade",
            "Confia no processo, não no relógio",
            "O melhor acontece quando você menos espera",
            "Comenta EU ACEITO se você confia no tempo",
            "Me segue para mais mensagens assim",
        ],
        "legenda": "Tudo tem o tempo certo — confia ⏳\nComenta EU ACEITO se você confia no tempo e me segue para mais mensagens ✨\n\n#confianca #tempocerto #leidaatracao #paciencia #espiritualidade #vaidarcerto",
    },
    "vencer o medo": {
        "busca": "light through dark clouds hope",
        "cor": "#e09a4a",
        "frases": [
            "O medo está te impedindo de viver",
            "Tudo que você quer está do outro lado do medo",
            "Sinta o medo e faça mesmo assim",
            "O medo é só um pensamento, não a verdade",
            "Você é mais forte do que aquilo que teme",
            "Comenta EU ACEITO se vai encarar o medo",
            "Me segue para mais lembretes assim",
        ],
        "legenda": "Tudo que você quer está do outro lado do medo 🦋\nComenta EU ACEITO se vai encarar o medo e me segue para mais lembretes ✨\n\n#coragem #venceromedo #leidaatracao #autoconfianca #espiritualidade #positividade",
    },
    "recomeco": {
        "busca": "sunrise new beginning horizon",
        "cor": "#8fd0a0",
        "frases": [
            "Recomeçar não é falhar",
            "Cada fim é um novo começo disfarçado",
            "Você pode começar de novo a qualquer momento",
            "Não se prenda ao que ficou para trás",
            "Sua melhor história ainda não foi escrita",
            "Comenta EU ACEITO se você está recomeçando",
            "Me segue para mais mensagens assim",
        ],
        "legenda": "Todo fim é um recomeço disfarçado 🌅\nComenta EU ACEITO se você está recomeçando e me segue para mais mensagens ✨\n\n#recomeco #novociclo #leidaatracao #renovacao #espiritualidade #positividade",
    },
    "intuicao": {
        "busca": "misty forest light rays",
        "cor": "#b7a6d9",
        "frases": [
            "Aquela sensação que você ignorou era sua intuição",
            "Seu corpo sabe antes da sua mente",
            "Confie no que sente, não só no que pensa",
            "Sua intuição é o universo falando com você",
            "Quanto mais você ouve, mais ela fala",
            "Comenta EU ACEITO se você confia na sua intuição",
            "Me segue para mais lembretes assim",
        ],
        "legenda": "Confia naquela sensação — ela nunca erra 👁️\nComenta EU ACEITO se você confia na sua intuição e me segue para mais ✨\n\n#intuicao #vozinterior #leidaatracao #espiritualidade #autoconhecimento #sincronicidade",
    },
    "destino": {
        "busca": "starry sky galaxy",
        "cor": "#7d6bd9",
        "frases": [
            "Você está exatamente onde deveria estar",
            "Nada na sua vida foi por acaso",
            "Cada erro te trouxe até aqui",
            "O universo não comete enganos",
            "Confia no caminho que você está trilhando",
            "Comenta EU ACEITO se você confia no seu caminho",
            "Me segue para mais mensagens assim",
        ],
        "legenda": "Nada na sua vida foi por acaso ✨\nComenta EU ACEITO se você confia no seu caminho e me segue para mais mensagens ✨\n\n#destino #proposito #leidaatracao #alinhamento #espiritualidade #vaidarcerto",
    },
    "sinais do universo": {
        "busca": "moon night sky stars",
        "cor": "#c5b3e6",
        "frases": [
            "Coincidências não existem",
            "Tudo que acontece tem um motivo",
            "Preste atenção nos detalhes ao seu redor",
            "O universo manda sinais o tempo todo",
            "Você só precisa aprender a enxergar",
            "Comenta EU ACEITO se você acredita nos sinais",
            "Me segue para mais mensagens assim",
        ],
        "legenda": "O universo está te mandando sinais 👀\nComenta EU ACEITO se você acredita nos sinais e me segue para mais mensagens ✨\n\n#sinais #sinaisdouniverso #leidaatracao #sincronicidade #espiritualidade #misticismo",
    },
    "poder da mente": {
        "busca": "galaxy nebula universe",
        "cor": "#9b7bd4",
        "frases": [
            "Você cria a sua realidade com seus pensamentos",
            "O que você pensa o dia todo, você atrai",
            "Mude seus pensamentos e mude sua vida",
            "Pense no que quer, não no que teme",
            "Sua mente é a ferramenta mais poderosa que existe",
            "Comenta EU ACEITO se você acredita nisso",
            "Me segue para mais ensinamentos assim",
        ],
        "legenda": "Você atrai aquilo que pensa 🧠\nComenta EU ACEITO se você acredita no poder da mente e me segue para mais ensinamentos ✨\n\n#poderdamente #leidaatracao #manifestacao #pensamentopositivo #espiritualidade #mentalidade",
    },
    "ritual antes de dormir": {
        "busca": "candle night moon",
        "cor": "#5b6bd9",
        "frases": [
            "Faça isso antes de dormir e as coisas vão mudar",
            "Fale em voz alta: eu mereço coisas boas",
            "Eu confio no tempo das coisas",
            "Tudo o que é meu já está vindo até mim",
            "Amanhã vai ser melhor do que hoje",
            "Comenta EU ACEITO se vai testar hoje",
            "Me segue para mais rituais assim",
        ],
        "legenda": "Faça isso hoje antes de dormir e volta aqui pra me contar 🙏\nComenta EU ACEITO se vai testar e me segue para mais rituais ✨\n\n#leidaatracao #manifestacao #ritual #positividade #vaidarcerto #espiritualidade #gratidao",
    },
    "fatos esotericos": {
        "busca": "tarot cards candle mystical",
        "cor": "#6d4bc7",
        "frases": [
            "Você sabia que o Tarot nasceu como jogo de cartas, não oráculo?",
            "Só virou ferramenta mística séculos depois",
            "O mesmo aconteceu com cristais e símbolos antigos",
            "Muito do que chamam de magia é história esquecida",
            "Quanto mais você estuda, mais o véu se abre",
            "Comenta EU ACEITO se você quer mais curiosidades",
            "Me segue para mais fatos esotéricos",
        ],
        "legenda": "Você sabia disso? 👀\nComenta EU ACEITO e me segue para mais curiosidades esotéricas ✨\n\n#esoterismo #tarot #misticismo #curiosidades #espiritualidade #ocultismo",
    },
    "significado oculto": {
        "busca": "tarot card dark mystery",
        "cor": "#8e5bd4",
        "frases": [
            "O que significa tirar a mesma carta repetidamente?",
            "O universo está insistindo em uma mensagem",
            "A carta repetida é um aviso, não uma coincidência",
            "Preste atenção no que ela representa na sua vida",
            "Ela aparece até você entender o recado",
            "Comenta qual carta você mais tira",
            "Me segue para decifrar os sinais comigo",
        ],
        "legenda": "Qual carta você mais tira? 👀\nComenta aqui e me segue para decifrar os significados ocultos ✨\n\n#tarot #significado #cartas #misticismo #espiritualidade #oraculo",
    },
    "sinais de manifestacao": {
        "busca": "butterfly feather light",
        "cor": "#e0c27a",
        "frases": [
            "3 sinais de que a lei da atração JÁ está funcionando",
            "Coincidências que se repetem sem explicação",
            "Sentir uma paz estranha, como se tudo estivesse certo",
            "Ver símbolos que significam algo só pra você",
            "Se isso está acontecendo, continua — está no caminho",
            "Comenta EU ACEITO se você já percebeu isso",
            "Me segue para mais sinais assim",
        ],
        "legenda": "Esses 3 sinais mostram que está funcionando ✨\nComenta EU ACEITO se você já viveu isso e me segue para mais 🙏\n\n#leidaatracao #manifestacao #sinais #espiritualidade #vaidarcerto #sincronicidade",
    },
    "signos": {
        "busca": "zodiac constellation stars",
        "cor": "#6d6fd9",
        "frases": [
            "Seu signo vai viver uma virada essa semana",
            "E não vai ser coincidência",
            "O alinhamento dos astros está a seu favor",
            "Uma oportunidade que você esperava vai aparecer",
            "Fique atento às pessoas que chegam perto",
            "Comenta teu signo aqui embaixo",
            "Me segue para a previsão de amanhã",
        ],
        "legenda": "Qual é o seu signo? ♈♉♊\nComenta aqui e me segue para a previsão de amanhã ✨\n\n#signos #astrologia #horoscopo #zodiaco #espiritualidade #misticismo",
    },
    "numeros e simbolos": {
        "busca": "sacred geometry clock",
        "cor": "#d9b34a",
        "frases": [
            "O mesmo número aparece na sua vida o tempo todo?",
            "Isso não é coincidência",
            "Cada número carrega uma mensagem do universo",
            "Ver 11:11 é um chamado para prestar atenção",
            "O universo fala com você por símbolos",
            "Comenta o número que você mais vê",
            "Me segue para decifrar o significado",
        ],
        "legenda": "Qual número você mais vê? 👀\nComenta aqui e me segue para decifrar os significados ✨\n\n#numeros #simbologia #1111 #leidaatracao #sinaisdouniverso #misticismo",
    },
    "origem e historia": {
        "busca": "ancient temple candle ritual",
        "cor": "#c98a4b",
        "frases": [
            "A história real por trás dos símbolos que você usa",
            "Muitos rituais vêm de tradições milenares",
            "O que você chama de magia já foi sabedoria antiga",
            "Conhecer a origem muda o poder do símbolo",
            "Respeitar a história é parte da prática",
            "Comenta EU ACEITO se você quer saber mais",
            "Me segue para mais histórias do oculto",
        ],
        "legenda": "Você conhece a origem desses símbolos? 👀\nComenta EU ACEITO e me segue para mais histórias ✨\n\n#simbolos #historia #ocultismo #misticismo #tradicao #espiritualidade",
    },
}


def listar_temas():
    return list(TEMAS.keys())


def listar_temas_com_busca():
    return [{"nome": n, "busca": d["busca"], "cor": d["cor"], "cta": CTAS.get(n)}
            for n, d in TEMAS.items()]


def obter_tema(nome):
    n = (nome or "").strip().lower()
    if n in TEMAS:
        return TEMAS[n]
    for k in TEMAS:
        if n and (n in k or k in n):
            return TEMAS[k]
    return None


# CTA de comentário/engajamento específico por tema (a 6ª frase do vídeo)
CTAS = {
    "lei da atracao": 'Comenta "EU RECEBO" e ativa isso hoje ✨',
    "gratidao": 'Comenta "GRATIDÃO" por algo bom que aconteceu hoje',
    "prosperidade": 'Comenta "PROSPERIDADE" e abre o caminho 💰',
    "amor proprio": 'Comenta "EU ME AMO" e se escolha hoje',
    "confianca no tempo": 'Comenta "CONFIO" e solta o controle',
    "vencer o medo": 'Comenta "CORAGEM" se vai enfrentar algo essa semana',
    "recomeco": 'Comenta "RECOMEÇO" se está pronto pra virar a página',
    "intuicao": 'Comenta "CONFIO NA MINHA INTUIÇÃO"',
    "destino": 'Comenta "ESTAVA ESCRITO" se isso ressoou',
    "sinais do universo": 'Comenta "111" se você viu o sinal da hora',
    "poder da mente": 'Comenta "EU POSSO" e reprograma agora',
    "ritual antes de dormir": "Salva pra fazer esse ritual hoje à noite",
    "fatos esotericos": "Compartilha com quem precisa conhecer isso",
    "significado oculto": "Comenta o que isso significou pra você",
    "sinais de manifestacao": 'Comenta "JÁ ESTÁ ACONTECENDO" se viu um desses sinais',
    "signos": "Comenta seu signo e me conta o que ressoou",
    "numeros e simbolos": "Comenta o número que você mais vê ultimamente",
    "origem e historia": "Compartilha essa história com alguém curioso",
}


def obter_cta(nome):
    return CTAS.get((nome or "").strip().lower())
