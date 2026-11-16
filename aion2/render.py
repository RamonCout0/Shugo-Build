"""Montagem dos embeds do Discord."""
from __future__ import annotations

from datetime import datetime, timezone

import discord

from .api import ALL_REGIONS
from .meta import MAIN_STATS, SLOT_ORDER, SLOT_GROUP, fmt_fx

CLASS_PT = {
    "Brawler": "Lutador",
    "Gladiator": "Gladiador", "Templar": "Templário", "Assassin": "Assassino", "Ranger": "Ranger",
    "Sorcerer": "Feiticeiro", "Spiritmaster": "Spiritmaster", "Elementalist": "Spiritmaster",
    "Cleric": "Clérigo", "Chanter": "Chanter",
}
CLASS_COLOR = {
    "Gladiator": 0xC0392B, "Templar": 0x2980B9, "Assassin": 0x8E44AD, "Ranger": 0x27AE60,
    "Sorcerer": 0xE67E22, "Spiritmaster": 0x16A085, "Elementalist": 0x16A085, "Cleric": 0xF1C40F, "Chanter": 0xD35400,
}
SLOT_PT = {
    "MainHand": "Arma", "SubHand": "Mão secundária", "Helmet": "Elmo", "Shoulder": "Ombro", "Torso": "Peito",
    "Pants": "Calça", "Gloves": "Luvas", "Boots": "Botas", "Cape": "Capa", "Belt": "Cinto", "Necklace": "Colar",
    "Earring": "Brincos", "Ring": "Anéis", "Bracelet": "Braceletes", "Amulet": "Amuleto", "Pendant": "Pingente",
    "Brooch": "Broches", "Rune": "Runas", "Arcana": "Arcanas",
}
GRADE_ICON = {"Mythic": "🟥", "Legend": "🟧", "Legendary": "🟧", "Unique": "🟨", "Epic": "🟪", "Rare": "🟦",
              "Common": "⬜"}
DAEV_FILE = "daevanion.png"
CAT_PT = {"Passive": "(passiva)", "Active": "(ativa)", "Dp": "(estigma)"}
MODE_PT = {"pve": "PvE", "pvp": "PvP"}


def class_label(cls: str) -> str:
    pt = CLASS_PT.get(cls)
    return f"{pt} ({cls})" if pt and pt != cls else cls


def scope_label(scope: str) -> str:
    return "🇰🇷 Coreia" if scope == "kr" else ("🌎 Global" if scope == "global" else f"🌎 {ALL_REGIONS.get(scope, scope)}")


def _clip(text: str, limit: int = 1024) -> str:
    return text if len(text) <= limit else text[: limit - 2] + "…"


def _base(meta: dict, section: str) -> discord.Embed:
    cls = meta["class"]
    e = discord.Embed(
        title=f"{class_label(cls)} — {MODE_PT[meta['mode']]} — {scope_label(meta['scope'])}",
        description=section,
        color=CLASS_COLOR.get(cls, 0x7F8C8D),
        timestamp=datetime.fromtimestamp(meta["ts"], tz=timezone.utc),
    )
    e.set_footer(text=f"Base: top {meta['n']} • critério: {meta['pvp_source']} • Shugo Build • dados oficiais NC")
    return e


def summary_embed(meta: dict) -> discord.Embed:
    t = meta["top"]
    e = _base(meta, "**Resumo do meta** — o top 1 e o que a maioria dos tops usa")
    if t.get("profileImage"):
        e.set_thumbnail(url=t["profileImage"])
    e.add_field(name="👑 Top 1", value=(
        f"**{t['characterName']}** — {t['serverName']} ({ALL_REGIONS.get(t['region'], t['region'])})\n"
        f"Poder: **{(t['combatPower'] or 0):,}** • Item Lv **{t.get('item_level') or '-'}** • Lv {t['characterLevel']}"
    ), inline=False)
    e.add_field(name="📊 Média do top", value=f"Poder {meta['avg_cp']:,}\nItem Lv {meta['avg_ilvl']}", inline=True)
    if meta["wings"]:
        e.add_field(name="🪽 Asa", value="\n".join(f"{w} ({p}%)" for w, p in meta["wings"]), inline=True)
    act = (meta["skills"].get("Active") or [])[:8]
    if act:
        e.add_field(name="✨ Skills principais", value=_clip("\n".join(
            f"`{s['pct']:>3}%` {s['name']} (Lv {s['lv']:g})" for s in act)), inline=False)
    main = []
    for slot in ("MainHand", "SubHand", "Torso", "Necklace", "Earring", "Ring"):
        it = (meta["gear"].get(slot) or [None])[0]
        if it:
            main.append(f"**{SLOT_PT.get(slot, slot)}:** {GRADE_ICON.get(it['grade'], '')} {it['name']} "
                        f"+{it['enchant']:g} ({it['pct']}%)")
    if main:
        e.add_field(name="🛡️ Equipamento principal", value=_clip("\n".join(main)), inline=False)
    return e


