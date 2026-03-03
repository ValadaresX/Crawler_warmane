# Relatório de Análise de Utilidade — Parâmetros do Crawler

**Data**: 2026-03-02
**Escopo**: Todos os 70 argumentos CLI do `adaptive_graph_crawler.py` + 23 campos expostos na TUI
**Método**: Análise estática de código-fonte + teoria de controle + princípios de design de sistemas

---

## Frameworks Teóricos Aplicados

### 1. Princípio da Parcimônia (Navalha de Occam aplicada a sistemas)
> "Um parâmetro só deve existir se removê-lo causaria uma perda funcional que não pode ser compensada por outro mecanismo."

Parâmetros que duplicam controle de outro parâmetro, ou cujo valor padrão nunca precisa mudar, são candidatos à remoção ou internalização como constante.

### 2. Teoria de Controle — Sobreposição de Malhas
Em sistemas de controle, quando duas malhas regulam a mesma variável (ex: taxa de requisições), uma delas domina e a outra se torna inerte. Manter a inerte cria complexidade sem benefício, a menos que sirva explicitamente como **guarda de segurança** (failsafe) para casos extremos.

### 3. Princípio da Ortogonalidade
> "Cada parâmetro deve controlar exatamente uma dimensão do comportamento. Se dois parâmetros afetam a mesma dimensão, são não-ortogonais e devem ser consolidados ou hierarquizados."

### 4. Princípio do Menor Espanto (Least Surprise)
> "O comportamento observável deve corresponder ao que o nome do parâmetro sugere."

Parâmetros cujo efeito real diverge da expectativa do nome são fontes de confusão operacional.

### 5. Hierarquia de Controle (Defense in Depth)
Em rate-limiting e proteção contra bloqueio, camadas sobrepostas são intencionais. A análise distingue entre:
- **Redundância intencional** (failsafe legítimo)
- **Redundância acidental** (complexidade sem ganho)

---

## Classificação dos Parâmetros

Cada parâmetro recebe uma classificação:

| Símbolo | Significado |
|---------|-------------|
| **ESSENCIAL** | Necessário, não pode ser removido |
| **ÚTIL** | Agrega valor em cenários reais |
| **INERTE** | Não surte efeito com os defaults atuais |
| **CONFLITANTE** | Interage de forma problemática com outro parâmetro |
| **REDUNDANTE** | Duplica controle de outro parâmetro |
| **BUG** | Comportamento diverge da intenção |

---

## 1. REDE — Controle de Taxa

### 1.1. `--http-rps` (0.90) — REDUNDANTE (failsafe benigno)

**O que faz**: Rate-limit por token bucket em `network.py`. Intervalo mínimo 1.11s entre requests.

**Problema**: O `adaptive_pause` (delay_min=1.3s) **sempre domina**. Com adaptive delay ativo, o RPS nunca é o fator limitante. Para que o RPS atuasse, seria necessário `delay_min * delay_factor_min < 1/rps`, ou seja `1.3 * 0.35 = 0.455 < 1.11` — o que é verdade! Mas o `_sleep_rate_limit` ocorre **dentro** do retrier, após o `adaptive_pause` já ter dormido. Então o RPS faz `max(0, 1.11 - tempo_já_dormido)`, que tipicamente é 0.

**Veredicto**: Manter como **failsafe silencioso**. Não expor na TUI. O RPS protege contra configuração agressiva de delays, mas o operador não precisa mexer nele.

**Na TUI**: Atualmente exposto. **Recomendação: remover da TUI** — é um parâmetro de infraestrutura, não operacional.

### 1.2. `--min-delay-seconds` (1.3) + `--max-delay-seconds` (3.1) — ESSENCIAL

**O que faz**: Define a banda de pausa adaptativa entre requests. O `delay_factor` multiplica linearmente.

**Interação com RPS**: Estes são os controles "reais" de velocidade. RPS é secundário.

**Na TUI**: Exposto como `delay_min` e `delay_max`. **BUG CRÍTICO descoberto** — ver seção de Bugs.

### 1.3. `--max-delay-cap-seconds` (20.0) — ÚTIL (mas não precisa exposição)

