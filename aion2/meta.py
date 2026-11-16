"""Agregação das builds dos tops em um 'meta' por classe/modo, comparação KR x Global e detecção de mudanças."""
from __future__ import annotations

import re
from collections import Counter, defaultdict

PVP_RE = re.compile(r"\bpvp\b", re.I)
PVE_RE = re.compile(r"\bpve\b", re.I)
PVP_CONTENT_RE = re.compile(r"abyss|어비스|arena|투기|pvp|conquest|정복|battlefield|전장", re.I)

# ordem de exibição dos slots
SLOT_ORDER = ["MainHand", "SubHand", "Helmet", "Shoulder", "Torso", "Pants", "Gloves", "Boots", "Cape", "Belt",
              "Necklace", "Earring1", "Earring2", "Ring1", "Ring2", "Bracelet1", "Bracelet2", "Amulet", "Pendant",
              "Brooch1", "Brooch2", "Rune1", "Rune2"] + [f"Arcana{i}" for i in range(1, 11)]
# slots "pareados" são agregados juntos (ex.: os dois anéis)
SLOT_GROUP = {"Earring1": "Earring", "Earring2": "Earring", "Ring1": "Ring", "Ring2": "Ring",
              "Bracelet1": "Bracelet", "Bracelet2": "Bracelet", "Brooch1": "Brooch", "Brooch2": "Brooch",
              "Rune1": "Rune", "Rune2": "Rune", **{f"Arcana{i}": "Arcana" for i in range(1, 11)}}
MAIN_STATS = ["STR", "DEX", "INT", "CON", "AGI", "WIS"]


FX_RE = re.compile(r"^(.*?)\s*([+-]\d+(?:\.\d+)?)\s*(%?)\s*$")


def _split_fx(desc: str) -> tuple[str, float]:
    """'Shadow Fall +1' -> ('Shadow Fall', 1); 'Critical Damage Tolerance +20%' -> ('Critical Damage Tolerance %', 20)."""
    m = FX_RE.match(desc.strip())
    if not m:
        return desc.strip(), 0.0
    name = m.group(1).strip() + (" %" if m.group(3) else "")
    return name, float(m.group(2))


def fmt_fx(name: str, val: float) -> str:
    pct = name.endswith(" %")
    base = name[:-2] if pct else name
    return f"{base} +{val:g}{'%' if pct else ''}"


# --------------------------------------------------------------- por personagem
def title_focus(info: dict) -> tuple[int, int]:
    """Conta efeitos PvP/PvE nos títulos equipados."""
    pvp = pve = 0
    for t in (info.get("title") or {}).get("titleList") or []:
        for s in t.get("equipStatList") or []:
            d = s.get("desc") or ""
            pvp += bool(PVP_RE.search(d))
            pve += bool(PVE_RE.search(d))
    return pvp, pve


def best_pvp_rank(info: dict) -> int | None:
    ranks = []
    for r in (info.get("ranking") or {}).get("rankingList") or []:
        if r.get("rank") and PVP_CONTENT_RE.search(r.get("rankingContentsName") or ""):
            ranks.append(r["rank"])
    return min(ranks) if ranks else None


NODE_TYPE = {"Start": "S", "Stat": "T", "SkillLevel": "K"}


def daevanion_from_details(boards: list[dict], details: dict[int, dict]) -> dict:
    """Soma os efeitos e guarda a grade de nós de cada tabuleiro (pra desenhar a imagem).

    nodes de cada tabuleiro: [linha, coluna, tipo S/T/K, raridade, aberto 0/1, nome]
    """
    skill_fx: dict[str, float] = defaultdict(float)
    stat_fx: dict[str, float] = defaultdict(float)
    out_boards = []
    for b in boards:
        d = details.get(b["id"])
        b = {k: v for k, v in b.items() if k != "nodes"}
        if d:
            b["nodes"] = [[n["row"], n["col"], NODE_TYPE[n["type"]], n.get("grade") or "", int(n.get("open") or 0),
                           n.get("name") or ""]
                          for n in d.get("nodeList") or [] if n.get("type") in NODE_TYPE]
            for target, key in ((skill_fx, "openSkillEffectList"), (stat_fx, "openStatEffectList")):
                for e in d.get(key) or []:
                    name, val = _split_fx(e.get("desc") or "")
                    if name:
                        target[name] += val
        out_boards.append(b)
    return {"boards": out_boards, "skill_fx": skill_fx, "stat_fx": stat_fx, "detailed": bool(details)}


