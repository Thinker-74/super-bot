"""Broker Capital.com — API REST per forex/commodity/indici."""

import asyncio
import logging
import time
import httpx

from signal_parser import Signal
from brokers.common import SPLIT_WEIGHTS
import config
import db

log = logging.getLogger(__name__)

BASE_URL_DEMO = "https://demo-api-capital.backend-capital.com"
BASE_URL_LIVE = "https://api-capital.backend-capital.com"

# Fallback hardcoded, il DB ha priorità (tabella symbol_map)
_DEFAULT_SYMBOL_MAP = {
    "XAUUSD": "GOLD",
    "GOLD": "GOLD",
    "XAGUSD": "SILVER",
    "SILVER": "SILVER",
    "XAUEUR": "GOLD_EUR",
    "BTCUSD": "BTCUSD",
    "ETHUSD": "ETHUSD",
    "USOIL": "OIL_CRUDE",
    "WTIUSD": "OIL_CRUDE",
    # Forex major/minor — epic identico su Capital.com
    "EURUSD": "EURUSD",
    "GBPUSD": "GBPUSD",
    "USDJPY": "USDJPY",
    "USDCHF": "USDCHF",
    "AUDUSD": "AUDUSD",
    "NZDUSD": "NZDUSD",
    "USDCAD": "USDCAD",
    "EURGBP": "EURGBP",
    "EURJPY": "EURJPY",
    "GBPJPY": "GBPJPY",
    "EURCHF": "EURCHF",
    "GBPCHF": "GBPCHF",
    "GBPNZD": "GBPNZD",
    "GBPAUD": "GBPAUD",
    "GBPCAD": "GBPCAD",
    "EURAUD": "EURAUD",
    "EURNZD": "EURNZD",
    "EURCAD": "EURCAD",
    "AUDNZD": "AUDNZD",
    "AUDCAD": "AUDCAD",
    "AUDCHF": "AUDCHF",
    "AUDJPY": "AUDJPY",
    "CADJPY": "CADJPY",
    "CHFJPY": "CHFJPY",
    "NZDJPY": "NZDJPY",
    "NZDCAD": "NZDCAD",
    "NZDCHF": "NZDCHF",
}


# Minimum deal sizes per instrument type (Capital.com live)
_MIN_DEAL_SIZE = {
    "GOLD": 0.01,
    "SILVER": 1,
    "_forex_default": 100,
}


