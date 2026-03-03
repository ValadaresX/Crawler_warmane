# Plano de Refatoração: Concisão com Legibilidade

Objetivo: reduzir código grande/lento/manual/redundante para soluções menores, mais claras e idiomáticas. Sem code golf, sem abreviações obscuras. Preservar comportamento; melhorar performance onde fizer sentido.

**Codebase atual:** ~5800 linhas (Python 3117, Rust 1694, Shell 977)

---

## Fase A — Python: Crawler (`scripts/adaptive_graph_crawler.py`, 1787 linhas)

### A1. Extrair wrapper genérico para `net_*` (linhas 419-499)

`net_fetch_text`, `net_post_form_json` e `net_analyze_character` compartilham a mesma estrutura: medir tempo, chamar função, gravar sucesso/erro, re-raise.

**Antes (80 linhas, 3 funções quase idênticas):**
```python
def net_fetch_text(args, state, url, timeout_seconds, max_wall_seconds=None):
    t0 = time.perf_counter()
    try:
        # ... setup wall timeout ...
        out = fetch_text(url, ...)
        record_network_event(args, state, ok=True, elapsed_ms=...)
        return out
    except Exception as exc:
        log_min_error(args, state, scope="http_get", message=str(exc), extra={"url": url})
        record_network_event(args, state, ok=False, elapsed_ms=..., error_text=str(exc))
        raise
```

**Depois (~30 linhas, 1 context manager + 3 chamadas curtas):**
```python
@contextlib.contextmanager
def _tracked_request(args, state, scope, extra=None):
    t0 = time.perf_counter()
    try:
        yield
        record_network_event(args, state, ok=True, elapsed_ms=(time.perf_counter() - t0) * 1000)
    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000
        log_min_error(args, state, scope=scope, message=str(exc), extra=extra)
        err = str(exc)
        if scope != "analyze_character" or is_network_like_error(err):
            record_network_event(args, state, ok=False, elapsed_ms=elapsed, error_text=err)
        raise

def _resolve_wall(args, explicit):
    w = explicit if explicit is not None else float(args.request_wall_timeout_seconds)
    return w if w > 0 else None

def net_fetch_text(args, state, url, timeout_seconds, max_wall_seconds=None):
    with _tracked_request(args, state, "http_get", {"url": url}):
        return fetch_text(url, timeout_seconds=timeout_seconds, max_wall_seconds=_resolve_wall(args, max_wall_seconds))

def net_post_form_json(args, state, url, form_data, timeout_seconds, max_wall_seconds=None):
    with _tracked_request(args, state, "http_post", {"url": url}):
        return post_form_json(url, form_data, timeout_seconds=timeout_seconds, max_wall_seconds=_resolve_wall(args, max_wall_seconds))

def net_analyze_character(args, state, summary_url):
    with _tracked_request(args, state, "analyze_character", {"summary_url": summary_url}):
        return analyze_character(summary_url, cache_path=args.item_cache_dir)
```
**Redução:** ~50 linhas → ~30 linhas. Elimina 3 blocos try/except quase idênticos.

---

### A2. Cadeias `if "keyword" in msg` → lookup em set (linhas 293-325)

`is_network_like_error` e `is_block_signal` usam cadeias de `if ... return True`.

**Antes (33 linhas):**
```python
def is_network_like_error(error_text):
    msg = str(error_text or "").lower()
    if parse_http_status(msg) is not None:
        return True
    if "network error" in msg:
        return True
    if "timeout" in msg:
        return True
    # ... 5 mais
    return False
```

**Depois (12 linhas):**
```python
_NETWORK_KEYWORDS = {"network error", "timeout", "temporarily", "connection"}
_BLOCK_KEYWORDS = {"access denied", "captcha", "cloudflare", "/cdn-cgi/challenge-platform/", "just a moment", "enable javascript and cookies"}
_BLOCK_STATUS = {403, 429}

def is_network_like_error(error_text):
    msg = str(error_text or "").lower()
    return parse_http_status(msg) is not None or any(k in msg for k in _NETWORK_KEYWORDS)

def is_block_signal(error_text):
    msg = str(error_text or "").lower()
    return parse_http_status(msg) in _BLOCK_STATUS or any(k in msg for k in _BLOCK_KEYWORDS)
```
**Redução:** 33 → 12 linhas.

---

### A3. Contadores de classe unificados (linhas 672-732)

`class_counts`, `class_counts_discovered` e `class_backlog_unprocessed` compartilham o mesmo loop: iterar dict, classificar, contar.

