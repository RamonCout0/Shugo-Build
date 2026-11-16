"""Voz de Shugo, nyang~ Todas as falas do Shugo Build passam por aqui."""
from __future__ import annotations

import random

FALAS = {
    "build": [
        "Nyerk! Aqui está a build de {cls} {modo}, nyang~ Copiadinha dos melhores, sem cobrar taxa! Bom, quase.",
        "Nyang nyang~ Shugo olhou os tops de {cls} e anotou tudo, nyerk! Usa direitinho, tá?",
        "Nyerk nyerk! Build de {cls} {modo} saindo quentinha do forno do Shugo~",
        "Shugo encontrou a build de {cls}, nyang! Se morrer no Abismo a culpa não é do Shugo, nyerk~",
    ],
    "comparar": [
        "Nyerk! Shugo atravessou o mar até a Coreia pra espiar o meta de {cls}, nyang~",
        "Nyang~ Coreia contra Global! Shugo trouxe a fofoca toda de {cls}, nyerk!",
        "Os Shugos coreanos contaram tudo pro Shugo, nyerk nyerk~ Olha só o {cls} deles!",
    ],
    "classes": [
        "Nyerk! Shugo colocou as classes em fila por poder, nyang~ Sem chorar, hein!",
        "Nyang~ Quem é o mais forte? Shugo mediu todo mundo, nyerk!",
    ],
    "top": [
        "Nyerk! Os mais fortes de {cls}, nyang~ Shugo fez até reverência pra eles!",
        "Nyang nyang~ Olha o top de {cls}! Shugo tremeu só de olhar, nyerk!",
    ],
    "jogador": [
        "Nyerk! Shugo foi até o {nome} e espiou o inventário inteirinho, nyang~",
        "Nyang~ Achei o {nome}! Shugo não mexeu em nada… só olhou, nyerk!",
        "Nyerk nyerk! Build do {nome} na mão, nyang~ Ele nem percebeu o Shugo!",
    ],
    "buscando": [
        "Nyerk… Shugo está correndo atrás do {nome}, espera um pouquinho, nyang~",
    ],
    "nao_achei": [
        "Nyerk?! Shugo procurou o **{nome}** em {regiao} e não achou, nyang… Confere o nome (e o servidor)!",
        "Nyang… Shugo cavou a Atreia inteira e nada de **{nome}** em {regiao}, nyerk! Escreveu certinho?",
    ],
    "sem_dados": [
        "Nyerk… Shugo ainda está juntando os dados dessa classe, nyang~ Volta daqui a pouquinho! "
        "(ou um admin pode usar `/atualizar`)",
        "Nyang! Shugo ainda não terminou de espiar os tops dessa região, nyerk~ Espera uns minutinhos!",
    ],
    "erro_api": [
        "Nyerk!! O site da NC deu um tropeção e o Shugo caiu junto, nyang… Tenta de novo já já! (`{erro}`)",
    ],
    "abismo_add": [
        "Nyerk! **{nome}** ({servidor}) agora está na lista de lendas do Abismo do Shugo, nyang~ "
        "A build dele vai liderar o meta PvP da classe no próximo ciclo!",
    ],
    "abismo_rm": [
        "Nyang~ Shugo riscou {n} nome(s) da lista do Abismo, nyerk!",
    ],
    "abismo_vazio": [
        "Nyerk? A lista do Abismo está vazia, nyang~ Usa `/abismo adicionar` pra ensinar o Shugo quem manda lá!",
    ],
    "canal_on": [
        "Nyerk! Shugo vai gritar as mudanças do meta aqui em {canal} toda hora, nyang~",
    ],
    "canal_off": [
        "Nyang… Shugo vai ficar quietinho agora, nyerk. Sem avisos!",
    ],
    "atualizando": [
        "Nyerk nyerk! Shugo saiu correndo pra espiar todo mundo, nyang~ Isso leva uns minutinhos!",
    ],
    "ja_atualizando": [
        "Nyang! Shugo já está correndo, nyerk~ Não dá pra correr duas vezes!",
    ],
    "atualizado": [
        "Nyerk! Shugo voltou, nyang~ {n} meta(s) mudaram!",
    ],
    "mudancas": [
        "Nyerk nyerk!! Novidades no meta, nyang~ Shugo viu tudo!",
        "Nyang~ Hora da fofoca do meta! Shugo trouxe as mudanças, nyerk!",
    ],
    "status": [
        "Nyerk! Relatório do Shugo, nyang~",
    ],
}


def fala(tipo: str, **kw) -> str:
    return random.choice(FALAS[tipo]).format(**kw)
