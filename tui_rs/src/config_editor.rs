//! Sistema de configuração interativa (aba Config).

use serde_json::{json, Value};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum ConfigGroup {
    Collection,
    Limits,
    Filters,
    Features,
}

/// Ordem canônica dos grupos — fonte única de verdade para layout e scroll.
pub(crate) const GROUP_ORDER: [(ConfigGroup, &str); 4] = [
    (ConfigGroup::Collection, "COLETA"),
    (ConfigGroup::Limits, "LIMITES"),
    (ConfigGroup::Filters, "FILTROS"),
    (ConfigGroup::Features, "FUNCIONALIDADES"),
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum ConfigFieldKind {
    Int,
    Bool,
    Choice,
}

/// Campo editável na aba de configuração.
#[derive(Debug, Clone)]
pub(crate) struct ConfigField {
    pub label: &'static str,
    pub key: &'static str,
    pub value: String,
    pub kind: ConfigFieldKind,
    pub group: ConfigGroup,
    pub hint: &'static str,
    pub choices: &'static [&'static str],
}

/// Estado do editor de configuração (aba Config).
#[derive(Debug, Clone)]
pub(crate) struct ConfigEditor {
    pub fields: Vec<ConfigField>,
    pub selected: usize,
    pub dirty: bool,
    pub status_msg: String,
    pub scroll_offset: usize,
    /// Altura interna visível da aba Config (atualizada após cada render).
    pub visible_height: usize,
    /// Se hints devem ser exibidos (atualizado após cada render).
    pub show_hints: bool,
}

macro_rules! cf {
    ($label:expr, $key:expr, $val:expr, Int, $grp:ident, $hint:expr) => {
        ConfigField { label: $label, key: $key, value: $val.into(), kind: ConfigFieldKind::Int, group: ConfigGroup::$grp, hint: $hint, choices: &[] }
    };
    ($label:expr, $key:expr, $val:expr, Bool, $grp:ident, $hint:expr) => {
        ConfigField { label: $label, key: $key, value: $val.into(), kind: ConfigFieldKind::Bool, group: ConfigGroup::$grp, hint: $hint, choices: &[] }
    };
    ($label:expr, $key:expr, $val:expr, Choice, $grp:ident, $hint:expr, $choices:expr) => {
        ConfigField { label: $label, key: $key, value: $val.into(), kind: ConfigFieldKind::Choice, group: ConfigGroup::$grp, hint: $hint, choices: $choices }
    };
}

impl ConfigEditor {
    pub fn new() -> Self {
        Self {
            fields: vec![
                // ── Coleta ──
                cf!("History players/ciclo",   "history_players_per_cycle",  "10", Int, Collection,
                    "Raizes do grafo escaneadas por ciclo. 0 = ilimitado"),
                cf!("Profiles/ciclo",          "profiles_per_cycle",         "3", Int, Collection,
                    "Perfis completos (gear, stats) coletados por ciclo. 0 = ilimitado"),
                cf!("Matchinfo/ciclo",         "max_matchinfo_per_cycle",    "120", Int, Collection,
                    "Detalhes de combate processados por ciclo. 0 = ilimitado"),
                cf!("Fase",                    "phase",             "auto", Choice, Collection,
                    "auto sempre usa hybrid; hybrid faz tudo; discover so busca novos",
                    &["auto", "discover", "convert", "hybrid"]),
                cf!("Modo selecao history",    "history_selection_mode", "auto", Choice, Collection,
                    "Estrategia de escolha de raizes para varredura de historico",
                    &["auto", "discovery", "balanced"]),
                // ── Limites ──
                cf!("Timeout ciclo (s)",       "cycle_max_seconds",         "420", Int, Limits,
                    "Duracao maxima de um ciclo. Ao expirar, novo ciclo inicia (padrao 7 min)"),
                cf!("Cooldown history (s)",    "history_cooldown_seconds",  "600", Int, Limits,
                    "Tempo minimo antes de re-escanear o history do mesmo player (padrao 10 min)"),
                cf!("Timeout raiz history (s)","history_root_max_seconds",  "180", Int, Limits,
                    "Timeout acumulado para varredura de history de um unico player"),
                cf!("Parada inatividade (s)",  "idle_stop_seconds",          "300", Int, Limits,
                    "Crawler para se nao descobrir players novos neste periodo. 0 = nunca parar por idle"),
                cf!("Seed ladder max",         "ladder_seed_max_players",    "50", Int, Limits,
                    "Quantos players extrair do ladder como semente inicial do grafo"),
                // ── Filtros ──
                cf!("Apenas level 80",         "only_level_80",       "true", Bool, Filters,
                    "Rejeita players que nao sao level 80 (endgame WotLK)"),
                // ── Funcionalidades ──
                cf!("Delay adaptativo",        "adaptive_delay",     "true", Bool,  Features,
                    "Ajusta delay automaticamente com base em erros. Mais erros = delay maior"),
                cf!("Revisita automatica",     "recollect_missing_fields", "false", Bool, Features,
                    "Recoleta players sem guild, profissoes ou talentos preenchidos"),
            ],
            selected: 0,
            dirty: false,
            status_msg: String::new(),
            scroll_offset: 0,
            visible_height: 30,
            show_hints: true,
        }
    }

