# Shugo Build — bot de builds do AION 2 para Discord

Bot do Discord que monta a **build completa de cada classe** (PvE e PvP) a partir dos tops reais,
**atualiza de hora em hora** e **compara o meta coreano com o global**.

Os dados vêm do **Character Info oficial da NC** (aion2.plaync.com), na Coreia e nas 5 regiões globais
(NA Oeste, NA Leste, Europa, América do Sul, Ásia).

## O que a build mostra

| Seção | Conteúdo |
|---|---|
| Resumo | Top 1 (nome, servidor, poder, item level), média do top, skills e equipamentos principais, asa |
| Equipamento | Item mais usado em cada slot (arma, armadura, acessórios, runas, arcanas) com % de uso, encanto médio e exceed (★) |
| Skills | Ativas na barra, skills DP e passivas, com % de uso e nível médio, e a barra do top 1 |
| Daevanion | % de nós abertos por tabuleiro, níveis de skill e atributos ganhos (somando todos os tabuleiros), escolhas do top 1 |
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
| `/canal` | (admin) Canal que recebe a cada hora as mudanças do meta |
| `/atualizar` | (admin) Força uma coleta agora |
| `/status` | Quantos personagens já foram analisados |

## Como o "top" é escolhido

- **PvE:** maior poder de combate no level máximo, com um peso pequeno para títulos com bônus PvE.
- **PvP:** a NC **não publica o ranking do Abismo** (o campo de ranking da API oficial vem vazio). Por isso a ordem é:
  1. ranking PvP oficial, que entra sozinho se a NC liberar;
  2. personagens marcados com `/abismo adicionar`. Se você sabe quem é o top 1 do Abismo no seu servidor, cadastre e ele vira a referência;
  3. sem nenhum dos dois, poder de combate com peso para títulos PvP equipados.

  O rodapé de cada build mostra qual critério foi usado.

A API não tem "listar ranking". Por isso o bot descobre personagens varrendo a busca oficial (ordenada por level)
com palavras-chave em rodízio. O pool cresce a cada ciclo, então **as primeiras horas têm menos dados** e o meta
fica mais preciso com o tempo.

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

O primeiro ciclo começa assim que o bot liga e leva uns 10 a 20 minutos para as 6 regiões. Depois roda a cada `UPDATE_MINUTES`.

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
5. Em **Settings**, deixe **Serverless / App Sleeping desligado**. O bot precisa ficar ligado pra rodar a coleta de hora em hora.
6. Pronto. Cada `git push` faz um deploy novo. Se o bot cair, o Railway reinicia sozinho (até 10 tentativas seguidas).

Notas:
- O bot não abre porta HTTP, então **não gere domínio** nem configure healthcheck.
- Os logs ficam na aba **Deployments → View Logs**. Procure por `ciclo completo` pra saber que a coleta terminou.
- Consumo: o bot é leve (cerca de 100 MB de RAM, CPU quase parada entre os ciclos). Cabe no plano Hobby.

## Avisos

- A API usada é a mesma que o site oficial usa, mas não é documentada. Se a NC mudar algo, o `/status` mostra o erro.
- O bot limita a velocidade das requisições (`REQUEST_INTERVAL`). Não abaixe muito, pra não sobrecarregar o site da NC.
- Equipamentos da Coreia e do global diferem naturalmente: a Coreia tem level 55 e itens mais altos, o global ainda é 45.
  A comparação foca em skills, Daevanion e asa, que são as escolhas que dá pra copiar.
