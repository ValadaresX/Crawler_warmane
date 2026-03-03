# Pipeline Checklist (HP -> GS)

Este arquivo serve para pausar/retomar o processo sem perder contexto.

Como usar:
- Marque `[x]` quando concluir a etapa.
- Preencha `Owner`, `Data`, `Notas` no checkpoint.
- Ao retomar, continue do primeiro item `[ ]`.

## Checkpoint Atual

- `Status`: Fase 54 concluída (quit total limpa no tmux sem pane morto)
- `Checkpoint ID`: `CP-48`
- `Owner`: usuário
- `Data`: 2026-02-27
- `Notas`: Ajustado encerramento por `Esc`/`q` para fechar completamente sem deixar `Pane is dead`: desliga `remain-on-exit` após startup saudável e monitor de quit passa a sinalizar diretamente o PID do crawler, com kill imediato da janela TUI.

## Fase 1: Coleta e Integridade de Dados

- [x] Coletar match-history completo do Narako
- [x] Deduplicar por `(name, realm)`
- [x] Limpar falhas permanentes de coleta no `state`
- [x] Confirmar unicidade no dataset final (`JSON` e `CSV`)
- [x] Fazer snapshot versionado do dataset atual (`v1`)
- [x] Registrar metadados do snapshot (timestamp, total rows, origem)

Comandos úteis:

```bash
python -c "import json; s=json.load(open('data/raw/state_match_history.json',encoding='utf-8')); print(len(s['players']), len(s['processed_players']), len(s['failed_players']))"
python -c "import json,collections; d=json.load(open('data/processed/players_dataset.json',encoding='utf-8')); c=collections.Counter((r['name'],r['realm']) for r in d); print(len(d), len(c), sum(v>1 for v in c.values()))"
```

## Fase 2: Baseline Estatístico (Offline)

- [x] Criar notebook/script de EDA (`HP`, `GS`, `classe`, `realm`)
- [x] Treinar baseline `HP only` (regressão simples)
- [x] Treinar baseline `HP + classe` (class-aware)
- [x] Medir MAE, RMSE, R² em validação holdout
- [x] Salvar relatório de baseline em `reports/baseline_v1.md`

## Fase 3: Modelo de Faixa (Recomendado)

- [x] Treinar modelo quantílico por classe (P10/P50/P90)
- [x] Avaliar cobertura dos intervalos (ex.: alvo 90%)
- [x] Calibrar intervalos (conformal/CQR ou ajuste empírico)
- [x] Congelar artefato `model_v1` para export
- [x] Salvar relatório técnico em `reports/model_v1.md`

## Fase 4: Export para Addon (Inferência Leve)

- [x] Definir formato final de export (tabela Lua ou JSON intermediário)
- [x] Exportar parâmetros compactos por classe
- [x] Implementar interpolação/lookup O(1) no addon
- [x] Exibir `GS estimado` + `faixa` + `confiança`
- [x] Criar fallback para casos sem classe/entrada inválida

## Fase 5: Validação Funcional em Arena

- [x] Testar em sessão real de arena
- [x] Comparar previsão vs GS real (amostra manual)
- [x] Ajustar thresholds de confiança
- [x] Revisar UX no addon (sem poluir combate)
- [x] Aprovar release interna `addon_v1`

## Fase 6: Operação e Manutenção

- [x] Definir rotina de atualização de dataset (semanal/quinzenal)
- [x] Rodar coleta incremental (`--full-sync`) periodicamente
- [x] Re-treinar modelo e comparar com versão anterior
- [x] Versionar artefatos (`dataset_vN`, `model_vN`, `addon_vN`)
- [x] Logar mudanças em `docs/pipeline/CHANGELOG_PIPELINE.md`

## Fase 7: Evolução Robusta (v2)

- [x] Implementar pipeline `v2` com calibração robusta por classe (sem paliativo)
- [x] Treinar e selecionar hiperparâmetros com critério de robustez (MAE + cobertura)
- [x] Aplicar correção de viés por classe e calibração conformal por classe (com shrinkage)
- [x] Gerar lookup `v2` com monotonicidade e invariantes (`p10 <= p50 <= p90`)
- [x] Exportar artefatos versionados `artifacts/model_v2/` e `exports/model_v2/`
- [x] Publicar relatórios `reports/baseline_v2.md` e `reports/model_v2.md`
- [x] Atualizar changelog com resultados comparativos v1 vs v2