    pub fn load_from_runtime(&mut self, state: &Value) {
        let map: &[(&str, &str)] = &[
            ("adaptive_delay", "adaptive_delay"),
            ("history_players_per_cycle", "history_players_per_cycle"),
            ("profiles_per_cycle", "profiles_per_cycle"),
            ("max_matchinfo_per_cycle", "max_matchinfo_per_cycle"),
            ("phase", "phase"),
            ("history_selection_mode", "history_selection_mode"),
            ("cycle_max_seconds", "cycle_max_seconds"),
            ("history_cooldown_seconds", "history_cooldown_seconds"),
            ("history_root_max_seconds", "history_root_max_seconds"),
            ("idle_stop_seconds", "idle_stop_seconds"),
            ("ladder_seed_max_players", "ladder_seed_max_players"),
            ("only_level_80", "only_level_80"),
            ("recollect_missing_fields", "recollect_missing_fields"),
        ];
        for (key, json_key) in map {
            if let Some(val) = state.get(*json_key).or_else(|| state.get(*key)) {
                if let Some(f) = self.fields.iter_mut().find(|f| f.key == *key) {
                    match val {
                        Value::Number(n) => {
                            if let Some(fv) = n.as_f64() {
                                f.value = format!("{fv}");
                            }
                        }
                        Value::Bool(b) => f.value = format!("{b}"),
                        Value::String(s) => {
                            if f.kind == ConfigFieldKind::Choice {
                                if f.choices.contains(&s.as_str()) {
                                    f.value = s.clone();
                                }
                            } else {
                                f.value = s.clone();
                            }
                        }
                        _ => {}
                    }
                }
            }
        }
    }

    pub fn increment_selected(&mut self) {
        let sel = self.selected;
        let Some(f) = self.fields.get_mut(sel) else { return };
        match f.kind {
            ConfigFieldKind::Int => {
                if let Ok(v) = f.value.parse::<i64>() {
                    let step = if v >= 100 { 10 } else if v >= 10 { 5 } else { 1 };
                    f.value = format!("{}", v + step);
                    self.dirty = true;
                }
            }
            ConfigFieldKind::Bool => {
                f.value = if f.value == "true" { "false".into() } else { "true".into() };
                self.dirty = true;
            }
            ConfigFieldKind::Choice => {
                if !f.choices.is_empty() {
                    let idx = f.choices.iter().position(|c| *c == f.value).unwrap_or(0);
                    f.value = f.choices[(idx + 1) % f.choices.len()].to_string();
                    self.dirty = true;
                }
            }
        }
    }

    pub fn decrement_selected(&mut self) {
        let sel = self.selected;
        let Some(f) = self.fields.get_mut(sel) else { return };
        match f.kind {
            ConfigFieldKind::Int => {
                if let Ok(v) = f.value.parse::<i64>() {
                    let step = if v > 100 { 10 } else if v > 10 { 5 } else { 1 };
                    f.value = format!("{}", (v - step).max(0));
                    self.dirty = true;
                }
            }
            ConfigFieldKind::Bool => {
                f.value = if f.value == "true" { "false".into() } else { "true".into() };
                self.dirty = true;
            }
            ConfigFieldKind::Choice => {
                if !f.choices.is_empty() {
                    let idx = f.choices.iter().position(|c| *c == f.value).unwrap_or(0);
                    let prev = if idx == 0 { f.choices.len() - 1 } else { idx - 1 };
                    f.value = f.choices[prev].to_string();
                    self.dirty = true;
                }
            }
        }
    }

    pub fn push_char(&mut self, ch: char) {
        if let Some(f) = self.fields.get_mut(self.selected) {
            if f.kind == ConfigFieldKind::Int && ch.is_ascii_digit() {
                f.value.push(ch);
                self.dirty = true;
            }
        }
    }

    pub fn backspace(&mut self) {
        if let Some(f) = self.fields.get_mut(self.selected) {
            if f.kind == ConfigFieldKind::Int {
                f.value.pop();
                self.dirty = true;
            }
        }
    }

    // ── Layout (espelha build_config_lines em ui.rs) ────────────