class CapitalBroker:

    def __init__(
        self,
        name: str = "capital",
        api_key: str = "",
        identifier: str = "",
        password: str = "",
        demo: bool = True,
    ):
        self.name = name
        self._api_key = api_key or config.CAPITAL_API_KEY
        self._identifier = identifier or config.CAPITAL_IDENTIFIER
        self._password = password or config.CAPITAL_PASSWORD
        self.base_url = BASE_URL_DEMO if demo else BASE_URL_LIVE
        self._session_token = ""
        self._cst = ""
        self._session_time = 0.0  # timestamp ultima autenticazione
        self._session_lock = asyncio.Lock()

    def _resolve_epic(self, symbol: str) -> tuple[str, bool]:
        """Converte simbolo segnale in epic Capital.com. Ritorna (epic, is_mapped)."""
        db_map = db.get_symbol_map("capital")
        if db_map and symbol in db_map:
            return db_map[symbol], True
        if symbol in _DEFAULT_SYMBOL_MAP:
            return _DEFAULT_SYMBOL_MAP[symbol], True
        # Fallback automatico: BTCUSDT → BTCUSD (toglie la T finale)
        if symbol.endswith("USDT"):
            return symbol[:-1], True
        # Nessuna traduzione trovata — potrebbe funzionare direttamente (forex)
        # ma potrebbe anche essere sbagliato
        return symbol, False

    async def _ensure_session(self):
        """Crea o rinnova sessione (scade dopo 10 min inattività)."""
        async with self._session_lock:
            if self._session_token and (time.time() - self._session_time) < 540:
                return  # sessione valida (refresh prima dei 10 min)
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.base_url}/api/v1/session",
                    json={
                        "identifier": self._identifier,
                        "password": self._password,
                    },
                    headers={"X-CAP-API-KEY": self._api_key},
                )
                resp.raise_for_status()
                self._session_token = resp.headers.get("X-SECURITY-TOKEN", "")
                self._cst = resp.headers.get("CST", "")
                self._session_time = time.time()
                log.info("Capital.com: sessione aperta")

    def _headers(self) -> dict:
        return {
            "X-SECURITY-TOKEN": self._session_token,
            "CST": self._cst,
            "X-CAP-API-KEY": self._api_key,
        }

    SPLIT_WEIGHTS = SPLIT_WEIGHTS

    async def get_current_price(self, symbol: str) -> tuple[float | None, float | None]:
        """Ritorna (bid, offer) per il simbolo. None se non disponibile."""
        await self._ensure_session()
        epic, _ = self._resolve_epic(symbol)
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self.base_url}/api/v1/markets/{epic}",
                    headers=self._headers(),
                )
                if resp.status_code == 200:
                    snap = resp.json().get("snapshot", resp.json())
                    return snap.get("bid"), snap.get("offer")
            except Exception as e:
                log.warning(f"Capital.com: get_current_price {epic} fallito: {e}")
        return None, None

    async def open_position(self, signal: Signal) -> dict:
        """Apre posizioni in base ai TP disponibili.

        - 0 TP: posizione singola senza take profit (solo SL se presente)
        - 1 TP: posizione singola con TP
        - 2 TP: split 50/50
        - 3 TP: split 60/20/20
        """
        await self._ensure_session()
        epic, is_mapped = self._resolve_epic(signal.symbol)

        if not is_mapped:
            db.add_alert(
                "symbol_unknown",
                f"Simbolo non configurato: {signal.symbol}",
                f"Segnale {signal.direction.value} {signal.symbol} ricevuto, "
                f"ma non esiste una traduzione per Capital.com. "
                f"Invio con epic '{epic}' (potrebbe fallire). "
                f"Configura la traduzione in Impostazioni > Simboli.",
            )
            log.warning(f"Capital.com: simbolo {signal.symbol} senza traduzione, uso '{epic}'")

        # Size: prima cerca per asset, poi fallback al default globale
        asset_size = db.get_asset_size(signal.symbol) or db.get_asset_size(epic)
        total_size = asset_size if asset_size else float(db.get_setting("default_size", "1"))
        tps = signal.take_profits or []

        # Costruisci lista posizioni in base al numero di TP
        positions_to_open = []
        if not tps:
            # Nessun TP: posizione singola, gestita manualmente o dal monitor
            positions_to_open = [{"tp": None, "size": total_size, "label": "single"}]
        else:
            n = min(len(tps), 3)
            weights = self.SPLIT_WEIGHTS.get(n, [1.0 / n] * n)
            for i in range(n):
                size = round(total_size * weights[i], 6)
                if size > 0:
                    positions_to_open.append({
                        "tp": tps[i],
                        "size": size,
                        "label": f"TP{i+1}" if n > 1 else "single",
                    })

        # Enforce minimum deal size per leg
        min_size = _MIN_DEAL_SIZE.get(epic, _MIN_DEAL_SIZE["_forex_default"])
        for pos in positions_to_open:
            if pos["size"] < min_size:
                log.warning(
                    f"Capital.com: {signal.symbol} {pos['label']} size {pos['size']} "
                    f"sotto minimo {min_size}, clamped a {min_size}"
                )
                pos["size"] = min_size

        results = []
        async with httpx.AsyncClient() as client:
            # Fetch prezzo corrente per validare TP prima dell'invio
            current_bid, current_offer = None, None
            try:
                mkt_resp = await client.get(
                    f"{self.base_url}/api/v1/markets/{epic}",
                    headers=self._headers(),
                )
                if mkt_resp.status_code == 200:
                    mkt_data = mkt_resp.json()
                    snap = mkt_data.get("snapshot", mkt_data)
                    current_bid = snap.get("bid")
                    current_offer = snap.get("offer")
                    log.info(f"Capital.com: {epic} bid={current_bid} offer={current_offer}")
            except Exception as e:
                log.warning(f"Capital.com: impossibile ottenere prezzo {epic}: {e}")

            for pos in positions_to_open:
                payload = {
                    "epic": epic,
                    "direction": signal.direction.value,
                    "size": pos["size"],
                }
                # Capital.com: livelli assoluti (non distanza) per TP/SL esatti
                if signal.stop_loss:
                    payload["stopLevel"] = signal.stop_loss
                if pos["tp"]:
                    # Valida TP rispetto al prezzo corrente
                    tp_valid = True
                    if current_offer is not None and signal.direction.value == "BUY":
                        if pos["tp"] <= current_offer:
                            tp_valid = False
                            log.warning(
                                f"Capital.com: {pos['label']} TP {pos['tp']} gia sotto "
                                f"offer {current_offer}, apro senza TP"
                            )
                    elif current_bid is not None and signal.direction.value == "SELL":
                        if pos["tp"] >= current_bid:
                            tp_valid = False
                            log.warning(
                                f"Capital.com: {pos['label']} TP {pos['tp']} gia sopra "
                                f"bid {current_bid}, apro senza TP"
                            )
                    if tp_valid:
                        payload["profitLevel"] = pos["tp"]

                try:
                    resp = await client.post(
                        f"{self.base_url}/api/v1/positions",
                        json=payload,
                        headers=self._headers(),
                    )
                    if resp.status_code != 200:
                        error_msg = resp.json().get("errorCode", resp.text[:200])
                        db.add_alert(
                            "trade_failed",
                            f"Apertura fallita: {signal.direction.value} {signal.symbol} {pos['label']}",
                            f"Epic: {epic}, Size: {pos['size']}, Errore: {error_msg}",
                        )
                        log.error(f"Capital.com: errore {pos['label']}: {error_msg}")
                        continue

                    data = resp.json()
                    deal_ref = data.get("dealReference", "")

                    confirm = await self._confirm_deal(client, deal_ref)
                    deal_id = ""
                    if confirm and confirm.get("affectedDeals"):
                        deal_id = confirm["affectedDeals"][0].get("dealId", "")

                    log.info(f"Capital.com: {pos['label']} aperta {epic} {signal.direction.value} "
                             f"size={pos['size']} TP={pos['tp']} deal_id={deal_id}")
                    results.append({
                        "deal_ref": deal_ref,
                        "deal_id": deal_id,
                        "epic": epic,
                        "label": pos["label"],
                        "size": pos["size"],
                        "tp": pos["tp"],
                    })
                except Exception as e:
                    log.error(f"Capital.com: eccezione {pos['label']}: {e}")

        if not results:
            raise Exception(f"Nessuna posizione aperta per {signal.symbol}")

        # Ritorna il primo risultato per compatibilita, ma salva tutti
        return {
            "deal_ref": results[0]["deal_ref"],
            "deal_id": results[0]["deal_id"],
            "epic": epic,
            "positions_opened": len(results),
            "all_deals": results,
        }

    async def _confirm_deal(self, client: httpx.AsyncClient, deal_ref: str) -> dict:
        """Verifica conferma apertura/chiusura posizione."""
        try:
            resp = await client.get(
                f"{self.base_url}/api/v1/confirms/{deal_ref}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            status = data.get("dealStatus", "")
            if status != "ACCEPTED":
                log.warning(f"Capital.com: deal {deal_ref} status={status}")
            return data
        except Exception as e:
            log.error(f"Capital.com: errore conferma deal {deal_ref}: {e}")
            return {}

    async def update_stop_loss(self, deal_id: str, new_stop_level: float) -> bool:
        """Aggiorna lo stop loss di una posizione aperta.

        Returns:
            True se aggiornato con successo.
        """
        await self._ensure_session()
        async with httpx.AsyncClient() as client:
            resp = await client.put(
                f"{self.base_url}/api/v1/positions/{deal_id}",
                json={
                    "stopLevel": new_stop_level,
                    "guaranteedStop": False,
                    "trailingStop": False,
                },
                headers=self._headers(),
            )
            if resp.status_code != 200:
                error_msg = resp.json().get("errorCode", resp.text[:200])
                log.error(f"Capital.com: errore update SL {deal_id}: {error_msg}")
                return False

            log.info(f"Capital.com: SL aggiornato {deal_id} → {new_stop_level}")
            return True

    async def close_position(self, symbol: str, position_id: str) -> dict:
        await self._ensure_session()
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{self.base_url}/api/v1/positions/{position_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            deal_ref = data.get("dealReference", "")
            log.info(f"Capital.com: posizione chiusa {position_id}")
            return {"closed": position_id, "deal_ref": deal_ref}

    async def get_positions(self) -> list[dict]:
        """Ritorna posizioni aperte con P&L, prezzo corrente, entry."""
        await self._ensure_session()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/positions",
                headers=self._headers(),
            )
            resp.raise_for_status()
            positions = resp.json().get("positions", [])
            return [
                {
                    "id": p["position"]["dealId"],
                    "deal_ref": p["position"].get("dealReference", ""),
                    "symbol": p["market"]["epic"],
                    "instrument_name": p["market"]["instrumentName"],
                    "direction": p["position"]["direction"],
                    "size": p["position"]["size"],
                    "entry_price": p["position"]["level"],
                    "current_bid": p["market"]["bid"],
                    "current_offer": p["market"]["offer"],
                    "pnl": p["position"]["upl"],
                    "stop_level": p["position"].get("stopLevel"),
                    "profit_level": p["position"].get("profitLevel"),
                    "currency": p["position"].get("currency", "USD"),
                    "created": p["position"].get("createdDateUTC", ""),
                    "leverage": p["position"].get("leverage", 1),
                }
                for p in positions
            ]

    async def get_account(self) -> dict:
        """Ritorna bilancio e stato account."""
        await self._ensure_session()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/accounts",
                headers=self._headers(),
            )
            resp.raise_for_status()
            accounts = resp.json().get("accounts", [])
            if not accounts:
                return {}
            acc = accounts[0]
            bal = acc.get("balance", {})
            return {
                "account_id": acc.get("accountId", ""),
                "account_type": acc.get("accountType", ""),
                "currency": acc.get("currency", ""),
                "balance": bal.get("balance", 0),
                "deposit": bal.get("deposit", 0),
                "pnl": bal.get("profitLoss", 0),
                "available": bal.get("available", 0),
            }

    async def get_closed_pnl(self, deal_ids: set[str]) -> dict[str, float]:
        """Recupera P&L reale per trade chiusi dalle transazioni Capital.com.

        Returns: {deal_id: pnl_reale} per i deal trovati.
        """
        if not deal_ids:
            return {}
        await self._ensure_session()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.base_url}/api/v1/history/transactions",
                    params={"from": "2026-03-01T00:00:00"},
                    headers=self._headers(),
                    timeout=10,
                )
                if resp.status_code != 200:
                    log.warning(f"Capital.com: transactions API {resp.status_code}")
                    return {}
                txns = resp.json().get("transactions", [])
                result = {}
                for t in txns:
                    did = t.get("dealId", "")
                    if did in deal_ids and t.get("transactionType") == "TRADE":
                        try:
                            result[did] = float(t["size"])
                        except (ValueError, KeyError):
                            pass
                return result
        except Exception as e:
            log.warning(f"Capital.com: errore transactions API: {e}")
            return {}

    async def search_market(self, term: str) -> list[dict]:
        """Cerca strumenti sul mercato Capital.com."""
        await self._ensure_session()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/markets",
                params={"searchTerm": term},
                headers=self._headers(),
            )
            resp.raise_for_status()
            markets = resp.json().get("markets", [])
            return [
                {
                    "epic": m["epic"],
                    "name": m["instrumentName"],
                    "type": m["instrumentType"],
                    "status": m["marketStatus"],
                    "bid": m.get("bid"),
                    "offer": m.get("offer"),
                }
                for m in markets
            ]
