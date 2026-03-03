//! Estado central da aplicação (App, ActiveTab).

use std::fs;
use std::process;
use std::time::{Instant, SystemTime};

use serde_json::{json, Value};

use crate::config_editor::ConfigEditor;
use crate::health::{age_secs_or_inf, write_json_atomic, RuntimeHealth};
use crate::ipc::{parse_crawler_status, CrawlerStatus};
use crate::snapshot::{maybe_round3, parse_snapshot, round2, round3, Snapshot};
use crate::time_utils::{lcg_next, now_epoch_ms, now_hms_with_offset, system_time_to_epoch_ms};
use crate::{Cli, ModeArg};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum ActiveTab {
    Dashboard,
    Config,
}

pub(crate) struct App {
    pub cfg: Cli,
    pub unicode: bool,
    pub frame_tick: u64,
    pub history: Vec<Snapshot>,
    pub current: Snapshot,
    pub last_state_mtime: Option<SystemTime>,
    pub demo_seed: u64,
    pub health: RuntimeHealth,
    pub active_tab: ActiveTab,
    pub config_editor: ConfigEditor,
    pub crawler_status: CrawlerStatus,
    pub control_msg: Option<(Instant, String)>,
    pub recollect_msg: Option<(Instant, String)>,
}

impl App {
    pub fn new(cfg: Cli) -> Self {
        let unicode = !cfg.ascii;
        Self {
            cfg,
            unicode,
            frame_tick: 0,
            history: Vec::new(),
            current: Snapshot::default(),
            last_state_mtime: None,
            demo_seed: 0xC0FFEEu64,
            health: RuntimeHealth::new(),
            active_tab: ActiveTab::Dashboard,
            config_editor: ConfigEditor::new(),
            crawler_status: CrawlerStatus::Unknown,
            control_msg: None,
            recollect_msg: None,
        }
    }

    pub fn refresh_data(&mut self) {
        let mut snapshot = match self.cfg.mode {
            ModeArg::Live | ModeArg::Text => self.load_live_snapshot(),
            ModeArg::Demo => self.build_demo_snapshot(),
        };
        snapshot.ts_epoch_ms = now_epoch_ms();
        snapshot.ts_hms = now_hms_with_offset(self.cfg.tz_offset_hours);
        self.current = snapshot.clone();
        self.history.push(snapshot);
        self.health.last_data_refresh_epoch_ms = now_epoch_ms();
        match self.health.last_cycle_seen {
            Some(last) if last == self.current.cycle => {
                self.health.stagnant_cycle_refreshes =
                    self.health.stagnant_cycle_refreshes.saturating_add(1);
            }
            _ => {
                self.health.last_cycle_seen = Some(self.current.cycle);
                self.health.stagnant_cycle_refreshes = 0;
            }
        }
        if self.history.len() > self.cfg.max_history.max(20) {
            let trim = self.history.len() - self.cfg.max_history.max(20);
            self.history.drain(0..trim);
        }
    }

    fn load_live_snapshot(&mut self) -> Snapshot {
        let path = &self.cfg.state_file;
        let metadata = fs::metadata(path).ok();
        let mtime = metadata.as_ref().and_then(|m| m.modified().ok());
        self.health.last_state_mtime_epoch_ms = mtime.map(system_time_to_epoch_ms).unwrap_or(0);
        let changed = mtime != self.last_state_mtime;
        let has_successful_read = self.health.state_reads_ok > 0;

        if !changed && !self.history.is_empty() && has_successful_read {
            let mut reused = self.current.clone();
            reused.ts_hms = now_hms_with_offset(self.cfg.tz_offset_hours);
            self.health.state_reuses = self.health.state_reuses.saturating_add(1);
            self.health.last_state_reuse_epoch_ms = now_epoch_ms();
            return reused;
        }

        let parsed = fs::read_to_string(path)
            .ok()
            .and_then(|raw| serde_json::from_str::<Value>(&raw).ok());
        if let Some(state) = parsed {
            self.last_state_mtime = mtime;
            self.health.state_reads_ok = self.health.state_reads_ok.saturating_add(1);
            self.health.last_state_read_ok_epoch_ms = now_epoch_ms();
            if !self.config_editor.dirty {
                self.config_editor.load_from_runtime(&state);
            }
            self.crawler_status = parse_crawler_status(&state);
            parse_snapshot(&state)
        } else {
            self.health.state_reads_fail = self.health.state_reads_fail.saturating_add(1);
            self.health.last_state_read_fail_epoch_ms = now_epoch_ms();
            if !self.history.is_empty() {
                let mut reused = self.current.clone();
                reused.ts_hms = now_hms_with_offset(self.cfg.tz_offset_hours);
                self.health.state_reuses = self.health.state_reuses.saturating_add(1);
                self.health.last_state_reuse_epoch_ms = now_epoch_ms();
                reused
            } else {
                Snapshot::default()
            }
        }
    }

