# Warmane Character Analyzer

Ferramenta para analisar personagem da armory da Warmane e retornar:

- `GearScoreLite` estimado (mesma fórmula do addon)
- `iLevel médio`
- `HP máximo estimado` (stamina da armory + base HP WotLK 3.3.5a)

## Estrutura modular

- `crawler/`: pacote principal do crawler adaptativo em grafo
  - `__main__.py`: entry point (`python -m crawler`)
  - `base.py`, `cli.py`, `cycle.py`, `discovery.py`, `history.py`, `http.py`, `profiles.py`, `state.py`
- `armory/`: biblioteca de análise de personagens Warmane
  - `analyzer.py`: orquestração da análise
  - `parser.py`: parsing da página do personagem
  - `items.py`: coleta/cache de metadados de item
  - `gearscore.py`: cálculo de GS
  - `health.py`: cálculo de HP
  - `models.py`: modelos de dados
  - `constants.py`: constantes e tabelas
  - `network.py`: HTTP com `httpx` + retry
  - `fileio.py`: I/O atômico (JSON, CSV, Parquet)
  - `runtime.py`: heartbeat e telemetria
  - `match_history.py`: parsing de match-history

## Requisitos

- Python 3.10+
- `beautifulsoup4`
- `httpx`
- `tenacity`
- `diskcache`

```bash
pip install beautifulsoup4 httpx tenacity diskcache
```

## Uso

```bash
python scripts/analyze_warmane_character.py "https://armory.warmane.com/character/Narako/Blackrock/summary"
```

Saída JSON:

```bash
python scripts/analyze_warmane_character.py "https://armory.warmane.com/character/Narako/Blackrock/summary" --json
```

## Coleta por Match ID (novo)

Para buscar os players de uma partida e calcular `GS`, `iLvl`, `HP`, `Spec/Talento` e `Classe`:

```bash
python scripts/fetch_warmane_match_players.py 42294487
```

Salvar também em JSON:

```bash
python scripts/fetch_warmane_match_players.py 42294487 --output-json reports/matches/match_42294487_players.json
```

Executar benchmark de 3 caminhos de aquisição do `matchinfo` e eleger o melhor:

```bash
python scripts/fetch_warmane_match_players.py 42294487 --path-tests
```

## Pipeline de Dataset (match-history)

Para montar dataset deduplicado de players que apareceram contra/ao lado de um personagem:

```bash
python scripts/build_dataset_from_match_history.py "https://armory.warmane.com/character/Narako/Blackrock/summary"
```

Saídas:

- `data/raw/state_match_history.json` (estado para retomar coletas)
- `data/processed/players_dataset.json` (dataset consolidado)
- `data/processed/players_dataset.csv` (dataset para análise/treino)

A pipeline já aplica navegação “humana” por padrão:

- requisições sequenciais (sem paralelismo agressivo)
- delay aleatório entre requests
- pausas longas periódicas
- deduplicação por `(name, realm)`
- retomada incremental por `state`

Para coleta mais conservadora:

```bash
python scripts/build_dataset_from_match_history.py "https://armory.warmane.com/character/Narako/Blackrock/summary" \
  --max-matches 40 --max-new-players 20 --min-delay-seconds 2.0 --max-delay-seconds 4.0
```

Para sincronizar até o fim (somente acrescentando novos dados):

```bash
python scripts/build_dataset_from_match_history.py "https://armory.warmane.com/character/Narako/Blackrock/match-history" \
  --full-sync --skip-failed --min-delay-seconds 2.0 --max-delay-seconds 4.0 \
  --break-every-requests 20 --break-min-seconds 10 --break-max-seconds 25
```

O script identifica instantaneamente o que já existe no `state` e aplica delay humano apenas nas requisições novas.

Para reduzir requisições de perfil usando a classe vinda do botão `Details` (`matchinfo`):

```bash
python scripts/build_dataset_from_match_history.py "https://armory.warmane.com/character/Narako/Blackrock/summary" \
  --target-classes "Priest,Warlock" --max-matches 80 --max-new-players 60
```

Para focar automaticamente classes com menor cobertura no dataset:

```bash
python scripts/build_dataset_from_match_history.py "https://armory.warmane.com/character/Narako/Blackrock/summary" \
  --min-profiles-per-class 300 --max-matches 120 --max-new-players 100
```

Notas:

- `matchinfo` já retorna `class` numérico por player (sem abrir perfil).
- Players sem `class_hint` podem ser incluídos com `--include-unknown-class-hint`.
- Com `--min-profiles-per-class`, a fila é priorizada por:
  - maior déficit de classe primeiro;
  - match mais recente primeiro (`source_match_ids`).

