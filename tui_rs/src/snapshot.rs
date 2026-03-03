use ratatui::prelude::Color;
use serde_json::{json, Value};

use crate::time_utils::{now_epoch_ms, now_hms};

pub const CLASS_ORDER: [&str; 10] = [
    "Death Knight",
    "Warrior",
    "Paladin",
    "Hunter",
    "Rogue",
    "Priest",
    "Shaman",
    "Mage",
    "Warlock",
    "Druid",
];

pub const CLASS_COLORS: [Color; 10] = [
    Color::Rgb(196, 31, 59),   // Death Knight
    Color::Rgb(199, 156, 110), // Warrior
    Color::Rgb(245, 140, 186), // Paladin
    Color::Rgb(171, 212, 115), // Hunter
    Color::Rgb(255, 245, 105), // Rogue
    Color::Rgb(255, 255, 255), // Priest
    Color::Rgb(0, 112, 222),   // Shaman
    Color::Rgb(105, 204, 240), // Mage
    Color::Rgb(148, 130, 201), // Warlock
    Color::Rgb(255, 125, 10),  // Druid
];

pub type TotalPointsBuild = (Vec<(f64, f64)>, u64, u64, u64, u64, u64, u64);

#[derive(Debug, Clone)]
pub struct Snapshot {
    pub cycle: u64,
    pub phase: String,
    pub players_total: u64,
    pub dataset_total: u64,
    pub failed_total: u64,
    pub delay_x: f64,
    pub err_seq: u64,
    pub lat_ema_ms: f64,
    pub history_roots: u64,
    pub details_done: u64,
    pub details_target: u64,
    pub players_new: u64,
    pub profiles_try: u64,
    pub profiles_ok: u64,
    pub profiles_fail: u64,
    pub class_counts: [u64; 10],
    pub ts_epoch_ms: u64,
    pub ts_hms: String,
}

impl Default for Snapshot {
    fn default() -> Self {
        Self {
            cycle: 0,
            phase: "-".to_string(),
            players_total: 0,
            dataset_total: 0,
            failed_total: 0,
            delay_x: 1.0,
            err_seq: 0,
            lat_ema_ms: 0.0,
            history_roots: 0,
            details_done: 0,
            details_target: 0,
            players_new: 0,
            profiles_try: 0,
            profiles_ok: 0,
            profiles_fail: 0,
            class_counts: [0; 10],
            ts_epoch_ms: now_epoch_ms(),
            ts_hms: now_hms(),
        }
    }
}

fn count_or_len(state: &Value, count_key: &str, object_key: &str) -> u64 {
    let direct = as_u64(state.get(count_key));
    if direct > 0 {
        return direct;
    }
    state
        .get(object_key)
        .and_then(Value::as_object)
        .map(|m| m.len() as u64)
        .unwrap_or(0)
}

macro_rules! cycle_u64 {
    ($lc:expr, $state:expr, $primary:expr) => {
        as_u64($lc.and_then(|c| c.get($primary)).or_else(|| $state.get($primary)))
    };
    ($lc:expr, $state:expr, $primary:expr, $fallback:expr) => {
        as_u64($lc.and_then(|c| c.get($primary)).or_else(|| $state.get($fallback)))
    };
}

