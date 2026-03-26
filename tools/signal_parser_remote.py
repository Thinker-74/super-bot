"""Parser segnali di trading — logica portata da v1, ripulita e generalizzata."""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Direction(Enum):
    BUY = "BUY"
    SELL = "SELL"


class UpdateAction(Enum):
    SL_TO_BE = "sl_to_be"          # Sposta SL a breakeven
    SL_TO_LEVEL = "sl_to_level"    # Sposta SL a un livello specifico
    TP_HIT = "tp_hit"              # TP colpito (informativo)
    SL_HIT = "sl_hit"              # SL colpito (informativo)
    CLOSE_ALL = "close_all"        # Chiudi tutto


@dataclass
class TradeUpdate:
    action: UpdateAction
    tp_level: int = 0              # 1, 2, 3 per TP_HIT
    new_sl: Optional[float] = None # Livello SL specifico (per SL_TO_LEVEL)
    raw_text: str = ""
    source: str = ""
    source_channel: str = ""


@dataclass
class Signal:
    symbol: str
    direction: Direction
    entry_price: Optional[float] = None
    entry_low: Optional[float] = None   # Estremo basso del range (se presente)
    entry_high: Optional[float] = None  # Estremo alto del range (se presente)
    stop_loss: Optional[float] = None
    take_profits: list[float] = field(default_factory=list)
    raw_text: str = ""
    source: str = ""  # "telegram", "discord", "webhook"
    source_channel: str = ""
    invalidated: bool = False


def parse_signal(text: str) -> Optional[Signal]:
    """Parsa un messaggio di testo e restituisce un Signal se valido."""
    text = text.strip()
    if not text:
        return None

    # Controlla invalidazione
    invalidation_patterns = [
        r"(?i)\b(cancel|invalid|annull|chiud|close)\b",
    ]
    is_invalidation = any(re.search(p, text) for p in invalidation_patterns)

    # Direzione
    direction = None
    if re.search(r"(?i)\bbuy\b", text):
        direction = Direction.BUY
    elif re.search(r"(?i)\bsell\b", text):
        direction = Direction.SELL

    if direction is None and not is_invalidation:
        return None

    # Simbolo — cerca pattern tipo XAUUSD, EURUSD, BTCUSDT, etc.
    # Escludi parole comuni e spazzatura OCR che matchano [A-Z]{3,10}
    _EXCLUDED_WORDS = {
        "BUY", "SELL", "HOLD", "SL", "TP", "ENTRY", "PRICE", "STOP", "LOSS",
        "CANCEL", "CLOSE", "OPEN", "NOW", "HIT", "TARGET", "PROFIT", "TAKE",
        "IMAGE", "OCR", "VIP", "FREE", "JOIN", "HERE", "CLICK", "CLICCA",
        "QUI", "PER", "ACCEDERE", "SALA", "THE", "AND", "FOR", "WITH",
        "CHART", "TRADE", "HISTORY", "SETTINGS", "POSITIONS", "ORDERS",
        "DEALS", "DEPOSIT", "BALANCE", "SWAP", "COMMISSION",
    }
    # Simboli di trading validi noti
    _KNOWN_SYMBOLS = {
        "XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD",
        "AUDUSD", "NZDUSD", "EURCHF", "EURGBP", "EURJPY", "GBPJPY", "GBPCHF",
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT",
        "BTCUSD", "ETHUSD", "BNBUSD", "SOLUSD", "DOGEUSD", "XRPUSD",
        "GOLD", "SILVER", "OIL", "USOIL",
        "US500", "US100", "DE40",
    }
    symbol = ""
    for m in re.finditer(r"\b([A-Z]{3,10}(?:/[A-Z]{3,6})?(?:USDT?)?)\b", text):
        candidate = m.group(1)
        if candidate in _KNOWN_SYMBOLS:
            symbol = candidate
            break
    # Fallback: accetta candidati non in blacklist (per simboli nuovi non ancora in whitelist)
    if not symbol:
        for m in re.finditer(r"\b([A-Z]{3,10}(?:/[A-Z]{3,6})?(?:USDT?)?)\b", text):
            candidate = m.group(1)
            if candidate not in _EXCLUDED_WORDS:
                symbol = candidate
                break

    if not symbol and not is_invalidation:
        return None

    # Entry price — supporta "entry: 2650", "entry point: 5190 / 5195", "BUY XAUUSD 2650"
    # Per range (5190 / 5195), prende la media
    entry_price = None
    entry_low = None
    entry_high = None
    range_match = re.search(r"(?i)(?:entry|entr[iy])\s*(?:point)?\s*:?\s*([\d.]+)\s*/\s*([\d.]+)", text)
    if range_match:
        v1, v2 = float(range_match.group(1)), float(range_match.group(2))
        entry_low = min(v1, v2)
        entry_high = max(v1, v2)
        entry_price = round((v1 + v2) / 2, 6)
    else:
        entry_match = re.search(r"(?i)(?:entry|entr[iy]|@|price)\s*(?:point)?\s*:?\s*([\d.]+)", text)
        if not entry_match:
            entry_match = re.search(r"(?i)(?:BUY|SELL)\s+[A-Z]{3,10}\s+([\d.]+)", text)
        if not entry_match:
            entry_match = re.search(r"(?i)[A-Z]{3,10}\s+(?:BUY|SELL)\s+([\d.]+)", text)
        if entry_match:
            entry_price = float(entry_match.group(1))

    # Stop loss
    sl_match = re.search(r"(?i)(?:sl|stop\s*loss)\s*:?\s*([\d.]+)", text)
    stop_loss = float(sl_match.group(1)) if sl_match else None

    # Take profits (TP1, TP2, TP3, ...) — ignora "OPEN" e valori non numerici
    # Filtra valori implausibili: se entry_price noto, scarta TP troppo distanti (>50%)
    # o troppo piccoli (< 1% dell'entry). Altrimenti accetta tutti i valori > 0.
    tp_matches = re.findall(r"(?i)tp\s*\d*\s*:\s*([\d.]+)", text)
    take_profits = []
    for tp in tp_matches:
        val = float(tp)
        if val <= 0:
            continue
        if entry_price and entry_price > 0:
            ratio = val / entry_price
            if ratio < 0.5 or ratio > 2.0:
                continue
        take_profits.append(val)

    signal = Signal(
        symbol=symbol,
        direction=direction or Direction.BUY,
        entry_price=entry_price,
        entry_low=entry_low,
        entry_high=entry_high,
        stop_loss=stop_loss,
        take_profits=take_profits,
        raw_text=text,
        invalidated=is_invalidation,
    )
    return signal