## Retomada Rápida (TL;DR)

- [x] Verificar estado atual:

```bash
python -c "import json; s=json.load(open('data/raw/state_match_history.json',encoding='utf-8')); print('matches',len(s['processed_match_ids']),'players',len(s['players']),'processed',len(s['processed_players']),'failed',len(s['failed_players']))"
```

- [x] Se precisar atualizar base:

```bash
python scripts/build_dataset_from_match_history.py "https://armory.warmane.com/character/Narako/Blackrock/match-history" --full-sync --skip-failed --min-delay-seconds 2.0 --max-delay-seconds 4.0 --break-every-requests 20 --break-min-seconds 10 --break-max-seconds 25
```

- [x] Continuar a partir da primeira tarefa não concluída em `Fase 2`.

## Fase 8: Organização Estrutural (Repo/Data)

- [x] Mover CLIs e pipelines para `scripts/`
- [x] Mover checklist/changelog para `docs/pipeline/`
- [x] Mover relatório de pesquisa para `docs/research/`
- [x] Reorganizar `data/` em `raw/`, `processed/`, `cache/`, `snapshots/`
- [x] Separar descarte local em `_trash/` (limpeza não destrutiva)

## Fase 9: Gestão de Lotes Offline (Retomada Segura)

- [x] Documentar escopo inicial do algoritmo na raiz para retomada de contexto
- [x] Criar script único de lotes com fila persistente e priorização por classe
- [x] Implementar barra de progresso simples (sem spam) em linha única
- [x] Implementar escrita atômica para evitar corrupção em interrupções
- [x] Implementar parada graciosa (`SIGINT/SIGTERM`) e retomada automática
- [x] Executar teste de primeiro lote e validar artefatos de estado/saída
- [x] Implementar modo nativo contínuo (`--run-forever`) com parada por platô de classes
- [x] Otimizar coleta online para usar `class_hint` do `matchinfo` e reduzir profile fetch por classe
- [x] Gerar fluxograma visual do algoritmo atualizado na raiz do projeto
- [x] Implementar crawler adaptativo em grafo (dinâmico, sem limite de ciclos por padrão)
- [x] Mapear dependências Python e gerar `requirements.txt` na raiz
- [x] Criar snapshot completo para Raspberry Pi OS no estágio atual de coleta
- [x] Criar script de bootstrap (`run_crawler_rpi.sh`) para checar/instalar libs e iniciar crawler


## Fase 10: Evolução Portável (v3)

- [x] Executar ablação de features no modelo quantílico (`lean` vs `rich`)
- [x] Rodar benchmark opcional com CatBoost (quando disponível no ambiente)
- [x] Calibrar arredondamento de `P50` para melhorar acerto exato de GS
- [x] Exportar artefatos `v3` em formato portátil (JSON agnóstico de linguagem)
- [x] Publicar relatórios `reports/baseline_v3.md` e `reports/model_v3.md`


## Fase 11: Modelo por Classe (v4)

- [x] Treinar modelos separados por classe
- [x] Calibrar por classe (offset + conformal + arredondamento)
- [x] Gerar comparativo v3 vs v4 por classe


## Fase 12: Hibrido Robusto (v4.1)

- [x] Comparar v3 vs modelo por classe no mesmo holdout
- [x] Selecionar por classe com regra de seguranca (MAE + cobertura)
- [x] Exportar lookup hibrido e comparativo por classe

## Fase 13: Benchmark Congelado + Coleta Dirigida (v4.2)

- [x] Congelar split train/calib/test para comparações justas
- [x] Treinar v3, v4_class e híbrido no mesmo benchmark
- [x] Gerar alvos de coleta por classe/faixa de HP com base em resíduos

## Fase 14: Execução GPU-First (v4.2+)

- [x] Definir CatBoost como caminho padrão de treino
- [x] Desativar busca GBR por padrão (reativação apenas por flag)
- [x] Forçar tentativa de treino em GPU por padrão
- [x] Permitir fallback CPU somente quando configurado e inevitável
- [x] Validar execução completa v4.2 com política GPU-first e artefatos finais

