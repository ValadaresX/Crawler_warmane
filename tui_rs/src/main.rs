mod app;
mod config_editor;
mod health;
mod ipc;
mod snapshot;
mod theme;
mod time_utils;
mod ui;

use std::io::{self, stdout};
use std::path::PathBuf;
use std::time::{Duration, Instant};

use clap::{Parser, ValueEnum};
use crossterm::event::{self, DisableMouseCapture, Event, KeyCode, KeyEventKind};
use crossterm::execute;
use crossterm::terminal::{
    disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen,
};
use ratatui::backend::CrosstermBackend;
use ratatui::Terminal;
use serde_json::json;

use health::{write_json_atomic, write_quit_signal};
use time_utils::{now_epoch_ms, now_hms_with_offset};

// Re-exports para que ui.rs (e outros) possam usar `crate::ActiveTab` etc.
pub(crate) use app::{ActiveTab, App};
pub(crate) use config_editor::{ConfigField, ConfigFieldKind, GROUP_ORDER};
pub(crate) use ipc::CrawlerStatus;
use ipc::{send_crawler_command, CrawlerCommand};

#[derive(Debug, Clone, Copy, PartialEq, Eq, ValueEnum)]
pub(crate) enum ModeArg {
    Live,
    Demo,
    Text,
}

impl std::fmt::Display for ModeArg {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(match self {
            Self::Live => "live",
            Self::Demo => "demo",
            Self::Text => "text",
        })
    }
}

#[derive(Debug, Clone, Parser)]
#[command(name = "crawler_tui_rs")]
#[command(version)]
#[command(about = "Dashboard TUI em Rust acoplado ao estado do crawler")]
pub(crate) struct Cli {
    #[arg(long, value_enum, default_value_t = ModeArg::Live)]
    pub mode: ModeArg,

    #[arg(long, default_value = "../data/raw/adaptive_crawler_runtime.json")]
    pub state_file: PathBuf,

    #[arg(long = "refresh-seconds", default_value_t = 0.8)]
    pub refresh_seconds: f64,

    #[arg(long, default_value_t = 12, value_parser = clap::value_parser!(u16).range(1..=120))]
    pub fps: u16,

    #[arg(long, default_value_t = 240)]
    pub max_history: usize,

    #[arg(long, default_value_t = 2.2)]
    pub exp_x: f64,

    #[arg(long)]
    pub once: bool,

    #[arg(long)]
    pub ascii: bool,

    #[arg(long)]
    pub quit_file: Option<PathBuf>,

    #[arg(long)]
    pub esc_quit: bool,

    #[arg(long)]
    pub health_file: Option<PathBuf>,

    #[arg(long = "health-interval-seconds", default_value_t = 1.0)]
    pub health_interval_seconds: f64,

    #[arg(long = "tz-offset-hours", default_value_t = 0, allow_hyphen_values = true, value_parser = clap::value_parser!(i32).range(-12..=14))]
    pub tz_offset_hours: i32,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let cfg = Cli::parse();
    eprintln!("[crawler_tui_rs v{}]", env!("CARGO_PKG_VERSION"));

    if cfg.mode == ModeArg::Text {
        run_text_mode(cfg);
        return Ok(());
    }

    let mut app = App::new(cfg);
    run_tui(&mut app)?;
    Ok(())
}

fn run_text_mode(cfg: Cli) {
    let mut app = App::new(cfg);
    loop {
        app.refresh_data();
        // Text mode has no terminal.draw(); treat each loop iteration as a
        // "render" so the health snapshot reports a fresh render_age.
        app.health.last_render_epoch_ms = now_epoch_ms();
        app.health.render_frames = app.health.render_frames.saturating_add(1);
        let interval = app.cfg.refresh_seconds.max(0.12);
        app.maybe_write_health_snapshot(0, interval);
        let s = &app.current;
        println!(
            "[{}] ciclo={} fase={} players={} dataset={} new={} perfis={}/{} lat={}ms falhas_seq={}",
            s.ts_hms,
            s.cycle,
            s.phase,
            s.players_total,
            s.dataset_total,
            s.players_new,
            s.profiles_ok,
            s.profiles_try,
            s.lat_ema_ms.round() as u64,
            s.err_seq
        );
        if app.cfg.once {
            break;
        }
        std::thread::sleep(Duration::from_secs_f64(interval));
    }
}