    fn build_demo_snapshot(&mut self) -> Snapshot {
        let tick = self.frame_tick;
        let mut seed = self.demo_seed ^ tick.wrapping_mul(0x9E3779B185EBCA87);

        let mut class_counts = [0u64; 10];
        for c in &mut class_counts {
            *c = 1500 + (lcg_next(&mut seed) % 4600);
        }

        self.demo_seed = lcg_next(&mut seed);

        Snapshot {
            cycle: 500 + tick / 10,
            phase: "hybrid".to_string(),
            players_total: 68_000 + tick / 3,
            dataset_total: 20_000 + tick / 4,
            failed_total: 9_500u64.saturating_sub((tick / 8).min(800)),
            delay_x: (1.2 - ((tick % 20) as f64 * 0.03)).max(0.35),
            err_seq: lcg_next(&mut seed) % 3,
            lat_ema_ms: 550.0 + (lcg_next(&mut seed) % 220) as f64,
            history_roots: 10,
            details_done: 20 + (lcg_next(&mut seed) % 100),
            details_target: 120,
            players_new: 4 + (lcg_next(&mut seed) % 24),
            profiles_try: 220,
            profiles_ok: 150 + (lcg_next(&mut seed) % 70),
            profiles_fail: lcg_next(&mut seed) % 60,
            class_counts,
            ts_epoch_ms: now_epoch_ms(),
            ts_hms: now_hms_with_offset(self.cfg.tz_offset_hours),
        }
    }

    pub fn maybe_write_health_snapshot(&mut self, render_fps: u16, data_interval: f64) {
        let Some(path) = self.cfg.health_file.as_ref() else {
            return;
        };
        let now_ms = now_epoch_ms();
        let uptime_s = ((now_ms.saturating_sub(self.health.start_epoch_ms)) as f64 / 1000.0).max(0.0);
        let data_age_s = (now_ms.saturating_sub(self.health.last_data_refresh_epoch_ms)) as f64 / 1000.0;
        let render_age_s = (now_ms.saturating_sub(self.health.last_render_epoch_ms)) as f64 / 1000.0;
        let state_ok_age_s = age_secs_or_inf(now_ms, self.health.last_state_read_ok_epoch_ms);
        let state_fail_age_s = age_secs_or_inf(now_ms, self.health.last_state_read_fail_epoch_ms);

        let mode = self.cfg.mode.to_string();
        let base_stale_s = (data_interval * 12.0).max(90.0);
        let mode_str = mode.as_str();
        let status = if mode_str != "live" {
            "ok"
        } else if self.health.state_reads_ok == 0 {
            if self.health.state_reads_fail > 0 {
                "degraded"
            } else {
                "warming"
            }
        } else if state_ok_age_s > base_stale_s {
            "stale"
        } else if self.health.state_reads_fail > self.health.state_reads_ok {
            "degraded"
        } else {
            "ok"
        };
        let class_counts_sum: u64 = self.current.class_counts.iter().copied().sum();

        let payload = json!({
            "schema": "crawler_tui_rs.health.v2",
            "tui_version": env!("CARGO_PKG_VERSION"),
            "app": {
                "compact_runtime_parser": true,
                "total_chart_time_window_seconds": 300,
            },
            "timestamp_epoch_ms": now_ms,
            "timestamp_hms": now_hms_with_offset(self.cfg.tz_offset_hours),
            "status": status,
            "mode": mode,
            "pid": process::id(),
            "uptime_seconds": round2(uptime_s),
            "config": {
                "state_file": self.cfg.state_file.display().to_string(),
                "refresh_seconds": round2(data_interval),
                "render_fps_target": render_fps,
                "health_interval_seconds": round2(self.cfg.health_interval_seconds.max(0.25)),
                "max_history": self.cfg.max_history,
            },
            "runtime": {
                "last_data_refresh_epoch_ms": self.health.last_data_refresh_epoch_ms,
                "last_render_epoch_ms": self.health.last_render_epoch_ms,
                "last_state_read_ok_epoch_ms": self.health.last_state_read_ok_epoch_ms,
                "last_state_read_fail_epoch_ms": self.health.last_state_read_fail_epoch_ms,
                "last_state_reuse_epoch_ms": self.health.last_state_reuse_epoch_ms,
                "last_state_mtime_epoch_ms": self.health.last_state_mtime_epoch_ms,
                "data_age_seconds": round3(data_age_s),
                "render_age_seconds": round3(render_age_s),
                "state_ok_age_seconds": maybe_round3(state_ok_age_s),
                "state_fail_age_seconds": maybe_round3(state_fail_age_s),
                "stagnant_cycle_refreshes": self.health.stagnant_cycle_refreshes,
                "render_frames": self.health.render_frames,
            },
            "reads": {
                "ok": self.health.state_reads_ok,
                "fail": self.health.state_reads_fail,
                "reused": self.health.state_reuses,
            },
            "snapshot": {
                "cycle": self.current.cycle,
                "phase": self.current.phase,
                "players_total": self.current.players_total,
                "dataset_total": self.current.dataset_total,
                "class_counts_sum": class_counts_sum,
                "players_new": self.current.players_new,
                "lat_ema_ms": round2(self.current.lat_ema_ms),
                "err_seq": self.current.err_seq,
                "delay_x": round3(self.current.delay_x),
            }
        });

        let _ = write_json_atomic(path, &payload);
    }
}