def has_nodes(build: dict | None) -> bool:
    return bool(build) and any(b.get("nodes") for b in build["daevanion"]["boards"])


def has_full_detail(build: dict | None) -> bool:
    """Build com tabuleiros nó a nó E detalhe dos itens (gemas/pedras)."""
    return has_nodes(build) and bool(build.get("items_detailed"))


# slots sem Soul Binding nem pedras: não vale gastar requisição
NO_DETAIL_SLOTS = {"Belt", "Rune1", "Rune2", "Amulet", "Pendant"}


def item_extras(d: dict) -> dict:
    """Do detalhe do item: gemas de habilidade (Soul Binding), Manastones e Theostone."""
    d = d.get("data", d) if isinstance(d, dict) else {}
    return {
        "sub_skills": [[s.get("id"), s.get("name"), s.get("level", 1)] for s in d.get("subSkills") or []],
        "stones": [[s.get("name"), s.get("value"), s.get("grade")] for s in d.get("magicStoneStat") or []],
        "god": [[s.get("name"), s.get("grade"), (s.get("desc") or "").split("\n")[0]] for s in d.get("godStoneStat") or []],
    }


def compact_build(region: str, info: dict, equip: dict, daev_details: dict[int, dict],
                  item_details: dict[str, dict] | None = None) -> dict:
    """Reduz as respostas da API ao que importa para a build."""
    p = info.get("profile") or {}
    stats = {s["type"]: {"name": s["name"], "value": s["value"]} for s in (info.get("stat") or {}).get("statList") or []}
    boards = [{"id": b["id"], "name": b["name"], "open": b.get("openNodeCount", 0),
               "total": b.get("totalNodeCount", 0), "pct": b.get("openPercent", 0)}
              for b in (info.get("daevanion") or {}).get("boardList") or []]
    daev = daevanion_from_details(boards, daev_details)
    eq = (equip.get("equipment") or {}).get("equipmentList") or []
    return {
        "region": region,
        "profile": {k: p.get(k) for k in ("characterId", "characterName", "className", "combatPower",
                                          "characterLevel", "serverId", "serverName", "raceName", "profileImage",
                                          "titleName")},
        "item_level": (stats.get("ItemLevel") or {}).get("value"),
        "stats": stats,
        "titles": [{"name": t["name"], "cat": t.get("equipCategory"),
                    "fx": [s.get("desc") for s in t.get("equipStatList") or []]}
                   for t in (info.get("title") or {}).get("titleList") or []],
        "ranking": (info.get("ranking") or {}).get("rankingList") or [],
        "daevanion": daev,
        "gear": [{"slot": e["slotPosName"], "id": e["id"], "name": e["name"], "grade": e.get("grade"),
                  "enchant": e.get("enchantLevel", 0), "exceed": e.get("exceedLevel", 0),
                  **(item_extras(item_details[e["slotPosName"]]) if item_details and e["slotPosName"] in item_details
                     else {})} for e in eq],
        "items_detailed": bool(item_details),
        "skills": [{"id": s["id"], "name": s["name"], "cat": s.get("category"), "equip": s.get("equip"),
                    "lv": s.get("skillLevel", 0)} for s in (equip.get("skill") or {}).get("skillList") or []
                   if s.get("acquired")],
        "wing": ((equip.get("petwing") or {}).get("wing") or {}).get("name"),
        "wing_enchant": ((equip.get("petwing") or {}).get("wing") or {}).get("enchantLevel"),
        "pet": ((equip.get("petwing") or {}).get("pet") or {}).get("name"),
    }


