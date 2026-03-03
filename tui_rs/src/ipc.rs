//! Comunicação TUI → crawler via IPC (comandos e status).

use serde_json::{json, Value};

use crate::health::write_json_atomic;
use crate::time_utils::now_hms_with_offset;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum CrawlerCommand {
    Start,
    Pause,
    Cancel,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum CrawlerStatus {
    Running,
    Paused,
    Stopped,
    Unknown,
}

pub(crate) fn send_crawler_command(state_file: &std::path::Path, cmd: CrawlerCommand, tz_offset: i32) {
    let cmd_name = match cmd {
        CrawlerCommand::Start => "start",
        CrawlerCommand::Pause => "pause",
        CrawlerCommand::Cancel => "cancel",
    };
    let cmd_path = state_file
        .parent()
        .unwrap_or(std::path::Path::new("."))
        .join("tui_commands.json");
    let payload = json!({
        "command": cmd_name,
        "timestamp": now_hms_with_offset(tz_offset)
    });
    let _ = write_json_atomic(&cmd_path, &payload);
}

pub(crate) fn parse_crawler_status(state: &Value) -> CrawlerStatus {
    if let Some(s) = state.get("crawler_status").and_then(Value::as_str) {
        return match s {
            "running" => CrawlerStatus::Running,
            "paused" => CrawlerStatus::Paused,
            "stopped" => CrawlerStatus::Stopped,
            _ => CrawlerStatus::Unknown,
        };
    }
    // Fallback: inferir do campo stage
    if let Some(stage) = state.get("stage").and_then(Value::as_str) {
        return match stage {
            "shutdown_start" | "shutdown_saved" => CrawlerStatus::Stopped,
            "paused" => CrawlerStatus::Paused,
            _ => CrawlerStatus::Running,
        };
    }
    CrawlerStatus::Unknown
}
