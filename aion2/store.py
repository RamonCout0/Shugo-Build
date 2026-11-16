"""Persistência em SQLite: pool de personagens, builds, snapshots do meta, seeds e config do Discord."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS characters (
    region TEXT NOT NULL,
    char_id TEXT NOT NULL,
    server_id INTEGER NOT NULL,
    server_name TEXT,
    name TEXT,
    pc_id INTEGER,
    class TEXT,
    level INTEGER,
    combat_power INTEGER,
    item_level INTEGER,
    pvp_rank INTEGER,          -- melhor posição em ranking PvP oficial (quando a NC liberar), menor = melhor
    pvp_titles INTEGER DEFAULT 0, -- nº de efeitos PvP nos títulos equipados
    pve_titles INTEGER DEFAULT 0,
    seeded INTEGER DEFAULT 0,  -- adicionado manualmente como top do Abismo
    profile_at REAL,
    build_at REAL,
    PRIMARY KEY (region, char_id)
);
CREATE INDEX IF NOT EXISTS idx_char_class ON characters(region, class, combat_power DESC);
CREATE TABLE IF NOT EXISTS builds (
    region TEXT NOT NULL,
    char_id TEXT NOT NULL,
    data TEXT NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (region, char_id)
);
CREATE TABLE IF NOT EXISTS meta_snapshots (
    scope TEXT NOT NULL,       -- 'kr', 'global', 'naw', ...
    class TEXT NOT NULL,
    mode TEXT NOT NULL,        -- 'pve' | 'pvp'
    ts REAL NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snap ON meta_snapshots(scope, class, mode, ts DESC);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS channels (guild_id INTEGER PRIMARY KEY, channel_id INTEGER NOT NULL);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    # ------------------------------------------------------------------- kv
    def get(self, k: str, default=None):
        row = self.db.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return json.loads(row["v"]) if row else default

    def set(self, k: str, v) -> None:
        self.db.execute("INSERT OR REPLACE INTO kv VALUES (?,?)", (k, json.dumps(v)))
        self.db.commit()

    # ----------------------------------------------------------- characters
    def upsert_search_hit(self, region: str, c: dict) -> None:
        self.db.execute(
            """INSERT INTO characters (region, char_id, server_id, server_name, name, pc_id, level)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(region, char_id) DO UPDATE SET
                 name=excluded.name, level=excluded.level, server_name=excluded.server_name""",
            (region, c["characterId"], c["serverId"], c.get("serverName"), c["name"], c.get("pcId"), c.get("level")),
        )

    def update_profile(self, region: str, char_id: str, **fields) -> None:
        fields["profile_at"] = time.time()
        cols = ", ".join(f"{k}=?" for k in fields)
        self.db.execute(f"UPDATE characters SET {cols} WHERE region=? AND char_id=?",
                        (*fields.values(), region, char_id))

    def mark_seed(self, region: str, char_id: str, seeded: bool = True) -> None:
        self.db.execute("UPDATE characters SET seeded=? WHERE region=? AND char_id=?", (int(seeded), region, char_id))
        self.db.commit()

    def commit(self) -> None:
        self.db.commit()

    def pc_class_map(self, region: str) -> dict[int, str]:
        rows = self.db.execute(
            "SELECT pc_id, class FROM characters WHERE region=? AND class IS NOT NULL AND pc_id IS NOT NULL GROUP BY pc_id",
            (region,),
        ).fetchall()
        return {r["pc_id"]: r["class"] for r in rows}

    def stale_profiles(self, region: str, min_level: int, max_age: float, limit: int) -> list[sqlite3.Row]:
        return self.db.execute(
            """SELECT * FROM characters WHERE region=? AND level>=? AND (profile_at IS NULL OR profile_at<?)
               ORDER BY seeded DESC, profile_at IS NOT NULL, combat_power DESC LIMIT ?""",
            (region, min_level, time.time() - max_age, limit),
        ).fetchall()

    def classes(self, regions: list[str]) -> list[str]:
        q = ",".join("?" * len(regions))
        return [r["class"] for r in self.db.execute(
            f"SELECT DISTINCT class FROM characters WHERE region IN ({q}) AND class IS NOT NULL ORDER BY class", regions)]

    def top(self, regions: list[str], cls: str, mode: str, limit: int, min_level: int = 0) -> list[sqlite3.Row]:
        q = ",".join("?" * len(regions))
        if mode == "pvp":
            # 1) ranking oficial PvP (se existir) 2) seeds manuais (top Abismo) 3) poder + títulos PvP
            order = ("pvp_rank IS NULL, pvp_rank ASC, seeded DESC, "
                     "combat_power * (1.0 + 0.04 * pvp_titles) DESC")
        else:
            order = "combat_power * (1.0 + 0.02 * pve_titles) DESC"
        return self.db.execute(
            f"""SELECT * FROM characters WHERE region IN ({q}) AND class=? AND combat_power IS NOT NULL
                AND level>=? ORDER BY {order} LIMIT ?""",
            (*regions, cls, min_level, limit),
        ).fetchall()

    def find_by_name(self, regions: list[str], name: str) -> list[sqlite3.Row]:
        q = ",".join("?" * len(regions))
        return self.db.execute(f"SELECT * FROM characters WHERE region IN ({q}) AND lower(name)=lower(?)",
                               (*regions, name)).fetchall()

    def count(self, region: str) -> dict:
        r = self.db.execute(
            "SELECT COUNT(*) n, SUM(combat_power IS NOT NULL) p, SUM(build_at IS NOT NULL) b, MAX(level) lv "
            "FROM characters WHERE region=?", (region,)).fetchone()
        return dict(r)

    # --------------------------------------------------------------- builds
    def save_build(self, region: str, char_id: str, data: dict) -> None:
        now = time.time()
        self.db.execute("INSERT OR REPLACE INTO builds VALUES (?,?,?,?)", (region, char_id, json.dumps(data), now))
        self.db.execute("UPDATE characters SET build_at=? WHERE region=? AND char_id=?", (now, region, char_id))

    def build(self, region: str, char_id: str) -> dict | None:
        row = self.db.execute("SELECT data FROM builds WHERE region=? AND char_id=?", (region, char_id)).fetchone()
        return json.loads(row["data"]) if row else None

    # ------------------------------------------------------------ snapshots
    def save_snapshot(self, scope: str, cls: str, mode: str, data: dict) -> None:
        self.db.execute("INSERT INTO meta_snapshots VALUES (?,?,?,?,?)", (scope, cls, mode, time.time(), json.dumps(data)))
        # mantém só os últimos 7 dias
        self.db.execute("DELETE FROM meta_snapshots WHERE ts<?", (time.time() - 7 * 86400,))
        self.db.commit()

    def last_snapshot(self, scope: str, cls: str, mode: str) -> dict | None:
        row = self.db.execute(
            "SELECT data FROM meta_snapshots WHERE scope=? AND class=? AND mode=? ORDER BY ts DESC LIMIT 1",
            (scope, cls, mode)).fetchone()
        return json.loads(row["data"]) if row else None

    # ------------------------------------------------------------- discord
    def set_channel(self, guild_id: int, channel_id: int | None) -> None:
        if channel_id is None:
            self.db.execute("DELETE FROM channels WHERE guild_id=?", (guild_id,))
        else:
            self.db.execute("INSERT OR REPLACE INTO channels VALUES (?,?)", (guild_id, channel_id))
        self.db.commit()

    def channels(self) -> list[int]:
        return [r["channel_id"] for r in self.db.execute("SELECT channel_id FROM channels")]
