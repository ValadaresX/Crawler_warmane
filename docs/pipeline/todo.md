# TODO Pipeline (Sessão Atual)

## Objetivo

Refatorar o crawler para **recoleta massiva enriquecida** dos players já conhecidos, com foco em:

- coleta completa do `summary` (Character Stats completos);
- itens equipados com `item_id`, `enchant` e `gems`;
- persistência principal em **Parquet**;
- robustez de rede (rate limit, retry/backoff, cache condicional, checkpoint/retomada);
- preparação de bundle RBP enxuto e exclusivo para operação do crawler.

## Plano

- [x] Atualizar checklist para abrir `Fase 30` (refatoração crawler enriquecido)
- [x] Refatorar camada HTTP com:
  - rate limiting por RPS;
  - backoff exponencial com jitter para `429/503`;
  - respeito a `Retry-After`;
  - cache local por URL com `ETag`/`Last-Modified`;
  - requests condicionais (`If-None-Match`/`If-Modified-Since`);
  - rotação de `User-Agent` e headers HTTP.
- [x] Ampliar parser/analyzer para coletar:
  - Character Stats completos (`Melee`, `Ranged`, `Attributes`, `Defense`, `Spell`, `Resistances`);
  - itens do summary com `enchant` e `gems`.
- [x] Evoluir crawler para:
  - modo de **recoleta de já processados**;
  - fila menos previsível (embaralhamento de páginas/IDs + visitas randômicas de diluição);
  - saída versionada em `CSV/JSON/Parquet`.
- [x] Validar em dry-run local (`--once`) com checkpoint e retomada
- [x] Sincronizar para `\\<LAN>\ssd\bundle_rpi_20260222_211132`
- [x] Limpar bundle remoto para ficar enxuto (somente componentes necessários ao crawler)
- [x] Executar rodada inicial de recoleta enriquecida com parâmetros conservadores de rede

## Notas

- Melhor MAE atual no pipeline arena residual permanece `209.75` (`v2`), e o foco desta etapa é **infra/coleta de dados** para próxima redução de erro.
- A recoleta enriquecida vai priorizar qualidade e reuso de cache para minimizar requisições desnecessárias.
- Backup da limpeza do bundle remoto: `\\<LAN>\ssd\bundle_rpi_20260222_211132_pruned_backup_20260226_125643`.

## Benchmark de Velocidade (Atual)

- [x] Rodar **5 estratégias realmente diferentes** para coletar o mesmo dado (`summary` enriquecido)
- [x] Medir por estratégia: `ok/min`, `sucesso`, `falhas`, `backoffs`
- [x] Escolher estratégia padrão de coleta pela melhor velocidade com adaptação a bloqueios

## Ajuste Operacional (2026-02-26)

- [x] Adicionar modo misto de coleta: sobrescrever processados + acrescentar novos (`--recollect-and-append`)
- [x] Remover gate operacional por `resilience` (manter apenas coleta de `level 80` por padrão)
- [x] Validar execução curta (`--once --dry-run`) com estado real
- [x] Sincronizar alteração para o bundle RBP remoto

## Política de Parada (2026-02-26)

- [x] Implementar política padrão: parar apenas por `bloqueio detectado` ou `idle sem novos players`
- [x] Adicionar `--idle-stop-seconds` (padrão `60`)
- [x] Adicionar `--block-detect-consecutive-errors` + `--no-stop-on-block-detected`
- [x] Desativar regras legadas por padrão e expor `--enable-legacy-stop-rules`
- [x] Corrigir recuperação automática de cache HTTP corrompido (`database disk image is malformed`)
- [x] Validar em `--dry-run` e sincronizar no bundle RBP

## TUI Isolada (2026-02-26)

- [x] Criar projeto isolado em `tui/` sem alterar fluxo do crawler
- [x] Implementar dashboard com cores clássicas por classe e gráfico de barras
- [x] Implementar modo `demo` (simulação) e `live` (estado real)
- [x] Implementar fallback automático para modo texto em caso de erro
- [x] Gerar `layout_spec_v1.json` para reprodução automatizada
- [x] Executar revisão minuciosa com smoke tests (`demo/live/text`)
- [x] Sincronizar pasta `tui/` no bundle RBP

## TUI Operacional v2 (Visao Operacional) (2026-02-26)

- [x] Reorganizar apenas o painel `Visao Operacional` (sem alterar `Players Coletados por Classe`)
- [x] Adicionar animações úteis e discretas para estado em tempo real (rede/funil/atividade)
- [x] Melhorar hierarquia visual dos KPIs (saúde, funil, throughput, tendência)
- [x] Validar smoke (`demo --once`, `live --once`, fallback texto)
- [x] Sincronizar alterações para `\\<LAN>\ssd\bundle_rpi_20260222_211132\tui`

## TUI Operacional v3 (Refino Forte para Leigo) (2026-02-26)

- [x] Refatorar `Visao Operacional` com categorias fixas e hierarquia forte
- [x] Traduzir termos técnicos para rótulos leigos sem perder precisão numérica
- [x] Garantir unidade numérica em todos os indicadores (`ms`, `%`, contagens)
- [x] Adicionar animações úteis e legíveis (status, pulso, tendência)
- [x] Validar smoke (`demo/live/text`) e sincronizar para RBP

## TUI Operacional v4 (Escala de Cor + Total XY) (2026-02-26)

- [x] Aplicar escala verde->vermelho para latência (`ms`) e `falhas seguidas`
- [x] Incluir bloco `Total` abaixo de `Players Coletados por Classe`
- [x] Renderizar gráfico X-Y com amostragem em eixo X exponencial e linha fina
- [x] Exibir numeração explícita abaixo do gráfico (`x` e `y` em números)
- [x] Adicionar proteções para histórico curto, dados ausentes e valores inválidos
- [x] Validar smoke, compile e sincronizar no RBP