# ------------------------------------------------------------------ agregação
def _pct(n: int, total: int) -> int:
    return round(100 * n / total) if total else 0


def aggregate(builds: list[dict], mode: str, pvp_source: str) -> dict:
    """Combina N builds de tops em um meta. builds[0] deve ser o top 1."""
    n = len(builds)
    if not n:
        return {"n": 0}
    top = builds[0]

    # equipamento: item mais usado por grupo de slot
    gear_cnt: dict[str, Counter] = defaultdict(Counter)
    gear_info: dict[int, dict] = {}
    gear_ench: dict[int, list] = defaultdict(list)
    for b in builds:
        seen: set[tuple[str, int]] = set()
        for g in b["gear"]:
            grp = SLOT_GROUP.get(g["slot"], g["slot"])
            gear_info[g["id"]] = g
            gear_ench[g["id"]].append((g["enchant"], g["exceed"]))
            if (grp, g["id"]) not in seen:  # conta cada item uma vez por personagem (ex.: 2 anéis iguais)
                seen.add((grp, g["id"]))
                gear_cnt[grp][g["id"]] += 1
    gear = {}
    for grp, cnt in gear_cnt.items():
        gear[grp] = []
        for item_id, c in cnt.most_common(3 if grp != "Arcana" else 10):
            e = gear_ench[item_id]
            gear[grp].append({"id": item_id, "name": gear_info[item_id]["name"], "grade": gear_info[item_id]["grade"],
                              "pct": _pct(c, n),
                              "enchant": round(sum(x[0] for x in e) / len(e), 1),
                              "exceed": round(sum(x[1] for x in e) / len(e), 1)})

    # skills: frequência e nível médio (ativas/DP só contam se estiverem na barra)
    sk_cnt: dict[str, Counter] = defaultdict(Counter)
    sk_lv: dict[int, list] = defaultdict(list)
    sk_name: dict[int, str] = {}
    for b in builds:
        for s in b["skills"]:
            if s["cat"] in ("Active", "Dp") and not s["equip"]:
                continue
            sk_cnt[s["cat"] or "?"][s["id"]] += 1
            sk_lv[s["id"]].append(s["lv"])
            sk_name[s["id"]] = s["name"]
    skills = {cat: [{"id": i, "name": sk_name[i], "pct": _pct(c, n),
                     "lv": round(sum(sk_lv[i]) / len(sk_lv[i]), 1)}
                    for i, c in cnt.most_common(14)]
              for cat, cnt in sk_cnt.items()}

    # daevanion
    board_pct: dict[str, list] = defaultdict(list)
    for b in builds:
        for bd in b["daevanion"]["boards"]:
            board_pct[bd["name"]].append(bd["pct"])
    detailed = [b for b in builds if b["daevanion"]["detailed"] and isinstance(b["daevanion"]["skill_fx"], dict)]

    def avg_fx(key: str, limit: int) -> list[tuple[str, float]]:
        tot: dict[str, float] = defaultdict(float)
        for b in detailed:
            for name, v in b["daevanion"][key].items():
                tot[name] += v
        avg = {k: round(v / len(detailed), 1) for k, v in tot.items()} if detailed else {}
        return sorted(avg.items(), key=lambda x: -x[1])[:limit]

    # mapa de calor dos tabuleiros: em cada nó, a fração dos tops (com detalhe) que abriu ele
    grid: dict[str, dict] = {}
    for b in builds:
        for bd in b["daevanion"]["boards"]:
            if not bd.get("nodes"):
                continue
            g = grid.setdefault(bd["name"], {"name": bd["name"], "n": 0, "cells": {}})
            g["n"] += 1
            for r, c, t, gr, op, *rest in bd["nodes"]:
                cell = g["cells"].setdefault((r, c), [r, c, t, gr, 0, rest[0] if rest else ""])
                cell[4] += op
    grids = [{"name": g["name"], "n": g["n"],
              "nodes": [[r, c, t, gr, round(op / g["n"], 2), nm] for r, c, t, gr, op, nm in g["cells"].values()]}
             for g in grid.values()]

    daev = {
        "boards": [{"name": k, "pct": round(sum(v) / len(v))} for k, v in board_pct.items()],
        "skill_fx": avg_fx("skill_fx", 20),   # bônus médio total de cada skill (somando todos os tabuleiros)
        "stat_fx": avg_fx("stat_fx", 15),
        "detailed_n": len(detailed),
        "grids": grids,
    }

    # gemas de habilidade (Soul Binding nos equipamentos), Manastones e Theostone — só tops com detalhe dos itens
    itemed = [b for b in builds if b.get("items_detailed")]
    gem_tot: dict[int, float] = defaultdict(float)
    gem_name: dict[int, str] = {}
    gem_cat = {s["id"]: s["cat"] for b in builds for s in b["skills"]}
    stone_cnt: Counter = Counter()
    stone_val: dict[str, list] = defaultdict(list)
    god_cnt: Counter = Counter()
    god_desc: dict[str, str] = {}
    for b in itemed:
        for g in b["gear"]:
            for sid, name, lv in g.get("sub_skills") or []:
                gem_tot[sid] += lv or 1
                gem_name[sid] = name
            for name, val, _grade in g.get("stones") or []:
                stone_cnt[name] += 1
                try:
                    stone_val[name].append(float(str(val).replace("+", "").replace("%", "")))
                except ValueError:
                    pass
            for name, _grade, desc in g.get("god") or []:
                god_cnt[name] += 1
                god_desc[name] = desc
    ni = len(itemed)
    gems = sorted(({"id": i, "name": gem_name[i], "cat": gem_cat.get(i, "?"), "avg": round(t / ni, 1)}
                   for i, t in gem_tot.items()), key=lambda x: -x["avg"])[:16] if ni else []
    stones = [{"name": s, "per_char": round(c / ni, 1),
               "avg": round(sum(stone_val[s]) / len(stone_val[s]), 1) if stone_val[s] else None}
              for s, c in stone_cnt.most_common(8)] if ni else []
    gods = [{"name": g, "pct": _pct(c, ni), "desc": god_desc[g]} for g, c in god_cnt.most_common(3)] if ni else []

    # stats médios
    stat_sum: dict[str, list] = defaultdict(list)
    stat_name = {}
    for b in builds:
        for k, v in b["stats"].items():
            stat_sum[k].append(v["value"])
            stat_name[k] = v["name"]
    stats = {k: {"name": stat_name[k], "avg": round(sum(v) / len(v))} for k, v in stat_sum.items()}

    titles = Counter(t["name"] for b in builds for t in b["titles"])
    title_fx = {t["name"]: t["fx"] for b in builds for t in b["titles"]}
    wings = Counter(b["wing"] for b in builds if b["wing"])

    return {
        "n": n, "mode": mode, "pvp_source": pvp_source,
        "avg_cp": round(sum(b["profile"]["combatPower"] or 0 for b in builds) / n),
        "avg_ilvl": round(sum(b["item_level"] or 0 for b in builds) / n),
        "top": {**top["profile"], "region": top["region"], "item_level": top["item_level"]},
        # sem a grade de nós (já está agregada em daevanion.grids): deixa o snapshot leve
        "top_build": {**top, "daevanion": {**top["daevanion"],
                                           "boards": [{k: v for k, v in bd.items() if k != "nodes"}
                                                      for bd in top["daevanion"]["boards"]]}},
        "gear": gear,
        "skills": skills,
        "daevanion": daev,
        "stats": stats,
        "titles": [(t, _pct(c, n), title_fx.get(t, [])) for t, c in titles.most_common(5)],
        "wings": [(w, _pct(c, n)) for w, c in wings.most_common(3)],
        "gems": gems, "stones": stones, "theostones": gods, "items_detailed_n": ni,
    }