def gear_embed(meta: dict) -> discord.Embed:
    e = _base(meta, "**Equipamento** — item mais usado em cada slot (`%` dos tops • encanto médio • exceed médio)")
    seen = []
    for slot in SLOT_ORDER:
        grp = SLOT_GROUP.get(slot, slot)
        if grp in seen or grp not in meta["gear"]:
            continue
        seen.append(grp)
        items = meta["gear"][grp]
        lim = 6 if grp == "Arcana" else 2
        val = "\n".join(f"{GRADE_ICON.get(i['grade'], '')} {i['name']} `+{i['enchant']:g}` "
                        f"{'`★' + format(i['exceed'], 'g') + '`' if i['exceed'] else ''} — {i['pct']}%"
                        for i in items[:lim])
        e.add_field(name=SLOT_PT.get(grp, grp), value=_clip(val), inline=grp != "Arcana")
        if len(e.fields) >= 22:
            break
    ni = meta.get("items_detailed_n") or 0
    if meta.get("stones"):
        e.add_field(name=f"💠 Manastones mais usadas (top {ni})", value=_clip("\n".join(
            f"**{st['name']}** — {st['per_char']:g} por personagem"
            + (f" • média +{st['avg']:g}" if st["avg"] is not None else "")
            for st in meta["stones"])), inline=False)
    if meta.get("theostones"):
        e.add_field(name="🔥 Theostone (arma)", value=_clip("\n".join(
            f"`{g['pct']:>3}%` **{g['name']}** — {g['desc']}" for g in meta["theostones"])), inline=False)
    return e


def skills_embed(meta: dict) -> discord.Embed:
    e = _base(meta, "**Skills** — `%` dos tops que usam • nível médio")
    names = {"Active": "⚔️ Ativas (na barra)", "Dp": "🔮 Estigmas", "Passive": "🔹 Passivas"}
    for cat in ("Active", "Dp", "Passive"):
        sk = meta["skills"].get(cat)
        if sk:
            e.add_field(name=names[cat], value=_clip("\n".join(
                f"`{s['pct']:>3}%` {s['name']} — Lv {s['lv']:g}" for s in sk)), inline=False)
    tb = meta["top_build"]
    top_sk = sorted((s for s in tb["skills"] if s["equip"] and s["cat"] == "Active"), key=lambda s: -s["lv"])
    if top_sk:
        e.add_field(name=f"👑 Barra do top 1 ({tb['profile']['characterName']})", value=_clip(", ".join(
            f"{s['name']} {s['lv']}" for s in top_sk)), inline=False)
    if meta.get("gems"):
        e.add_field(name=f"💎 Gemas de habilidade nos equipamentos (Soul Binding) — média dos top {meta['items_detailed_n']}",
                    value=_clip("\n".join(f"**{g['name']}** +{g['avg']:g} {CAT_PT.get(g['cat'], '')}"
                                          for g in meta["gems"])), inline=False)
    return e


def daevanion_embed(meta: dict) -> discord.Embed:
    d = meta["daevanion"]
    e = _base(meta, f"**Daevanion** — progresso médio dos tabuleiros e efeitos mais escolhidos "
                    f"(detalhado nos top {d['detailed_n']})")
    if d.get("grids"):
        e.set_image(url=f"attachment://{DAEV_FILE}")  # a imagem dos tabuleiros é anexada pelo bot
    elif d["boards"]:
        e.add_field(name="🧩 Tabuleiros (% de nós abertos, média)", value=_clip("\n".join(
            f"**{b['name']}** {'▰' * (b['pct'] // 10)}{'▱' * (10 - b['pct'] // 10)} {b['pct']}%" for b in d["boards"])),
            inline=False)
    if d["skill_fx"]:
        e.add_field(name="✨ Níveis de skill ganhos (soma de todos os tabuleiros, média dos tops)", value=_clip("\n".join(
            fmt_fx(n, v) for n, v in d["skill_fx"])), inline=False)
    if d["stat_fx"]:
        e.add_field(name="📈 Atributos ganhos (média)", value=_clip("\n".join(
            fmt_fx(n, v) for n, v in d["stat_fx"])), inline=False)
    tb = meta["top_build"]["daevanion"]
    if tb["detailed"] and isinstance(tb["skill_fx"], dict) and tb["skill_fx"]:
        top_fx = sorted(tb["skill_fx"].items(), key=lambda x: -x[1])
        e.add_field(name=f"👑 Top 1 ({meta['top']['characterName']})", value=_clip(", ".join(
            fmt_fx(n, v) for n, v in top_fx)), inline=False)
    return e


