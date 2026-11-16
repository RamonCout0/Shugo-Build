"""Cliente assíncrono para a API pública do Character Info oficial do AION 2 (plaync).

Endpoints descobertos no próprio site oficial (aion2.plaync.com/ko-kr/characters e /en-us/characters):
  - busca:       https://api-search.plaync.com/{aion2|aion2global}/search/v2/character
  - perfil:      https://aion2.plaync.com/api/character/info
  - equipamento: https://aion2.plaync.com/api/character/equipment   (inclui skills, asa e pet)
  - daevanion:   https://aion2.plaync.com/api/character/daevanion/detail
  - classes/pc:  https://aion2.plaync.com/en-us/api/gameinfo/{classes,pcdata}  (só global)

Não é uma API documentada: a NC pode mudar sem aviso. Tudo aqui passa por um limitador de taxa
para não sobrecarregar o site.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from urllib.parse import unquote

import aiohttp

log = logging.getLogger(__name__)

SEARCH_BASE = "https://api-search.plaync.com"
SITE_BASE = "https://aion2.plaync.com"

GLOBAL_REGIONS = {
    "naw": "América do Norte (Oeste)",
    "nae": "América do Norte (Leste)",
    "eu": "Europa",
    "la": "América do Sul",
    "as": "Ásia",
}
ALL_REGIONS = {"kr": "Coreia", **GLOBAL_REGIONS}


class ApiError(Exception):
    pass


@dataclass
class RateLimiter:
    min_interval: float = 0.35
    _last: float = 0.0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def wait(self) -> None:
        async with self._lock:
            delay = self._last + self.min_interval - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._last = time.monotonic()


class Aion2Api:
    def __init__(self, session: aiohttp.ClientSession, min_interval: float = 0.35):
        self.session = session
        self.limiter = RateLimiter(min_interval)

    # ------------------------------------------------------------------ http
    async def _get(self, url: str, params: dict, retries: int = 3) -> dict:
        params = {k: v for k, v in params.items() if v is not None}
        for attempt in range(retries):
            await self.limiter.wait()
            try:
                async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=25)) as r:
                    if r.status == 429 or r.status >= 500:
                        raise ApiError(f"HTTP {r.status}")
                    if r.status != 200:
                        text = await r.text()
                        raise ApiError(f"HTTP {r.status}: {text[:200]}")
                    ctype = r.headers.get("Content-Type", "")
                    if "json" not in ctype:
                        raise ApiError(f"resposta não-JSON de {url} (a NC pode ter mudado a API)")
                    return await r.json()
            except (aiohttp.ClientError, asyncio.TimeoutError, ApiError) as e:
                if attempt == retries - 1 or (isinstance(e, ApiError) and "HTTP 4" in str(e) and "429" not in str(e)):
                    raise ApiError(str(e)) from e
                await asyncio.sleep(2 * (attempt + 1))
        raise ApiError("falhou")

    # --------------------------------------------------------------- helpers
    @staticmethod
    def _svc(region: str) -> tuple[str, dict]:
        """Retorna (prefixo de busca, params extras de perfil) para a região."""
        if region == "kr":
            return "aion2", {"lang": "en"}  # lang=en devolve nomes em inglês até no servidor coreano
        if region not in GLOBAL_REGIONS:
            raise ValueError(f"região desconhecida: {region}")
        return "aion2global", {"lang": "en", "region": region}

    # ------------------------------------------------------------- endpoints
    async def search(self, region: str, keyword: str, page: int = 1, size: int = 40,
                     pc_ids: list[int] | None = None, server_id: int | None = None,
                     sort: str = "level") -> dict:
        prefix, _ = self._svc(region)
        params = {
            "keyword": keyword, "page": page, "size": size, "sort": sort,
            "pcId": ",".join(map(str, pc_ids)) if pc_ids else None,
            "serverId": server_id,
        }
        if region != "kr":
            params.update(region=region, localeInfo="en-US")
        data = await self._get(f"{SEARCH_BASE}/{prefix}/search/v2/character", params)
        for c in data.get("list", []):
            c["characterId"] = unquote(c["characterId"])
            c["name"] = c["name"].replace("<strong>", "").replace("</strong>", "")
        return data

    async def info(self, region: str, char_id: str, server_id: int) -> dict:
        _, extra = self._svc(region)
        return await self._get(f"{SITE_BASE}/api/character/info",
                               {**extra, "characterId": char_id, "serverId": server_id})

    async def equipment(self, region: str, char_id: str, server_id: int) -> dict:
        _, extra = self._svc(region)
        return await self._get(f"{SITE_BASE}/api/character/equipment",
                               {**extra, "characterId": char_id, "serverId": server_id})

    async def daevanion(self, region: str, char_id: str, server_id: int, board_id: int) -> dict:
        _, extra = self._svc(region)
        return await self._get(f"{SITE_BASE}/api/character/daevanion/detail",
                               {**extra, "characterId": char_id, "serverId": server_id, "boardId": board_id})

    async def item_detail(self, region: str, char_id: str, server_id: int, item: dict) -> dict:
        """Detalhe de um item equipado: Soul Binding (subStats/subSkills), Manastones e Theostone."""
        _, extra = self._svc(region)
        return await self._get(f"{SITE_BASE}/api/character/equipment/item", {
            **extra, "id": item["id"], "enchantLevel": item.get("enchantLevel", 0),
            "characterId": char_id, "serverId": server_id, "slotPos": item["slotPos"]})

    async def global_servers(self, region: str = "naw") -> list[dict]:
        data = await self._get(f"{SITE_BASE}/en-us/api/gameinfo/servers", {"lang": "en-US", "region": region})
        return data.get("serverList", [])

    async def find_character(self, region: str, name: str, server_name: str | None = None) -> dict | None:
        """Busca um personagem pelo nome exato (e servidor, opcional)."""
        data = await self.search(region, name, size=40)
        name_l = name.lower()
        for c in data.get("list", []):
            if c["name"].lower() == name_l and (not server_name or c["serverName"].lower() == server_name.lower()):
                return c
        return None