# ---------------------------------------------------------------- comparações
def compare(kr: dict, gl: dict) -> dict:
    """Diferenças entre o meta coreano e o global (mesma classe/modo)."""
    out = {"cp": (kr.get("avg_cp", 0), gl.get("avg_cp", 0)),
           "ilvl": (kr.get("avg_ilvl", 0), gl.get("avg_ilvl", 0)),
           "lvl": ((kr.get("top") or {}).get("characterLevel"), (gl.get("top") or {}).get("characterLevel")),
           "skills_kr_only": [], "skills_gl_only": [], "daev_kr_only": [], "daev_gl_only": [],
           "wing": ((kr.get("wings") or [("-", 0)])[0], (gl.get("wings") or [("-", 0)])[0])}

    def skill_pct(meta):
        return {s["id"]: s for cat in ("Active", "Dp") for s in (meta.get("skills") or {}).get(cat, [])}

    ks, gs = skill_pct(kr), skill_pct(gl)
    for sid, s in ks.items():
        if s["pct"] >= 50 and gs.get(sid, {}).get("pct", 0) < s["pct"] - 30:
            out["skills_kr_only"].append((s["name"], s["pct"], gs.get(sid, {}).get("pct", 0)))
    for sid, s in gs.items():
        if s["pct"] >= 50 and ks.get(sid, {}).get("pct", 0) < s["pct"] - 30:
            out["skills_gl_only"].append((s["name"], ks.get(sid, {}).get("pct", 0), s["pct"]))

    # Daevanion: skills que um lado investe bem mais (diferença de bônus médio >= 1)
    kd = dict((kr.get("daevanion") or {}).get("skill_fx", []))
    gd = dict((gl.get("daevanion") or {}).get("skill_fx", []))
    out["daev_kr_only"] = sorted([(d, v, gd.get(d, 0)) for d, v in kd.items() if v - gd.get(d, 0) >= 1],
                                 key=lambda x: x[2] - x[1])[:6]
    out["daev_gl_only"] = sorted([(d, kd.get(d, 0), v) for d, v in gd.items() if v - kd.get(d, 0) >= 1],
                                 key=lambda x: x[1] - x[2])[:6]
    return out


