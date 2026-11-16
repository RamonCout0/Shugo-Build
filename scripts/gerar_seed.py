"""Gera o banco pré-carregado (seed/aion2-seed.db.gz) que vai junto no repositório.

Assim o Shugo Build já liga com o meta pronto, em vez de passar ~1h coletando do zero.
Rode de vez em quando no seu PC e faça commit do arquivo gerado:

    python scripts/gerar_seed.py                 # 1 ciclo, todas as regiões
    python scripts/gerar_seed.py --ciclos 2      # pool maior (mais preciso, demora o dobro)
    python scripts/gerar_seed.py --regioes kr la naw
"""
from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import logging
import shutil
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import aiohttp  # noqa: E402

from aion2.api import ALL_REGIONS, Aion2Api  # noqa: E402
from aion2.collector import Collector, Settings  # noqa: E402
from aion2.store import Store  # noqa: E402

SEED_DIR = ROOT / "seed"
WORK_DB = SEED_DIR / "trabalho.db"      # ignorado pelo git (*.db)
SEED_GZ = SEED_DIR / "aion2-seed.db.gz"  # este vai pro repositório


async def main(ciclos: int, regioes: list[str], intervalo: float, completar: bool = False) -> None:
    SEED_DIR.mkdir(exist_ok=True)
    # continua de um seed anterior, se existir (o pool só cresce)
    if not WORK_DB.exists() and SEED_GZ.exists():
        with gzip.open(SEED_GZ, "rb") as src, open(WORK_DB, "wb") as dst:
            shutil.copyfileobj(src, dst)
    store = Store(WORK_DB)
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0 (shugo-build-bot)",
                                              "Referer": "https://aion2.plaync.com/"}) as s:
        col = Collector(Aion2Api(s, intervalo), store, Settings())
        if completar:
            t0 = time.time()
            logging.info("completando tabuleiros e gemas dos tops (sem refazer a coleta)…")
            await col.complete_details(regioes)
            logging.info("levou %.0f min", (time.time() - t0) / 60)
        for i in range(ciclos):
            t0 = time.time()
            logging.info("ciclo %d/%d…", i + 1, ciclos)
            await col.run_cycle(regioes)
            logging.info("ciclo %d levou %.0f min", i + 1, (time.time() - t0) / 60)
            # o bot no Railway conta a agenda (domingo quinzenal) a partir desta coleta
            store.set("last_full_cycle", time.time())
    store.db.close()

    db = sqlite3.connect(WORK_DB)
    # o seed só precisa do snapshot mais recente de cada meta
    db.execute("""DELETE FROM meta_snapshots WHERE rowid NOT IN (
                    SELECT MAX(rowid) FROM meta_snapshots GROUP BY scope, class, mode)""")
    db.execute("DELETE FROM channels")  # config do Discord não vai no seed
    # versão do seed: o bot troca o banco do volume quando recebe um seed mais novo (ver restore_seed)
    db.execute("INSERT OR REPLACE INTO kv VALUES ('seed_version', ?)", (json.dumps(time.time()),))
    db.commit()
    db.execute("VACUUM")
    db.close()
    with open(WORK_DB, "rb") as src, gzip.open(SEED_GZ, "wb", compresslevel=9) as dst:
        shutil.copyfileobj(src, dst)
    logging.info("seed salvo: %s (%.1f MB)", SEED_GZ, SEED_GZ.stat().st_size / 1e6)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ciclos", type=int, default=1)
    ap.add_argument("--regioes", nargs="+", default=list(ALL_REGIONS), choices=list(ALL_REGIONS))
    ap.add_argument("--intervalo", type=float, default=0.35, help="segundos entre requisições")
    ap.add_argument("--completar", action="store_true",
                    help="só completa tabuleiros/gemas dos tops do seed atual (use com --ciclos 0)")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(asctime)s %(message)s")
    asyncio.run(main(a.ciclos, a.regioes, a.intervalo, a.completar))
