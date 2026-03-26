# super-bot — CHANGELOG sessioni

## Sessione 2026-03-27 — Range check ingresso per segnali Svetli (V2 produzione)

### Problema
Segnali Svetli con range di ingresso (es. "Entry Point: 4399.0 / 4389.0") venivano mediati in un singolo entry_price e il trade aperto sempre, anche se il prezzo corrente era fuori dal range suggerito dall'analista.

### Soluzione
Implementata logica range check ispirata alla V1 (Marco), applicata alla V2 in produzione su ollasrv:

1. **signal_parser.py** — Aggiunti campi `entry_low` e `entry_high` al dataclass `Signal`. Il parser preserva gli estremi del range oltre alla media.
2. **brokers/capital.py** — Nuovo metodo `get_current_price(symbol)` → `(bid, offer)` via API Capital.com.
3. **router.py** — Nuovo gate `_range_check()`: confronta prezzo corrente (offer per BUY, bid per SELL) con `[entry_low, entry_high]`. Se fuori range → blocca + alert nel DB.

### Analisi storica
Su 71 segnali totali, 3 avevano range (di cui 1 spazzatura OCR). Risultati simulazione:
- SIG#81 SELL GOLD: prezzo 4440.83, range 4449-4459 → **BLOCCATO** (era fuori range)
- SIG#82 BUY GOLD: prezzo 4394.63, range 4389-4399 → Passa (dentro range)

### File modificati (su ollasrv, /home/michele/autotrade-v2/)
- `signal_parser.py` — dataclass Signal + parsing range
- `brokers/capital.py` — get_current_price()
- `router.py` — _range_check() + integrazione in route()

### Stato operativo
- Autotrade riavviato in tmux `trader`, attivo e in ascolto
- Range check attivo per tutti i segnali con entry range

---

## Sessione 2026-03-17 — Code review completa + fix 10 problemi (alta + media)

### Problemi affrontati
- IP Ollama hardcoded obsoleto (.65) in 5 file — connessioni fallite senza .env
- `claude.py` crash su `content[]` vuoto (IndexError non gestito in decide/generate)
- Streaming API bypassava retry e logging, errori mid-stream non gestiti
- `routing.yaml` puntava a modelli non installati su ollasrv (deepseek-r1, qwen2.5-coder:14b)
- `github.py` crash su commenti da utenti eliminati (`c.user` None)
- `_parse_decision` non validava che il mode scelto da Claude esistesse
- `Router` non validava YAML all'init (file vuoto o default_mode inesistente → crash criptico)
- Default mode hardcoded in `handler.py` e `_process_issue` — divergeva da routing.yaml
- Logica `list_models` duplicata tra CLI e API (parsing httpx identico in 2 posti)

### Soluzioni adottate
- Aggiornato IP fallback a .63 in main.py, app.py, ollama.py, .env.example, CLAUDE.md
- Aggiunta guardia `if not msg.content` in ClaudeAdapter.decide() e .generate()
- Streaming API riscritto: usa adapter.generate() (con retry) + log_request + error handling
- routing.yaml allineato: coding→qwen2.5-coder:7b, reasoning/docs→qwen3:8b
- Guard `c.user.login if c.user else "ghost"` in github.py
- `_parse_decision` accetta `valid_modes` e fa fallback se mode non esiste
- Router.__init__ valida chiavi YAML obbligatorie e coerenza default_mode
- Rimosso default "reasoning_light" da handler.py (ora stringa vuota, Router gestisce fallback)
- `_process_issue` usa `router.route(mode)` senza bypass hardcoded
- Estratto `OllamaAdapter.list_models()`, usato da CLI e API — eliminata duplicazione

### File modificati
- `src/superbot/main.py` — IP, _list_models refactored, _process_issue fix
- `src/superbot/api/app.py` — IP, streaming rewrite, list_models via adapter
- `src/superbot/adapters/claude.py` — guard content[], validazione mode
- `src/superbot/adapters/github.py` — guard c.user None
- `src/superbot/adapters/ollama.py` — nuovo list_models(), IP docstring
- `src/superbot/gateway/handler.py` — default mode → ""
- `src/superbot/router/router.py` — validazione YAML all'init
- `config/routing.yaml` — modelli allineati a ollasrv
- `.env.example` — IP aggiornato
- `CLAUDE.md` — IP aggiornato
- `tests/test_router.py`, `tests/test_api.py`, `tests/test_cli.py`, `tests/test_handler.py` — allineati

### Decisioni tecniche
- routing.yaml reasoning_light/heavy/docs tutti su qwen3:8b (unico modello general-purpose su ollasrv)
- handler.py non ha piu un default mode — unica fonte di verita: Router via routing.yaml
- Streaming API semplificato: perde streaming reale ma guadagna retry + logging + error handling

### Punti aperti
- Fix bassa priorita non applicati: inject_context ridondante, GitHubAdapter nel REPL, or None
- Gap test: _process_issue, _repl, streaming, state/logger non coperti
- Notifiche Telegram, AI Decisions dashboard, Review engine (da sessioni precedenti)

---

## Sessione 2026-03-16 (2) — Trading daemon operativo + Ollama integrato

