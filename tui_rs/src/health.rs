use std::fs;
use std::io;
use std::path::Path;

use serde_json::Value;

use crate::time_utils::now_epoch_ms;

#[derive(Debug, Clone)]
pub struct RuntimeHealth {
    pub start_epoch_ms: u64,
    pub last_data_refresh_epoch_ms: u64,
    pub last_render_epoch_ms: u64,
    pub last_state_read_ok_epoch_ms: u64,
    pub last_state_read_fail_epoch_ms: u64,
    pub last_state_reuse_epoch_ms: u64,
    pub last_state_mtime_epoch_ms: u64,
    pub state_reads_ok: u64,
    pub state_reads_fail: u64,
    pub state_reuses: u64,
    pub render_frames: u64,
    pub stagnant_cycle_refreshes: u64,
    pub last_cycle_seen: Option<u64>,
}

impl RuntimeHealth {
    pub fn new() -> Self {
        let now = now_epoch_ms();
        Self {
            start_epoch_ms: now,
            last_data_refresh_epoch_ms: now,
            last_render_epoch_ms: now,
            last_state_read_ok_epoch_ms: 0,
            last_state_read_fail_epoch_ms: 0,
            last_state_reuse_epoch_ms: 0,
            last_state_mtime_epoch_ms: 0,
            state_reads_ok: 0,
            state_reads_fail: 0,
            state_reuses: 0,
            render_frames: 0,
            stagnant_cycle_refreshes: 0,
            last_cycle_seen: None,
        }
    }
}

pub fn age_secs_or_inf(now_ms: u64, epoch_ms: u64) -> f64 {
    if epoch_ms > 0 {
        (now_ms.saturating_sub(epoch_ms)) as f64 / 1000.0
    } else {
        f64::INFINITY
    }
}

pub fn write_json_atomic(path: &Path, payload: &Value) -> io::Result<()> {
    let parent = path.parent().unwrap_or(Path::new("."));
    fs::create_dir_all(parent)?;

    let mut tmp = tempfile::NamedTempFile::new_in(parent)?;
    let data = serde_json::to_vec_pretty(payload)
        .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e.to_string()))?;
    io::Write::write_all(&mut tmp, &data)?;
    tmp.persist(path).map_err(|e| e.error)?;
    Ok(())
}

pub fn write_quit_signal(path: Option<&std::path::PathBuf>, tz_offset_hours: i32) {
    if let Some(p) = path {
        if let Some(parent) = p.parent() {
            let _ = fs::create_dir_all(parent);
        }
        let payload = format!(
            "quit_requested_at={}\n",
            crate::time_utils::now_hms_with_offset(tz_offset_hours)
        );
        let _ = fs::write(p, payload);
    }
}