## Fase 15: Data Treatment Robusto (v4.3)

- [x] Implementar deduplicação temporal por `(name, realm)` com score de confiabilidade
- [x] Implementar limpeza robusta de outliers por classe/faixa de HP
- [x] Implementar balanceamento de treino por classe + `hp_bin`
- [x] Adicionar barra de progresso simples para etapas longas
- [ ] Rodar treino completo v4.3 e comparar métricas com v4.2

## Fase 16: Seed Ladder + Árvore Multi-Root

- [x] Integrar parsing de ladder para seed local de players (`SoloQ/1/80`)
- [x] Limitar seed inicial por rank (`top N`, padrão 50)
- [x] Priorizar seeds da ladder no topo da árvore de descoberta
- [x] Processar múltiplos roots de `match-history` por ciclo (padrão 10)
- [x] Expor flags CLI para `ladder_seed_*` e `history_players_per_cycle`
- [x] Corrigir `dynamic_profiles_per_cycle` para não forçar coleta quando `need=0`

## Fase 17: Automação Operacional do Crawler

- [x] Implementar controle de atraso adaptativo por qualidade de rede/HTTP
- [x] Implementar retry de `failed_players` com cooldown e backoff por tipo de falha
- [x] Implementar telemetria de funil por ciclo (descoberta/conversão/falhas)
- [x] Implementar monitor de ganho marginal por classe e condição de parada opcional
- [x] Implementar backup local automático pós-execução no `run_crawler_rpi.sh`
- [x] Implementar sync automático opcional para diretório externo via `SYNC_TARGET_DIR`
- [x] Ajustar `collect_surplus` para não ser bloqueado por `respect_class_plateau`

## Fase 18: Protótipo Dashboard TUI (Isolado)

- [x] Criar módulo separado `apps/crawler_tui/v1_test`
- [x] Implementar layout inspirado em `tui.md` (header ornamental, split 60/40, footer com keybinds)
- [x] Implementar modo `demo` com animações em tempo real
- [x] Implementar modo `live` lendo `data/raw/adaptive_crawler_state.json`
- [x] Adicionar visual de torres para throughput/falhas
- [x] Publicar instruções de execução em `apps/crawler_tui/v1_test/README.md`
- [x] Aplicar cores clássicas por classe + alinhamento real de colunas no painel esquerdo
- [x] Remover modo responsivo e fixar proporção operacional em `120x30` com aviso para terminal menor
- [x] Substituir bloco redundante por `Priority Queue` + `Recent Cycles` com métricas derivadas
- [x] Bloquear render e atualização de snapshot quando terminal iniciar menor que `120x30`
- [x] Externalizar layout/labels para `layout_schema.json` e carregar por `--layout-schema`
- [x] Refatorar `dashboard_tui.py` para reduzir duplicação (helpers de table/panel/grid/layout)
- [x] Remover código morto não utilizado (campos/séries de torres/funções órfãs)
- [x] Adicionar flag operacional `--tui` no launcher do crawler (`run_crawler_rpi.sh`) com sync via `state-file`

## Fase 19: Coleta Dirigida por Faixa de HP (Long Run)

- [x] Adicionar meta por classe com filtro de HP no crawler (`--target-hp-min`, `--target-hp-max`)
- [x] Adicionar modo `hybrid` para executar `discover` e `convert` no mesmo ciclo
- [x] Ajustar modo `auto` para reativar discovery quando faltar backlog nas classes com déficit
- [x] Atualizar logs de ciclo para explicitar alvo de faixa de HP ativo
- [x] Atualizar documentação operacional no `README.md` com comando de execução longa

## Fase 20: Laboratório Isolado HP+Classe->GS

- [x] Sincronizar dados mais recentes do RBP para o projeto local
- [x] Criar subprojeto isolado (`subprojetos/lab_hp_classe_gs_isolado`)
- [x] Copiar dataset e estado para `subprojetos/lab_hp_classe_gs_isolado/data/input`
- [x] Criar script inicial de avaliação supervisionada (`HP + classe -> GS`)
- [x] Gerar relatório inicial de acurácia no subprojeto isolado

## Fase 21: Dashboard de Treino GPU + Export Addon Leve