**O que faz**: Teto absoluto para pausa adaptativa. Previne delays absurdos quando `delay_factor` explode.

**Na TUI**: Não exposto. **Correto — é parâmetro de segurança, não operacional.**

### 1.4. `--no-adaptive-delay` — ÚTIL (diagnóstico)

**O que faz**: Desativa o multiplicador adaptativo. Pausa fixa entre `min` e `max`.

**Uso**: Diagnóstico — isolar se o comportamento lento é do servidor ou do adaptive.

**Na TUI**: Exposto. **OK.**

### 1.5. Parâmetros do adaptive delay (6 flags) — INERTE para operação normal

| Flag | Default | Classificação |
|------|---------|---------------|
| `--adaptive-delay-min-factor` | 0.35 | ÚTIL (determina velocidade máxima) |
| `--adaptive-delay-max-factor` | 8.0 | ÚTIL (determina lentidão máxima) |
| `--adaptive-delay-success-decay` | 0.985 | INERTE (tuning fino, nunca precisa mudar) |
| `--adaptive-delay-error-growth` | 1.20 | INERTE (idem) |
| `--adaptive-delay-hard-backoff-errors` | 6 | INERTE (idem) |
| `--adaptive-delay-hard-backoff-seconds` | 8.0 | INERTE (idem) |

**Análise**: São parâmetros do controlador PID (proporcional-integral do backoff). Ajustá-los requer compreensão da dinâmica do servidor Warmane. Os defaults funcionam. Nenhum deve estar na TUI.

**Na TUI**: Nenhum exposto. **Correto.**

### 1.6. `--random-visit-prob` (0.18) — ÚTIL

**O que faz**: Probabilidade de "visita aleatória" a player fora da fila normal. Previne padrão sequencial detectável.

**Na TUI**: Exposto. **Questionável** — operador raramente precisa mudar isso. Candidato a remoção da TUI se espaço for necessário.

### 1.7. `--random-visit-every-*` (3 flags) — INERTE

`every-pages` (7), `every-matchinfos` (40), `every-profiles` (20) — triggers periódicos para random visit além da probabilidade.

**Na TUI**: Não expostos. **Correto — tuning interno.**

---

## 2. TIMEOUTS — Hierarquia de 3 Níveis

### 2.1. Nível 1: Por tentativa individual

| Flag | Default | Classificação |
|------|---------|---------------|
| `--timeout-seconds` | 30 | ESSENCIAL |
| `--matchinfo-timeout-seconds` | 18 | ESSENCIAL |

**Análise**: Necessários. Timeout de conexão/leitura HTTP básico.

**Na TUI**: Não expostos. **Correto — raramente precisam mudar.**

### 2.2. Nível 2: Retry (por request completo)

| Flag | Default | Classificação |
|------|---------|---------------|
| `--http-max-retries` | 5 | **INERTE** |
| `--http-backoff-base-seconds` | 1.0 | ÚTIL |
| `--http-backoff-cap-seconds` | 45.0 | ÚTIL |

**`max-retries` é INERTE**: Com os defaults, o wall timeout (90s) corta após ~3 tentativas. As 5 retries nunca são alcançadas. Seria necessário `wall_timeout >= 5 * (30 + backoff_medio)` ≈ 200s para que 5 retries acontecessem.

**Falta validação**: Não existe `request_wall_timeout >= timeout_seconds` (só existe para matchinfo). Configurar `--request-wall-timeout-seconds 20 --timeout-seconds 30` faria o wall cortar antes da 1ª tentativa — **gap de validação**.

### 2.3. Nível 3: Wall timeout (tempo total)

| Flag | Default | Classificação |
|------|---------|---------------|
| `--request-wall-timeout-seconds` | 90.0 | ESSENCIAL |
| `--matchinfo-request-wall-timeout-seconds` | 45.0 | ESSENCIAL |

**Análise**: Estes são os controles reais de timeout. `max-retries` é secundário.

### 2.4. Timeouts de escopo maior

| Flag | Default | Classificação |
|------|---------|---------------|
| `--history-root-max-seconds` | 180.0 | ESSENCIAL |
| `--cycle-max-seconds` | 420.0 | ESSENCIAL |
| `--history-detail-error-streak-stop` | 12 | ÚTIL |

