# TUI Rust (`tui_rs`)

Dashboard operacional em Rust (`ratatui`) para acompanhar o crawler Warmane em tempo real.

Objetivo: entregar visualização fluida no Raspberry Pi sem mexer no core do crawler Python.

## Escopo e arquitetura

Esta pasta é isolada do crawler e tem integração por arquivo de estado.

- Entrada principal recomendada: `data/raw/adaptive_crawler_runtime.json` (heartbeat leve, alta fluidez).
- Entrada legada compatível: `data/raw/adaptive_crawler_state.json`.
- Saída opcional de controle: `quit-file` (sinal para encerramento total via launcher).
- Saída opcional de observabilidade: `health-file` (JSON sobrescrito, sem crescimento de log).

Arquivos-chave:

- `src/main.rs`: app TUI (`live`, `demo`, `text`), render e telemetria.
- `run_tui_rs.sh`: runner para RPi (inclui `CARGO_TARGET_DIR` fora do SSD quando necessário).
- `check_tui_health.py`: verificador rápido de saúde da TUI (retorna `exit code`).
- `Cargo.toml`: dependências e lints rígidos de Rust/Clippy.

## Recursos da UI

- `Players Coletados por Classe` com cores clássicas de WoW 3.3.5.
- Bloco `Total` com gráfico X-Y e escala exponencial no eixo X.
- Painel `Visao Operacional Avancada` com:
  - saúde da conexão (`latência`, `falhas seguidas`, score);
  - andamento de details/profiles;
  - ritmo recente (`players_new`).
- Escala de cor verde -> vermelho em latência e falhas sequenciais.
- Leitura de estado desacoplada do render (`refresh-seconds` vs `fps`).

## Requisitos

### Linux / RPi

- `rustup` + `cargo` instalados.
- terminal com suporte a cor (`TERM=xterm-256color` recomendado).

### Windows

- Rust toolchain instalado (`cargo` no `PATH`).
- PowerShell ou terminal compatível.

## Comandos rápidos (linha única)

### RPi (direto no módulo)

```bash
cd /mnt/ssd/bundle_rpi_20260222_211132/tui_rs && chmod +x run_tui_rs.sh && ./run_tui_rs.sh --mode live --state-file ../data/raw/adaptive_crawler_runtime.json --refresh-seconds 0.8 --fps 10 --health-file ../data/raw/tui_rs_health.json --health-interval-seconds 1.0
```

### Windows (PowerShell)

```powershell
cd D:\Projetos_Git\check_players\tui_rs; cargo run --release -- --mode live --state-file ..\data\raw\adaptive_crawler_runtime.json --refresh-seconds 0.8 --fps 12 --health-file ..\data\raw\tui_rs_health.json --health-interval-seconds 1.0
```

### Demo local (sem crawler)

```bash
cd /mnt/ssd/bundle_rpi_20260222_211132/tui_rs && ./run_tui_rs.sh --mode demo --refresh-seconds 0.5 --fps 12
```

### Smoke test (uma leitura e sai)

```bash
cd /mnt/ssd/bundle_rpi_20260222_211132/tui_rs && ./run_tui_rs.sh --mode live --state-file ../data/raw/adaptive_crawler_runtime.json --once
```

## Integração oficial com o crawler

A forma recomendada em produção é iniciar pelo launcher:

```bash
cd /mnt/ssd/bundle_rpi_20260222_211132 && ./run_crawler_rpi.sh --tui-rs --tui-rs-mode live --tui-rs-focus tui --tui-rs-refresh-seconds 0.80 --tui-rs-fps 10 --tui-rs-health-file data/raw/tui_rs_health.json --tui-rs-health-interval-seconds 1.0 --phase hybrid --collect-surplus-classes --recollect-and-append --profiles-per-cycle 400 --http-rps 5.5 --http-max-connections 10 --http-max-retries 6 --skip-failed --allow-missing-resilience --idle-stop-seconds 120 --block-detect-consecutive-errors 8
```

Requisitos para exibir a TUI com crawler:

- sessão `tmux` ativa;
- `cargo` disponível no ambiente onde o launcher roda.

Se `tmux` não estiver disponível, o launcher continua em modo texto (fallback seguro).

## Keybinds

- `q` + `q` (duas vezes em até 2s): sai da TUI.
- `Esc`: sai da TUI quando iniciada com `--esc-quit`.
- Quando iniciada via `run_crawler_rpi.sh --tui-rs`: o quit também encerra o crawler de forma limpa.

Proteção anti-saída acidental:

- Nos primeiros ~1.5s após iniciar, a TUI ignora quit por tecla.

## Health snapshot e monitoramento

A TUI pode gravar um snapshot de saúde em JSON, sempre sobrescrevendo o mesmo arquivo (sem spam).