def stats_embed(meta: dict) -> discord.Embed:
    e = _base(meta, "**Atributos e títulos** — média dos tops")
    st = meta["stats"]
    main = [f"**{st[k]['name']}**: {st[k]['avg']}" for k in MAIN_STATS if k in st]
    if main:
        e.add_field(name="Atributos base", value="\n".join(main), inline=True)
    gods = [f"**{v['name']}**: {v['avg']}" for k, v in st.items() if k not in MAIN_STATS and k != "ItemLevel"]
    if gods:
        e.add_field(name="Atributos divinos", value=_clip("\n".join(gods)), inline=True)
    if meta["titles"]:
        e.add_field(name="🏷️ Títulos equipados mais comuns", value=_clip("\n".join(
            f"`{p:>3}%` **{t}** — {', '.join(f for f in fx if f)}" for t, p, fx in meta["titles"])), inline=False)
    return e


SECTIONS = {
    "resumo": ("Resumo", summary_embed),
    "equip": ("Equipamento", gear_embed),
    "skills": ("Skills", skills_embed),
    "daevanion": ("Daevanion", daevanion_embed),
    "stats": ("Stats/Títulos", stats_embed),
}


def compare_embed(cls: str, mode: str, kr: dict, gl: dict, cmp: dict) -> discord.Embed:
    e = discord.Embed(title=f"🇰🇷 Coreia x 🌎 Global — {class_label(cls)} {MODE_PT[mode]}",
                      color=CLASS_COLOR.get(cls, 0x7F8C8D),
                      description="A Coreia está à frente em conteúdo; o que eles usam hoje tende a chegar no global.")
    e.add_field(name="Nível / poder / item lv (média do top)", value=(
        f"🇰🇷 Lv {cmp['lvl'][0] or '-'} • {cmp['cp'][0]:,} • iLv {cmp['ilvl'][0]}\n"
        f"🌎 Lv {cmp['lvl'][1] or '-'} • {cmp['cp'][1]:,} • iLv {cmp['ilvl'][1]}"), inline=False)
    for key, label in (("top", "👑 Top 1"),):
        e.add_field(name=label, value=(
            f"🇰🇷 {kr['top']['characterName']} ({kr['top']['serverName']}) — {kr['top']['combatPower']:,}\n"
            f"🌎 {gl['top']['characterName']} ({gl['top']['serverName']}) — {gl['top']['combatPower']:,}"), inline=False)
    if cmp["skills_kr_only"]:
        e.add_field(name="⚔️ Skills que a Coreia usa e o global não", value=_clip("\n".join(
            f"{n} — 🇰🇷 {a}% x 🌎 {b}%" for n, a, b in cmp["skills_kr_only"])), inline=False)
    if cmp["skills_gl_only"]:
        e.add_field(name="⚔️ Skills mais usadas no global", value=_clip("\n".join(
            f"{n} — 🇰🇷 {a}% x 🌎 {b}%" for n, a, b in cmp["skills_gl_only"])), inline=False)
    if cmp["daev_kr_only"]:
        e.add_field(name="🧩 Daevanion: Coreia investe mais em", value=_clip("\n".join(
            f"{d} — 🇰🇷 +{a:g} x 🌎 +{b:g}" for d, a, b in cmp["daev_kr_only"])), inline=False)
    if cmp["daev_gl_only"]:
        e.add_field(name="🧩 Daevanion: global investe mais em", value=_clip("\n".join(
            f"{d} — 🇰🇷 +{a:g} x 🌎 +{b:g}" for d, a, b in cmp["daev_gl_only"])), inline=False)
    (wk, pk), (wg, pg) = cmp["wing"]
    e.add_field(name="🪽 Asa mais usada", value=f"🇰🇷 {wk} ({pk}%)\n🌎 {wg} ({pg}%)", inline=False)
    if not any(cmp[k] for k in ("skills_kr_only", "skills_gl_only", "daev_kr_only", "daev_gl_only")):
        e.add_field(name="Resultado", value="Skills e Daevanion praticamente iguais nos dois metas.", inline=False)
    e.set_footer(text="Equipamentos diferem naturalmente (a Coreia tem level e itens mais altos).")
    return e