**Antes (60 linhas, 3 funções):**
```python
def class_counts(processed_players, hp_min=None, hp_max=None):
    out = {k: 0 for k in CHARACTER_CLASSES}
    for row in processed_players.values():
        if not isinstance(row, dict): continue
        if hp_min is not None or hp_max is not None:
            if not hp_in_range(row.get("estimated_hp"), ...): continue
        c = norm_class(row.get("class"))
        if c: out[c] += 1
    return out
# + class_counts_discovered (idêntica com "class_hint_name")
# + class_backlog_unprocessed (idêntica com filtro de exclusão)
```

**Depois (~25 linhas, 1 função genérica):**
```python
def _count_by_class(items, class_key="class", exclude_keys=None, hp_filter=None):
    out = {k: 0 for k in CHARACTER_CLASSES}
    excl = exclude_keys or set()
    for key, row in (items.items() if isinstance(items, dict) else []):
        if not isinstance(row, dict) or key in excl:
            continue
        if hp_filter and not hp_in_range(row.get("estimated_hp"), *hp_filter):
            continue
        c = norm_class(row.get(class_key))
        if c:
            out[c] += 1
    return out

def class_counts(pp, hp_min=None, hp_max=None):
    return _count_by_class(pp, "class", hp_filter=(hp_min, hp_max) if hp_min is not None or hp_max is not None else None)

def class_counts_discovered(players):
    return _count_by_class(players, "class_hint_name")

def class_backlog_unprocessed(players, processed_players):
    return _count_by_class(players, "class_hint_name", exclude_keys=set(processed_players))
```
**Redução:** 60 → 25 linhas. Performance igual (único passo por dict).

---

### A4. Acúmulo de `cycle_metrics` com helper (linhas 1403-1447)

14 linhas fazendo `int(cycle_metrics["k"]) + int(root_stats.get("k", 0))` e 8 linhas copiando `int(profile_stats.get("k", 0))`.

**Antes (22 linhas):**
```python
cycle_metrics["history_pages_ok"] = int(cycle_metrics["history_pages_ok"]) + int(root_stats.get("pages_scanned", 0))
cycle_metrics["history_page_errors"] = int(cycle_metrics["history_page_errors"]) + int(root_stats.get("page_errors", 0))
# ... 5 mais idênticos
```

**Depois (12 linhas):**
```python
_HISTORY_METRIC_MAP = {
    "history_pages_ok": "pages_scanned",
    "history_page_errors": "page_errors",
    "history_matches_seen": "matches_seen",
    "history_new_match_ids": "new_match_ids",
    "history_details_target": "details_target",
    "history_details_done": "details_done",
    "history_detail_errors": "detail_errors",
}

def _accum_metrics(target, source, mapping):
    for tkey, skey in mapping.items():
        target[tkey] = int(target.get(tkey, 0)) + int(source.get(skey, 0))
```
**Redução:** 22 → 12 linhas.

---

### A5. Redundância `int(stats["key"]) + 1` no `collect_profiles` (linhas 1006-1130)

Os stats já são `int`, mas o código faz `int(stats["key"]) + 1` em ~10 lugares. Simplificar para `stats["key"] += 1`.

**Antes:**
```python
stats["skipped_failed_cooldown"] = int(stats["skipped_failed_cooldown"]) + 1
```
**Depois:**
```python
stats["skipped_failed_cooldown"] += 1
```
**Redução:** ~10 linhas ficam mais curtas (mesma contagem, menor ruído visual).

---

## Fase B — Rust: TUI (`tui_rs/src/`, 1694 linhas)

### B1. Extrair `count_or_len` para snapshot parsing (snapshot.rs linhas 82-117)

O bloco `players_total`, `dataset_total`, `failed_total` repete o mesmo padrão 3 vezes: "tenta valor direto, senão conta chaves do objeto".

**Antes (36 linhas):**
```rust
let players_total = {
    let direct = as_u64(state.get("players_total"));
    if direct > 0 { direct }
    else { state.get("players").and_then(Value::as_object).map(|m| m.len() as u64).unwrap_or(0) }
};
// repetido 3x
```

**Depois (12 linhas):**
```rust
fn count_or_len(state: &Value, count_key: &str, object_key: &str) -> u64 {
    let direct = as_u64(state.get(count_key));
    if direct > 0 { return direct; }
    state.get(object_key).and_then(Value::as_object).map(|m| m.len() as u64).unwrap_or(0)
}
// ...
let players_total = count_or_len(state, "players_total", "players");
let dataset_total = count_or_len(state, "dataset_total", "processed_players");
let failed_total = count_or_len(state, "failed_total", "failed_players");
```
**Redução:** 36 → 12 linhas.

