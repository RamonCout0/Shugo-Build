"""Shugo Build — bot do Discord com o meta de builds do AION 2 (PvE/PvP), Coreia x Global, atualizado domingo de madrugada (quinzenal)."""
from __future__ import annotations

import asyncio
import gzip
import io
import json
import logging
import os
import shutil
import sqlite3
import sys
from pathlib import Path

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

from aion2 import board_image, render, schedule
from aion2.shugo import fala
from aion2.api import ALL_REGIONS, Aion2Api, ApiError
from aion2.collector import Collector, Settings
from aion2.meta import compare
from aion2.store import Store

load_dotenv()
# stdout: o Railway mostra stderr como erro (vermelho) nos logs
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), stream=sys.stdout,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot")


def db_path() -> str:
    """DB_PATH explícito > volume do Railway (dados sobrevivem a deploys) > arquivo local."""
    if os.getenv("DB_PATH"):
        p = Path(os.environ["DB_PATH"])
    elif os.getenv("RAILWAY_VOLUME_MOUNT_PATH"):
        p = Path(os.environ["RAILWAY_VOLUME_MOUNT_PATH"]) / "aion2.db"
    else:
        if os.getenv("RAILWAY_ENVIRONMENT"):
            log.warning("Nenhum volume no Railway: o banco será apagado a cada deploy. Crie um volume em /data.")
        p = Path("aion2.db")
    p.parent.mkdir(parents=True, exist_ok=True)
    restore_seed(p)
    return str(p)


SEED_GZ = Path(__file__).resolve().parent / "seed" / "aion2-seed.db.gz"


def _kv(con: sqlite3.Connection, k: str, default=0.0):
    try:
        row = con.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return json.loads(row[0]) if row else default
    except sqlite3.Error:
        return default


def restore_seed(p: Path) -> None:
    """Usa o seed do repositório quando:
    - o banco está vazio (primeiro deploy / volume novo), ou
    - o seed é uma versão mais nova (ex.: completado com tabuleiros/gemas) e o bot não fez coleta própria depois dele.
    Ao trocar, mantém o canal do /canal e os tops do Abismo cadastrados."""
    if not SEED_GZ.exists():
        return
    tmp = p.with_suffix(".seed-tmp")
    with gzip.open(SEED_GZ, "rb") as src, open(tmp, "wb") as dst:
        shutil.copyfileobj(src, dst)
    seed = sqlite3.connect(tmp)
    seed_ver, seed_cycle = _kv(seed, "seed_version"), _kv(seed, "last_full_cycle")
    seed.close()

    empty, keep_reason = True, ""
    if p.exists():
        try:
            con = sqlite3.connect(p)
            empty = not con.execute("SELECT COUNT(*) FROM meta_snapshots").fetchone()[0]
            db_ver, db_cycle = _kv(con, "seed_version"), _kv(con, "last_full_cycle")
            con.close()
            if not empty and seed_ver <= db_ver:
                keep_reason = "o seed não é mais novo"
            elif not empty and (db_cycle or 0) > (seed_cycle or 0):
                keep_reason = "o bot já coletou dados mais novos que o seed"
        except sqlite3.Error:
            empty = True  # tabelas ainda não existem
    if keep_reason:
        tmp.unlink(missing_ok=True)
        log.info("banco atual mantido (%s)", keep_reason)
        return

    if not empty:  # leva junto o que é configuração do servidor
        new = sqlite3.connect(tmp)
        new.execute("ATTACH DATABASE ? AS old", (str(p),))
        try:
            new.execute("INSERT OR REPLACE INTO channels SELECT * FROM old.channels")
            new.execute("INSERT OR IGNORE INTO characters SELECT * FROM old.characters WHERE seeded=1")
            new.execute("UPDATE characters SET seeded=1 WHERE (region, char_id) IN "
                        "(SELECT region, char_id FROM old.characters WHERE seeded=1)")
            new.execute("INSERT OR IGNORE INTO builds SELECT b.* FROM old.builds b JOIN old.characters c "
                        "ON b.region=c.region AND b.char_id=c.char_id WHERE c.seeded=1")
            new.commit()
        except sqlite3.Error as e:
            log.warning("não consegui copiar canal/tops do Abismo do banco antigo: %s", e)
        new.execute("DETACH DATABASE old")
        new.close()
    os.replace(tmp, p)
    log.info("Nyerk! Banco pré-carregado %s de %s — o meta já está disponível, nyang~",
             "restaurado" if empty else "atualizado (versão nova do seed)", SEED_GZ.name)