Exemplo de check rápido:

```bash
cd /mnt/ssd/bundle_rpi_20260222_211132/tui_rs && python3 check_tui_health.py --health-file ../data/raw/tui_rs_health.json
```

Exemplo de check em JSON:

```bash
cd /mnt/ssd/bundle_rpi_20260222_211132/tui_rs && python3 check_tui_health.py --health-file ../data/raw/tui_rs_health.json --json
```

`exit code` do checker:

- `0`: `OK`
- `1`: `ALERT` (degradação/stale parcial)
- `2`: `FAIL` (arquivo ausente, JSON inválido ou stale crítico)

## Flags CLI da TUI

- `--mode live|demo|text`: fonte dos dados.
- `--state-file <path>`: caminho do estado do crawler.
- `--refresh-seconds <float>`: intervalo de leitura de dados.
- `--fps <int>`: taxa alvo de render da UI (`1..30`, clamp interno).
- `--max-history <int>`: tamanho máximo de histórico para gráficos.
- `--exp-x <float>`: intensidade da escala exponencial no gráfico X-Y (`1.2..4.0`, clamp interno).
- `--quit-file <path>`: arquivo-sinal para quit total quando usado com launcher.
- `--esc-quit`: habilita quit imediato por `Esc`.
- `--health-file <path>`: caminho do snapshot de saúde.
- `--health-interval-seconds <float>`: intervalo de atualização da saúde.
- `--once`: roda um ciclo e encerra.
- `--ascii`: usa caracteres ASCII no lugar de braille/unicode.

Observação operacional:
- O rodapé mostra `state_age` (idade da última atualização real do `state-file`). Se crescer continuamente, o crawler não está publicando estado novo.
- A TUI limita o render ao ritmo de `refresh-seconds` (não renderiza mais rápido que a chegada de dados).

## Contrato mínimo do `state-file` (modo live)

Campos esperados (com tolerância a ausência):

- `cycle`
- `players` (objeto)
- `processed_players` (objeto com `class`)
- `failed_players` (objeto)
- `network.delay_factor`
- `network.consecutive_errors`
- `network.stats.latency_ms_ema`
- `telemetry.cycles[-1].phase`
- `telemetry.cycles[-1].history_roots`
- `telemetry.cycles[-1].history_details_done`
- `telemetry.cycles[-1].history_details_target`
- `telemetry.cycles[-1].players_new`
- `telemetry.cycles[-1].profiles_attempted`
- `telemetry.cycles[-1].profiles_ok`
- `telemetry.cycles[-1].profiles_failed`

Se algum campo faltar, a TUI degrada com fallback seguro (sem panic).

## Troubleshooting rápido

### TUI não abre e launcher cai para print

- Causa comum: fora de `tmux` ou sem `cargo`.
- Ação:
  - instale `tmux` e rode dentro de sessão;
  - valide `cargo --version`.

### `Pane is dead (status 0)` no tmux

- Em geral indica saída limpa da TUI.
- Ação:
  - reabrir com `--tui-rs-focus tui`;
  - confirmar se não houve `q` duplo involuntário;
  - verificar health file para confirmar atividade recente.

### Estado não atualiza (tela “congelada”)

- Ação:
  - checar timestamp do `state-file`;
  - usar checker de health para idade de dados/render;
  - validar se crawler realmente está em execução.

### SSD montado em `ro` no RPi

- Sintoma: erro em `target/release/.cargo-lock` (read-only).
- Ação:
  - usar `run_tui_rs.sh` (já direciona build para `CARGO_TARGET_DIR` fora do SSD por padrão);
  - ou exportar manualmente `CARGO_TARGET_DIR=$HOME/.cargo-target-rpi`.

## Performance no Raspberry Pi

- Faixa prática recomendada:
  - `--refresh-seconds 0.8`
  - `--fps 8..12`
- Se CPU estiver alta:
  - reduza `--fps` primeiro;
  - mantenha `refresh-seconds` em `0.8` ou `1.0`.

## Lint e testes do módulo

Na raiz do projeto:

```powershell
cargo fmt --all -- --check
```

```powershell
cargo check
```

```powershell
cargo clippy --all-targets --all-features -- -D warnings
```

```powershell
cargo test
```

```powershell
cargo nextest run --all-targets --all-features
```

```powershell
python -m pytest tests/test_health_status_e2e.py -q
```

## Fluxo operacional recomendado (resumo)

1. Iniciar `tmux`.
2. Rodar `run_crawler_rpi.sh` com `--tui-rs ...`.
3. Verificar janela da TUI (`tmux select-window -t <id>`).
4. Monitorar saúde com `check_tui_health.py` quando necessário.
5. Encerrar com `q` + `q` na TUI (quit total limpo).