## TUI Operacional v5 (Suavização + FPS desacoplado) (2026-02-26)

- [x] Investigar lentidão percebida com `--refresh-seconds 0.8`
- [x] Desacoplar frequência de render (`fps`) da frequência de leitura de dados
- [x] Elevar suavidade da curva XY com rasterização de alta resolução (braille/subpixel)
- [x] Validar em `120x30` e `130x40` com smoke `demo/live/text`

## TUI Rust v1 (Acoplamento ao Crawler) (2026-02-27)

- [x] Criar projeto isolado `tui_rs/` com `ratatui` + `crossterm` + `serde_json`
- [x] Implementar leitura de `data/raw/adaptive_crawler_state.json` com parser tolerante
- [x] Replicar layout operacional (classes + total XY + painel de operação)
- [x] Implementar modo `demo` e modo `live` com CLI simples
- [x] Otimizar para RPi (render leve, baixo custo, taxa de atualização configurável)
- [x] Criar script de execução no RPi com `CARGO_TARGET_DIR` fora do SSD ro
- [x] Validar build e execução local (Windows) e documentar comandos RPi

## TUI Rust v2 (Integração no Launcher) (2026-02-27)

- [x] Integrar `--tui-rs` no `run_crawler_rpi.sh` sem quebrar `--tui` legado
- [x] Adicionar flags de runtime (`--tui-rs-mode`, `--tui-rs-refresh-seconds`, `--tui-rs-fps`, `--tui-rs-state-file`)
- [x] Garantir fallback seguro quando `tmux`/`cargo`/script não estiver disponível
- [x] Documentar comando completo no `README.md`

## TUI Rust v3 (Quit Total por Tecla) (2026-02-27)

- [x] Implementar `--quit-file` no binário Rust e disparo ao pressionar `q`/`Esc`
- [x] Integrar monitor de sinal no launcher para encerrar crawler ao quit da TUI
- [x] Adicionar opção `--tui-rs-quit-file` no launcher
- [x] Atualizar documentação com comportamento de quit total
- [x] Sincronizar alterações no bundle RBP

## TUI Rust v4 (Foco + Diagnóstico de Acoplamento) (2026-02-27)

- [x] Adicionar `--tui-rs-focus` (`tui|crawler|none`) para controlar foco inicial no tmux
- [x] Forçar foco na janela da TUI por padrão para reduzir falso positivo de "não abriu"
- [x] Exibir IDs de janela crawler/TUI no launcher para depuração operacional
- [x] Emitir diagnóstico automático quando a janela da TUI morrer logo após start

## TUI Rust v5 (Validação Precisa sem Log Spam) (2026-02-27)

- [x] Implementar `health snapshot` em JSON sobrescrito (sem crescimento) no binário Rust
- [x] Expor flags no launcher (`--tui-rs-health-file`, `--tui-rs-health-interval-seconds`)
- [x] Implementar checker operacional (`tui_rs/check_tui_health.py`) com saída de uma linha + códigos de status
- [x] Documentar comando de verificação rápida no `README.md` e `tui_rs/README.md`
- [x] Validar leitura/escrita atômica para evitar arquivo parcial durante atualização

## TUI Rust v6 (Anti-Órfão + Lints + Testes) (2026-02-27)

- [x] Implementar monitor anti-órfão no launcher para encerrar crawler ao perder sessão dona
- [x] Expor flags de controle (`--no-stop-on-owner-exit`, `--owner-exit-grace-seconds`)
- [x] Criar `pyproject.toml` (base do `dlLogs`) com Ruff + Ty em modo rígido
- [x] Atualizar ferramentas no Windows (`ruff`, `ty`, `mypy`, `pytest`) e componentes Rust (`clippy`, `rustfmt`)
- [x] Criar scripts de lint (`scripts/lint_python.ps1`, `scripts/lint_rust.ps1`)
- [x] Criar suíte automatizada para TUI/acoplamento (`tests/`)
- [x] Validar `5 passed` em `pytest tests -q` + lint Python/Rust sem falhas

## Crawler v44 (Anti-Travamento em Produção) (2026-02-27)

- [x] Diagnosticar travamento real (`cycle` congelado com `details` parcial e `profiles_try=0`)
- [x] Adicionar limite de tempo total por request HTTP (`fetch_text` / `post_form_json`)
- [x] Diferenciar timeout de `matchinfo` (mais curto) para evitar bloqueio longo de root
- [x] Adicionar timeout de root de history e corte por streak de erros em details
- [x] Adicionar timeout máximo de ciclo para impedir ciclo infinito/longo demais
- [x] Criar testes automatizados para `wall timeout` de rede
- [x] Validar suíte (`pytest tests -q`) e lints após correção

## TUI Rust v45 (Pane Dead no Startup) (2026-02-27)

- [x] Remover saída por `Esc` e manter quit explícito por `q`
- [x] Adicionar proteção anti-quit acidental nos primeiros 1.5s de execução da TUI
- [x] Adicionar retry único automático no launcher quando a pane da TUI morre no startup
- [x] Atualizar documentação (`README.md`, `tui_rs/README.md`) para quit via `q`
- [x] Validar com `cargo check`, lints e `pytest tests -q`

## TUI Rust v46 (Anti-Q Acidental) (2026-02-27)

- [x] Confirmar que `Pane is dead (status 0)` implica saída limpa da TUI (quit acionado)
- [x] Implementar confirmação de quit: `q` duas vezes em até 2s
- [x] Manter janela de proteção inicial de 1.5s no startup
- [x] Atualizar docs para novo comportamento de quit
- [x] Validar regressão (`cargo check`, `pytest`, lints)