- [x] Implementar treino em tempo real com painel gráfico no terminal (Rich Live)
- [x] Forçar treino em GPU sem fallback para CPU no modelo principal
- [x] Comparar automaticamente abordagem global vs abordagem por classe
- [x] Exportar artefato addon-friendly O(1) em lookup (`addon_lookup_hp_class_gs_v1.json`)
- [x] Atualizar documentação do laboratório com fluxo GPU obrigatório

## Fase 22: Hardening do Dashboard de Treino (120x30)

- [x] Corrigir exibição de `No Improve` para não passar de `patience` no painel
- [x] Exibir placeholder na tabela de classes enquanto não houver `MAE` por classe
- [x] Adicionar gráfico de barras em tempo real (`MAE atual`, `MAE melhor`, `RMSE`)
- [x] Forçar render da sessão visual em proporção `120x30`
- [x] Bloquear execução live em terminal menor que `120x30` (ou liberar com flag explícita)
- [x] Criar suíte `pytest` para regressão visual/estado do dashboard
- [x] Evitar encerramento visual abrupto ao fim (painel persistente + opções `pause/hold`)
- [x] Executar suíte e validar resultado (`7 passed`)

## Fase 23: Benchmark HPO (Optuna vs GA) no Laboratório Isolado

- [x] Implementar script de benchmark comparativo (`benchmark_hpo_optuna_ga_hp_classe_gs.py`)
- [x] Reutilizar função única de treino/avaliação em GPU para os dois métodos
- [x] Implementar busca `Optuna (TPE)` com budget configurável
- [x] Implementar busca `GA` com budget equivalente e seed fixa
- [x] Publicar relatório comparativo em `reports/hpo_optuna_vs_ga_hp_class_gs_v1.{json,md}`
- [x] Criar testes de regressão dos utilitários GA em `tests/test_hpo_optuna_ga.py`
- [x] Validar suíte completa do laboratório (`10 passed`)
- [x] Validar benchmark longo (`budget=24`, `iterations=1200`) com artefatos de melhor modelo

## Fase 24: Linha Exponencial de Melhor MAE + Modo Teste Visual

- [x] Substituir painel de barras por gráfico de linha X/Y em tempo real
- [x] Plotar Y com série de melhor MAE acumulado (cumulative min)
- [x] Implementar escala exponencial no eixo X do gráfico
- [x] Adicionar modo `--visual-test-mode` com `--visual-test-steps` e `--visual-test-delay`
- [x] Validar render em `120x30` no smoke do modo visual
- [x] Atualizar testes e validar suíte do laboratório (`12 passed`)

## Fase 25: Pesquisa de Tratamento de Dados (Meta MAE<=150)

- [x] Definir 5 hipóteses de tratamento e registrar racional técnico
- [x] Implementar runner comparativo GPU (`pesquisa_tratamento_dados_mae150.py`)
- [x] Executar 5 experimentos no mesmo split para comparação justa
- [x] Publicar relatório comparativo em `reports/pesquisa_tratamento_dados_mae150_v1.{json,md}`
- [x] Identificar abordagens não promissoras para evitar retrabalho
- [x] Refazer rodada com escopo de produção (`estimated_hp` + `class`) sobrescrevendo resultados anteriores
- [x] Confirmar melhor hipótese válida para addon (`E3_CLASS_SPECIALIST`, MAE=237.6365)
- [x] Confirmar que meta `MAE<=150` não foi atingida neste escopo
- [x] Atualizar suíte e validar estabilidade (`16 passed`)

## Fase 26: Arena Observável -> GS (Combat Log Residual v1)

- [x] Implementar parser de rounds do `rotAval` (`index.json` + `round_*.txt`)
- [x] Extrair features por inimigo nas janelas `0-15s` e `0-30s`
- [x] Fazer join com labels do armory local (`players_dataset.csv`) com relatório de cobertura/ambiguidade
- [x] Treinar baseline/prior/residual com split por `enemy_guid` (sem leakage)
- [x] Publicar artefatos:
  - [x] `data/processed/arena_enemy_round_dataset_v1.csv`
  - [x] `reports/arena_residual_v1.md`

## Fase 42: Observabilidade da TUI Rust sem Spam