pub fn parse_snapshot(state: &Value) -> Snapshot {
    let players_total = count_or_len(state, "players_total", "players");
    let mut dataset_total = count_or_len(state, "dataset_total", "processed_players");
    let failed_total = count_or_len(state, "failed_total", "failed_players");

    let mut class_counts = compact_class_counts(state).unwrap_or([0u64; 10]);
    if class_counts == [0u64; 10] {
        if let Some(processed) = state.get("processed_players").and_then(Value::as_object) {
            for p in processed.values() {
                let class = p.get("class").and_then(Value::as_str).unwrap_or_default();
                if let Some(i) = class_index(class) {
                    class_counts[i] = class_counts[i].saturating_add(1);
                }
            }
        }
    }
    let class_sum: u64 = class_counts.iter().copied().sum();
    if dataset_total < class_sum {
        dataset_total = class_sum;
    }

    let last_cycle = state.get("telemetry_last").or_else(|| {
        state
            .get("telemetry")
            .and_then(|t| t.get("cycles"))
            .and_then(Value::as_array)
            .and_then(|arr| arr.last())
    });

    let network = state.get("network").unwrap_or(&Value::Null);
    let net_stats = network.get("stats").unwrap_or(&Value::Null);

    Snapshot {
        cycle: as_u64(state.get("cycle")),
        phase: as_str(
            last_cycle
                .and_then(|c| c.get("phase"))
                .or_else(|| state.get("phase")),
            "-",
        ),
        players_total,
        dataset_total,
        failed_total,
        delay_x: as_f64(
            network.get("delay_factor"),
            as_f64(state.get("delay_x"), 1.0),
        )
        .max(0.0),
        err_seq: {
            let from_net = as_u64(network.get("consecutive_errors"));
            if from_net > 0 {
                from_net
            } else {
                as_u64(state.get("err_seq"))
            }
        },
        lat_ema_ms: as_f64(
            net_stats.get("latency_ms_ema"),
            as_f64(state.get("lat_ema_ms"), 0.0),
        )
        .max(0.0),
        history_roots: cycle_u64!(last_cycle, state, "history_roots"),
        details_done: cycle_u64!(last_cycle, state, "history_details_done", "details_done"),
        details_target: cycle_u64!(last_cycle, state, "history_details_target", "details_target"),
        players_new: cycle_u64!(last_cycle, state, "players_new"),
        profiles_try: {
            let v = cycle_u64!(last_cycle, state, "profiles_attempted");
            if v > 0 { v } else { as_u64(state.get("profiles_try")) }
        },
        profiles_ok: cycle_u64!(last_cycle, state, "profiles_ok"),
        profiles_fail: {
            let v = cycle_u64!(last_cycle, state, "profiles_failed");
            if v > 0 { v } else { as_u64(state.get("profiles_fail")) }
        },
        class_counts,
        ts_epoch_ms: now_epoch_ms(),
        ts_hms: now_hms(),
    }
}

pub fn round2(v: f64) -> f64 {
    (v * 100.0).round() / 100.0
}

pub fn round3(v: f64) -> f64 {
    (v * 1000.0).round() / 1000.0
}

pub fn maybe_round3(v: f64) -> Value {
    if v.is_finite() {
        json!(round3(v))
    } else {
        Value::Null
    }
}

pub fn ratio(done: f64, total: f64) -> f64 {
    if total <= 0.0 {
        0.0
    } else {
        (done / total).clamp(0.0, 1.0)
    }
}

pub fn ratio_between(value: f64, good: f64, bad: f64) -> f64 {
    if bad <= good {
        if value > bad {
            1.0
        } else {
            0.0
        }
    } else {
        ((value - good) / (bad - good)).clamp(0.0, 1.0)
    }
}

pub fn gradient_green_red(ratio: f64) -> Color {
    let r = ratio.clamp(0.0, 1.0);
    let (r0, g0, b0) = (39.0, 174.0, 96.0);
    let (r1, g1, b1) = (192.0, 57.0, 43.0);
    let rr = (r0 + (r1 - r0) * r).round() as u8;
    let gg = (g0 + (g1 - g0) * r).round() as u8;
    let bb = (b0 + (b1 - b0) * r).round() as u8;
    Color::Rgb(rr, gg, bb)
}

pub fn net_health_score(s: &Snapshot) -> u8 {
    let err_penalty = (s.err_seq as f64 * 11.0).min(45.0);
    let lat_penalty = ((s.lat_ema_ms - 350.0).max(0.0) / 25.0).min(30.0);
    let delay_penalty = ((s.delay_x - 1.0).max(0.0) * 25.0).min(25.0);
    let score = (100.0 - err_penalty - lat_penalty - delay_penalty).clamp(0.0, 100.0);
    score.round() as u8
}