## Gestão de lotes offline (sem rede)

Para gerar lotes locais com retomada segura (sem requisições Warmane):

```bash
python scripts/manage_offline_batches.py --batch-size 80 --max-batches 1
```

Saídas:

- `data/raw/offline_batch_state.json` (estado/cursor da fila)
- `data/processed/batches/batch_0001.json` (lote gerado)
- `data/processed/batches/index.json` (índice dos lotes)

O script usa:

- barra de progresso em linha única (sem spam)
- escrita atômica (`tmp + replace`)
- parada segura com `Ctrl+C` e retomada no próximo run

Modo nativo contínuo até platô por classe:

```bash
python scripts/manage_offline_batches.py --run-forever --batch-size 80 --stop-on-plateau --plateau-cycles 12 --plateau-min-samples-per-class 120 --sleep-seconds 2
```

Regra de platô por classe neste modo:

- classe `esgotada`: processados da classe >= total disponível da classe no dataset atual
- ou classe `estagnada`: sem progresso por `N` ciclos e já com mínimo de amostras

## Treino offline v3 (portável)

Para treinar o modelo v3 usando apenas dataset local:

```bash
python scripts/run_offline_pipeline_v3.py
```

Saídas:

- `artifacts/model_v3/` (bundle e metadata da execução)
- `exports/model_v3/gs_lookup_v3.json` (lookup + regras de inferência + calibração)
- `reports/baseline_v3.md` e `reports/model_v3.md` (métricas auditáveis)

## Crawler adaptativo dinâmico (grafo de players)

Para rodar o crawler de forma contínua e inteligente (sem limite de ciclos por padrão):

```bash
python -m crawler "https://armory.warmane.com/character/Narako/Blackrock/summary"
```

O algoritmo:

- escolhe dinamicamente qual `match-history` explorar (árvore de ramificações)
- usa `class_hint` do `matchinfo` para reduzir requests
- prioriza coleta por deficiência de classe
- suporta meta por classe em faixa de HP (`--target-hp-min/--target-hp-max`)
- suporta modo `hybrid` para rodar `discover + convert` no mesmo ciclo
- prioriza recência de partidas
- exibe hierarquia visual por ciclo + barras de progresso por fase (`pages`, `matches`, `profiles`)
- salva checkpoint atômico (`state` + `dataset`) sem corromper arquivos
- para automaticamente no platô (pode desativar com `--no-stop-on-plateau`)

Exemplo para coletar lacunas de classes em `HP 25k-40k` por horas:

```bash
./run_crawler_rpi.sh \
  --phase hybrid \
  --target-min-per-class 900 \
  --target-hp-min 25000 \
  --target-hp-max 40000 \
  --profiles-per-cycle 120 \
  --history-players-per-cycle 20 \
  --collect-surplus-classes \
  --skip-failed \
  --min-resilience 0 \
  --allow-missing-resilience \
  --no-stop-on-target \
  --no-stop-on-plateau \
  --no-stop-on-marginal-gain \
  "https://armory.warmane.com/character/Bicharka/Blackrock/summary"
```

## Execução no Raspberry Pi OS

Na pasta do projeto (ou snapshot copiado), rode:

```bash
chmod +x run_crawler_rpi.sh
./run_crawler_rpi.sh "https://armory.warmane.com/character/Narako/Blackrock/summary"
```

Com TUI sincronizada:

```bash
./run_crawler_rpi.sh \
  --tui \
  --tui-mode live \
  --tui-refresh-seconds 0.70 \
  --tui-layout-schema apps/crawler_tui/v1_test/layout_schema.json \
  "https://armory.warmane.com/character/Narako/Blackrock/summary"
```

Com TUI Rust (recomendado em RPi):