**Na TUI**: `cycle-max-seconds` e `history-root-max-seconds` expostos. **Correto.**

**Ausência notável**: Não existe timeout de sessão total. O crawler roda indefinidamente até STOP, idle, ou block. Isso é intencional (operação contínua), mas poderia ter um `--max-session-minutes` para operações autônomas (ex: cron).

---

## 3. COLETA — Limites por Ciclo

### 3.1. `--history-players-per-cycle` (10) — ESSENCIAL

**O que faz**: Quantos "roots" (players) são escaneados via match-history por ciclo.

**Interação**: Cada root pode gerar até `max-matchinfo-per-cycle` requests de detail + várias páginas de history. O custo real é `roots * (pages + matchinfos)`.

**Na TUI**: Exposto. **Correto.**

### 3.2. `--max-history-pages-per-cycle` (0 = ilimitado) — ÚTIL mas perigoso

**Problema com default 0**: Ilimitado significa que um root com 50+ páginas de history fará 50+ requests. Com 10 roots, podem ser 500+ requests só de páginas, antes de matchinfo.

**Mitigação**: `history-root-max-seconds` (180s) e `cycle-max-seconds` (420s) limitam temporalmente. Mas a carga instantânea pode ser alta.

**Recomendação**: Default deveria ser 10-20, não 0. O `0 = ilimitado` é um anti-padrão para um sistema que roda em RPi.

**Na TUI**: Não exposto. **Deveria estar, ou o default deveria ser mais seguro.**

### 3.3. `--max-matchinfo-per-cycle` (120) — ESSENCIAL

**Na TUI**: Exposto. **Correto.** (Default na TUI é "0" = ilimitado, mas no argparse é 120. **Inconsistência de defaults** — ver seção de Bugs.)

### 3.4. `--profiles-per-cycle` (3) — ESSENCIAL

**Na TUI**: Exposto. **Correto.**

### 3.5. `--dynamic-profiles-per-cycle` + `--max-profiles-per-cycle` — INERTE

`dynamic` está `False` por padrão. `max-profiles-per-cycle` (8) **só funciona se dynamic estiver ativo**. Isso não é documentado.

**Na TUI**: Nenhum exposto. **Correto — funcionalidade desabilitada.**

### 3.6. `--history-selection-mode` (auto) — ÚTIL

Modos: `auto`, `class_need`, `discovery`, `balanced`. Controla como os roots são priorizados.

**Na TUI**: Exposto. **Correto.**

### 3.7. `--history-cooldown-seconds` (600) — ESSENCIAL

**Na TUI**: Exposto. **Correto.**

---

## 4. FASES — Seleção de Modo de Operação

### 4.1. `--phase` (auto) — ESSENCIAL

Controla se o ciclo faz discovery (history), convert (profiles), ambos (hybrid), ou automático.

**Na TUI**: Exposto como Choice. **Correto.**

### 4.2. `--discovery-target-per-class` (500) — ÚTIL mas confuso

**Confusão com `--target-min-per-class`**:
- `target-min-per-class` (500) = meta de players **processados** (convertidos) por classe
- `discovery-target-per-class` (500) = meta de players **descobertos** por classe

Mesmo default (500) mas significados diferentes. O operador pode pensar que são a mesma coisa.

**Recomendação**: Os nomes deveriam explicitar a diferença. Ex: `--min-discovered-per-class` e `--min-processed-per-class`.

**Na TUI**: Exposto como "Meta descoberta/classe". **Aceitável**, mas a label é ambígua.

---

## 5. METAS E PARADA

### 5.1. `--target-min-per-class` (500) — ESSENCIAL

**Na TUI**: Exposto. **Correto.**

### 5.2. `--target-ratio-to-max` (0.0) — INERTE

**O que faz**: Com 0.0, o target é sempre `target-min-per-class`. Para funcionar, precisaria de algo como 0.8 ("todas as classes devem ter pelo menos 80% da classe com mais amostras").

**Problema**: Default 0.0 = desligado. Feature existe mas ninguém usa.