def parse_update(text: str) -> Optional[TradeUpdate]:
    """Parsa un messaggio di update (TP hit, SL spostato, ecc.). Ritorna None se non riconosciuto."""
    text = text.strip()
    if not text:
        return None

    # TP hit: "TP1 ✅", "TP2 ✅", "TP3 ✅" (con o senza testo dopo)
    tp_match = re.search(r"(?i)\bTP\s*([123])\s*[✅✓☑]", text)
    if tp_match:
        tp_level = int(tp_match.group(1))
        # Controlla se c'e' istruzione SL a BE nello stesso messaggio
        has_be = bool(re.search(r"(?i)(SL\s*(a|to)\s*BE|breakeven|break\s*even|sposti?amo\s*SL)", text))
        if has_be:
            return TradeUpdate(
                action=UpdateAction.SL_TO_BE, tp_level=tp_level, raw_text=text)
        return TradeUpdate(
            action=UpdateAction.TP_HIT, tp_level=tp_level, raw_text=text)

    # SL hit: "SL ❌", "SL hit", "Stop loss colpito"
    if re.search(r"(?i)\bSL\s*[❌✗✘]|\bstop\s*loss\s*(hit|colpito|raggiunto)", text):
        return TradeUpdate(action=UpdateAction.SL_HIT, raw_text=text)

    # Spostamento SL esplicito con livello: "SL a 4555", "Sposta SL a 4555.50"
    # Richiede verbo d'azione oppure "SL a/to" — escluso "SL: valore" (definizione segnale)
    sl_move = re.search(r"(?i)(?:sposta|muovi|move|aggiorna)\s*SL\s*(?:a|to|@|:)\s*([\d.]+)", text)
    if not sl_move:
        sl_move = re.search(r"(?i)\bSL\s+(?:a|to)\s+([\d.]+)", text)
    if sl_move:
        new_sl = float(sl_move.group(1))
        return TradeUpdate(
            action=UpdateAction.SL_TO_LEVEL, new_sl=new_sl, raw_text=text)

    return None