TOKEN = os.environ.get("DISCORD_TOKEN", "")
GUILD_ID = int(os.getenv("GUILD_ID", "0") or 0)  # opcional: sincroniza comandos na hora nesse servidor
REGIONS = [r.strip() for r in os.getenv("REGIONS", "kr,naw,nae,eu,la,as").split(",") if r.strip()]

SCOPE_CHOICES = [app_commands.Choice(name="🇰🇷 Coreia", value="kr"),
                 app_commands.Choice(name="🌎 Global (todas as regiões)", value="global")] + \
                [app_commands.Choice(name=f"🌎 {v}", value=k) for k, v in ALL_REGIONS.items() if k != "kr"]
REGION_CHOICES = [app_commands.Choice(name=v, value=k) for k, v in ALL_REGIONS.items()]
MODE_CHOICES = [app_commands.Choice(name="PvE", value="pve"), app_commands.Choice(name="PvP (Abismo)", value="pvp")]


class MetaBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.store = Store(db_path())
        log.info("banco de dados: %s", self.store.path)
        self.http_session: aiohttp.ClientSession | None = None
        self.api: Aion2Api | None = None
        self.collector: Collector | None = None

    async def setup_hook(self):
        self.http_session = aiohttp.ClientSession(headers={
            "User-Agent": "Mozilla/5.0 (shugo-build-bot)", "Referer": "https://aion2.plaync.com/"})
        self.api = Aion2Api(self.http_session, float(os.getenv("REQUEST_INTERVAL", "0.35")))
        self.collector = Collector(self.api, self.store, Settings(top_n=int(os.getenv("TOP_N", "15"))))
        if GUILD_ID:
            g = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=g)
            await self.tree.sync(guild=g)
        else:
            await self.tree.sync()
        last = self.collector.last_full_cycle()
        log.info("coleta agendada: %s • próxima: %s", schedule.describe(),
                 schedule.next_run(last).strftime("%d/%m/%Y %H:%M"))
        self.update_loop.start()

    async def close(self):
        if self.http_session:
            await self.http_session.close()
        await super().close()

    @tasks.loop(minutes=15)
    async def update_loop(self):
        """Só confere a agenda; a coleta em si roda domingo de madrugada (quinzenal por padrão)."""
        if self.collector.running.locked():
            return
        if not getattr(self, "_details_checked", False):
            # uma vez por boot: completa tabuleiros/gemas dos top 3 que faltarem (banco antigo, sem precisar de seed)
            self._details_checked = True
            if self.store.has_meta() and self.collector.needs_details(REGIONS):
                log.info("Nyerk! Completando tabuleiros do Daevanion e gemas dos tops em segundo plano, nyang~")
                try:
                    await self.collector.complete_details(REGIONS)
                except Exception:
                    log.exception("completar detalhes falhou")
                return
        never = not self.store.has_meta()  # banco vazio e sem seed: coleta uma vez pra não ficar sem dados
        if not never and not schedule.is_due(self.collector.last_full_cycle()):
            return
        log.info("Nyerk! Hora da coleta%s, nyang~", " inicial (banco vazio)" if never else " agendada")
        try:
            changes = await self.collector.run_cycle(REGIONS)
        except Exception:
            log.exception("ciclo de atualização falhou")
            return
        if changes:
            await self.post_changes(changes)

    @update_loop.before_loop
    async def _wait_ready(self):
        await self.wait_until_ready()

    async def post_changes(self, changes: dict[str, list[str]]):
        e = discord.Embed(title="🔄 Shugo Build — mudanças no meta desde a última coleta", color=0x5865F2)
        for key, lines in list(changes.items())[:20]:
            scope, cls, mode = key.split("|")
            e.add_field(name=f"{render.scope_label(scope)} • {render.class_label(cls)} • {render.MODE_PT[mode]}",
                        value=render._clip("\n".join(lines)), inline=False)
        for cid in self.store.channels():
            ch = self.get_channel(cid)
            if ch:
                try:
                    await ch.send(content=fala("mudancas"), embed=e)
                except discord.HTTPException as err:
                    log.warning("não consegui postar em %s: %s", cid, err)

    def get_meta(self, scope: str, cls: str, mode: str) -> dict | None:
        meta = self.store.last_snapshot(scope, cls, mode)
        if not meta or not meta.get("n"):
            meta = self.collector.compute_meta(scope, cls, mode)
        return meta if meta.get("n") else None