**Na TUI**: Exposto. **Questionável** — parâmetro avançado que o operador típico não entende.

### 5.3. `--target-hp-min` / `--target-hp-max` (None) — ÚTIL mas de nicho

**O que faz**: Filtra jogadores por honor points. Apenas players com HP na faixa contam para as metas.

**Interação com auto mode**: Quando filtro HP está ativo, o need de discovery usa o deficit de *conversão* (não discovery). Isso é correto porque o crawler não sabe o HP de um player antes de processá-lo.

**Na TUI**: Não expostos. **Correto — parâmetro de nicho para análises específicas.**

### 5.4. `--no-stop-on-target` — **INERTE**

**Problema**: Seta `stop_on_target=False`, mas essa flag **só é verificada** dentro de `if enable_legacy_stop_rules` (que é `False` por padrão). Ou seja, `--no-stop-on-target` nunca faz nada sozinho. O operador precisaria passar `--enable-legacy-stop-rules --no-stop-on-target`, o que é contraditório (habilitar regras legadas para desabilitar uma delas).

**Classificação**: INERTE — código morto efetivo.

### 5.5. `--enable-legacy-stop-rules` — REDUNDANTE

Regras legadas: parar quando todas as classes atingirem target. Substituído pelo modo `auto` que naturalmente desacelera quando metas são atingidas.

**Na TUI**: Não exposto. **Correto — legado.**

### 5.6. `--idle-stop-seconds` (60) — **CONFLITANTE**

**Problema grave**: Mede tempo de **relógio** desde o último ciclo com `new_players > 0`. Um único ciclo longo (> 60s) sem discovery já dispara idle stop. Com `cycle-max-seconds=420s`, o crawler pode fazer um ciclo de 7 minutos e ser parado por idle.

**O campo `no_progress_cycles`** (conta ciclos sem progresso) existe no state mas **não é usado em nenhuma condição de parada**. Seria um critério melhor: "parar após N ciclos sem novos players" em vez de "parar após N segundos sem novos players".

**Na TUI**: Exposto. **O valor deveria ser muito maior (300-600s) ou o critério deveria ser por ciclos, não tempo.**

### 5.7. `--block-detect-consecutive-errors` (8) + `--no-stop-on-block-detected` — ESSENCIAL

Detecção de bloqueio (403/429/captcha). Funciona corretamente.

**Na TUI**: Não exposto. **Correto — parâmetro de segurança.**

---

## 6. FILTROS DE PLAYER

### 6.1. `--only-level-80` (True, via `--allow-non80`) — ESSENCIAL

WotLK endgame é level 80. Coletar outros níveis geralmente não faz sentido para análise PvP.

**Na TUI**: Exposto como "Apenas level 80". **Correto.**

### 6.2. `--min-resilience` (200) + `--allow-missing-resilience` — **INERTE / BUG**

**Problema descoberto**: Esses argumentos são parseados mas **não são passados** para `analyze_character()`. O crawler os ignora completamente. A filtragem por resilience (se existir) depende de defaults hardcoded dentro do módulo `analyzer`, não desses flags.

**Na TUI**: Não expostos. **Correto por acaso — são parâmetros fantasma.**

**Recomendação**: Remover do argparse ou implementar de fato (forward para analyze_character).

### 6.3. `--collect-surplus-classes` (False) — ESSENCIAL

**O que faz**: Quando False, classes que já atingiram a meta são puladas no convert. Quando True, coleta tudo.

**Na TUI**: Exposto. **Correto.**

### 6.4. `--include-unknown-class-hint` (False) — ÚTIL

**O que faz**: Players sem classe identificada (ex: nunca apareceram em match detail) são pulados. Ligando isso, o crawler tenta coletá-los (a classe é determinada ao processar o perfil).

**Na TUI**: Exposto. **Correto.**

### 6.5. `--skip-failed` (False) — ÚTIL (mas default deveria ser True)

**O que faz**: Players que falharam na coleta anterior são pulados por um período (cooldown baseado no tipo de erro). Com False, players falhados são retentados imediatamente.

**Recomendação**: Default `True` seria mais seguro. Reattempt sem cooldown pode gerar loops em players permanentemente inacessíveis (renomeados, deletados, banidos).