### Problemi affrontati
- Dashboard monitor :9090 troppo dispersiva, font minuscoli, 1/3 schermo vuoto
- Claude Code su ollasrv bloccato al wizard di onboarding (mai completato)
- Ollama mai chiamato nel flusso: scoring_rules sentiment/onchain restituivano sempre 0
- data_completeness fermo all'85% (2 famiglie senza dati)
- qwen3:8b con /no_think restituiva risposta vuota (campo "thinking" invece di "response")
- Capital.com rifiutava ordini: usava stopLevel (livello assoluto) invece di stopDistance (distanza)
- CPU% nel monitor gonfiato: ps aux mostra media storica, non istantanea
- Daemon inesistente: nessun meccanismo per cicli automatici di analisi

### Soluzioni adottate
- Redesign dashboard monitor :9090 — layout compatto single-screen, font ingranditi (15px base)
- Link "Server Monitor" aggiunto nella nav di Autotrade :8080
- Fix CPU% nel monitor: da `ps aux` (media storica) a `top -bn2` (istantanea)
- Claude Code onboarding completato su ollasrv (OAuth login mvalenti@technet.it)
- Creato `strategy/ollama_screener.py` — chiama qwen3:8b per analisi sentiment/macro, qwen2.5-coder:7b per validazione JSON
- Integrato ollama_screener nel runner (Step 1.5 tra raccolta dati e confluence scoring)
- Aggiornato `scoring_rules.py` — score_sentiment e score_onchain usano dati LLM (peso 40% nel sotto-score)
- Fix qwen3 /no_think: il modello metteva risposta in campo "thinking" invece di "response"
- Creato `strategy/daemon.py` — loop continuo ogni N minuti, chiama runner + Claude per decisioni Layer 3
- Creato `strategy/cron_runner.sh` — approccio alternativo via cron (pronto, non attivato)
- Fix `brokers/capital.py` — da `stopLevel`/`profitLevel` a `stopDistance`/`profitDistance`
- Test end-to-end: daemon → Ollama (GPU) → webhook → Autotrade → Capital.com demo → posizione aperta e chiusa

### File modificati/deployati
- `tools/ollasrv-monitor.py` — redesign layout + font + CPU istantanea → deployato su ollasrv
- `strategy/ollama_screener.py` — NUOVO, deployato su ollasrv
- `strategy/runner.py` — aggiunto Step 1.5 (chiamata ollama_screener), deployato
- `strategy/scoring_rules.py` — integrazione LLM 40% in sentiment/onchain, deployato
- `strategy/daemon.py` — NUOVO, deployato su ollasrv
- `strategy/cron_runner.sh` — NUOVO, deployato su ollasrv
- `brokers/capital.py` — fix stopDistance/profitDistance, deployato su ollasrv
- `dashboard/templates/index.html` — aggiunto link "Server Monitor" nella nav, su ollasrv

### Decisioni tecniche
- Intervallo daemon: 3 minuti (non 4h — crypto 24/7, il mercato non aspetta)
- Ollama nel Layer 1 (Step 1.5): arricchisce famiglie sentiment/onchain con analisi qualitativa
- Peso LLM nel sotto-score: 40% LLM + 60% deterministico (non 100% LLM)
- Due approcci daemon: Python loop (A, stanotte) vs cron (B, domani) per confronto
- Claude Code su ollasrv: login OAuth (non API key), account mvalenti@technet.it

### Stato operativo attuale
- Daemon attivo in tmux `trader`, intervallo 3 min, dry-run
- Ollama funzionante: data_completeness 100% (tutte le famiglie hanno dati)
- Ciclo completo in ~29 secondi (di cui ~20s per 4 chiamate Ollama)
- Log: `logs/daemon/daemon_YYYYMMDD.log` + DB `autotrade.db` tabella `strategy_decisions`
- Monitor :9090 attivo in tmux `monitor`
- Cron alternativo pronto: `crontab /home/michele/cron-trading.txt`

### Punti aperti
- Notifiche Telegram non implementate
- Sezione "AI Decisions" nella dashboard :8080 non implementata
- Review engine (Layer 4) da implementare per aggiornamento pesi dopo 30+ decisioni
- ~~routing.yaml di superbot punta a modelli non presenti su ollasrv~~ → risolto in sessione 2026-03-17

---

## Sessione 2026-03-16 (1) — Ripristino infrastruttura ollasrv per Trading Ecosystem

### Problemi affrontati
- Server ollasrv cambiato IP (.65 → .63), Ollama e modelli rimossi
- Driver NVIDIA non installati, Ollama crashava, Node.js assente

### Soluzioni adottate
- NVIDIA 550, Ollama 0.18.0, Node.js 22, Claude Code 2.1.76
- Modelli qwen3:8b + qwen2.5-coder:7b scaricati e testati
- Dashboard monitor :9090 deployata

---

## Sessione 2026-03-05 — Orchestratore Claude (issue #10)
- Implementato ClaudeAdapter con decide() + generate()
- Modello routing: haiku (economico), generazione: sonnet
- 9 nuovi test, tutti verdi. Commit 02b53fd.

## Sessione 2026-03-04 — v1.0.0 completato
- Streaming, --list-models, FastAPI gateway, timeout fix
- Issues #1-#6 chiuse. 57 test verdi. CI verde.
- Commit 51cc0f5.
