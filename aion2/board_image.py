"""Desenha os tabuleiros do Daevanion (grade 15x15) numa imagem PNG para o Discord.

Inspirado no visual do jogo, sem copiar: losangos = nós de habilidade (+1 skill), quadrados = atributos,
círculo = início. Nó aceso = aberto. No meta, o brilho é a % dos tops que abriram aquele nó.
"""
from __future__ import annotations

import io
import math

from PIL import Image, ImageDraw, ImageFont

S = 2            # supersampling (desenha em 2x e reduz = bordas suaves)
CELL = 21 * S    # tamanho de cada casa da grade
GRID = 15
PAD = 14 * S
HEAD = 34 * S    # espaço do título de cada tabuleiro
COLS = 3

BG = (17, 20, 28)
PANEL = (27, 31, 42)
PANEL_EDGE = (52, 58, 76)
TEXT = (232, 234, 240)
MUTED = (140, 148, 168)
LINK_OFF = (44, 49, 63)

# (tipo, raridade) -> cor
COLORS = {
    ("K", "Legend"): (255, 154, 60),    # habilidade lendária
    ("K", "Rare"): (74, 163, 255),      # habilidade
    ("K", "Unique"): (186, 104, 255),
    ("K", "Epic"): (186, 104, 255),
    ("T", "Unique"): (236, 198, 92),    # atributo raro
    ("T", "Legend"): (255, 154, 60),
    ("T", "Rare"): (110, 190, 255),
    ("T", "Common"): (139, 160, 184),   # atributo comum
    ("S", ""): (245, 245, 245),         # início
}


# fontes: latina (acentos, —, •) e coreana (nomes em Hangul). Docker instala DejaVu + Nanum; no Windows usa as do sistema.
LATIN_FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/segoeui.ttf",
               "C:/Windows/Fonts/arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"]
CJK_FONTS = ["/usr/share/fonts/truetype/nanum/NanumGothic.ttf", "C:/Windows/Fonts/malgun.ttf",
             "/System/Library/Fonts/AppleSDGothicNeo.ttc"]
_cache: dict[tuple, ImageFont.ImageFont] = {}


def _load(paths: list[str], size: int):
    key = (tuple(paths), size)
    if key not in _cache:
        for p in paths:
            try:
                _cache[key] = ImageFont.truetype(p, size * S)
                break
            except OSError:
                continue
        else:
            try:
                _cache[key] = ImageFont.load_default(size=size * S)
            except TypeError:
                _cache[key] = ImageFont.load_default()
    return _cache[key]


def _font(size: int):
    return _load(LATIN_FONTS, size)


def _is_cjk(ch: str) -> bool:
    o = ord(ch)
    return 0x1100 <= o <= 0x11FF or 0x3130 <= o <= 0x318F or 0xAC00 <= o <= 0xD7AF or 0x4E00 <= o <= 0x9FFF \
        or 0x3040 <= o <= 0x30FF


def _runs(text: str, size: int):
    """Quebra o texto em trechos latinos/coreanos, cada um com a fonte certa."""
    runs: list[tuple[str, object]] = []
    for ch in text:
        f = _load(CJK_FONTS, size) if _is_cjk(ch) else _font(size)
        if runs and runs[-1][1] is f:
            runs[-1] = (runs[-1][0] + ch, f)
        else:
            runs.append((ch, f))
    return runs


def _text(d: ImageDraw.ImageDraw, xy, text: str, size: int, fill) -> None:
    x, y = xy
    for chunk, f in _runs(text, size):
        d.text((x, y), chunk, font=f, fill=fill)
        x += d.textlength(chunk, font=f)


def _textlen(d: ImageDraw.ImageDraw, text: str, size: int) -> float:
    return sum(d.textlength(chunk, font=f) for chunk, f in _runs(text, size))


def _color(t: str, g: str) -> tuple[int, int, int]:
    return COLORS.get((t, g)) or COLORS.get((t, "Common")) or COLORS.get((t, "")) or (170, 170, 170)


def _mix(a, b, k: float):
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


def _shape(d: ImageDraw.ImageDraw, t: str, cx: float, cy: float, col, fill: float) -> None:
    """fill: 0 = fechado (só contorno), 1 = aberto (aceso), entre = mapa de calor."""
    dim = _mix(PANEL, col, 0.35)
    body = _mix(_mix(PANEL, col, 0.12), col, fill)
    outline = _mix(dim, (255, 255, 255), 0.35 * fill) if fill > 0 else dim
    if t == "K":  # losango (gema de habilidade)
        r = CELL * 0.46
        if fill > 0.5:  # brilho em volta dos nós de habilidade acesos
            g = r * 1.35
            d.polygon([(cx, cy - g), (cx + g, cy), (cx, cy + g), (cx - g, cy)], fill=_mix(PANEL, col, 0.25 * fill))
        d.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=body, outline=outline, width=S)
    elif t == "S":  # início
        r = CELL * 0.36
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col, outline=(255, 255, 255), width=S)
    else:  # atributo
        r = CELL * 0.30
        d.rounded_rectangle([cx - r, cy - r, cx + r, cy + r], radius=2 * S, fill=body, outline=outline, width=S)


