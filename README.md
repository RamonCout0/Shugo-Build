# Shugo Build — bot de builds do AION 2 para Discord

Bot do Discord que monta a **build completa de cada classe** (PvE e PvP) a partir dos tops reais,
**atualiza sozinho domingo de madrugada, a cada duas semanas** e **compara o meta coreano com o global**.

Os dados vêm do **Character Info oficial da NC** (aion2.plaync.com), na Coreia e nas 5 regiões globais
(NA Oeste, NA Leste, Europa, América do Sul, Ásia).

## O que a build mostra

| Seção | Conteúdo |
|---|---|
| Resumo | Top 1 (nome, servidor, poder, item level), média do top, skills e equipamentos principais, asa |
| Equipamento | Item mais usado em cada slot (arma, armadura, acessórios, runas, arcanas) com % de uso, encanto médio e exceed (★), Manastones mais usadas e Theostone |
| Skills | Ativas na barra, Estigmas e passivas, com % de uso e nível médio, a barra do top 1 e as **gemas de habilidade** (+1 de Soul Binding nos equipamentos) |
| Daevanion | **Imagem dos tabuleiros** (6 no global, 9 na Coreia). No meta, o brilho de cada nó é a % dos tops que abriu; no `/jogador`, aceso = aberto. Também lista os níveis de skill e atributos ganhos |
| Stats/Títulos | Atributos base e divinos médios, títulos equipados mais comuns e seus efeitos |

## Comandos

| Comando | O que faz |
|---|---|
| `/build classe modo [região]` | Build recomendada, com botões pra trocar de seção |
| `/comparar classe modo` | 🇰🇷 x 🌎: poder, skills e Daevanion que cada lado usa mais, e a asa |
| `/classes modo [região]` | Classes ordenadas pelo poder médio dos tops |
| `/top classe modo [região]` | Lista os 15 melhores |
| `/jogador nome região [servidor]` | Build de qualquer personagem, consultada na hora |
| `/abismo adicionar/remover/lista` | (admin) Lista manual dos tops do Abismo |
| `/canal` | (admin) Canal que recebe as mudanças do meta depois de cada coleta |
| `/atualizar` | (admin) Força uma coleta agora (leva uns 40 a 60 min) |
| `/status` | Quantos personagens já foram analisados, última e próxima coleta |

## Como o "top" é escolhido

- **PvE:** maior poder de combate no level máximo, com um peso pequeno para títulos com bônus PvE.
- **PvP:** a NC **não publica o ranking do Abismo** (o campo de ranking da API oficial vem vazio). Por isso a ordem é:
  1. ranking PvP oficial, que entra sozinho se a NC liberar;
  2. personagens marcados com `/abismo adicionar`. Se você sabe quem é o top 1 do Abismo no seu servidor, cadastre e ele vira a referência;
  3. sem nenhum dos dois, poder de combate com peso para títulos PvP equipados.

  O rodapé de cada build mostra qual critério foi usado.

A API não tem "listar ranking". Por isso o bot descobre personagens varrendo a busca oficial (ordenada por level)
com palavras-chave em rodízio. O pool cresce a cada ciclo, então o meta fica mais preciso com o tempo.

## Quando ele atualiza

Pra gastar pouco, a coleta roda **domingo às 04:00 (horário de Brasília), um domingo sim e outro não**.
No resto do tempo o bot só responde comandos, e o `/jogador` continua consultando ao vivo.

- A contagem das duas semanas começa na última coleta completa, inclusive a do seed. Isso fica salvo no banco, então reiniciar o bot não muda a agenda.
- Se o bot estiver fora do ar no domingo, ele espera o domingo seguinte.
- O `/atualizar` força uma coleta na hora e reinicia a contagem.
- Pra mudar a agenda, use as variáveis `UPDATE_EVERY_WEEKS` (1 = todo domingo), `UPDATE_HOUR`, `UPDATE_WEEKDAY` e `UPDATE_TZ`.

## Instalação