fn run_tui(app: &mut App) -> Result<(), Box<dyn std::error::Error>> {
    enable_raw_mode()?;
    let mut out = stdout();
    execute!(out, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(out);
    let mut terminal = Terminal::new(backend)?;

    let result = run_loop(&mut terminal, app);

    disable_raw_mode()?;
    execute!(
        terminal.backend_mut(),
        LeaveAlternateScreen,
        DisableMouseCapture
    )?;
    terminal.show_cursor()?;

    result
}

fn run_loop(
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
    app: &mut App,
) -> Result<(), Box<dyn std::error::Error>> {
    let started_at = Instant::now();
    let mut quit_armed_at: Option<Instant> = None;
    let data_interval = app.cfg.refresh_seconds.max(0.12);
    let health_interval = app.cfg.health_interval_seconds.max(0.25);
    let data_duration = Duration::from_secs_f64(data_interval);
    let requested_render_fps = app.cfg.fps.clamp(1, 30);
    let requested_render_interval = Duration::from_secs_f64(1.0 / requested_render_fps as f64);
    // Em operacao, nao rende mais rapido que a chegada de dados novos.
    let render_interval = requested_render_interval.max(data_duration);
    let render_fps = (1.0 / render_interval.as_secs_f64())
        .round()
        .clamp(1.0, 30.0) as u16;
    let health_duration = Duration::from_secs_f64(health_interval);

    let mut next_data_at = Instant::now();
    let mut next_render_at = Instant::now();
    let mut next_health_at = Instant::now();
    let mut sampled_once = false;

    loop {
        let now = Instant::now();

        if now >= next_data_at {
            app.refresh_data();
            next_data_at = now + data_duration;
            sampled_once = true;
        }

        if now >= next_render_at {
            terminal.draw(|f| ui::ui(f, app, render_fps, data_interval))?;
            app.health.last_render_epoch_ms = now_epoch_ms();
            app.health.render_frames = app.health.render_frames.saturating_add(1);
            next_render_at = now + render_interval;
            // Atualizar params de layout da aba Config para scroll correto
            if let Ok(sz) = terminal.size() {
                // body_area = height - tabs(3) - footer(3); inner = body - border(2)
                let config_inner_h = (sz.height as usize).saturating_sub(8);
                app.config_editor.visible_height = config_inner_h;
                app.config_editor.show_hints = config_inner_h >= 20;
            }
        }

        if now >= next_health_at {
            app.maybe_write_health_snapshot(render_fps, data_interval);
            next_health_at = now + health_duration;
        }

        let now2 = Instant::now();
        let until_data = next_data_at.saturating_duration_since(now2);
        let until_render = next_render_at.saturating_duration_since(now2);
        let until_health = next_health_at.saturating_duration_since(now2);
        let poll_timeout = until_data
            .min(until_render)
            .min(until_health)
            // Evita busy-loop desnecessario em hardware limitado (RPi).
            .min(Duration::from_millis(250));

        if event::poll(poll_timeout)? {
            match event::read()? {
                Event::Key(k) if k.kind == KeyEventKind::Press => {
                    // ── Teclas globais (qualquer aba) ──
                    let mut handled = false;
                    match k.code {
                        KeyCode::Char('q') | KeyCode::Char('Q')
                            if started_at.elapsed() >= Duration::from_millis(1500) =>
                        {
                            let now_key = Instant::now();
                            if let Some(armed) = quit_armed_at {
                                if now_key.duration_since(armed) <= Duration::from_secs(2) {
                                    write_quit_signal(app.cfg.quit_file.as_ref(), app.cfg.tz_offset_hours);
                                    break;
                                }
                            }
                            quit_armed_at = Some(now_key);
                            handled = true;
                        }
                        KeyCode::Char('1') => {
                            app.active_tab = ActiveTab::Dashboard;
                            quit_armed_at = None;
                            handled = true;
                        }
                        KeyCode::Char('2') => {
                            app.active_tab = ActiveTab::Config;
                            app.config_editor.status_msg.clear();
                            quit_armed_at = None;
                            handled = true;
                        }
                        KeyCode::Tab => {
                            app.active_tab = match app.active_tab {
                                ActiveTab::Dashboard => ActiveTab::Config,
                                ActiveTab::Config => ActiveTab::Dashboard,
                            };
                            if app.active_tab == ActiveTab::Config {
                                app.config_editor.status_msg.clear();
                            }
                            quit_armed_at = None;
                            handled = true;
                        }
                        KeyCode::BackTab => {
                            app.active_tab = match app.active_tab {
                                ActiveTab::Dashboard => ActiveTab::Config,
                                ActiveTab::Config => ActiveTab::Dashboard,
                            };
                            if app.active_tab == ActiveTab::Config {
                                app.config_editor.status_msg.clear();
                            }
                            quit_armed_at = None;
                            handled = true;
                        }
                        _ => {}
                    }

                    if !handled {
                        match app.active_tab {
                            ActiveTab::Dashboard => {
                                match k.code {
                                    KeyCode::Char('s') | KeyCode::Char('S') => {
                                        let cmd = match app.crawler_status {
                                            CrawlerStatus::Running => CrawlerCommand::Pause,
                                            _ => CrawlerCommand::Start,
                                        };
                                        let label = match cmd {
                                            CrawlerCommand::Pause => "Pausa solicitada",
                                            CrawlerCommand::Start => "Início solicitado",
                                            CrawlerCommand::Cancel => "Cancelamento solicitado",
                                        };
                                        send_crawler_command(&app.cfg.state_file, cmd, app.cfg.tz_offset_hours);
                                        app.control_msg = Some((Instant::now(), label.into()));
                                        quit_armed_at = None;
                                    }
                                    KeyCode::Char('x') | KeyCode::Char('X') => {
                                        send_crawler_command(&app.cfg.state_file, CrawlerCommand::Cancel, app.cfg.tz_offset_hours);
                                        app.control_msg = Some((Instant::now(), "Cancelamento solicitado".into()));
                                        quit_armed_at = None;
                                    }
                                    KeyCode::Char('r') | KeyCode::Char('R') => {
                                        let cmd_path = app.cfg.state_file.parent()
                                            .unwrap_or(std::path::Path::new("."))
                                            .join("tui_commands.json");
                                        let cmd = json!({
                                            "command": "recollect",
                                            "filter": "missing_fields",
                                            "timestamp": now_hms_with_offset(app.cfg.tz_offset_hours)
                                        });
                                        let _ = write_json_atomic(&cmd_path, &cmd);
                                        app.recollect_msg = Some((Instant::now(), "Revisita solicitada!".into()));
                                        quit_armed_at = None;
                                    }
                                    KeyCode::Esc
                                        if app.cfg.esc_quit
                                            && started_at.elapsed() >= Duration::from_millis(1500) =>
                                    {
                                        write_quit_signal(app.cfg.quit_file.as_ref(), app.cfg.tz_offset_hours);
                                        break;
                                    }
                                    _ => {
                                        quit_armed_at = None;
                                    }
                                }
                            }
                            ActiveTab::Config => {
                                match k.code {
                                    KeyCode::Esc => {
                                        app.active_tab = ActiveTab::Dashboard;
                                        app.config_editor.dirty = false;
                                        app.config_editor.status_msg.clear();
                                    }
                                    KeyCode::Up => {
                                        app.config_editor.select_prev();
                                    }
                                    KeyCode::Down => {
                                        app.config_editor.select_next();
                                    }
                                    KeyCode::PageUp => {
                                        app.config_editor.page_up();
                                    }
                                    KeyCode::PageDown => {
                                        app.config_editor.page_down();
                                    }
                                    KeyCode::Home => {
                                        app.config_editor.select_first();
                                    }
                                    KeyCode::End => {
                                        app.config_editor.select_last();
                                    }
                                    KeyCode::Char('+') | KeyCode::Char('=') => {
                                        app.config_editor.increment_selected();
                                    }
                                    KeyCode::Char('-') => {
                                        app.config_editor.decrement_selected();
                                    }
                                    KeyCode::Char(' ') | KeyCode::Right => {
                                        app.config_editor.increment_selected();
                                    }
                                    KeyCode::Left => {
                                        app.config_editor.decrement_selected();
                                    }
                                    KeyCode::Backspace => {
                                        app.config_editor.backspace();
                                    }
                                    KeyCode::Enter => {
                                        let config_json = app.config_editor.to_json();
                                        let config_path = app.cfg.state_file.parent()
                                            .unwrap_or(std::path::Path::new("."))
                                            .join("tui_config.json");
                                        match write_json_atomic(&config_path, &config_json) {
                                            Ok(()) => {
                                                // Salvar config + reiniciar crawler
                                                send_crawler_command(
                                                    &app.cfg.state_file,
                                                    CrawlerCommand::Start,
                                                    app.cfg.tz_offset_hours,
                                                );
                                                app.config_editor.status_msg =
                                                    "Config aplicada".into();
                                                app.config_editor.dirty = false;
                                            }
                                            Err(e) => {
                                                app.config_editor.status_msg = format!("Erro: {e}");
                                            }
                                        }
                                    }
                                    KeyCode::Char(ch) => {
                                        app.config_editor.push_char(ch);
                                    }
                                    _ => {
                                        quit_armed_at = None;
                                    }
                                }
                            }
                        }
                    }
                    // Re-render imediato após qualquer tecla para responsividade
                    next_render_at = Instant::now();
                }
                Event::Key(_) => {}
                Event::Resize(_, h) => {
                    let config_inner_h = (h as usize).saturating_sub(8);
                    app.config_editor.visible_height = config_inner_h;
                    app.config_editor.show_hints = config_inner_h >= 20;
                    app.config_editor.ensure_visible();
                    next_render_at = Instant::now();
                }
                _ => {}
            }
        }

        app.frame_tick = app.frame_tick.wrapping_add(1);
        if app.cfg.once && sampled_once {
            break;
        }
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::thread;

    fn mk_cli(state_file: PathBuf) -> Cli {
        Cli {
            mode: ModeArg::Live,
            state_file,
            refresh_seconds: 0.1,
            fps: 10,
            max_history: 64,
            exp_x: 2.2,
            once: true,
            ascii: true,
            quit_file: None,
            esc_quit: false,
            health_file: None,
            health_interval_seconds: 1.0,
            tz_offset_hours: 0,
        }
    }


    fn mk_temp_path(name: &str) -> (PathBuf, PathBuf) {
        let dir = std::env::temp_dir().join(format!(
            "crawler_tui_rs_tests_{}_{}_{}",
            std::process::id(),
            name,
            now_epoch_ms()
        ));
        let file = dir.join("state.json");
        (dir, file)
    }

    #[test]
    fn load_live_snapshot_retries_before_first_success() -> io::Result<()> {
        let (dir, file) = mk_temp_path("retry_first_success");
        fs::create_dir_all(&dir)?;
        fs::write(&file, "{invalid")?;

        let mut app = App::new(mk_cli(file.clone()));
        app.refresh_data();
        app.refresh_data();

        assert_eq!(app.health.state_reads_ok, 0);
        assert_eq!(app.health.state_reads_fail, 2);

        let _ = fs::remove_dir_all(dir);
        Ok(())
    }

    #[test]
    fn load_live_snapshot_reuses_last_good_on_parse_error() -> io::Result<()> {
        let (dir, file) = mk_temp_path("reuse_last_good");
        fs::create_dir_all(&dir)?;
        fs::write(
            &file,
            json!({
                "cycle": 7,
                "players": {"a": {}},
                "telemetry": { "cycles": [ { "phase": "hybrid" } ] }
            })
            .to_string(),
        )?;

        let mut app = App::new(mk_cli(file.clone()));
        app.refresh_data();
        assert_eq!(app.current.cycle, 7);

        thread::sleep(Duration::from_millis(20));
        fs::write(&file, "{bad_json")?;
        app.refresh_data();

        assert_eq!(app.current.cycle, 7);
        assert_eq!(app.health.state_reads_ok, 1);
        assert_eq!(app.health.state_reads_fail, 1);

        let _ = fs::remove_dir_all(dir);
        Ok(())
    }
}