def diff_snapshots(old: dict | None, new: dict) -> list[str]:
    """Mudanças relevantes entre dois snapshots do mesmo meta (para o aviso automático)."""
    if not old or not old.get("n") or not new.get("n"):
        return []
    lines = []
    ot, nt = old["top"], new["top"]
    if ot.get("characterId") != nt.get("characterId"):
        lines.append(f"👑 Novo top 1: **{nt['characterName']}** ({nt['serverName']}) "
                     f"— antes {ot['characterName']}")
    for slot in ("MainHand", "SubHand", "Torso", "Necklace", "Earring", "Ring"):
        o = (old["gear"].get(slot) or [{}])[0]
        n = (new["gear"].get(slot) or [{}])[0]
        if o.get("id") and n.get("id") and o["id"] != n["id"]:
            lines.append(f"🛡️ {slot}: **{n['name']}** ({n['pct']}%) passou {o['name']}")
    o_sk = {s["id"] for s in (old["skills"].get("Active") or [])[:10]}
    n_sk = {s["id"]: s for s in (new["skills"].get("Active") or [])[:10]}
    for sid, s in n_sk.items():
        if sid not in o_sk and s["pct"] >= 50:
            lines.append(f"✨ Skill subiu no meta: **{s['name']}** ({s['pct']}%)")
    if old.get("avg_cp") and abs(new["avg_cp"] - old["avg_cp"]) / old["avg_cp"] > 0.05:
        lines.append(f"📈 Poder médio do top: {old['avg_cp']:,} → {new['avg_cp']:,}")
    return lines