**Na TUI**: Não exposto. **Deveria estar ou o default deveria ser True.**

### 6.6. Parâmetros de retry por player falhado (6 flags) — ÚTIL mas excessivo

| Flag | Default | O que controla |
|------|---------|----------------|
| `--failed-retry-base-seconds` | 1200 (20min) | Cooldown base para retry genérico |
| `--failed-policy-retry-seconds` | 21600 (6h) | Cooldown para erro de policy (403) |
| `--failed-client-retry-seconds` | 43200 (12h) | Cooldown para erro de cliente (4xx) |
| `--failed-other-retry-seconds` | 10800 (3h) | Cooldown para outros erros |
| `--failed-retry-cap-seconds` | 172800 (48h) | Teto de cooldown |
| `--failed-backoff-max-exp` | 6 | Expoente máximo do backoff |

**Análise**: 6 parâmetros para controlar cooldowns de retry por tipo de erro. Isso é sobre-engenharia. Na prática, bastaria 1 parâmetro (`--failed-retry-cooldown-seconds`) com o tipo de erro determinando um multiplicador interno fixo.

**Na TUI**: Nenhum exposto. **Correto — complexidade interna.**

---

## 7. FUNCIONALIDADES

### 7.1. `--collect-talents` (False) — ÚTIL

+1 request HTTP por player. Custo mensurável.

**Na TUI**: Exposto. **Correto.**

### 7.2. `--recollect-missing-fields` (False) — ÚTIL

Revisita players processados com campos enriquecidos ausentes.

**Na TUI**: Exposto. **Correto.**

### 7.3. `--recollect-all-processed` + `--recollect-and-append` — CONFLITANTE

**Conflito**: Se ambos forem passados, `recollect-and-append` tem precedência e `recollect-all-processed` é ignorado silenciosamente. Não há aviso.

**Na TUI**: Nenhum exposto. **Correto — são flags de operação especial (one-shot).**

### 7.4. `--recollect-batch-size` (10) — ÚTIL

**Na TUI**: Não exposto. **OK — parâmetro de tuning interno.**

---

## 8. BUGS E CONFLITOS FUNCIONAIS ENCONTRADOS

### BUG 1: IPC da TUI não altera delay — SEVERO

**Local**: `adaptive_graph_crawler.py:1554-1555`

```python
"delay_min": ("pause_min", float),
"delay_max": ("pause_max", float),
```

A TUI escreve `delay_min` e `delay_max` no `tui_config.json`. O crawler mapeia para `args.pause_min` e `args.pause_max`. **Porém**, o `adaptive_pause()` (linha 333-334) lê `args.min_delay_seconds` e `args.max_delay_seconds`. Os nomes não correspondem!

**Efeito**: Quando o operador ajusta "Delay mínimo" e "Delay máximo" na TUI e pressiona Enter, **a mudança é aplicada a atributos que ninguém lê**. O crawler continua usando os delays originais.

**Correção necessária**: Mudar o mapeamento para:
```python
"delay_min": ("min_delay_seconds", float),
"delay_max": ("max_delay_seconds", float),
```

### BUG 2: IPC da TUI não altera RPS em runtime — MÉDIO

**Local**: O `configure_http()` é chamado uma vez em `run()`. A TUI pode alterar `args.http_rps` via IPC, mas `network.py._CONFIG.rps` **não é atualizado** — foi fixado na inicialização.

**Efeito**: Alterar RPS na TUI não tem efeito real. (Mitigado pelo fato de RPS ser redundante com adaptive delay — ver item 1.1.)

**Recomendação**: Remover RPS da TUI (ver item 1.1) resolve o problema ao eliminar a interface enganosa.

### BUG 3: Defaults inconsistentes entre TUI e argparse

| Campo | Default na TUI | Default no argparse | Discrepância |
|-------|---------------|---------------------|--------------|
| `history_players_per_cycle` | "0" | 10 | TUI sugere ilimitado, argparse usa 10 |
| `profiles_per_cycle` | "0" | 3 | TUI sugere ilimitado, argparse usa 3 |
| `max_matchinfo_per_cycle` | "0" | 120 | TUI sugere ilimitado, argparse usa 120 |

