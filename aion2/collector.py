"""Ciclo de coleta: descobre personagens no level máximo, atualiza perfis, baixa builds dos tops e recalcula o meta.

Como a API oficial não tem endpoint de "listar ranking", a descoberta é feita varrendo a busca
oficial (ordenada por level) com várias palavras-chave em rodízio. A cada ciclo o pool cresce e os
tops são reavaliados pelo poder de combate.
"""
from __future__ import annotations

import asyncio
import logging
import string
import time
from dataclasses import dataclass

from .api import GLOBAL_REGIONS, Aion2Api, ApiError
from .meta import aggregate, best_pvp_rank, compact_build, diff_snapshots, title_focus
from .store import Store

log = logging.getLogger(__name__)

# sílabas comuns em nomes coreanos + letras/duplas latinas (nomes globais e coreanos com letras)
KR_KEYWORDS = list("가나다라마바사아자차카타파하루리미시니지키비디이소도로모보코토포호고우유주수무부구쿠후"
                   "은린란민진빈선연현원윤아별달빛검신천용") + list(string.ascii_lowercase)
GL_KEYWORDS = list(string.ascii_lowercase) + [a + b for a in "aeiou" for b in "lnrst"] + \
              ["ka", "ki", "ma", "mi", "ra", "ri", "sa", "da", "la", "na", "xx", "zz", "ya", "yu", "lu"]


@dataclass
class Settings:
    keywords_per_cycle: int = 8     # quantas palavras-chave por ciclo por região
    pages_per_keyword: int = 3      # páginas de 40 por palavra
    profile_budget: int = 220       # perfis (info) por ciclo por região
    profile_max_age: float = 12 * 3600
    top_n: int = 15                 # quantos tops por classe/modo entram na média do meta
    detail_top: int = 3             # quantos tops têm Daevanion detalhado (nó a nó)
    build_max_age: float = 50 * 60  # rebaixa a build dos tops a cada ~1h


def scope_regions(scope: str) -> list[str]:
    return list(GLOBAL_REGIONS) if scope == "global" else [scope]