    /// Computa o offset em linhas de cada campo, espelhando `build_config_lines`.
    pub fn field_line_offsets(&self) -> Vec<usize> {
        let mut offsets = vec![0usize; self.fields.len()];
        let mut line = 0usize;
        for (group, _) in &GROUP_ORDER {
            let group_fields: Vec<usize> = self
                .fields
                .iter()
                .enumerate()
                .filter(|(_, f)| f.group == *group)
                .map(|(i, _)| i)
                .collect();
            if group_fields.is_empty() {
                continue;
            }
            line += 2; // cabeçalho do grupo (título + linha vazia)
            for &idx in &group_fields {
                offsets[idx] = line;
                line += 1; // linha do campo
                if self.show_hints {
                    line += 1; // linha do hint
                }
            }
            line += 1; // linha vazia após grupo
        }
        offsets
    }

    /// Total de linhas produzidas (espelha `build_config_lines().len()`).
    pub fn total_lines(&self) -> usize {
        let mut line = 0usize;
        for (group, _) in &GROUP_ORDER {
            let count = self.fields.iter().filter(|f| f.group == *group).count();
            if count == 0 {
                continue;
            }
            line += 2; // cabeçalho
            line += count; // campos
            if self.show_hints {
                line += count; // hints
            }
            line += 1; // linha vazia final
        }
        line
    }

    /// Ajusta `scroll_offset` para manter o campo selecionado visível.
    pub fn ensure_visible(&mut self) {
        if self.visible_height == 0 {
            return;
        }
        let offsets = self.field_line_offsets();
        let Some(&field_line) = offsets.get(self.selected) else {
            return;
        };
        let field_height = if self.show_hints { 2 } else { 1 };
        let total = self.total_lines();
        let max_scroll = total.saturating_sub(self.visible_height);
        // Campo acima da viewport → scroll up (margem de 1 linha para contexto)
        if field_line <= self.scroll_offset {
            self.scroll_offset = field_line.saturating_sub(1);
        }
        // Campo abaixo da viewport → scroll down
        let field_bottom = field_line + field_height;
        if field_bottom >= self.scroll_offset + self.visible_height {
            self.scroll_offset = (field_bottom + 1).saturating_sub(self.visible_height);
        }
        self.scroll_offset = self.scroll_offset.min(max_scroll);
    }

    // ── Navegação ───────────────────────────────────────────────

    pub fn select_prev(&mut self) {
        if self.selected > 0 {
            self.selected -= 1;
            self.ensure_visible();
        }
    }

    pub fn select_next(&mut self) {
        if self.selected + 1 < self.fields.len() {
            self.selected += 1;
            self.ensure_visible();
        }
    }

    pub fn page_up(&mut self) {
        if self.fields.is_empty() {
            return;
        }
        let lines_per_field = if self.show_hints { 2 } else { 1 };
        let page_fields = (self.visible_height / lines_per_field).max(1).saturating_sub(1);
        self.selected = self.selected.saturating_sub(page_fields);
        self.ensure_visible();
    }

    pub fn page_down(&mut self) {
        if self.fields.is_empty() {
            return;
        }
        let lines_per_field = if self.show_hints { 2 } else { 1 };
        let page_fields = (self.visible_height / lines_per_field).max(1).saturating_sub(1);
        self.selected = (self.selected + page_fields).min(self.fields.len() - 1);
        self.ensure_visible();
    }

    pub fn select_first(&mut self) {
        self.selected = 0;
        self.ensure_visible();
    }

    pub fn select_last(&mut self) {
        if !self.fields.is_empty() {
            self.selected = self.fields.len() - 1;
            self.ensure_visible();
        }
    }

