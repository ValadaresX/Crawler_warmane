use std::time::{SystemTime, UNIX_EPOCH};

pub fn now_hms() -> String {
    now_hms_with_offset(0)
}

pub fn now_hms_with_offset(tz_offset_hours: i32) -> String {
    let epoch_secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64;
    let local_secs = epoch_secs + (tz_offset_hours as i64) * 3600;
    let day_secs = local_secs.rem_euclid(86_400) as u64;
    let h = day_secs / 3600;
    let m = (day_secs % 3600) / 60;
    let s = day_secs % 60;
    format!("{h:02}:{m:02}:{s:02}")
}

pub fn now_epoch_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

pub fn system_time_to_epoch_ms(st: SystemTime) -> u64 {
    st.duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

pub fn lcg_next(seed: &mut u64) -> u64 {
    *seed = seed
        .wrapping_mul(6364136223846793005)
        .wrapping_add(1442695040888963407);
    *seed
}