1. Crie um app chamado **Shugo Build** em https://discord.com/developers/applications (o nome e o avatar que aparecem no Discord vêm daí). Em **Bot**, clique em *Reset Token* e copie o token.
2. Em **OAuth2 → URL Generator**, marque `bot` e `applications.commands`, com as permissões *Send Messages* e *Embed Links*. Abra a URL gerada e convide o bot pro seu servidor.
3. Prepare o ambiente:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate          # Windows  (Linux/Mac: source .venv/bin/activate)
   pip install -r requirements.txt
   copy .env.example .env          # Linux/Mac: cp .env.example .env
   ```
4. Coloque o `DISCORD_TOKEN` no `.env`. Opcional: coloque o `GUILD_ID` do seu servidor pros comandos aparecerem na hora.
5. `python bot.py`

### Banco pré-carregado (o bot já liga sabendo o meta)

Uma coleta completa das 6 regiões leva **uns 40 a 60 minutos**, porque o bot consulta o site da NC devagar de propósito.
Pra ninguém esperar, o repositório traz um banco já preenchido em `seed/aion2-seed.db.gz`:

- quando o bot liga com o banco vazio (primeiro deploy, volume novo), ele restaura esse arquivo e o `/build` já funciona na hora;
- depois disso, a coleta quinzenal de domingo vai atualizando por cima, e o seed nunca sobrescreve dados que o bot já tem;
- durante a coleta, cada região é liberada assim que termina (a Coreia sai primeiro), sem esperar as outras.

Pra atualizar o seed (vale a pena quando o volume for novo ou o seed estiver muito velho):

```bash
python scripts/gerar_seed.py
git add seed/aion2-seed.db.gz && git commit -m "Atualiza seed" && git push
```

Rodar com `--ciclos 2` deixa o pool maior e o meta mais preciso, mas demora o dobro.
O `--ciclos 0 --completar` só baixa os tabuleiros nó a nó e as gemas dos top 3 que ainda não têm, sem refazer a coleta.

Os detalhes de tabuleiro e equipamento custam ~35 consultas por personagem, por isso só são buscados para os
**top 3 de cada classe/modo** (e na hora, no `/jogador`, que leva uns 15 segundos).

Para testar sem Discord: `python smoke_test.py kr naw`. Ele faz um ciclo pequeno e imprime os embeds.

## Rodando 24h no Railway

O projeto já vem com `Dockerfile` e `railway.json`, então o Railway sabe construir e iniciar o bot sozinho.

1. Suba este projeto pro GitHub. O `.env` não vai junto, e é assim mesmo que tem que ser.
2. No [Railway](https://railway.com), clique em **New Project → Deploy from GitHub repo** e escolha o repositório.
3. No serviço, abra **Variables** e adicione:
   - `DISCORD_TOKEN`: o token do bot (obrigatório)
   - `GUILD_ID`: o ID do seu servidor (opcional, faz os comandos aparecerem na hora)
   - as outras do `.env.example` só se quiser mudar o padrão
4. **Crie um volume:** clique com o botão direito no serviço → **Attach Volume**, com mount path `/data`.
   O bot detecta o volume sozinho e guarda o banco lá. **Sem o volume, todo deploy apaga o histórico e o
   bot recomeça a coleta do zero.** Se esquecer, os logs mostram um aviso.
5. Em **Settings**, deixe **Serverless / App Sleeping desligado**. O bot precisa ficar ligado pra responder comandos e pra rodar a coleta de domingo.
6. Pronto. Cada `git push` faz um deploy novo. Se o bot cair, o Railway reinicia sozinho (até 10 tentativas seguidas).

Notas:
- O bot não abre porta HTTP, então **não gere domínio** nem configure healthcheck.
- Os logs ficam na aba **Deployments → View Logs**. Procure por `ciclo completo` pra saber que a coleta terminou.
- Consumo: fora do domingo de coleta, o bot só fica conectado ao Discord (cerca de 100 MB de RAM e CPU quase zero).
  Pode deixar com pouca CPU e uns 256 MB de RAM. Abaixo disso, o Railway pode matar o processo durante a coleta.

## Avisos

- A API usada é a mesma que o site oficial usa, mas não é documentada. Se a NC mudar algo, o `/status` mostra o erro.
- O bot limita a velocidade das requisições (`REQUEST_INTERVAL`). Não abaixe muito, pra não sobrecarregar o site da NC.
- Equipamentos da Coreia e do global diferem naturalmente: a Coreia tem level 55 e itens mais altos, o global ainda é 45.
  A comparação foca em skills, Daevanion e asa, que são as escolhas que dá pra copiar.