pub fn net_status_label(score: u8) -> (&'static str, Color) {
    if score >= 80 {
        ("MUITO BOA", Color::Rgb(46, 204, 113))   // Theme::SUCCESS
    } else if score >= 60 {
        ("BOA", Color::Rgb(0, 180, 216))           // Theme::PRIMARY
    } else if score >= 40 {
        ("INSTAVEL", Color::Yellow)
    } else {
        ("CRITICA", Color::Rgb(231, 76, 60))       // Theme::DANGER
    }
}

pub fn phase_label(phase: &str) -> &'static str {
    match phase {
        "discover" => "descoberta",
        "convert" => "atualizacao",
        "hybrid" => "misto",
        _ => "indefinido",
    }
}

pub fn spinner_frame(tick: u64, unicode: bool) -> &'static str {
    if unicode {
        const FRAMES: [&str; 10] = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
        FRAMES[(tick as usize) % FRAMES.len()]
    } else {
        const FRAMES: [&str; 4] = ["|", "/", "-", "\\"];
        FRAMES[(tick as usize) % FRAMES.len()]
    }
}

pub fn pulse_frame(tick: u64, unicode: bool) -> &'static str {
    if unicode {
        const PULSE: [&str; 5] = ["•  ", "•• ", "•••", " ••", "  •"];
        PULSE[(tick as usize) % PULSE.len()]
    } else {
        const PULSE: [&str; 5] = [".  ", ".. ", "...", " ..", "  ."];
        PULSE[(tick as usize) % PULSE.len()]
    }
}

pub fn stats_new_players(history: &[Snapshot]) -> (f64, u64, u64) {
    let data: Vec<u64> = history
        .iter()
        .rev()
        .take(24)
        .map(|h| h.players_new)
        .collect();
    if data.is_empty() {
        return (0.0, 0, 0);
    }
    let sum: u64 = data.iter().sum();
    let min = *data.iter().min().unwrap_or(&0);
    let max = *data.iter().max().unwrap_or(&0);
    let avg = sum as f64 / data.len() as f64;
    (avg, min, max)
}

pub fn build_total_points(
    history: &[Snapshot],
    sample_count: usize,
    exp_x: f64,
) -> TotalPointsBuild {
    const WINDOW_SECONDS: u64 = 5 * 60;
    if history.is_empty() {
        return (
            vec![(0.0, 0.0)],
            0,
            WINDOW_SECONDS / 2,
            WINDOW_SECONDS,
            0,
            0,
            0,
        );
    }

    let exp = exp_x.clamp(1.2, 4.0);
    let latest_ts = history
        .last()
        .map(|s| s.ts_epoch_ms)
        .filter(|ts| *ts > 0)
        .unwrap_or_else(now_epoch_ms);
    let window_start = latest_ts.saturating_sub(WINDOW_SECONDS * 1000);

    let mut windowed: Vec<&Snapshot> = history
        .iter()
        .filter(|s| s.ts_epoch_ms >= window_start && s.ts_epoch_ms <= latest_ts)
        .collect();
    if windowed.is_empty() {
        windowed.push(history.last().unwrap_or(&history[0]));
    }

    let n = windowed.len();
    let samples = sample_count.clamp(12, 480);
    let mut points = Vec::with_capacity(samples);
    let mut last_idx = usize::MAX;

    for i in 0..samples {
        let ratio = i as f64 / (samples - 1).max(1) as f64;
        let idx = ((ratio.powf(exp) * (n - 1) as f64).round() as usize).min(n - 1);
        if idx == last_idx {
            continue;
        }
        last_idx = idx;
        let snap = windowed[idx];
        let x_s = (snap.ts_epoch_ms.saturating_sub(window_start)) as f64 / 1000.0;
        points.push((x_s, snap.players_total as f64));
    }

    let x0 = 0;
    let x1 = WINDOW_SECONDS;
    let xm = WINDOW_SECONDS / 2;

    let mut ymin = u64::MAX;
    let mut ymax = 0u64;
    for (_, y) in &points {
        let yy = y.round() as u64;
        ymin = ymin.min(yy);
        ymax = ymax.max(yy);
    }
    if ymin == u64::MAX {
        ymin = 0;
    }
    let ycur = windowed.last().map(|s| s.players_total).unwrap_or(0);

    (points, x0, xm, x1, ymin, ymax, ycur)
}