**Efeito**: A TUI mostra "0" (ilimitado) como default, mas o crawler realmente inicia com os defaults do argparse (10, 3, 120). Apenas se o operador pressionar Enter na TUI (sem mudar nada), os valores seriam sobrescritos para 0. Isso pode causar ciclos extremamente longos inesperadamente.

**Correção necessária**: Alinhar defaults da TUI com os do argparse, ou carregar os defaults reais do runtime ao inicializar.

### BUG 4: `--min-resilience` e `--allow-missing-resilience` não fazem nada

Argumentos parseados mas nunca forwarded para `analyze_character()`. São parâmetros fantasma.

---

## 9. TABELA CONSOLIDADA — DECISÃO POR PARÂMETRO

### Legenda de Ação

| Ação | Significado |
|------|-------------|
| **MANTER** | Parâmetro funciona, é útil, sem mudança |
| **MANTER (failsafe)** | Não expor na TUI, funciona como guarda |
| **REMOVER DA TUI** | Parâmetro existe mas não deve ser exposto |
| **ADICIONAR NA TUI** | Deveria estar exposto |
| **CORRIGIR** | Bug ou conflito precisa de fix |
| **DEPRECAR** | Candidato a remoção futura do argparse |
| **INTERNALIZAR** | Transformar de flag em constante no código |

### Parâmetros de Rede (10)

| # | Parâmetro | Class. | Ação | Motivo |
|---|-----------|--------|------|--------|
| 1 | `http-rps` | REDUNDANTE | **REMOVER DA TUI** | Dominado pelo adaptive; IPC não funciona; failsafe interno |
| 2 | `min-delay-seconds` | ESSENCIAL | **CORRIGIR IPC** | Bug: TUI grava em `pause_min`, crawler lê `min_delay_seconds` |
| 3 | `max-delay-seconds` | ESSENCIAL | **CORRIGIR IPC** | Bug: TUI grava em `pause_max`, crawler lê `max_delay_seconds` |
| 4 | `no-adaptive-delay` | ÚTIL | MANTER | OK |
| 5 | `max-delay-cap-seconds` | ÚTIL | MANTER (failsafe) | Segurança interna |
| 6 | `adaptive-delay-*` (6 flags) | INERTE | **INTERNALIZAR** | Tuning fino, nunca ajustado em operação |
| 7 | `random-visit-prob` | ÚTIL | **REMOVER DA TUI** | Parâmetro de anti-detecção, operador não precisa ajustar |
| 8 | `random-visit-every-*` (3 flags) | INERTE | MANTER (failsafe) | Tuning interno |

### Parâmetros de Timeout (7)

| # | Parâmetro | Class. | Ação | Motivo |
|---|-----------|--------|------|--------|
| 1 | `timeout-seconds` | ESSENCIAL | MANTER | Base HTTP |
| 2 | `matchinfo-timeout-seconds` | ESSENCIAL | MANTER | POST específico |
| 3 | `http-max-retries` | **INERTE** | **DEPRECAR** | Wall timeout sempre corta antes; falsa expectativa de 5 retries |
| 4 | `http-backoff-base/cap` | ÚTIL | MANTER (failsafe) | Controle de backoff interno |
| 5 | `request-wall-timeout-seconds` | ESSENCIAL | **CORRIGIR** | Adicionar validação `>= timeout-seconds` |
| 6 | `matchinfo-request-wall-timeout` | ESSENCIAL | MANTER | Já validado |
| 7 | `history-root-max-seconds` | ESSENCIAL | MANTER | Protege roots longos |

### Parâmetros de Ciclo (8)