bot = MetaBot()


# ------------------------------------------------------------------ helpers
async def class_autocomplete(inter: discord.Interaction, current: str):
    classes = bot.store.classes(list(ALL_REGIONS))
    cur = current.lower()
    return [app_commands.Choice(name=render.class_label(c), value=c) for c in classes
            if cur in c.lower() or cur in render.CLASS_PT.get(c, "").lower()][:25]


class SectionView(discord.ui.View):
    def __init__(self, meta: dict, owner_id: int):
        super().__init__(timeout=600)
        self.meta = meta
        self._daev_png: bytes | None = None  # desenha uma vez e reaproveita
        for key, (label, _) in render.SECTIONS.items():
            btn = discord.ui.Button(label=label, style=discord.ButtonStyle.primary if key == "resumo"
                                    else discord.ButtonStyle.secondary, custom_id=f"sec:{key}")
            btn.callback = self._make_cb(key)
            self.add_item(btn)

    def _make_cb(self, key: str):
        async def cb(inter: discord.Interaction):
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.style = (discord.ButtonStyle.primary if item.custom_id == f"sec:{key}"
                                  else discord.ButtonStyle.secondary)
            embed = render.SECTIONS[key][1](self.meta)
            files: list[discord.File] = []
            if key == "daevanion" and self.meta["daevanion"].get("grids"):
                await inter.response.defer()  # desenhar leva ~1s: evita estourar os 3s do Discord
                if self._daev_png is None:
                    self._daev_png = await asyncio.to_thread(board_image.meta_image, self.meta)
                if self._daev_png:
                    files.append(discord.File(io.BytesIO(self._daev_png), filename=render.DAEV_FILE))
                await inter.edit_original_response(embed=embed, view=self, attachments=files)
                return
            await inter.response.edit_message(embed=embed, view=self, attachments=files)
        return cb


async def player_files(build: dict) -> list[discord.File]:
    png = await asyncio.to_thread(board_image.build_image, build)
    return [discord.File(io.BytesIO(png), filename=render.DAEV_FILE)] if png else []


def NO_DATA() -> str:
    return fala("sem_dados")


# ----------------------------------------------------------------- comandos
@bot.tree.command(name="build", description="Build completa recomendada (top da classe): equipamento, skills, Daevanion, stats")
@app_commands.describe(classe="Classe", modo="PvE ou PvP", regiao="Coreia, Global ou uma região")
@app_commands.autocomplete(classe=class_autocomplete)
@app_commands.choices(modo=MODE_CHOICES, regiao=SCOPE_CHOICES)
async def build_cmd(inter: discord.Interaction, classe: str, modo: app_commands.Choice[str],
                    regiao: app_commands.Choice[str] | None = None):
    scope = regiao.value if regiao else "global"
    meta = bot.get_meta(scope, classe, modo.value)
    if not meta:
        return await inter.response.send_message(NO_DATA(), ephemeral=True)
    await inter.response.send_message(fala("build", cls=render.class_label(classe), modo=modo.name),
                                      embed=render.summary_embed(meta), view=SectionView(meta, inter.user.id))


@bot.tree.command(name="comparar", description="Compara o meta coreano com o global para uma classe")
@app_commands.autocomplete(classe=class_autocomplete)
@app_commands.choices(modo=MODE_CHOICES)
async def compare_cmd(inter: discord.Interaction, classe: str, modo: app_commands.Choice[str]):
    kr = bot.get_meta("kr", classe, modo.value)
    gl = bot.get_meta("global", classe, modo.value)
    if not kr or not gl:
        return await inter.response.send_message(NO_DATA(), ephemeral=True)
    await inter.response.send_message(fala("comparar", cls=render.class_label(classe)), embed=render.compare_embed(classe, modo.value, kr, gl, compare(kr, gl)))