---

### B2. Macro `cycle_field!` para extração do snapshot (snapshot.rs linhas 175-214)

8 campos seguem o padrão `as_u64(last_cycle.and_then(|c| c.get("X")).or_else(|| state.get("Y")))`.

**Antes (40 linhas):**
```rust
history_roots: as_u64(
    last_cycle.and_then(|c| c.get("history_roots")).or_else(|| state.get("history_roots")),
),
// repetido 8x com nomes diferentes
```

**Depois (~15 linhas):**
```rust
macro_rules! cycle_u64 {
    ($lc:expr, $state:expr, $primary:expr) => {
        as_u64($lc.and_then(|c| c.get($primary)).or_else(|| $state.get($primary)))
    };
    ($lc:expr, $state:expr, $primary:expr, $fallback:expr) => {
        as_u64($lc.and_then(|c| c.get($primary)).or_else(|| $state.get($fallback)))
    };
}
// ...
history_roots: cycle_u64!(last_cycle, state, "history_roots"),
details_done: cycle_u64!(last_cycle, state, "history_details_done", "details_done"),
```
**Redução:** 40 → 15 linhas.

---

### B3. Implementar `Display` para `ModeArg` (main.rs linhas 424-428, 910-914)

Conversão `mode → &str` duplicada em 2 lugares.

**Antes (duplicado):**
```rust
let mode = match app.cfg.mode {
    ModeArg::Live => "live",
    ModeArg::Demo => "demo",
    ModeArg::Text => "text",
};
```

**Depois (4 linhas, uma vez):**
```rust
impl std::fmt::Display for ModeArg {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(match self { Self::Live => "live", Self::Demo => "demo", Self::Text => "text" })
    }
}
```
**Redução:** 10 → 4 linhas + elimina duplicação.

---

### B4. Helper `age_or_inf` para health (main.rs linhas 410-422)

Padrão `if epoch > 0 { (now - epoch) / 1000.0 } else { INFINITY }` repetido 2 vezes.

**Antes (8 linhas):**
```rust
let state_ok_age_s = if app.health.last_state_read_ok_epoch_ms > 0 {
    (now_ms.saturating_sub(app.health.last_state_read_ok_epoch_ms)) as f64 / 1000.0
} else {
    f64::INFINITY
};
// duplicado para state_fail_age_s
```

**Depois (5 linhas):**
```rust
fn age_secs_or_inf(now_ms: u64, epoch_ms: u64) -> f64 {
    if epoch_ms > 0 { (now_ms.saturating_sub(epoch_ms)) as f64 / 1000.0 } else { f64::INFINITY }
}
let state_ok_age_s = age_secs_or_inf(now_ms, app.health.last_state_read_ok_epoch_ms);
let state_fail_age_s = age_secs_or_inf(now_ms, app.health.last_state_read_fail_epoch_ms);
```
**Redução:** 8 → 5 linhas.

---

### B5. Desmembrar `draw_right` (main.rs linhas 699-907)

Função de 208 linhas que renderiza 5 categorias + gauges + sparkline. Dividir em sub-funções por seção.

**Ação:** Extrair `draw_category_summary`, `draw_health_gauges`, `draw_collection_progress`, `draw_recent_pace`, `draw_sparkline`. Cada uma 20-40 linhas.
**Benefício:** Legibilidade e testabilidade. Redução líquida ~10 linhas (eliminação de variáveis intermediárias duplicadas).

---

## Fase C — Shell: Launcher (`run_crawler_rpi.sh`, 781 linhas)

### C1. Helper `kill_and_wait` (linhas ~202-213)
Padrão idêntico `if [[ -n "$PID" ]]; kill; wait; fi` repetido 3 vezes.
**Redução:** 12 → 4 linhas.

### C2. Helper `make_abs` para caminhos (linhas ~520-548)
Padrão `if [[ "$VAR" != /* ]]; VAR="$BASE/$VAR"; fi` repetido 4 vezes.
**Redução:** 16 → 5 linhas.

### C3. Helper `append_flag` em `start_crawler_tui_rpi.sh` (linhas ~98-112)
Padrão `if [[ "$FLAG" == "1" ]]; ARGS+=(--flag); fi` repetido 5 vezes.
**Redução:** 15 → 6 linhas.

### C4. Loop para backup de arquivos (linhas ~763-777)
Padrão `[[ -f "$FILE" ]] && cp -f "$FILE" "$DIR/"` repetido 5× em 2 lugares.
**Redução:** 10 → 3 linhas por bloco.