fn compact_class_counts(state: &Value) -> Option<[u64; 10]> {
    if let Some(arr) = state.get("class_counts").and_then(Value::as_array) {
        let mut out = [0u64; 10];
        for (idx, item) in arr.iter().take(10).enumerate() {
            out[idx] = as_u64(Some(item));
        }
        return Some(out);
    }

    let obj = state.get("class_counts").and_then(Value::as_object)?;
    let mut out = [0u64; 10];
    for (name, value) in obj {
        if let Some(idx) = class_index(name) {
            out[idx] = as_u64(Some(value));
        }
    }
    Some(out)
}

fn class_index(class_name: &str) -> Option<usize> {
    let mut norm = class_name.to_ascii_lowercase();
    norm.retain(|c| c != ' ' && c != '_' && c != '-');
    match norm.as_str() {
        "deathknight" | "dk" => Some(0),
        "warrior" => Some(1),
        "paladin" => Some(2),
        "hunter" => Some(3),
        "rogue" => Some(4),
        "priest" => Some(5),
        "shaman" => Some(6),
        "mage" => Some(7),
        "warlock" => Some(8),
        "druid" => Some(9),
        _ => None,
    }
}

fn as_u64(v: Option<&Value>) -> u64 {
    match v {
        Some(Value::Number(n)) => n
            .as_u64()
            .or_else(|| n.as_i64().map(|x| x.max(0) as u64))
            .unwrap_or(0),
        Some(Value::String(s)) => s.parse::<u64>().unwrap_or(0),
        Some(Value::Bool(b)) => u64::from(*b),
        _ => 0,
    }
}

fn as_f64(v: Option<&Value>, default: f64) -> f64 {
    match v {
        Some(Value::Number(n)) => n.as_f64().unwrap_or(default),
        Some(Value::String(s)) => s.parse::<f64>().unwrap_or(default),
        Some(Value::Bool(b)) => {
            if *b {
                1.0
            } else {
                0.0
            }
        }
        _ => default,
    }
}