@bot.tree.command(name="classes", description="Classes ordenadas pelo poder médio dos tops")
@app_commands.choices(modo=MODE_CHOICES, regiao=SCOPE_CHOICES)
async def tier_cmd(inter: discord.Interaction, modo: app_commands.Choice[str], regiao: app_commands.Choice[str] | None = None):
    scope = regiao.value if regiao else "global"
    rows = [(c, m) for c in bot.collector.classes(scope) if (m := bot.get_meta(scope, c, modo.value))]
    if not rows:
        return await inter.response.send_message(NO_DATA(), ephemeral=True)
    rows.sort(key=lambda x: -x[1]["avg_cp"])
    await inter.response.send_message(fala("classes"), embed=render.tier_embed(scope, modo.value, rows))


@bot.tree.command(name="top", description="Lista os tops de uma classe")
@app_commands.autocomplete(classe=class_autocomplete)
@app_commands.choices(modo=MODE_CHOICES, regiao=SCOPE_CHOICES)
async def top_cmd(inter: discord.Interaction, classe: str, modo: app_commands.Choice[str],
                  regiao: app_commands.Choice[str] | None = None):
    from aion2.collector import scope_regions
    scope = regiao.value if regiao else "global"
    rows = bot.store.top(scope_regions(scope), classe, modo.value, 15)
    if not rows:
        return await inter.response.send_message(NO_DATA(), ephemeral=True)
    lines = []
    for i, r in enumerate(rows, 1):
        tag = " 🏆" if r["seeded"] else (f" #{r['pvp_rank']}" if r["pvp_rank"] else "")
        lines.append(f"`{i:>2}.` **{r['name']}**{tag} — {r['server_name']} ({r['region']}) • "
                     f"{(r['combat_power'] or 0):,} • iLv {r['item_level'] or '-'}")
    e = discord.Embed(title=f"Top {render.class_label(classe)} {render.MODE_PT[modo.value]} — {render.scope_label(scope)}",
                      description="\n".join(lines), color=render.CLASS_COLOR.get(classe, 0x7F8C8D))
    e.set_footer(text="🏆 = top do Abismo adicionado manualmente • use /jogador para ver a build de alguém")
    await inter.response.send_message(fala("top", cls=render.class_label(classe)), embed=e)


@bot.tree.command(name="jogador", description="Busca a build atual de qualquer personagem (consulta ao vivo)")
@app_commands.choices(regiao=REGION_CHOICES)
async def player_cmd(inter: discord.Interaction, nome: str, regiao: app_commands.Choice[str], servidor: str | None = None):
    await inter.response.defer()
    try:
        hit = await bot.api.find_character(regiao.value, nome, servidor)
        if not hit:
            return await inter.followup.send(fala("nao_achei", nome=nome, regiao=regiao.name))
        bot.store.upsert_search_hit(regiao.value, hit)
        build = await bot.collector.fetch_build(regiao.value, hit["characterId"], hit["serverId"], detailed=True)
        bot.store.commit()
    except ApiError as e:
        return await inter.followup.send(fala("erro_api", erro=str(e)[:150]))
    await inter.followup.send(fala("jogador", nome=build['profile']['characterName']),
                              embeds=render.player_embeds(build), files=await player_files(build))


abismo = app_commands.Group(name="abismo", description="Lista manual dos tops do Abismo (a NC não publica o ranking)",
                            default_permissions=discord.Permissions(manage_guild=True))