### C5. `parse_valued_arg` para case do argparse (linhas ~272-394)
Validação inline `if [[ "$#" -lt 2 ]]; echo; exit; fi` repetida ~15 vezes.
**Redução:** ~45 linhas de boilerplate → 1 helper + chamadas inline.

---

## Fase D — Python: Módulo `network.py` (435 linhas)

### D1. `_env_float`, `_env_int`, `_env_bool` → função genérica (linhas 61-85)

Três funções quase idênticas para parsear env vars.

**Antes (25 linhas):**
```python
def _env_float(name, default):
    raw = str(os.getenv(name, "")).strip()
    if not raw: return default
    try: return float(raw)
    except: return default
# + _env_int (idêntica com int())
# + _env_bool (idêntica com set lookup)
```

**Depois (8 linhas):**
```python
def _env(name, default, cast=str):
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        return cast(raw)
    except Exception:
        return default

_env_bool = lambda name, default: _env(name, default, lambda v: v.lower() in {"1","true","yes","y","on"})
```
**Redução:** 25 → 10 linhas.

---

## Fase E — Mudanças Estruturais (impacto alto, risco controlado)

### E1. Extrair `crawl_cycle` do monolito `run()` (crawler.py linhas 1249-1582)

A função `run()` tem 420 linhas e mistura: setup, loop principal, lógica de cada fase, acumulação de métricas, condições de parada e shutdown. Extrair o corpo do loop em `_run_cycle()`.

**Situação atual:** Toda lógica operacional numa única função gigante. Qualquer mudança numa fase arrisca regressão em outra.

**Proposta:**
```python
def _run_cycle(args, state, processed_match_ids, cycle_context) -> CycleResult:
    """Executa um ciclo completo (history + convert) e retorna métricas."""
    ...

def run(args) -> int:
    # setup...
    while not STOP:
        result = _run_cycle(args, state, processed_match_ids, ctx)
        # stop conditions + save...
```
**Benefício:** `run()` fica com ~80 linhas (setup + loop + shutdown). `_run_cycle()` com ~200 linhas. Cada uma testável isoladamente.
**Redução:** ~40 linhas (variáveis intermediárias eliminadas). Ganho real: isolamento de responsabilidade.

---

### E2. Typed stats com dataclass em vez de dicts manuais (crawler.py linhas 823-988)

`crawl_history` e `collect_profiles` constroem dicts de stats manualmente com strings como chaves. Erros de typo em chaves são silenciosos.

**Situação atual:**
```python
stats: dict[str, int | str] = {"root": f"{name}@{realm}", "pages_scanned": 0, ...}
# ... 150 linhas depois ...
stats["details_done"] = details_done  # typo aqui = bug silencioso
```

**Proposta:**
```python
@dataclass
class HistoryStats:
    root: str = ""
    pages_scanned: int = 0
    page_errors: int = 0
    matches_seen: int = 0
    new_match_ids: int = 0
    details_target: int = 0
    details_done: int = 0
    detail_errors: int = 0
    players_new: int = 0
    root_error: str = ""

@dataclass
class ProfileStats:
    candidates: int = 0
    chosen: int = 0
    attempted: int = 0
    ok: int = 0
    failed: int = 0
    skipped_failed_cooldown: int = 0
    skipped_unknown_class: int = 0
    skipped_plateau_class: int = 0
    skipped_no_need: int = 0
    fail_by_kind: dict[str, int] = field(default_factory=lambda: {"transient": 0, "policy": 0, "client": 0, "other": 0})
```
**Benefício:** Autocompletar do editor, erro de compilação em typos, `.asdict()` para serialização. ~0 linhas a menos, mas elimina uma classe inteira de bugs.

---

### E3. Consolidar `configure_http` com update parcial idiomático (network.py linhas 88-146)

Atualmente: 8 blocos `if param is not None: cfg.field = cast(param)` sequenciais.

**Proposta:** Usar `dataclasses.replace()` ou um dict-merge pattern:
```python
def configure_http(**overrides):
    global _CONFIG, ...
    with _CONFIG_LOCK:
        base = _CONFIG or _default_config()
        updates = {k: v for k, v in overrides.items() if v is not None}
        cfg = dataclasses.replace(base, **updates)
        ...
```
**Redução:** ~20 linhas. Mais extensível (adicionar campo novo = 0 linhas de boilerplate).

---

### E4. Unificar `start_crawler_tui_rpi.sh` + `start_crawler_tui_rpi_rebuild.sh`

O script rebuild (9 linhas) apenas exporta `TUI_RS_FORCE_BUILD=1` e chama o start. São 2 arquivos onde 1 basta.