- [x] Implementar arquivo de saúde em JSON sobrescrito (sem append) no binário Rust
- [x] Expor parâmetros no launcher para caminho e intervalo do health snapshot
- [x] Criar verificador operacional em uma linha com `exit code` para automação
- [x] Documentar comando de checagem rápida no README principal e no README da TUI Rust
  - [x] `artifacts/model_arena_residual_v1/run_summary_v1.json`
  - [x] `data/processed/arena_enemy_round_dataset_v2.csv`
  - [x] `reports/arena_residual_v2.md`
  - [x] `artifacts/model_arena_residual_v2/run_summary_v2.json`

## Fase 27: Export Addon Leve + Robustez v2

- [x] Implementar export addon leve para arena (`JSON + Lua`) baseado em sinais observáveis
- [x] Publicar artefatos de export:
  - [x] `exports/model_arena_v2/gs_arena_lookup_v2.json`
  - [x] `exports/model_arena_v2/gs_arena_estimator_v2.lua`
  - [x] `reports/arena_export_addon_v2.md`
  - [x] `artifacts/model_arena_residual_v2/export_addon_summary_v2.json`
- [x] Rodar robustez multi-seed do modelo principal v2
- [x] Publicar robustez:
  - [x] `reports/arena_residual_v2_robustness.md`
  - [x] `artifacts/model_arena_residual_v2/robustness_summary_v2.json`

## Fase 28: HP -> Stamina + Prior GS

- [x] Implementar experimento dedicado (`BaseHealth + k_spec + LUT(stam->GS)`)
- [x] Comparar cenário produção (`hp_mode=auto`) vs cenário potencial (`hp_mode=oracle_label`)
- [x] Publicar artefatos:
  - [x] `scripts/run_arena_hp_stamina_pipeline_v1.py`
  - [x] `reports/arena_hp_stamina_pipeline_v1.md`
  - [x] `artifacts/model_arena_residual_v2/hp_stamina_summary_v1.json`

## Fase 29: Spell Signatures (Dano/Cura) no Residual

- [x] Implementar parser v3 com assinaturas de spells de dano/cura e vocabulário por janela
- [x] Treinar e comparar v3 (`spells`) vs v2 (referência) no mesmo split por `enemy_guid`
- [x] Adicionar gate por calibração para não degradar (`use_spells_by_calib_gate`)
- [x] Publicar artefatos:
  - [x] `scripts/run_arena_log_residual_v3_spells.py`
  - [x] `data/processed/arena_enemy_round_dataset_v3_spells.csv`
  - [x] `reports/arena_residual_v3_spells.md`
  - [x] `artifacts/model_arena_residual_v3_spells/run_summary_v3_spells.json`

## Fase 30: Refatoração Crawler Enriquecido (RBP)

- [x] Planejar etapa em `docs/pipeline/todo.md` antes da execução
- [x] Refatorar cliente HTTP com:
  - [x] rate limit por RPS
  - [x] backoff exponencial com jitter para `429/503`
  - [x] suporte a `Retry-After`
  - [x] cache condicional por URL (`ETag`, `Last-Modified`, `If-None-Match`, `If-Modified-Since`)
  - [x] rotação de `User-Agent` e headers HTTP
- [x] Ampliar parser/analyzer para coletar `summary` completo:
  - [x] Character Stats completos
  - [x] itens com `item_id`, `enchant`, `gems`
- [x] Persistir datasets em Parquet:
  - [x] `data/processed/players_dataset.parquet`
  - [x] `data/processed/players_items.parquet`
- [x] Habilitar modo de recoleta de players já processados com checkpoint/retomada
- [x] Reduzir padrão de varredura sequencial (embaralhamento de páginas/IDs + visitas randômicas)
- [x] Sincronizar crawler refatorado para o bundle `\\<LAN>\ssd\bundle_rpi_20260222_211132`
- [x] Limpar bundle remoto para manter somente artefatos necessários ao crawler
- [x] Executar rodada inicial de recoleta enriquecida no bundle (fim a fim)

## Fase 31: Modo Misto de Coleta (Processados + Novos)