def _board(d: ImageDraw.ImageDraw, x0: int, y0: int, board: dict) -> None:
    w = GRID * CELL + 2 * PAD
    h = HEAD + GRID * CELL + PAD
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=10 * S, fill=PANEL, outline=PANEL_EDGE, width=S)
    _text(d, (x0 + PAD, y0 + 10 * S), board["name"], 17, TEXT)
    if board.get("subtitle"):
        sub = board["subtitle"]
        tw = _textlen(d, sub, 13)
        _text(d, (x0 + w - PAD - tw, y0 + 13 * S), sub, 13, MUTED)

    cells = {(n[0], n[1]): n for n in board["nodes"]}
    gx, gy = x0 + PAD, y0 + HEAD

    def center(r, c):
        return gx + (c - 1) * CELL + CELL / 2, gy + (r - 1) * CELL + CELL / 2

    # ligações entre nós vizinhos (acesas quando os dois lados estão abertos)
    for (r, c), n in cells.items():
        for dr, dc in ((0, 1), (1, 0)):
            m = cells.get((r + dr, c + dc))
            if not m:
                continue
            k = min(n[4], m[4])
            col = _mix(LINK_OFF, _mix(_color(n[2], n[3]), _color(m[2], m[3]), 0.5), k * 0.8)
            (ax, ay), (bx, by) = center(r, c), center(r + dr, c + dc)
            d.line([(ax, ay), (bx, by)], fill=col, width=max(S, int(3 * S * (0.4 + 0.6 * k))))
    for (r, c), n in sorted(cells.items(), key=lambda kv: kv[1][2] == "K"):  # gemas por cima
        cx, cy = center(r, c)
        _shape(d, n[2], cx, cy, _color(n[2], n[3]), float(n[4]))


def _legend(d: ImageDraw.ImageDraw, x: int, y: int, heat: bool) -> None:
    items = [("K", "Legend", "Habilidade +1 (lendária)"), ("K", "Rare", "Habilidade +1"),
             ("T", "Unique", "Atributo raro"), ("T", "Common", "Atributo"), ("S", "", "Início")]
    for t, g, label in items:
        _shape(d, t, x + CELL / 2, y + CELL / 2, _color(t, g), 1.0)
        _text(d, (x + CELL + 6 * S, y + 3 * S), label, 13, TEXT)
        x += int(CELL + 14 * S + _textlen(d, label, 13))
    note = ("brilho = % dos tops que abriram o nó" if heat else "aceso = aberto • apagado = fechado")
    _text(d, (x + 10 * S, y + 3 * S), note, 13, MUTED)


def render_boards(boards: list[dict], title: str, heat: bool) -> bytes:
    """boards: [{"name", "subtitle", "nodes": [[linha, coluna, tipo, raridade, valor 0..1, nome], ...]}]"""
    boards = [b for b in boards if b.get("nodes")]
    if not boards:
        raise ValueError("sem tabuleiros com nós")
    cols = min(COLS, len(boards))
    rows = math.ceil(len(boards) / cols)
    bw = GRID * CELL + 2 * PAD
    bh = HEAD + GRID * CELL + PAD
    gap = 12 * S
    top = 46 * S
    legend_h = 40 * S
    W = PAD + cols * bw + (cols - 1) * gap + PAD
    H = top + rows * bh + (rows - 1) * gap + legend_h + PAD
    W = max(W, 1180 * S)  # cabe a legenda mesmo com poucos tabuleiros
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    _text(d, (PAD, 12 * S), title, 20, TEXT)
    for i, b in enumerate(boards):
        r, c = divmod(i, cols)
        _board(d, PAD + c * (bw + gap), top + r * (bh + gap), b)
    _legend(d, PAD, top + rows * bh + (rows - 1) * gap + 12 * S, heat)
    img = img.resize((W // S, H // S), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


# ----------------------------------------------------------------- atalhos
def meta_image(meta: dict) -> bytes | None:
    """Mapa de calor dos tops (meta da classe)."""
    grids = (meta.get("daevanion") or {}).get("grids") or []
    if not grids:
        return None
    pct = {b["name"]: b["pct"] for b in meta["daevanion"]["boards"]}
    boards = [{"name": g["name"], "nodes": g["nodes"],
               "subtitle": f"{pct.get(g['name'], 0)}% em média • {g['n']} tops"} for g in grids]
    from .render import MODE_PT, class_label, scope_label  # import tardio: evita ciclo
    title = (f"Daevanion — {class_label(meta['class'])} {MODE_PT[meta['mode']]} — "
             f"{scope_label(meta['scope']).split(' ', 1)[-1]}")
    return render_boards(boards, title, heat=True)


def build_image(build: dict) -> bytes | None:
    """Tabuleiros de um personagem (aberto/fechado)."""
    boards = [{"name": b["name"], "nodes": b["nodes"], "subtitle": f"{b['open']}/{b['total']} nós • {b['pct']}%"}
              for b in build["daevanion"]["boards"] if b.get("nodes")]
    if not boards:
        return None
    p = build["profile"]
    return render_boards(boards, f"Daevanion — {p['characterName']} ({p['serverName']})", heat=False)
