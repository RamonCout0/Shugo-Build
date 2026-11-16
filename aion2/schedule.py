"""Agenda da coleta: domingo de madrugada, a cada N semanas (padrão: um domingo sim, outro não).

Configurável por variáveis de ambiente:
  UPDATE_TZ=America/Sao_Paulo   fuso usado pra "domingo de madrugada"
  UPDATE_WEEKDAY=6              0=segunda … 6=domingo
  UPDATE_HOUR=4                 hora local
  UPDATE_EVERY_WEEKS=2          1 = todo domingo, 2 = quinzenal
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo(os.getenv("UPDATE_TZ", "America/Sao_Paulo"))
WEEKDAY = int(os.getenv("UPDATE_WEEKDAY", "6"))
HOUR = int(os.getenv("UPDATE_HOUR", "4"))
EVERY_WEEKS = max(1, int(os.getenv("UPDATE_EVERY_WEEKS", "2")))

WEEKDAY_PT = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def next_run(last_run: float | None, now: datetime | None = None) -> datetime:
    """Próxima coleta: o próximo domingo HOUR:00 que esteja a pelo menos EVERY_WEEKS semanas da última."""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    cand = now.replace(hour=HOUR, minute=0, second=0, microsecond=0)
    cand += timedelta(days=(WEEKDAY - cand.weekday()) % 7)
    if cand <= now - timedelta(hours=6):  # já passou (com 6h de tolerância se o bot estava fora do ar)
        cand += timedelta(days=7)
    if last_run:
        last = datetime.fromtimestamp(last_run, TZ)
        # quinzenal = pula (EVERY_WEEKS - 1) domingos depois da última coleta.
        # Mínimo de (semanas-1)*7 + 1 dias: a coleta de dom 04:50 vale pro dom de 2 semanas depois,
        # e um seed gerado na segunda vale pro domingo de 13 dias depois (não o de 6).
        while cand - last < timedelta(weeks=EVERY_WEEKS - 1, days=1):
            cand += timedelta(days=7)
    return cand


def is_due(last_run: float | None, now: datetime | None = None) -> bool:
    now = (now or datetime.now(TZ)).astimezone(TZ)
    return now >= next_run(last_run, now)


def describe() -> str:
    freq = "todo" if EVERY_WEEKS == 1 else f"a cada {EVERY_WEEKS}"
    dia = WEEKDAY_PT[WEEKDAY]
    return f"{freq} {dia} às {HOUR:02d}:00 ({TZ.key})" if EVERY_WEEKS == 1 else \
        f"{dia} às {HOUR:02d}:00, {freq} semanas ({TZ.key})"