- [x] Implementar flag `--recollect-and-append` no crawler
- [x] Manter sobrescrita dos processados com atualização de `collected_at_utc`
- [x] Permitir inclusão de players novos no mesmo ciclo de `convert`
- [x] Remover bloqueio operacional por `min_resilience` no fluxo de coleta
- [x] Aplicar regra de elegibilidade por nível (`level 80` por padrão)
- [x] Validar em `--once --dry-run` com estado real
- [x] Sincronizar patch para bundle remoto RBP

## Fase 32: Política de Parada Operacional

- [x] Implementar detector de bloqueio por sinais de HTTP/challenge (`403/429`, Cloudflare/captcha, erros consecutivos)
- [x] Implementar parada por inatividade de novos players em segundos (`--idle-stop-seconds`, padrão 60)
- [x] Limitar regras de parada padrão a: bloqueio detectado OU inatividade de novos players
- [x] Manter regras legadas disponíveis apenas via `--enable-legacy-stop-rules`
- [x] Corrigir recuperação automática quando cache HTTP SQLite estiver corrompido
- [x] Validar comportamento com `--dry-run` e sincronizar no RBP

## Fase 33: Dashboard TUI Isolado (Sem Plug no Crawler)

- [x] Criar pasta isolada `tui/` com entrypoint e runner próprios
- [x] Implementar dashboard com hierarquia visual (header, classes, KPIs, footer)
- [x] Aplicar cores clássicas de classes WoW 3.3.5
- [x] Implementar modo `demo` para simulação sem dependência do crawler
- [x] Implementar modo `live` lendo `data/raw/adaptive_crawler_state.json`
- [x] Implementar fallback para modo texto em caso de erro da TUI
- [x] Publicar especificação de layout em JSON para reprodução automatizada
- [x] Validar com smoke tests e sincronizar para o RBP

## Fase 34: TUI Operacional v2 (Visao Operacional)

- [x] Reorganizar somente o painel `Visao Operacional` (sem alterar `Players Coletados por Classe`)
- [x] Adicionar animações úteis para leitura de estado em tempo real
- [x] Separar KPIs por bloco lógico (`Saude da Rede`, `Funil`, `Fluxo`, `Tendencia`)
- [x] Validar smoke (`demo --once`, `live --once`, fallback texto)
- [x] Sincronizar `tui/dashboard_tui.py` para o bundle RBP

## Fase 35: TUI Sofisticada v3 (Linguagem Leiga + Métricas Numéricas)

- [x] Reestruturar `Visao Operacional` com divisão por categorias claras e hierarquia forte
- [x] Trocar labels técnicos por nomes de leitura leiga sem perder precisão
- [x] Garantir que métricas essenciais exibam número e unidade (`ms`, `%`, contagem/score)
- [x] Harmonizar animações úteis (spinner, pulso, marcador de tendência) com foco operacional
- [x] Validar smoke (`demo/live/text`) e sincronizar no bundle RBP

## Fase 36: Escala de Cor + Total XY Exponencial

- [x] Aplicar escala verde->vermelho em `ms` e `falhas seguidas` no painel operacional
- [x] Incluir bloco `Total` abaixo da sessão de classes
- [x] Renderizar gráfico X-Y com linha fina e eixo X com amostragem exponencial
- [x] Exibir numeração explícita abaixo do gráfico (`x(ciclo)` e `y(players)`)
- [x] Adicionar mitigação para valores inválidos e histórico insuficiente
- [x] Validar (`py_compile`, `demo/live/text`) e sincronizar no RBP

## Fase 37: Suavização de Render + Curva XY Fina

- [x] Diagnosticar impacto de `--refresh-seconds 0.8` na fluidez visual
- [x] Separar `leitura_dados` de `render fps` para reduzir sensação de lentidão
- [x] Implementar curva XY em alta resolução com braille/subpixel
- [x] Validar em tela operacional ampla (`130x40`) e padrão
- [x] Sincronizar atualização no bundle RBP

## Fase 38: TUI Rust v1 (Ratatui + Acoplamento Crawler)

- [x] Criar projeto isolado `tui_rs/` com `Cargo.toml` e binário principal
- [x] Implementar leitura tolerante de `adaptive_crawler_state.json`
- [x] Implementar layout: classes por cor + `Total` X-Y exponencial + painel operacional
- [x] Implementar modos `live`, `demo` e `text`
- [x] Otimizar loop para RPi (leitura desacoplada de render e cache por mtime)
- [x] Validar `cargo check` e execução local (`--mode text --once`, `--mode demo --once`)
- [x] Documentar execução em `tui_rs/README.md` e script `tui_rs/run_tui_rs.sh`

