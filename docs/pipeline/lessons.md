# Lessons Learned

## 2026-02-24

- Para treinos longos, preparar o código e entregar comando único para execução em terminal separado, sem bloquear o fluxo principal.
- Em mudanças de etapa no pipeline, atualizar imediatamente `docs/pipeline/PIPELINE_CHECKLIST.md` e `docs/pipeline/todo.md`.
- Quando o usuário pedir formato específico de comando, manter o padrão em todas as respostas seguintes (ex.: comandos multi-linha com `\`).
- Em modo `convert` com demanda de classe zerada, não forçar tentativas mínimas (`profiles=1`) para evitar ciclos improdutivos.
- `--collect-surplus-classes` deve ignorar o filtro de plateau por classe; caso contrário o crawler pode ficar sem candidatos mesmo com coleta de excedente habilitada.
- Antes de aplicar referência visual (`*.md` de design), confirmar tamanho/conteúdo real do arquivo para evitar implementar sobre arquivo vazio/desatualizado.
- Em TUI técnica, evitar painéis que repetem os mesmos números; cada área deve responder a uma pergunta operacional diferente (estado por classe, prioridade, funil, saúde e tendência).
- Em execução longa com saída redirecionada (`tee`/log), evitar checkpoints de progresso a cada 5%; usar intervalo maior para manter logs legíveis.
- Em `tee` + rodagem longa do crawler, preferir barra de progresso em modo linha apenas no início/fim do bloco para evitar poluição de log.

## 2026-02-25

- Quando o usuário reforçar política de execução (`GPU absoluta`), converter isso em regra de código e de validação explícita (falhar cedo sem fallback silencioso).
- Em dashboards em tempo real, nunca exibir estado inválido para operador (ex.: `No Improve` acima de `patience`); clamp visual e teste automatizado são obrigatórios.
- Componentes que dependem de cálculo pós-treino devem renderizar placeholder claro durante a fase intermediária para evitar interpretação errada de erro.
- Evitar `alt-screen` como padrão em sessões operacionais: para uso manual, o painel final deve permanecer visível até o operador encerrar.
- Em instruções para subagente/execução, evitar ambiguidade de comando (`pip install optuna .`); sempre enviar comando mínimo e explícito.
- Em comandos para usuário no Windows/PowerShell, não usar quebra de linha com `\`; usar linha única ou continuação com crase `` ` ``.
- Em dataset com sinais ricos já coletados (`resilience`, `stamina`, `average_item_level`, `spec`), testar primeiro abordagem simples com todas as features cruas antes de engenharia/limpeza pesada.
- Limpeza agressiva + balanceamento pode piorar MAE quando a cobertura já é boa; só manter se melhorar no mesmo protocolo de validação.
- Antes de validar ganho de MAE, travar o escopo de features ao cenário real de deploy (addon): se o runtime só tem `HP + classe`, descartar experimentos com sinais indisponíveis.

## 2026-02-26

- Em ciclos com `ok=0` e `fail` alto, validar imediatamente se o cache HTTP foi contaminado por payload não-textual antes de atribuir causa à rede.
- Para benchmark operacional, limitar duração por teste (máx. 1 minuto) quando o objetivo for decisão rápida de configuração.
- Em operação contínua, manter política de parada explícita e mínima: apenas bloqueio real detectado ou inatividade objetiva por tempo (`idle`) definido.
- Em `diskcache`, corrupção pode aparecer só na escrita (`cache.set`) mesmo quando a abertura do cache funciona; a recuperação automática deve existir em leitura **e** escrita.
- No modo `hybrid`, ausência de candidatos em `history` não deve impedir `profiles`; se discovery ficar sem alvo, o ciclo deve seguir para conversão.
- Em progresso inline, mensagens de evento (`History X@Realm`) precisam quebrar linha antes de imprimir para não corromper o log visual.
- Scripts executados em Linux via `bash` precisam ser tolerantes a `CRLF`; sanitizar `argv` (`\r`) evita quebra de flags como `--mode demo`.
- Quando o usuário pedir redesign visual "não sutil", aplicar refatoração estrutural de verdade (categorias claras, labels leigos e métricas com unidade), não apenas ajustes cosméticos.
- Em dashboard operacional, métricas de saúde (`latência`, `erros consecutivos`) devem usar escala de cor contínua e sempre mostrar número bruto com unidade para evitar leitura ambígua.
- Em TUI com `refresh` de dados mais alto (ex.: `0.8s`), separar taxa de render da taxa de coleta de estado evita sensação de lentidão sem aumentar carga de I/O.
- Para este projeto/usuário, priorizar comandos de execução em linha única para reduzir erro de copy/paste no terminal remoto.
- Em workflows com múltiplos processos (crawler + TUI), mapear explicitamente ações de teclado de "quit total"; sem sinalização coordenada o operador assume que parou tudo quando só fechou a interface.
- Em tmux, criar janela da TUI não garante visibilidade imediata; é necessário definir política de foco explícita no launcher para evitar diagnóstico falso de "TUI não abriu".

## 2026-02-27

- Para validar TUI em produção, não depender só de percepção visual: manter `health snapshot` sobrescrito (sem append) e checker com `exit code` para diagnóstico objetivo sem poluir disco.
- Em execução via `tmux`, fechar terminal pode deixar processo vivo; usar monitor anti-órfão no launcher (detach grace + encerramento limpo) para impedir lock "preso" em rodada seguinte.
- Em PowerShell, comando nativo não falha automaticamente em `exit code` não-zero de processos externos; scripts de lint devem checar `$LASTEXITCODE` explicitamente.
- Em crawler de rede com retries e backoff, timeout por tentativa não basta; é obrigatório ter timeout de parede (tentativa+backoff) para evitar ciclo congelado por minutos.
- Em TUI dentro de tmux, `Esc` pode gerar encerramento acidental no boot dependendo de sequência de teclado/foco; para operação contínua, usar quit explícito (`q`) e debounce inicial.
- Em casos de `Pane is dead (status 0)`, tratar como saída limpa acidental: exigir confirmação de quit (`q` duplo em janela curta) evita encerramento por evento de teclado isolado.