class Collector:
    def __init__(self, api: Aion2Api, store: Store, settings: Settings | None = None):
        self.api = api
        self.store = store
        self.s = settings or Settings()
        self.running = asyncio.Lock()
        self.last_run: float | None = None
        self.last_error: str | None = None

    # ------------------------------------------------------------- descoberta
    async def discover(self, region: str) -> int:
        kws = KR_KEYWORDS if region == "kr" else GL_KEYWORDS
        cursor = self.store.get(f"cursor:{region}", 0)
        cap = self.store.get(f"cap:{region}", 0)
        found = 0
        for i in range(self.s.keywords_per_cycle):
            kw = kws[(cursor + i) % len(kws)]
            for page in range(1, self.s.pages_per_keyword + 1):
                try:
                    data = await self.api.search(region, kw, page=page, size=40)
                except ApiError as e:
                    log.warning("busca %s/%s falhou: %s", region, kw, e)
                    break
                hits = data.get("list") or []
                if not hits:
                    break
                cap = max(cap, max(h["level"] for h in hits))
                for h in hits:
                    if h["level"] >= cap - 1:
                        self.store.upsert_search_hit(region, h)
                        found += 1
                if hits[-1]["level"] < cap - 1:  # já saiu do level máximo
                    break
        self.store.set(f"cursor:{region}", (cursor + self.s.keywords_per_cycle) % len(kws))
        self.store.set(f"cap:{region}", cap)
        self.store.commit()
        return found

    # ---------------------------------------------------------------- perfis
    async def refresh_profiles(self, region: str, cache: dict) -> int:
        cap = self.store.get(f"cap:{region}", 0)
        rows = self.store.stale_profiles(region, max(cap - 1, 1), self.s.profile_max_age, self.s.profile_budget)
        done = 0
        for r in rows:
            try:
                info = await self.api.info(region, r["char_id"], r["server_id"])
            except ApiError as e:
                log.debug("info %s falhou: %s", r["name"], e)
                continue
            cache[(region, r["char_id"])] = info
            self._apply_profile(region, r["char_id"], info)
            done += 1
        self.store.commit()
        return done

    def _apply_profile(self, region: str, char_id: str, info: dict) -> None:
        p = info.get("profile") or {}
        ilvl = next((s["value"] for s in (info.get("stat") or {}).get("statList") or [] if s["type"] == "ItemLevel"), None)
        pvp, pve = title_focus(info)
        self.store.update_profile(region, char_id, **{
            "class": p.get("className"), "level": p.get("characterLevel"), "combat_power": p.get("combatPower"),
            "item_level": ilvl, "pvp_rank": best_pvp_rank(info), "pvp_titles": pvp, "pve_titles": pve,
            "name": p.get("characterName"), "pc_id": p.get("pcId"),
        })

    # ---------------------------------------------------------------- builds
    async def fetch_build(self, region: str, char_id: str, server_id: int, detailed: bool,
                          cache: dict | None = None) -> dict:
        info = (cache or {}).get((region, char_id)) or await self.api.info(region, char_id, server_id)
        self._apply_profile(region, char_id, info)
        equip = await self.api.equipment(region, char_id, server_id)
        details = {}
        if detailed:
            for b in (info.get("daevanion") or {}).get("boardList") or []:
                if b.get("open"):
                    try:
                        details[b["id"]] = await self.api.daevanion(region, char_id, server_id, b["id"])
                    except ApiError as e:
                        log.debug("daevanion %s/%s falhou: %s", char_id, b["id"], e)
        build = compact_build(region, info, equip, details)
        self.store.save_build(region, char_id, build)
        return build

    async def refresh_builds(self, region: str, cache: dict) -> int:
        cap = self.store.get(f"cap:{region}", 0)
        n = 0
        for cls in self.store.classes([region]):
            wanted: dict[str, tuple] = {}
            for mode in ("pve", "pvp"):
                for i, r in enumerate(self.store.top([region], cls, mode, self.s.top_n, cap - 1)):
                    detailed = i < self.s.detail_top
                    if r["char_id"] not in wanted or detailed:
                        wanted[r["char_id"]] = (r, detailed)
            for char_id, (r, detailed) in wanted.items():
                old = self.store.build(region, char_id)
                fresh = r["build_at"] and time.time() - r["build_at"] < self.s.build_max_age
                if fresh and (not detailed or (old and old["daevanion"]["detailed"])):
                    continue
                try:
                    await self.fetch_build(region, char_id, r["server_id"], detailed, cache)
                    n += 1
                except ApiError as e:
                    log.debug("build %s falhou: %s", r["name"], e)
            self.store.commit()
        return n

    # ------------------------------------------------------------------ meta
    def compute_meta(self, scope: str, cls: str, mode: str) -> dict:
        regions = scope_regions(scope)
        cap = max(self.store.get(f"cap:{r}", 0) for r in regions)
        rows = self.store.top(regions, cls, mode, self.s.top_n, cap - 1)
        builds = [b for r in rows if (b := self.store.build(r["region"], r["char_id"]))]
        if mode == "pvp":
            if rows and rows[0]["pvp_rank"]:
                src = "ranking PvP oficial"
            elif rows and rows[0]["seeded"]:
                src = "lista manual de tops do Abismo"
            else:
                src = "estimativa: poder de combate + títulos PvP (a NC não publica ranking do Abismo)"
        else:
            src = "poder de combate"
        meta = aggregate(builds, mode, src)
        meta["scope"] = scope
        meta["class"] = cls
        meta["ts"] = time.time()
        return meta

    def classes(self, scope: str) -> list[str]:
        return self.store.classes(scope_regions(scope))

    # ----------------------------------------------------------------- ciclo
    async def run_cycle(self, regions: list[str] | None = None) -> dict[str, list[str]]:
        """Roda um ciclo completo. Retorna {"scope|classe|modo": [mudanças]}."""
        regions = regions or ["kr", *GLOBAL_REGIONS]
        async with self.running:
            t0 = time.time()
            for region in regions:
                cache: dict = {}
                try:
                    d = await self.discover(region)
                    p = await self.refresh_profiles(region, cache)
                    b = await self.refresh_builds(region, cache)
                    log.info("[%s] descobertos=%d perfis=%d builds=%d", region, d, p, b)
                except Exception as e:  # um erro numa região não para as outras
                    log.exception("ciclo %s falhou", region)
                    self.last_error = f"{region}: {e}"
            changes: dict[str, list[str]] = {}
            for scope in ["kr", "global", *GLOBAL_REGIONS]:
                for cls in self.classes(scope):
                    for mode in ("pve", "pvp"):
                        meta = self.compute_meta(scope, cls, mode)
                        if not meta.get("n"):
                            continue
                        old = self.store.last_snapshot(scope, cls, mode)
                        diff = diff_snapshots(old, meta)
                        if diff and scope in ("kr", "global"):
                            changes[f"{scope}|{cls}|{mode}"] = diff
                        self.store.save_snapshot(scope, cls, mode, meta)
            self.last_run = time.time()
            log.info("ciclo completo em %.0fs", time.time() - t0)
            return changes