## Fase 39: Launcher Integrado com TUI Rust

- [x] Adicionar suporte `--tui-rs` no `run_crawler_rpi.sh`
- [x] Expor opções `--tui-rs-mode`, `--tui-rs-refresh-seconds`, `--tui-rs-fps`, `--tui-rs-state-file`
- [x] Manter compatibilidade com `--tui` legado (com prioridade para Rust quando ambos ativos)
- [x] Implementar fallback seguro sem interromper crawler quando dependências de TUI faltarem
- [x] Atualizar documentação de execução no `README.md`

## Fase 40: Quit Total via Tecla na TUI Rust

- [x] Adicionar `--quit-file` na TUI Rust e escrever sinal em `q`/`Esc`
- [x] Implementar monitor de sinal no `run_crawler_rpi.sh`
- [x] Encerrar crawler de forma limpa quando quit for solicitado pela TUI
- [x] Expor `--tui-rs-quit-file` para customizar o caminho do sinal
- [x] Atualizar documentação e sincronizar no RBP

## Fase 41: Diagnóstico de Acoplamento (tmux foco/visibilidade)

- [x] Adicionar `--tui-rs-focus` com validação de entrada
- [x] Definir foco padrão em `tui` para visualização imediata
- [x] Exibir janela atual do crawler e janela da TUI para troubleshooting
- [x] Diagnosticar pane morta após start com captura das últimas linhas
- [x] Atualizar documentação de execução com foco explícito

## Fase 43: Anti-Órfão + Qualidade de Código

- [x] Adicionar monitor anti-órfão no launcher para encerrar ao perder sessão dona
- [x] Expor `--no-stop-on-owner-exit` e `--owner-exit-grace-seconds`
- [x] Criar `pyproject.toml` na raiz com Ruff + Ty (regras rígidas)
- [x] Atualizar no Windows: `ruff`, `ty`, `mypy`, `pytest`
- [x] Garantir componentes Rust `clippy` e `rustfmt`
- [x] Criar scripts operacionais de lint:
  - [x] `scripts/lint_python.ps1`
  - [x] `scripts/lint_rust.ps1`
- [x] Criar testes automatizados para TUI/acoplamento:
  - [x] `tests/test_tui_rs_health_checker.py`
  - [x] `tests/test_tui_rs_runtime.py`
  - [x] `tests/test_coupling_launcher_contract.py`
- [x] Validar execução:
  - [x] `powershell -ExecutionPolicy Bypass -File scripts/lint_python.ps1`
  - [x] `powershell -ExecutionPolicy Bypass -File scripts/lint_rust.ps1`
  - [x] `python -m pytest tests -q` (`5 passed`)

## Fase 44: Anti-Travamento de Ciclo (Produção)

- [x] Adicionar limite de tempo total por request em `network.py` (`max_wall_seconds`)
- [x] Aplicar `wall timeout` nos wrappers de rede do crawler
- [x] Introduzir timeout curto específico para `matchinfo` (`--matchinfo-timeout-seconds`)
- [x] Introduzir timeout total específico de `matchinfo` (`--matchinfo-request-wall-timeout-seconds`)
- [x] Introduzir timeout por root de history (`--history-root-max-seconds`)
- [x] Introduzir corte por streak de erros em details (`--history-detail-error-streak-stop`)
- [x] Introduzir timeout máximo por ciclo (`--cycle-max-seconds`)
- [x] Adicionar teste automatizado de wall-timeout:
  - [x] `tests/test_network_wall_timeout.py`
- [x] Validar regressão:
  - [x] `python -m pytest tests -q` (`7 passed`)
  - [x] `powershell -ExecutionPolicy Bypass -File scripts/lint_python.ps1`

## Fase 45: Estabilidade da TUI Rust no Startup

- [x] Remover encerramento por `Esc` e manter quit somente por `q`
- [x] Adicionar debounce de quit no startup (1.5s)
- [x] Adicionar retry único automático no launcher para pane dead no boot
- [x] Atualizar documentação de keybinds (`q` para quit total)
- [x] Validar:
  - [x] `cargo check --manifest-path tui_rs/Cargo.toml`
  - [x] `python -m pytest tests -q` (`7 passed`)
  - [x] lints Python/Rust sem falhas