fn as_str(v: Option<&Value>, default: &str) -> String {
    match v {
        Some(Value::String(s)) if !s.trim().is_empty() => s.clone(),
        _ => default.to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use proptest::prelude::*;

    #[test]
    fn parse_snapshot_is_tolerant_to_missing_fields() {
        let s = parse_snapshot(&json!({}));
        assert_eq!(s.cycle, 0);
        assert_eq!(s.players_total, 0);
        assert_eq!(s.dataset_total, 0);
        assert_eq!(s.phase, "-");
    }

    #[test]
    fn parse_snapshot_maps_class_aliases() {
        let s = parse_snapshot(&json!({
            "processed_players": {
                "a": { "class": "death_knight" },
                "b": { "class": "dk" },
                "c": { "class": "PALADIN" },
                "d": { "class": "unknown" }
            }
        }));
        assert_eq!(s.class_counts[0], 2);
        assert_eq!(s.class_counts[2], 1);
        assert_eq!(s.dataset_total, 4);
    }

    #[test]
    fn parse_snapshot_supports_compact_runtime_payload() {
        let s = parse_snapshot(&json!({
            "cycle": 777,
            "phase": "hybrid",
            "players_total": 1000,
            "dataset_total": 450,
            "failed_total": 20,
            "delay_x": 0.55,
            "err_seq": 3,
            "lat_ema_ms": 612.4,
            "class_counts": {
                "death knight": 11,
                "mage": 22
            },
            "telemetry_last": {
                "phase": "discover",
                "history_roots": 4,
                "history_details_done": 12,
                "history_details_target": 30,
                "players_new": 9,
                "profiles_attempted": 80,
                "profiles_ok": 50,
                "profiles_failed": 10
            }
        }));
        assert_eq!(s.cycle, 777);
        assert_eq!(s.players_total, 1000);
        assert_eq!(s.dataset_total, 450);
        assert_eq!(s.failed_total, 20);
        assert_eq!(s.phase, "discover");
        assert_eq!(s.history_roots, 4);
        assert_eq!(s.details_done, 12);
        assert_eq!(s.details_target, 30);
        assert_eq!(s.players_new, 9);
        assert_eq!(s.profiles_try, 80);
        assert_eq!(s.profiles_ok, 50);
        assert_eq!(s.profiles_fail, 10);
        assert_eq!(s.class_counts[0], 11);
        assert_eq!(s.class_counts[7], 22);
    }

    #[test]
    fn build_total_points_clamps_and_keeps_latest() {
        let mut history = Vec::new();
        for i in 0..8 {
            history.push(Snapshot {
                cycle: i,
                players_total: 100 + i,
                ts_epoch_ms: 1_000_000 + i * 10_000,
                ..Snapshot::default()
            });
        }
        let (points, _, _, _, _, _, ycur) = build_total_points(&history, 1, 9.0);
        // sample_count=1 is clamped to 12; exponential sampling with dedup
        // yields <= 12 unique points (8 snapshots -> 6 unique indices).
        assert!(points.len() >= 1 && points.len() <= 12);
        // No duplicate x values after dedup
        let mut xs: Vec<u64> = points.iter().map(|(x, _)| (*x * 1000.0) as u64).collect();
        let before = xs.len();
        xs.dedup();
        assert_eq!(xs.len(), before, "duplicate x values found");
        assert_eq!(ycur, 107);
    }

    #[test]
    fn maybe_round3_null_for_non_finite() {
        assert_eq!(maybe_round3(f64::INFINITY), Value::Null);
    }

    fn arb_json_value() -> impl Strategy<Value = Value> {
        let leaf = prop_oneof![
            Just(Value::Null),
            any::<bool>().prop_map(Value::Bool),
            any::<i64>().prop_map(|n| Value::Number(n.into())),
            any::<String>().prop_map(Value::String),
        ];

        leaf.prop_recursive(4, 64, 8, |inner| {
            prop_oneof![
                prop::collection::vec(inner.clone(), 0..6).prop_map(Value::Array),
                prop::collection::vec((any::<String>(), inner), 0..6).prop_map(|entries| {
                    let mut map = serde_json::Map::new();
                    for (k, v) in entries {
                        map.insert(k, v);
                    }
                    Value::Object(map)
                }),
            ]
        })
    }

    proptest! {
        #[test]
        fn parse_snapshot_is_stable_for_any_json(input in arb_json_value()) {
            let s = parse_snapshot(&input);
            let class_sum: u64 = s.class_counts.iter().sum();

            prop_assert!(s.delay_x.is_finite());
            prop_assert!(s.lat_ema_ms.is_finite());
            prop_assert!(s.delay_x >= 0.0);
            prop_assert!(s.lat_ema_ms >= 0.0);
            prop_assert!(class_sum <= s.dataset_total);
            prop_assert!(!s.phase.trim().is_empty());
        }

        #[test]
        fn parse_snapshot_is_stable_for_malformed_contract(
            cycle in arb_json_value(),
            players in arb_json_value(),
            processed_players in arb_json_value(),
            failed_players in arb_json_value(),
            network in arb_json_value(),
            telemetry in arb_json_value()
        ) {
            let mut root = serde_json::Map::new();
            root.insert("cycle".to_string(), cycle);
            root.insert("players".to_string(), players);
            root.insert("processed_players".to_string(), processed_players);
            root.insert("failed_players".to_string(), failed_players);
            root.insert("network".to_string(), network);
            root.insert("telemetry".to_string(), telemetry);

            let s = parse_snapshot(&Value::Object(root));
            prop_assert!(s.delay_x.is_finite());
            prop_assert!(s.lat_ema_ms.is_finite());
            prop_assert!(s.delay_x >= 0.0);
            prop_assert!(s.lat_ema_ms >= 0.0);
        }
    }
}
