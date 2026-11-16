"""Teste rápido sem Discord: roda um ciclo pequeno e imprime os embeds gerados."""
import asyncio, json, logging, sys
import aiohttp
from aion2.api import Aion2Api
from aion2.collector import Collector, Settings
from aion2.store import Store
from aion2.meta import compare
from aion2 import render

logging.basicConfig(level=logging.INFO)

async def main():
    regions = sys.argv[1:] or ["kr", "naw"]
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0 (shugo-build-bot)",
                                              "Referer": "https://aion2.plaync.com/"}) as s:
        col = Collector(Aion2Api(s, 0.3), Store("smoke.db"),
                        Settings(keywords_per_cycle=3, pages_per_keyword=2, profile_budget=60, top_n=5, detail_top=1))
        await col.run_cycle(regions)
        scope2 = "global" if any(r != "kr" for r in regions) else "kr"
        for scope in dict.fromkeys(["kr", scope2]):
            print(scope, "classes:", col.classes(scope))
        cls = next(c for c in col.classes("kr") if c in col.classes(scope2))
        for mode in ("pve", "pvp"):
            kr = col.compute_meta("kr", cls, mode); gl = col.compute_meta(scope2, cls, mode)
            for fn in render.SECTIONS.values():
                e = fn[1](kr)
                d = e.to_dict(); assert len(e) <= 6000, len(e)
                print("\n===", d["title"], "|", d["description"])
                for f in d.get("fields", []):
                    assert len(f["value"]) <= 1024
                    print(f"-- {f['name']}\n{f['value']}")
            c = render.compare_embed(cls, mode, kr, gl, compare(kr, gl)).to_dict()
            print("\n=== COMPARAR", json.dumps(c, ensure_ascii=False)[:1500])
        print("\nTIER:", render.tier_embed("kr", "pve", sorted(
            [(c, col.compute_meta("kr", c, "pve")) for c in col.classes("kr")], key=lambda x: -x[1]["avg_cp"])).to_dict()["fields"][0]["value"])

asyncio.run(main())