## Fase 46: Proteção Anti-Q Acidental

- [x] Implementar confirmação de saída (`q` duas vezes em até 2s)
- [x] Preservar bloqueio de quit nos primeiros 1.5s após start
- [x] Atualizar documentação de operação para novo keybind
- [x] Validar:
  - [x] `cargo check --manifest-path tui_rs/Cargo.toml`
  - [x] `python -m pytest tests -q` (`7 passed`)
  - [x] lints Python/Rust sem falhas

## Fase 47: README de Handoff Completo (TUI Rust)

- [x] Reestruturar `tui_rs/README.md` com contexto completo de operação
- [x] Documentar arquitetura e contrato mínimo do `adaptive_crawler_state.json`
- [x] Consolidar comandos em linha única para RPi e Windows
- [x] Documentar integração oficial com `run_crawler_rpi.sh --tui-rs`
- [x] Documentar health snapshot + checker com códigos de saída
- [x] Documentar troubleshooting e tuning de performance no RPi

## Fase 48: Documentação Operacional (Prevenção de Erros)

- [x] Consolidar anti-padrões explícitos (o que não fazer)
- [x] Definir regras de conduta e checklist de pré-execução
- [x] Registrar definição de pronto (DoD) e priorização em incidentes

## Fase 49: Documentação Local do `tui_rs`

- [x] Documentar contratos que não podem quebrar (`mode`, `quit`, `health`)
- [x] Documentar anti-padrões e fluxo de validação local da pasta
- [x] Registrar lição de escopo após feedback corretivo do usuário

## Fase 50: Hardening do Lock de Execução do Launcher

- [x] Detectar lock legado/novo com parser robusto
- [x] Validar PID ativo com metadados (`boot_id`, `start_ticks`) para evitar falso positivo por reuso
- [x] Verificar `cmdline` do PID para confirmar que pertence ao crawler/launcher
- [x] Limpar lock corrompido/stale automaticamente com motivo explícito
- [x] Manter compatibilidade com lock legado (arquivo contendo apenas PID)

## Fase 51: Auto-TMUX para TUI Rust (VNC Friendly)

- [x] Detectar `--tui-rs` antes da aquisição do lock
- [x] Reexecutar launcher automaticamente dentro de `tmux` quando fora de sessão
- [x] Evitar recursão com flag de guarda (`CRAWLER_AUTO_TMUX_REEXEC`)
- [x] Expor toggle operacional (`AUTO_TMUX_FOR_TUI_RS=0`) para desativar auto-tmux
- [x] Atualizar README com comportamento novo e fallback

## Fase 52: ESC para Quit Total (Operação VNC)

- [x] Adicionar flag `--esc-quit` no binário `tui_rs`
- [x] Implementar encerramento por `Esc` respeitando debounce de startup (1.5s)
- [x] Expor controle no launcher (`--tui-rs-esc-quit` / `--no-tui-rs-esc-quit`)
- [x] Ativar `Esc` por padrão no launcher para fluxo operacional
- [x] Imprimir aviso explícito no start: `Esc` inicia quit total
- [x] Atualizar READMEs (root + `tui_rs`)

## Fase 53: Anti-Freeze End-to-End (State Update)

- [x] Diagnosticar freeze com leitura remota de `state-file` e `tui_rs_health.json`
- [x] Adicionar monitor de stale-state no launcher com parada segura por timeout
- [x] Expor flags de controle (`--state-stale-stop-seconds`, `--state-stale-check-interval-seconds`, `--no-state-stale-stop`)
- [x] Exibir `state_age` no rodapé da TUI para distinguir “ciclo longo” vs “travamento”
- [x] Atualizar documentação operacional com novo monitor anti-freeze

## Fase 54: Quit Total Limpo no TMUX

- [x] Desligar `remain-on-exit` da janela TUI após startup saudável
- [x] Monitor de quit da TUI sinaliza diretamente o processo Python do crawler
- [x] Matar janela TUI no momento do quit para evitar tela `Pane is dead`
- [x] Garantir cleanup de processos residuais no `trap` de saída