    pub fn to_json(&self) -> Value {
        let mut map = serde_json::Map::new();
        for f in &self.fields {
            let val: Value = match f.kind {
                ConfigFieldKind::Int => f.value.parse::<i64>().map(|v| json!(v)).unwrap_or(Value::Null),
                ConfigFieldKind::Bool => json!(f.value == "true"),
                ConfigFieldKind::Choice => json!(f.value),
            };
            map.insert(f.key.to_string(), val);
        }
        Value::Object(map)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn field_line_offsets_with_hints() {
        let mut ed = ConfigEditor::new();
        ed.show_hints = true;
        let offsets = ed.field_line_offsets();
        // Collection: 5 campos. Header=2 linhas, cada campo=2 linhas (field+hint)
        assert_eq!(offsets[0], 2);  // primeiro campo (Collection)
        assert_eq!(offsets[1], 4);  // segundo campo
        assert_eq!(offsets[4], 10); // quinto campo (último da Collection)
        // Limits: header inicia em 2+5*2+1=13, primeiro campo em 13+2=15
        assert_eq!(offsets[5], 15); // primeiro campo (Limits)
    }

    #[test]
    fn field_line_offsets_without_hints() {
        let mut ed = ConfigEditor::new();
        ed.show_hints = false;
        let offsets = ed.field_line_offsets();
        // Collection: 5 campos. Header=2 linhas, cada campo=1 linha
        assert_eq!(offsets[0], 2);  // primeiro campo (Collection)
        assert_eq!(offsets[1], 3);
        assert_eq!(offsets[4], 6);  // último da Collection
        // Limits: header inicia em 2+5+1=8, primeiro campo em 8+2=10
        assert_eq!(offsets[5], 10); // primeiro campo (Limits)
    }

    #[test]
    fn total_lines_consistent_with_offsets() {
        for hints in [true, false] {
            let mut ed = ConfigEditor::new();
            ed.show_hints = hints;
            let total = ed.total_lines();
            let offsets = ed.field_line_offsets();
            let last_field = ed.fields.len() - 1;
            let last_offset = offsets[last_field];
            let field_h = if hints { 2 } else { 1 };
            // O total deve ser >= offset do último campo + sua altura + 1 (trailing)
            assert!(total >= last_offset + field_h + 1,
                "total={total} last_offset={last_offset} hints={hints}");
        }
    }

    #[test]
    fn ensure_visible_scrolls_down() {
        let mut ed = ConfigEditor::new();
        ed.show_hints = false;
        ed.visible_height = 10;
        ed.scroll_offset = 0;
        ed.selected = ed.fields.len() - 1;
        ed.ensure_visible();
        assert!(ed.scroll_offset > 0, "deveria ter scrollado para baixo");
    }

    #[test]
    fn ensure_visible_scrolls_up() {
        let mut ed = ConfigEditor::new();
        ed.show_hints = false;
        ed.visible_height = 10;
        ed.scroll_offset = 100;
        ed.selected = 0;
        ed.ensure_visible();
        assert!(ed.scroll_offset <= 1, "deveria ter scrollado para cima, got {}", ed.scroll_offset);
    }

    #[test]
    fn select_next_stops_at_last() {
        let mut ed = ConfigEditor::new();
        ed.visible_height = 50;
        ed.show_hints = false;
        let last = ed.fields.len() - 1;
        ed.selected = last;
        ed.select_next();
        assert_eq!(ed.selected, last);
    }

    #[test]
    fn select_prev_stops_at_zero() {
        let mut ed = ConfigEditor::new();
        ed.visible_height = 50;
        ed.show_hints = false;
        ed.selected = 0;
        ed.select_prev();
        assert_eq!(ed.selected, 0);
    }

    #[test]
    fn page_navigation_moves_selection() {
        let mut ed = ConfigEditor::new();
        ed.show_hints = false;
        ed.visible_height = 10;
        ed.selected = 0;
        ed.page_down();
        assert!(ed.selected > 0, "page_down deveria avançar seleção");
        let after_down = ed.selected;
        ed.page_up();
        assert!(ed.selected < after_down, "page_up deveria recuar seleção");
    }

    #[test]
    fn select_first_last() {
        let mut ed = ConfigEditor::new();
        ed.visible_height = 50;
        ed.show_hints = false;
        ed.select_last();
        assert_eq!(ed.selected, ed.fields.len() - 1);
        ed.select_first();
        assert_eq!(ed.selected, 0);
    }

    #[test]
    fn full_traversal_keeps_selected_visible() {
        for hints in [true, false] {
            let mut ed = ConfigEditor::new();
            ed.show_hints = hints;
            ed.visible_height = 12;
            // Navegar do primeiro ao último campo
            for _ in 0..ed.fields.len() {
                ed.select_next();
                let offsets = ed.field_line_offsets();
                let line = offsets[ed.selected];
                let field_h = if hints { 2 } else { 1 };
                assert!(line >= ed.scroll_offset,
                    "campo {}: linha {line} acima do scroll {} (hints={hints})",
                    ed.selected, ed.scroll_offset);
                assert!(line + field_h <= ed.scroll_offset + ed.visible_height,
                    "campo {}: linha {line}+{field_h} abaixo da viewport {}+{} (hints={hints})",
                    ed.selected, ed.scroll_offset, ed.visible_height);
            }
            // Voltar ao primeiro
            for _ in 0..ed.fields.len() {
                ed.select_prev();
                let offsets = ed.field_line_offsets();
                let line = offsets[ed.selected];
                assert!(line >= ed.scroll_offset,
                    "volta campo {}: linha {line} acima do scroll {} (hints={hints})",
                    ed.selected, ed.scroll_offset);
            }
        }
    }
}