@abismo.command(name="adicionar", description="Marca um personagem como top do Abismo (vira referência pro meta PvP)")
@app_commands.choices(regiao=REGION_CHOICES)
async def abismo_add(inter: discord.Interaction, nome: str, regiao: app_commands.Choice[str], servidor: str | None = None):
    await inter.response.defer(ephemeral=True)
    try:
        hit = await bot.api.find_character(regiao.value, nome, servidor)
        if not hit:
            return await inter.followup.send(fala("nao_achei", nome=nome, regiao=regiao.name))
        bot.store.upsert_search_hit(regiao.value, hit)
        await bot.collector.fetch_build(regiao.value, hit["characterId"], hit["serverId"], detailed=True)
        bot.store.mark_seed(regiao.value, hit["characterId"])
    except ApiError as e:
        return await inter.followup.send(fala("erro_api", erro=str(e)[:150]))
    await inter.followup.send(fala("abismo_add", nome=hit["name"], servidor=hit["serverName"]))


@abismo.command(name="remover", description="Remove um personagem da lista de tops do Abismo")
@app_commands.choices(regiao=REGION_CHOICES)
async def abismo_rm(inter: discord.Interaction, nome: str, regiao: app_commands.Choice[str]):
    rows = [r for r in bot.store.find_by_name([regiao.value], nome) if r["seeded"]]
    for r in rows:
        bot.store.mark_seed(regiao.value, r["char_id"], False)
    await inter.response.send_message(fala("abismo_rm", n=len(rows)), ephemeral=True)


@abismo.command(name="lista", description="Mostra os tops do Abismo cadastrados")
async def abismo_list(inter: discord.Interaction):
    rows = bot.store.db.execute(
        "SELECT name, server_name, region, class, combat_power FROM characters WHERE seeded=1 ORDER BY class").fetchall()
    text = "\n".join(f"**{r['name']}** — {render.class_label(r['class'] or '?')} • {r['server_name']} ({r['region']}) "
                     f"• {(r['combat_power'] or 0):,}" for r in rows) or fala("abismo_vazio")
    await inter.response.send_message(render._clip(text, 1900), ephemeral=True)


bot.tree.add_command(abismo)


@bot.tree.command(name="canal", description="Define este canal para receber as mudanças do meta a cada hora")
@app_commands.default_permissions(manage_guild=True)
async def channel_cmd(inter: discord.Interaction, desativar: bool = False):
    bot.store.set_channel(inter.guild_id, None if desativar else inter.channel_id)
    await inter.response.send_message(fala("canal_off") if desativar else
                                      fala("canal_on", canal=inter.channel.mention), ephemeral=True)


@bot.tree.command(name="atualizar", description="Força um ciclo de coleta agora")
@app_commands.default_permissions(manage_guild=True)
async def update_cmd(inter: discord.Interaction):
    if bot.collector.running.locked():
        return await inter.response.send_message(fala("ja_atualizando"), ephemeral=True)
    await inter.response.send_message(fala("atualizando"), ephemeral=True)
    changes = await bot.collector.run_cycle(REGIONS)
    if changes:
        await bot.post_changes(changes)
    await inter.followup.send(fala("atualizado", n=len(changes)), ephemeral=True)


@bot.tree.command(name="status", description="Quantos personagens o bot já analisou e quando atualizou")
async def status_cmd(inter: discord.Interaction):
    lines = [fala("status")]
    for r in REGIONS:
        c = bot.store.count(r)
        lines.append(f"**{ALL_REGIONS[r]}** — {c['n'] or 0} no pool • {c['p'] or 0} perfis • "
                     f"{c['b'] or 0} builds • level máx {c['lv'] or '-'}")
    last = bot.collector.last_full_cycle()
    nxt = schedule.next_run(last)
    lines.append(f"\nÚltima coleta completa: {f'<t:{int(last)}:f>' if last else 'ainda nenhuma'}"
                 f"{' • **rodando agora**' if bot.collector.running.locked() else ''}")
    lines.append(f"Próxima: <t:{int(nxt.timestamp())}:f> (<t:{int(nxt.timestamp())}:R>) • {schedule.describe()}")
    if bot.collector.last_error:
        lines.append(f"Último erro: `{bot.collector.last_error[:200]}`")
    await inter.response.send_message("\n".join(lines), ephemeral=True)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Nyerk! Falta o DISCORD_TOKEN, nyang~ Coloque no .env (local) ou em Variables (Railway).")
    bot.run(TOKEN, log_handler=None)
