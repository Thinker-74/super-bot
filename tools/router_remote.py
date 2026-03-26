"""Signal Router — riceve segnali da qualsiasi sorgente e li instrada ai broker configurati."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

from signal_parser import Signal, TradeUpdate, UpdateAction
import db

log = logging.getLogger(__name__)

# Sorgenti drive-through: eseguono diretto senza risk check aggiuntivo
DRIVE_THROUGH_CHANNELS = {"3192001947"}  # SVETLI VIP — attendibile dopo fix parsing
# Canali che richiedono AI gate (shadow analysis sincrona) prima dell'apertura
AI_GATE_CHANNELS = {"1001435439141"}  # Nation Forex — filtrato dopo SIG#82 (-$88)


class BrokerClient(Protocol):
    """Interfaccia che ogni broker deve implementare."""

    name: str

    async def open_position(self, signal: Signal) -> dict: ...
    async def close_position(self, symbol: str, position_id: str) -> dict: ...
    async def get_positions(self) -> list[dict]: ...
    async def get_current_price(self, symbol: str) -> tuple[float | None, float | None]: ...


@dataclass
class RouteRule:
    """Regola di instradamento: quali simboli vanno a quale broker."""
    broker_name: str
    symbols: list[str]       # lista simboli, o ["*"] per tutti
    asset_class: str = ""    # "forex", "crypto", "commodity" — filtro opzionale
    source_filter: str = ""  # "telegram", "webhook", "" = qualsiasi sorgente


class SignalRouter:
    def __init__(self):
        self._brokers: dict[str, BrokerClient] = {}
        self._rules: list[RouteRule] = []

    def register_broker(self, broker: BrokerClient):
        self._brokers[broker.name] = broker
        log.info(f"Broker registrato: {broker.name}")

    def add_rule(self, rule: RouteRule):
        self._rules.append(rule)
        log.info(f"Regola: {rule.symbols} → {rule.broker_name}")

    def _resolve_brokers(self, signal: Signal) -> list[BrokerClient]:
        """Trova i broker a cui inviare il segnale in base alle regole."""
        targets = []
        for rule in self._rules:
            if rule.broker_name not in self._brokers:
                continue
            # Filtro per sorgente: se la regola ha source_filter, deve matchare
            if rule.source_filter and signal.source != rule.source_filter:
                continue
            if "*" in rule.symbols or signal.symbol in rule.symbols:
                targets.append(self._brokers[rule.broker_name])
        return targets

    def _is_drive_through(self, signal: Signal) -> bool:
        """Controlla se il segnale proviene da una sorgente drive-through."""
        if not signal.source_channel:
            return False
        # Match diretto su channel_id, gestendo prefisso Telegram -100
        sig_ch = signal.source_channel.lstrip("-")
        return any(sig_ch.endswith(ch) for ch in DRIVE_THROUGH_CHANNELS)

    def _is_ai_gated(self, signal: Signal) -> bool:
        """Controlla se il segnale deve passare dal gate AI prima dell'apertura."""
        if not signal.source_channel:
            return False
        sig_ch = signal.source_channel.lstrip("-")
        return any(sig_ch.endswith(ch) for ch in AI_GATE_CHANNELS)

    async def _ai_gate(self, signal: Signal, signal_id: int) -> tuple[bool, str]:
        """Gate AI pre-apertura: shadow analysis sincrona. Ritorna (ok, agreement)."""
        try:
            from strategy.shadow_analyzer import analyze_svetli_signal
            agreement = await analyze_svetli_signal(
                signal_id, signal.symbol, signal.direction.value)
            if agreement == "agree":
                log.info(f"AI GATE OK sig#{signal_id} {signal.symbol}: AI concorda")
                return True, agreement
            log.info(f"AI GATE BLOCCO sig#{signal_id} {signal.symbol}: AI={agreement}")
            db.add_alert(
                "ai_gate_block",
                f"AI ha bloccato {signal.direction.value} {signal.symbol}",
                f"sig#{signal_id} agreement={agreement} — trade NON aperto",
            )
            return False, agreement
        except Exception as e:
            log.error(f"AI gate errore sig#{signal_id}: {e}")
            db.add_alert(
                "ai_gate_error",
                f"AI gate fallito per {signal.symbol}",
                f"Errore: {e}. Trade bloccato per sicurezza.",
            )
            return False, "error"

    async def _range_check(self, signal: Signal, signal_id: int) -> bool:
        """Controlla se il prezzo corrente e dentro il range di ingresso.
        Ritorna True se OK (dentro range o nessun range), False se fuori range."""
        if signal.entry_low is None or signal.entry_high is None:
            return True

        targets = self._resolve_brokers(signal)
        if not targets:
            return True

        broker = targets[0]
        if not hasattr(broker, "get_current_price"):
            log.warning(f"Broker {broker.name} non supporta get_current_price, skip range check")
            return True

        bid, offer = await broker.get_current_price(signal.symbol)
        if bid is None or offer is None:
            log.warning(f"Range check: impossibile ottenere prezzo per {signal.symbol}, skip")
            return True

        from signal_parser import Direction
        current_price = offer if signal.direction == Direction.BUY else bid

        if current_price < signal.entry_low or current_price > signal.entry_high:
            log.info(
                f"RANGE CHECK BLOCCO sig#{signal_id} {signal.direction.value} {signal.symbol}: "
                f"prezzo={current_price} fuori range [{signal.entry_low}-{signal.entry_high}]"
            )
            db.add_alert(
                "range_check_block",
                f"Prezzo fuori range per {signal.direction.value} {signal.symbol}",
                f"sig#{signal_id} prezzo corrente={current_price}, "
                f"range ammesso=[{signal.entry_low}-{signal.entry_high}]. Trade NON aperto.",
            )
            return False

        log.info(
            f"Range check OK sig#{signal_id} {signal.symbol}: "
            f"prezzo={current_price} in [{signal.entry_low}-{signal.entry_high}]"
        )
        return True

    async def route(self, signal: Signal, signal_id: int = 0) -> list[dict]:
        """Instrada un segnale ai broker appropriati. Ritorna i risultati."""
        targets = self._resolve_brokers(signal)
        if not targets:
            log.warning(f"Nessun broker configurato per {signal.symbol}")
            return []

        # Risk check per segnali NON drive-through
        is_dt = self._is_drive_through(signal)
        if not is_dt and not signal.invalidated:
            try:
                from strategy.risk_check import check_all
                ok, violations = check_all(
                    signal.symbol,
                    signal.direction.value,
                    signal.stop_loss or 0,
                )
                if not ok:
                    log.info(f"Router BLOCCO {signal.symbol}: {violations}")
                    return [{"broker": "risk_check", "action": "blocked",
                             "violations": violations}]
            except Exception as e:
                log.error(f"Risk check errore nel router: {e}")
                db.add_alert(
                    "risk_check_error",
                    f"Risk check fallito per {signal.symbol}",
                    f"Errore: {e}. Trade bloccato per sicurezza.",
                )
                return [{"broker": "risk_check", "action": "blocked",
                         "violations": [f"risk check error: {e}"]}]

        # AI gate per canali Telegram — analisi sincrona PRIMA dell'apertura
        if self._is_ai_gated(signal) and not signal.invalidated and signal_id:
            ai_ok, agreement = await self._ai_gate(signal, signal_id)
            if not ai_ok:
                return [{"broker": "ai_gate", "action": "blocked",
                         "agreement": agreement}]

        # Range check: se il segnale ha entry_low/entry_high, verifica prezzo corrente
        if not signal.invalidated and signal.entry_low is not None:
            range_ok = await self._range_check(signal, signal_id)
            if not range_ok:
                return [{"broker": "range_check", "action": "blocked",
                         "entry_low": signal.entry_low, "entry_high": signal.entry_high}]

        results = []
        for broker in targets:
            try:
                if signal.invalidated:
                    # Chiudi posizioni aperte per questo simbolo
                    positions = await broker.get_positions()
                    for pos in positions:
                        if pos.get("symbol") == signal.symbol:
                            r = await broker.close_position(signal.symbol, pos["id"])
                            results.append({"broker": broker.name, "action": "close", **r})
                else:
                    r = await broker.open_position(signal)
                    # Salva tutti i trade nel DB (multi-posizione 60/20/20)
                    all_deals = r.get("all_deals", [])
                    if all_deals and signal_id:
                        for deal in all_deals:
                            db.log_trade(signal_id, broker.name,
                                         deal.get("deal_ref", ""),
                                         deal.get("deal_id", ""))
                    elif signal_id:
                        db.log_trade(signal_id, broker.name,
                                     r.get("deal_ref", ""),
                                     r.get("deal_id", ""))
                    results.append({"broker": broker.name, "action": "open", **r})
            except Exception as e:
                log.error(f"Errore {broker.name}: {e}")
                results.append({"broker": broker.name, "error": str(e)})

        # Shadow analysis in background per SVETLI (drive-through) — solo tracking
        if is_dt and not signal.invalidated and signal_id:
            try:
                from strategy.shadow_analyzer import analyze_svetli_signal
                asyncio.create_task(analyze_svetli_signal(
                    signal_id, signal.symbol, signal.direction.value))
                log.info(f"Shadow analysis avviata per sig#{signal_id} {signal.symbol}")
            except Exception as e:
                log.warning(f"Shadow analysis trigger error: {e}")

        return results

    async def apply_update(self, update: TradeUpdate) -> list[dict]:
        """Applica un update (TP hit, SL move) ai trade aperti del canale."""
        open_trades = db.get_open_trades_by_channel(update.source_channel)
        if not open_trades:
            log.debug(f"Update ignorato: nessun trade aperto per canale {update.source_channel}")
            return []

        results = []

        if update.action == UpdateAction.SL_TO_BE:
            # Sposta SL a breakeven su tutti i trade aperti del canale
            for trade in open_trades:
                entry = trade.get("entry_price") or trade.get("signal_entry")
                if not entry or not trade.get("deal_id"):
                    continue
                broker = self._brokers.get(trade.get("broker", ""))
                if not broker:
                    continue
                try:
                    ok = await broker.update_stop_loss(trade["deal_id"], entry)
                    if ok:
                        log.info(f"Update SVETLI: SL→BE {trade['deal_id']} SL={entry}")
                        results.append({"deal_id": trade["deal_id"], "action": "sl_to_be", "sl": entry})
                except Exception as e:
                    log.error(f"Update SL→BE fallito {trade['deal_id']}: {e}")

        elif update.action == UpdateAction.SL_TO_LEVEL and update.new_sl:
            for trade in open_trades:
                if not trade.get("deal_id"):
                    continue
                broker = self._brokers.get(trade.get("broker", ""))
                if not broker:
                    continue
                try:
                    ok = await broker.update_stop_loss(trade["deal_id"], update.new_sl)
                    if ok:
                        log.info(f"Update SVETLI: SL→{update.new_sl} {trade['deal_id']}")
                        results.append({"deal_id": trade["deal_id"], "action": "sl_to_level", "sl": update.new_sl})
                except Exception as e:
                    log.error(f"Update SL→{update.new_sl} fallito {trade['deal_id']}: {e}")

        elif update.action in (UpdateAction.TP_HIT, UpdateAction.SL_HIT):
            log.info(f"Update SVETLI: {update.action.value} TP{update.tp_level} (informativo)")
            results.append({"action": update.action.value, "tp_level": update.tp_level})

        return results