**Proposta:** Adicionar `--force-rebuild-tui` ao script start. Eliminar o arquivo rebuild.
```bash
# start_crawler_tui_rpi.sh
if [[ "$1" == "--rebuild-tui" ]]; then
    export TUI_RS_FORCE_BUILD=1
    shift
fi
```
**Redução:** 1 arquivo a menos no projeto. Docs atualizados.

---

### E5. Rust: separar `health.rs` de `main.rs` (main.rs linhas 97-511)

`RuntimeHealth` struct + `maybe_write_health_snapshot` + `write_json_atomic` + `write_quit_signal` = ~420 linhas misturadas com a lógica do app e UI.

**Proposta:** Mover para `tui_rs/src/health.rs`:
- `RuntimeHealth` struct + impl
- `maybe_write_health_snapshot()`
- `write_json_atomic()`
- `write_quit_signal()`
- `age_secs_or_inf()` (B4)

**Resultado:** `main.rs` fica com ~600 linhas (app + UI). `health.rs` com ~180 linhas (toda lógica de saúde).
**Benefício:** Separação clara de responsabilidades. Health testável isoladamente.

---

### E6. Rust: separar `ui.rs` de `main.rs` (main.rs linhas 523-944)

As funções `ui`, `draw_header`, `draw_left`, `draw_right`, `draw_footer` e auxiliares de rendering = ~420 linhas.

**Proposta:** Mover para `tui_rs/src/ui.rs`. `main.rs` fica só com `App`, `Cli`, `run_*` e `main()`.

**Resultado com E5+E6:** `main.rs` fica com ~250 linhas (structs + entrypoints). Arquitetura de 5 módulos:
```
main.rs      (~250 linhas) - App, Cli, main, run_tui, run_text
ui.rs        (~420 linhas) - todas as funções de rendering
health.rs    (~180 linhas) - RuntimeHealth, health snapshot, atomic IO
snapshot.rs  (~630 linhas) - parsing de estado (já existe)
time_utils.rs (~38 linhas) - utilitários de tempo (já existe)
```

---

## Resumo de Impacto (Atualizado)

| Fase | Arquivo | Itens | Impacto |
|------|---------|-------|---------|
| A    | crawler.py | A1-A5 | ~80 linhas eliminadas |
| B    | tui_rs/*.rs | B1-B5 | ~70 linhas eliminadas |
| C    | *.sh | C1-C5 | ~80 linhas eliminadas |
| D    | network.py | D1 | ~15 linhas eliminadas |
| E    | estrutural | E1-E6 | ~60 linhas eliminadas + separação de módulos |
| **Total** | | **21 refatorações** | **~305 linhas + 3 novos módulos Rust** |

**Ganho qualitativo:**
- Nenhuma função >120 linhas (hoje: `run()` tem 420, `draw_right` tem 208)
- Dicts manuais de stats → dataclasses tipadas (elimina classe de bugs)
- 3 módulos Rust isolados em vez de 1 monolito de 1026 linhas
- Shell com helpers reutilizáveis em vez de copy-paste

---

## Ordem de Execução Recomendada

**Grupo 1 — Baixo risco, alto impacto em legibilidade:**
1. A2 (keywords → sets)
2. A5 (int() redundante)
3. B3 (Display para ModeArg)
4. B4 (age_or_inf helper)
5. D1 (env parsers)

**Grupo 2 — Refatorações de extração (médio risco):**
6. A1 (context manager net_*)
7. A3 (contadores unificados)
8. A4 (metrics helper)
9. B1 (count_or_len)
10. B2 (macro cycle_u64!)

**Grupo 3 — Mudanças estruturais shell:**
11. C1-C4 (helpers shell)
12. C5 (parse_valued_arg)
13. E4 (unificar scripts start/rebuild)

**Grupo 4 — Mudanças estruturais Python:**
14. E2 (dataclasses para stats)
15. E3 (configure_http idiomático)
16. E1 (extrair _run_cycle)

**Grupo 5 — Mudanças estruturais Rust:**
17. E5 (health.rs)
18. E6 (ui.rs)
19. B5 (split draw_right dentro de ui.rs)

---

## Critérios de Aceitação

- [ ] Todos os 38 testes Python + 9 testes Rust continuam passando
- [ ] `cargo clippy` sem warnings novos
- [ ] Comportamento idêntico ao atual (diff de saída zero em --dry-run --once)
- [ ] Nenhuma feature adicionada, apenas reestruturação
- [ ] Nenhuma função com mais de 120 linhas após Fase E
- [ ] `main.rs` com menos de 300 linhas após E5+E6