```bash
./run_crawler_rpi.sh --tui-rs --tui-rs-mode live --tui-rs-focus tui --tui-rs-refresh-seconds 0.80 --tui-rs-fps 10 --tui-rs-health-file data/raw/tui_rs_health.json --tui-rs-health-interval-seconds 1.0 --phase hybrid --collect-surplus-classes --recollect-and-append --history-players-per-cycle 10 --max-history-pages-per-cycle 0 --max-matchinfo-per-cycle 120 --profiles-per-cycle 400 --http-rps 5.5 --http-max-connections 10 --http-max-retries 6 --request-wall-timeout-seconds 90 --matchinfo-timeout-seconds 18 --matchinfo-request-wall-timeout-seconds 45 --history-root-max-seconds 180 --history-detail-error-streak-stop 12 --cycle-max-seconds 420 --min-delay-seconds 0 --max-delay-seconds 0.2 --adaptive-delay-error-growth 1.8 --adaptive-delay-success-decay 0.96 --adaptive-delay-hard-backoff-errors 2 --adaptive-delay-hard-backoff-seconds 4 --random-visit-prob 0.01 --random-visit-every-pages 40 --random-visit-every-matchinfos 120 --random-visit-every-profiles 40 --skip-failed --allow-missing-resilience --idle-stop-seconds 120 --block-detect-consecutive-errors 8
```

Atalho recomendado (evita erro de copy/paste):

```bash
chmod +x start_crawler_tui_rpi.sh
./start_crawler_tui_rpi.sh
```

Forçar rebuild da TUI Rust (quando suspeitar de binário antigo):

```bash
./start_crawler_tui_rpi.sh --rebuild-tui
```

Verificação de versão/estado da TUI:

```bash
cat data/raw/tui_rs_health.json | sed -n '1,220p'
```

Esperado:

- `schema: crawler_tui_rs.health.v2`
- `app.compact_runtime_parser: true`
- `snapshot.class_counts_sum` presente.

Checagem precisa da TUI sem gerar spam:

```bash
python3 tui_rs/check_tui_health.py --health-file data/raw/tui_rs_health.json
```

O `run_crawler_rpi.sh`:

- cria/usa `.venv` local
- valida dependências do `requirements.txt`
- instala libs faltantes via `pip`
- tenta instalar `python3-venv`/`python3-pip` com `sudo apt-get` se necessário
- aplica lock para evitar duas instâncias simultâneas
- inicia `python -m crawler`
- com `--tui-rs` fora de tmux, cria sessão tmux automaticamente e reexecuta o launcher (pode desativar com `AUTO_TMUX_FOR_TUI_RS=0`)
- opcionalmente abre a TUI (`--tui`) em janela dedicada do `tmux` (largura/altura completas), lendo o mesmo `state-file` do crawler
- opcionalmente abre a TUI Rust (`--tui-rs`) em janela dedicada do `tmux` (mais fluida em hardware limitado)
- por padrão, ao usar `--tui-rs`, a tecla `Esc` na TUI dispara quit total (desative com `--no-tui-rs-esc-quit`)
- `--tui-rs-focus` controla foco inicial da sessão tmux (`tui|crawler|none`, padrão `tui`)
- `--tui-rs-health-file` grava snapshot de saúde da TUI em JSON sobrescrito (sem crescimento de log)
- heartbeat leve de runtime ativo por padrão (`data/raw/adaptive_crawler_runtime.json`) para TUI sem congelamento em ciclo longo
- monitor anti-freeze ativo por padrão (usa runtime-state quando habilitado; `--state-stale-stop-seconds`, default `180`); desative com `--no-state-stale-stop`
- por padrão, ativa monitor anti-órfão: se a sessão dona morrer/desanexar por tempo contínuo, o crawler encerra (`--no-stop-on-owner-exit` desativa; `--owner-exit-grace-seconds` ajusta grace)
- anti-travamento de rede/ciclo: limites de tempo por request/root/ciclo (`--request-wall-timeout-seconds`, `--matchinfo-request-wall-timeout-seconds`, `--history-root-max-seconds`, `--cycle-max-seconds`)
- na TUI Rust, `q` duas vezes (até 2s) faz quit total: fecha a TUI e encerra o crawler de forma limpa

## Lint e Testes (Windows)

```powershell
powershell -ExecutionPolicy Bypass -File scripts/lint_python.ps1
powershell -ExecutionPolicy Bypass -File scripts/lint_rust.ps1
python -m pytest tests -q
```

## Releases

Para lançar uma nova versão:

1. Atualizar os manifests:
   ```bash
   ./scripts/bump_version.sh 1.1.0
   ```
2. Editar `CHANGELOG.md` com as mudanças da nova versão.
3. Commit e tag:
   ```bash
   git add VERSION pyproject.toml tui_rs/Cargo.toml CHANGELOG.md
   git commit -m "v1.1.0: <descricao>"
   git tag -a v1.1.0 -m "v1.1.0: <descricao>"
   ```
4. Push:
   ```bash
   git push origin main --follow-tags
   ```

## Observações

- O HP calculado é referência sem buffs/debuffs temporários.
- Cache de itens: `data/cache/item_metadata/`.
