# Changelog

Todas as mudanças notáveis neste projeto serão documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e o projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [1.1.0] - 2026-03-03

Reorganização de pastas e nomes para estrutura profissional.

### Alterado
- Crawler movido de `scripts/` para pacote `crawler/` (invocação via `python -m crawler`)
- Biblioteca renomeada de `warmane_character_analyzer/` para `armory/`
- Arquivos internos renomeados: `armory_parser` → `parser`, `atomic_io` → `fileio`, `item_metadata` → `items`, `runtime_state` → `runtime`
- Launcher atualizado para invocar `python -m crawler` em vez de script direto
- `pyproject.toml` atualizado com novos nomes de pacotes

### Removido
- `scripts/benchmark_collection.py` (artefato one-off)
- `start_crawler_tui_rpi_rebuild.sh` (deprecated; usar `--rebuild-tui`)
- `docs/gemini_tui.md` (notas de sessão antiga)

## [1.0.0] - 2026-03-03

Release inaugural do projeto completo (crawler + TUI Rust).

### Incluído
- Crawler adaptativo em grafo (`crawler/`) com:
  - descoberta por match-history multi-root
  - coleta enriquecida de perfis (stats, itens, enchants, gems)
  - rate limiting, retry com backoff exponencial, cache condicional HTTP
  - timeout por request, root, ciclo e parede
  - delay adaptativo por qualidade de rede
  - retry inteligente de players falhados
  - telemetria de funil por ciclo
  - controle IPC (pause/start/cancel) via TUI
  - seed por ladder + árvore multi-root
  - modos de fase: auto, discover, convert, hybrid
  - persistência em JSON, CSV e Parquet
- TUI Rust (`tui_rs/`) com ratatui:
  - dashboard operacional com classes por cor WoW
  - grafico Total X-Y com eixo temporal
  - painel de saude de rede (latencia, delay, erros)
  - health snapshot em JSON (schema v2)
  - quit duplo (q+q) anti-acidental
  - aba Config para ajuste de parametros em tempo real
  - modos live, demo, text
- Launcher (`run_crawler_rpi.sh`):
  - bootstrap de venv e dependencias
  - lock anti-concorrencia com validacao de PID
  - integracao tmux com auto-tmux
  - monitor anti-orfao e anti-freeze
  - quit total limpo no tmux
- Biblioteca Python (`armory/`):
  - analyzer, parser, network, fileio, runtime, constants
- Suite de testes (Python + Rust)
- Pipeline offline de treino (v1-v4) com export para addon WoW
- Documentacao operacional completa

[1.1.0]: https://github.com/ValadaresX/Crawler_warmane/releases/tag/v1.1.0
[1.0.0]: https://github.com/ValadaresX/Crawler_warmane/releases/tag/v1.0.0