| # | Parâmetro | Class. | Ação | Motivo |
|---|-----------|--------|------|--------|
| 1 | `cycle-max-seconds` | ESSENCIAL | MANTER | Hard cap temporal |
| 2 | `history-players-per-cycle` | ESSENCIAL | **CORRIGIR default TUI** | TUI diz "0", argparse diz 10 |
| 3 | `max-history-pages-per-cycle` | ÚTIL | **ADICIONAR NA TUI ou fixar default** | Default 0=ilimitado é perigoso no RPi |
| 4 | `max-matchinfo-per-cycle` | ESSENCIAL | **CORRIGIR default TUI** | TUI diz "0", argparse diz 120 |
| 5 | `profiles-per-cycle` | ESSENCIAL | **CORRIGIR default TUI** | TUI diz "0", argparse diz 3 |
| 6 | `dynamic-profiles-per-cycle` | INERTE | MANTER | Feature desabilitada, sem impacto |
| 7 | `max-profiles-per-cycle` | INERTE | MANTER | Só funciona com dynamic ativo |
| 8 | `history-cooldown-seconds` | ESSENCIAL | MANTER | Previne re-scan prematuro |

### Parâmetros de Fase (3)

| # | Parâmetro | Class. | Ação | Motivo |
|---|-----------|--------|------|--------|
| 1 | `phase` | ESSENCIAL | MANTER | Controle central de operação |
| 2 | `history-selection-mode` | ÚTIL | MANTER | Tuning da seleção de roots |
| 3 | `discovery-target-per-class` | ÚTIL | MANTER | Mas renomear label para evitar confusão com `target-min-per-class` |

### Parâmetros de Meta/Parada (8)

| # | Parâmetro | Class. | Ação | Motivo |
|---|-----------|--------|------|--------|
| 1 | `target-min-per-class` | ESSENCIAL | MANTER | Meta principal |
| 2 | `target-ratio-to-max` | INERTE | **REMOVER DA TUI** | Default 0.0 = desligado; feature obscura que confunde |
| 3 | `target-hp-min/max` | ÚTIL | MANTER | Nicho, mas funcional |
| 4 | `no-stop-on-target` | **INERTE** | **DEPRECAR** | Só funciona com `--enable-legacy-stop-rules` |
| 5 | `enable-legacy-stop-rules` | REDUNDANTE | **DEPRECAR** | Substituído pelo auto mode |
| 6 | `idle-stop-seconds` | **CONFLITANTE** | **CORRIGIR** | Mede relógio, não ciclos; default 60s muito baixo |
| 7 | `block-detect-consecutive-errors` | ESSENCIAL | MANTER | Proteção anti-ban |
| 8 | `no-stop-on-block-detected` | ÚTIL | MANTER | Para ignorar falsos positivos |

### Parâmetros de Filtro (5)

| # | Parâmetro | Class. | Ação | Motivo |
|---|-----------|--------|------|--------|
| 1 | `only-level-80` | ESSENCIAL | MANTER | Filtro fundamental |
| 2 | `min-resilience` | **BUG** | **DEPRECAR ou implementar** | Não faz nada |
| 3 | `allow-missing-resilience` | **BUG** | **DEPRECAR ou implementar** | Não faz nada |
| 4 | `collect-surplus-classes` | ESSENCIAL | MANTER | Controle de foco |
| 5 | `include-unknown-class-hint` | ÚTIL | MANTER | Borda de grafo |

### Parâmetros de Funcionalidade (5)

| # | Parâmetro | Class. | Ação | Motivo |
|---|-----------|--------|------|--------|
| 1 | `collect-talents` | ÚTIL | MANTER | +1 req/player, operador decide |
| 2 | `recollect-missing-fields` | ÚTIL | MANTER | Migração de dados |
| 3 | `recollect-all-processed` | ÚTIL | MANTER | Operação especial |
| 4 | `recollect-and-append` | **CONFLITANTE** | **DOCUMENTAR** | Suprime `recollect-all-processed` silenciosamente |
| 5 | `skip-failed` | ÚTIL | MANTER | Default deveria ser True |

### Parâmetros de Seed (3)

| # | Parâmetro | Class. | Ação | Motivo |
|---|-----------|--------|------|--------|
| 1 | `character_url` (positional) | ESSENCIAL | MANTER | Seed inicial |
| 2 | `ladder-seed-url` | ESSENCIAL | MANTER | Seed por ladder |
| 3 | `ladder-seed-max-players` | ÚTIL | MANTER | Controle de volume do seed |

### Parâmetros Operacionais (7)