def tier_embed(scope: str, mode: str, rows: list[tuple[str, dict]]) -> discord.Embed:
    e = discord.Embed(title=f"📊 Classes por poder do top — {MODE_PT[mode]} — {scope_label(scope)}", color=0x5865F2,
                      description="Média de poder de combate do top de cada classe (não é tier list de DPS).")
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (cls, m) in enumerate(rows):
        lines.append(f"{medals[i] if i < 3 else f'`{i + 1}.`'} **{class_label(cls)}** — média {m['avg_cp']:,} "
                     f"• top 1 {m['top']['characterName']} {m['top']['combatPower']:,}")
    e.add_field(name="Ranking", value=_clip("\n".join(lines) or "Sem dados ainda."), inline=False)
    return e


def player_embeds(build: dict) -> list[discord.Embed]:
    p = build["profile"]
    e = discord.Embed(title=f"{p['characterName']} — {class_label(p['className'])}",
                      description=f"{p['serverName']} • {p.get('raceName') or ''} • {ALL_REGIONS.get(build['region'])}\n"
                                  f"Lv {p['characterLevel']} • Poder **{(p['combatPower'] or 0):,}** • "
                                  f"Item Lv **{build['item_level']}**",
                      color=CLASS_COLOR.get(p["className"], 0x7F8C8D))
    if p.get("profileImage"):
        e.set_thumbnail(url=p["profileImage"])
    gear = "\n".join(f"**{SLOT_PT.get(SLOT_GROUP.get(g['slot'], g['slot']), g['slot'])}**: "
                     f"{GRADE_ICON.get(g['grade'], '')} {g['name']} +{g['enchant']}"
                     f"{' ★' + str(g['exceed']) if g['exceed'] else ''}"
                     for g in build["gear"] if not g["slot"].startswith("Arcana"))
    e.add_field(name="Equipamento", value=_clip(gear or "-"), inline=False)
    arc = ", ".join(g["name"] for g in build["gear"] if g["slot"].startswith("Arcana"))
    if arc:
        e.add_field(name="Arcanas", value=_clip(arc), inline=False)
    sk = sorted((s for s in build["skills"] if s["equip"] and s["cat"] in ("Active", "Dp")), key=lambda s: -s["lv"])
    e.add_field(name="Skills na barra", value=_clip(", ".join(f"{s['name']} {s['lv']}" for s in sk) or "-"), inline=False)
    gems: dict[str, int] = {}
    stones: dict[str, int] = {}
    for g in build["gear"]:
        for _sid, name, lv in g.get("sub_skills") or []:
            gems[name] = gems.get(name, 0) + (lv or 1)
        for name, _v, _gr in g.get("stones") or []:
            stones[name] = stones.get(name, 0) + 1
    if gems:
        e.add_field(name="💎 Gemas de habilidade (Soul Binding)", value=_clip(", ".join(
            f"{n} +{v}" for n, v in sorted(gems.items(), key=lambda x: -x[1]))), inline=False)
    if stones:
        e.add_field(name="💠 Manastones", value=_clip(", ".join(
            f"{n} ×{c}" for n, c in sorted(stones.items(), key=lambda x: -x[1]))), inline=False)
    theo = [x[0] for g in build["gear"] for x in g.get("god") or []]
    if theo:
        e.add_field(name="🔥 Theostone", value=_clip(", ".join(theo)), inline=False)
    d = build["daevanion"]
    e2 = discord.Embed(title=f"{p['characterName']} — Daevanion e títulos", color=e.color)
    if any(b.get("nodes") for b in d["boards"]):
        e2.set_image(url=f"attachment://{DAEV_FILE}")
    else:
        e2.add_field(name="Tabuleiros", value=_clip("\n".join(
            f"**{b['name']}** {b['open']}/{b['total']} ({b['pct']}%)" for b in d["boards"]) or "-"), inline=False)
    if d["skill_fx"]:
        e2.add_field(name="Bônus de skill", value=_clip(", ".join(
            fmt_fx(n, v) for n, v in sorted(d["skill_fx"].items(), key=lambda x: -x[1]))), inline=False)
    if d["stat_fx"]:
        e2.add_field(name="Bônus de atributo", value=_clip(", ".join(
            fmt_fx(n, v) for n, v in sorted(d["stat_fx"].items(), key=lambda x: -x[1]))), inline=False)
    if build["titles"]:
        e2.add_field(name="Títulos equipados", value=_clip("\n".join(
            f"**{t['name']}** — {', '.join(f for f in t['fx'] if f)}" for t in build["titles"])), inline=False)
    if build.get("wing"):
        e2.add_field(name="Asa / Pet", value=f"{build['wing']} +{build.get('wing_enchant') or 0} • {build.get('pet') or '-'}",
                     inline=False)
    return [e, e2]