| # | Parâmetro | Class. | Ação | Motivo |
|---|-----------|--------|------|--------|
| 1 | `once` | ÚTIL | MANTER | Debug/teste |
| 2 | `dry-run` | ÚTIL | MANTER | Teste seguro |
| 3 | `import-legacy` | ÚTIL | MANTER | Migração |
| 4 | `reset-network-adaptive-on-start` | ÚTIL | MANTER | Segurança padrão |
| 5 | `progress-mode` | ÚTIL | MANTER | Display |
| 6 | `telemetry-keep-cycles` | ÚTIL | MANTER | Memória |
| 7 | `runtime-state-interval-seconds` | ÚTIL | MANTER | Heartbeat TUI |

---

## 10. CAMPOS DA TUI — RECOMENDAÇÃO FINAL

### Campos a REMOVER da TUI (3)

| Campo atual | Motivo da remoção |
|-------------|-------------------|
| `rps` (Rate limit) | Redundante, IPC não funciona, failsafe interno |
| `random_visit_prob` | Anti-detecção interno, não operacional |
| `target_ratio_to_max` | Feature inerte (default 0.0), confusa |

### Campos a CORRIGIR na TUI (5)

| Campo | Correção |
|-------|----------|
| `delay_min` | Fix IPC: mapear para `min_delay_seconds` |
| `delay_max` | Fix IPC: mapear para `max_delay_seconds` |
| `history_players_per_cycle` | Default na TUI: "10" (não "0") |
| `profiles_per_cycle` | Default na TUI: "3" (não "0") |
| `max_matchinfo_per_cycle` | Default na TUI: "120" (não "0") |

### Campos a ADICIONAR na TUI (0-1)

| Campo candidato | Prioridade | Motivo |
|-----------------|-----------|--------|
| `max_history_pages_per_cycle` | Baixa | Só se default 0 não for alterado para 15 |

### Campos que ESTÃO CORRETOS na TUI (15)

`adaptive_delay`, `history_players_per_cycle`, `profiles_per_cycle`, `max_matchinfo_per_cycle`, `phase`, `history_selection_mode`, `cycle_max_seconds`, `history_cooldown_seconds`, `history_root_max_seconds`, `idle_stop_seconds`, `target_min_per_class`, `discovery_target_per_class`, `only_level_80`, `collect_surplus_classes`, `include_unknown_class_hint`, `collect_talents`, `recollect_missing_fields`, `ladder_seed_max_players`.

---

## 11. RESUMO EXECUTIVO

| Categoria | Total | Essencial | Útil | Inerte | Bug/Conflito |
|-----------|-------|-----------|------|--------|--------------|
| Rede | 17 | 3 | 4 | 8 | 2 |
| Timeout | 7 | 5 | 1 | 1 | 0 |
| Ciclo | 8 | 5 | 1 | 2 | 0 |
| Fase | 3 | 1 | 2 | 0 | 0 |
| Meta/Parada | 8 | 3 | 2 | 2 | 1 |
| Filtro | 5 | 2 | 1 | 0 | 2 |
| Funcionalidade | 5 | 0 | 4 | 0 | 1 |
| Seed | 3 | 2 | 1 | 0 | 0 |
| Operacional | 7 | 0 | 7 | 0 | 0 |
| **TOTAL** | **63** | **21** | **23** | **13** | **6** |

**De 63 parâmetros analisados** (excluindo 7 de Path):
- **21 (33%)** são essenciais — não podem ser removidos
- **23 (37%)** são úteis em cenários reais
- **13 (21%)** são inertes — poderiam ser constantes internas
- **6 (10%)** têm bugs ou conflitos que precisam de correção

**Ações prioritárias**:
1. **CORRIGIR BUG IPC delay** (severo, efeito nulo de ajuste de delay pela TUI)
2. **CORRIGIR defaults TUI** (3 campos com "0" em vez dos valores reais)
3. **REMOVER `rps` da TUI** (enganoso, IPC não funciona)
4. **CORRIGIR `idle-stop-seconds`** (conflita com ciclos longos)
5. **DEPRECAR parâmetros mortos** (`no-stop-on-target`, `enable-legacy-stop-rules`, `min-resilience`)
