use ratatui::layout::{Alignment, Constraint, Layout, Rect};
use ratatui::prelude::{Color, Line, Modifier, Span, Style};
use ratatui::symbols;
use ratatui::text::Text;
use ratatui::widgets::{
    Axis, Block, BorderType, Borders, Cell, Chart, Dataset, GraphType, LineGauge, Paragraph, Row,
    Scrollbar, ScrollbarOrientation, ScrollbarState, Sparkline, Table, Tabs, Wrap,
};
use ratatui::Frame;

use crate::snapshot::{
    build_total_points, gradient_green_red, net_health_score, net_status_label, phase_label,
    pulse_frame, ratio, ratio_between, spinner_frame, stats_new_players, CLASS_COLORS, CLASS_ORDER,
};
use crate::theme::Theme;
use crate::{ActiveTab, App, ConfigFieldKind, CrawlerStatus, GROUP_ORDER};

pub fn ui(frame: &mut Frame, app: &App, render_fps: u16, data_interval: f64) {
    let area = frame.area();
    let responsive = area.width < 100;
    let compact_v = area.height < 30;

    let [tabs_area, body_area, footer_area] = Layout::vertical([
        Constraint::Length(3),
        Constraint::Min(10),
        Constraint::Length(3),
    ])
    .areas(area);

    draw_hud(frame, tabs_area, app);

    match app.active_tab {
        ActiveTab::Dashboard => {
            if responsive {
                // Layout empilhado vertical em terminais estreitos
                let [top_area, bottom_area] =
                    Layout::vertical([Constraint::Percentage(55), Constraint::Percentage(45)])
                        .areas(body_area);
                draw_left(frame, top_area, app, compact_v);
                draw_right(frame, bottom_area, app, compact_v);
            } else {
                let [left_area, right_area] =
                    Layout::horizontal([Constraint::Percentage(58), Constraint::Percentage(42)])
                        .areas(body_area);
                draw_left(frame, left_area, app, compact_v);
                draw_right(frame, right_area, app, compact_v);
            }
        }
        ActiveTab::Config => {
            draw_config_tab(frame, body_area, app);
        }
    }

    draw_footer(frame, footer_area, app, render_fps, data_interval);
}

// ── HUD compacto (Fase 2) ────────────────────────────────────────

fn draw_hud(frame: &mut Frame, area: Rect, app: &App) {
    let border_style = Theme::status_border(app.crawler_status, app.frame_tick);
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(border_style);
    let inner = block.inner(area);
    frame.render_widget(block, area);

    // Dividir inner em 3 colunas: titulo | tabs | badge
    let title_width = 18u16;
    let badge_width = 14u16;
    let tabs_width = inner.width.saturating_sub(title_width + badge_width);

    let [title_area, tabs_area, badge_area] = Layout::horizontal([
        Constraint::Length(title_width),
        Constraint::Length(tabs_width),
        Constraint::Length(badge_width),
    ])
    .areas(inner);

    // Titulo
    frame.render_widget(
        Paragraph::new(Span::styled("WARMANE CRAWLER", Theme::title())),
        title_area,
    );

    // Tabs
    let selected = match app.active_tab {
        ActiveTab::Dashboard => 0,
        ActiveTab::Config => 1,
    };
    let tabs = Tabs::new(vec![
        Line::from(" Dashboard "),
        Line::from(" Config "),
    ])
    .select(selected)
    .style(Style::default().fg(Theme::SECONDARY))
    .highlight_style(
        Style::default()
            .fg(Color::Black)
            .bg(Theme::PRIMARY)
            .add_modifier(Modifier::BOLD),
    )
    .divider(Span::styled(" | ", Style::default().fg(Theme::SECONDARY)));
    frame.render_widget(tabs, tabs_area);

    // Badge de status
    let (label, fg, bg) = Theme::status_badge(app.crawler_status);
    let badge = Paragraph::new(Span::styled(
        format!(" {label} "),
        Style::default().fg(fg).bg(bg).add_modifier(Modifier::BOLD),
    ))
    .alignment(Alignment::Right);
    frame.render_widget(badge, badge_area);
}

// ── Aba Config ───────────────────────────────────────────────────

fn build_config_lines<'a>(app: &'a App, show_hints: bool) -> Vec<Line<'a>> {
    let mut lines: Vec<Line<'a>> = Vec::new();

    for (group, title) in &GROUP_ORDER {
        let fields: Vec<(usize, &crate::ConfigField)> = app
            .config_editor
            .fields
            .iter()
            .enumerate()
            .filter(|(_, f)| f.group == *group)
            .collect();
        if fields.is_empty() {
            continue;
        }

        // Separador de grupo
        let sep = "\u{2501}".repeat(32);
        lines.push(Line::from(vec![
            Span::styled(
                format!(" \u{2501}\u{2501} {title} "),
                Theme::group_title(),
            ),
            Span::styled(sep, Style::default().fg(Theme::SECONDARY)),
        ]));
        lines.push(Line::from(""));

        for (idx, field) in &fields {
            let selected = *idx == app.config_editor.selected;
            let indicator = if selected { " \u{25B6} " } else { "   " };
            let label_style = if selected {
                Style::default()
                    .fg(Theme::ACCENT)
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(Color::White)
            };

            let display_val = match field.kind {
                ConfigFieldKind::Bool => {
                    if field.value == "true" {
                        "[ ON  ]".to_string()
                    } else {
                        "[ OFF ]".to_string()
                    }
                }
                ConfigFieldKind::Choice => {
                    format!("[ \u{25C0} {} \u{25B6} ]", field.value)
                }
                _ => format!("[ {} ]", field.value),
            };

            let val_style = if selected {
                Style::default().fg(Theme::ACCENT)
            } else {
                match field.kind {
                    ConfigFieldKind::Bool => {
                        if field.value == "true" {
                            Style::default().fg(Theme::SUCCESS)
                        } else {
                            Style::default().fg(Theme::SECONDARY)
                        }
                    }
                    ConfigFieldKind::Choice => Style::default().fg(Theme::PRIMARY),
                    _ => Style::default().fg(Theme::SUCCESS),
                }
            };

            let label_padded = format!("{:<26}", field.label);
            lines.push(Line::from(vec![
                Span::styled(indicator, label_style),
                Span::styled(label_padded, label_style),
                Span::styled(display_val, val_style),
            ]));

            if show_hints {
                lines.push(Line::from(Span::styled(
                    format!("      {}", field.hint),
                    Theme::unit(),
                )));
            }
        }
        lines.push(Line::from(""));
    }
    lines
}

fn draw_config_tab(frame: &mut Frame, area: Rect, app: &App) {
    let outer_block = Theme::block_titled("Configuracao")
        .border_style(Theme::status_border(app.crawler_status, app.frame_tick));
    let inner = outer_block.inner(area);
    frame.render_widget(outer_block, area);

    let show_hints = inner.height >= 20;
    let lines = build_config_lines(app, show_hints);
    let total_lines = lines.len();
    let visible = inner.height as usize;
    let max_scroll = total_lines.saturating_sub(visible);
    let scroll = app.config_editor.scroll_offset.min(max_scroll);

    let para = Paragraph::new(Text::from(lines))
        .wrap(Wrap { trim: false })
        .scroll((scroll as u16, 0));
    frame.render_widget(para, inner);

    if total_lines > visible {
        let mut sb_state = ScrollbarState::new(max_scroll).position(scroll);
        let scrollbar = Scrollbar::new(ScrollbarOrientation::VerticalRight)
            .track_symbol(Some("\u{2591}"))
            .thumb_symbol("\u{2588}")
            .track_style(Style::default().fg(Color::DarkGray))
            .thumb_style(Style::default().fg(Theme::PRIMARY));
        frame.render_stateful_widget(scrollbar, area, &mut sb_state);
    }
}

// ── Painel esquerdo (Fase 4) ─────────────────────────────────────

fn draw_left(frame: &mut Frame, area: Rect, app: &App, compact_v: bool) {
    let block = Theme::block()
        .border_style(Theme::status_border(app.crawler_status, app.frame_tick));
    let inner = block.inner(area);
    frame.render_widget(block, area);

    if compact_v {
        // Sem gráfico em terminais baixos
        let [kpi_area, classes_area] =
            Layout::vertical([Constraint::Length(3), Constraint::Min(8)]).areas(inner);
        draw_kpi_cards(frame, kpi_area, app);
        draw_classes_table(frame, classes_area, app);
    } else {
        let [kpi_area, classes_area, total_area] = Layout::vertical([
            Constraint::Length(3),
            Constraint::Min(11),
            Constraint::Min(8),
        ])
        .areas(inner);
        draw_kpi_cards(frame, kpi_area, app);
        draw_classes_table(frame, classes_area, app);
        draw_total_chart(frame, total_area, app);
    }
}

fn draw_kpi_cards(frame: &mut Frame, area: Rect, app: &App) {
    let s = &app.current;
    let prev = if app.history.len() >= 2 {
        &app.history[app.history.len() - 2]
    } else {
        s
    };

    let [c1, c2, c3] =
        Layout::horizontal([Constraint::Ratio(1, 3), Constraint::Ratio(1, 3), Constraint::Ratio(1, 3)])
            .areas(area);

    // Card 1: Total Players
    let delta_p = s.players_total as i64 - prev.players_total as i64;
    let delta_str = if delta_p > 0 {
        format!(" +{delta_p} \u{25B2}")
    } else if delta_p < 0 {
        format!(" {delta_p} \u{25BC}")
    } else {
        String::new()
    };
    let delta_color = if delta_p > 0 {
        Theme::SUCCESS
    } else if delta_p < 0 {
        Theme::DANGER
    } else {
        Theme::SECONDARY
    };

    frame.render_widget(
        Paragraph::new(vec![
            Line::from(Span::styled("TOTAL PLAYERS", Theme::label())),
            Line::from(vec![
                Span::styled(format!("{}", s.players_total), Theme::value()),
                Span::styled(delta_str, Style::default().fg(delta_color)),
            ]),
        ]),
        c1,
    );

    // Card 2: Taxa descoberta
    let (avg_new, _, _) = stats_new_players(&app.history);
    frame.render_widget(
        Paragraph::new(vec![
            Line::from(Span::styled("DESCOBERTA", Theme::label())),
            Line::from(vec![
                Span::styled(format!("{avg_new:.1}"), Theme::value()),
                Span::styled(" /ciclo", Theme::unit()),
            ]),
        ]),
        c2,
    );

    // Card 3: Ciclo + Fase
    let phase = phase_label(&s.phase);
    frame.render_widget(
        Paragraph::new(vec![
            Line::from(Span::styled("CICLO", Theme::label())),
            Line::from(vec![
                Span::styled(format!("{}", s.cycle), Theme::value()),
                Span::styled(format!("  {phase}"), Theme::unit()),
            ]),
        ]),
        c3,
    );
}

fn draw_classes_table(frame: &mut Frame, area: Rect, app: &App) {
    let title_block = Theme::block_titled("Distribuicao por Classe");
    let inner = title_block.inner(area);
    frame.render_widget(title_block, area);

    let counts = app.current.class_counts;
    let max_count = counts.iter().copied().max().unwrap_or(1).max(1);
    let bar_width = inner.width.saturating_sub(28).clamp(8, 44) as usize;

    let rows: Vec<Row> = CLASS_ORDER
        .iter()
        .enumerate()
        .map(|(i, class_name)| {
            let count = counts[i];
            let r = count as f64 / max_count as f64;
            let len = (r * bar_width as f64).round() as usize;
            let bar = if len == 0 {
                String::new()
            } else {
                let ch = if app.unicode { "\u{2588}" } else { "#" };
                ch.repeat(len)
            };

            Row::new(vec![
                Cell::from(Span::styled(
                    *class_name,
                    Style::default().fg(CLASS_COLORS[i]),
                )),
                Cell::from(Span::styled(
                    format!("{count}"),
                    Style::default()
                        .fg(CLASS_COLORS[i])
                        .add_modifier(Modifier::BOLD),
                )),
                Cell::from(Span::styled(bar, Style::default().fg(CLASS_COLORS[i]))),
            ])
        })
        .collect();

    let table = Table::new(
        rows,
        [
            Constraint::Length(13),
            Constraint::Length(8),
            Constraint::Min(10),
        ],
    )
    .header(
        Row::new(vec!["Classe", "Qtd", ""])
            .style(Theme::label()),
    )
    .column_spacing(1);

    frame.render_widget(table, inner);
}

fn draw_total_chart(frame: &mut Frame, area: Rect, app: &App) {
    let block = Theme::block_titled("Total Players");
    let inner = block.inner(area);
    frame.render_widget(block, area);

    if inner.height < 4 {
        return;
    }

    let samples = inner.width.max(20) as usize * 2;
    let (points, x0, _xm, x1, ymin, ymax, ycur) =
        build_total_points(&app.history, samples, app.cfg.exp_x);

    let x_lo = x0 as f64;
    let mut x_hi = x1 as f64;
    if (x_hi - x_lo).abs() < f64::EPSILON {
        x_hi = x_lo + 1.0;
    }
    let y_lo = ymin as f64;
    let mut y_hi = ymax as f64;
    if (y_hi - y_lo).abs() < f64::EPSILON {
        y_hi = y_lo + 1.0;
    }

    let marker = if app.unicode {
        symbols::Marker::Braille
    } else {
        symbols::Marker::Dot
    };
    let datasets = vec![Dataset::default()
        .name(format!("total={ycur}"))
        .marker(marker)
        .graph_type(GraphType::Line)
        .style(Style::default().fg(Theme::CHART_HI))
        .data(&points)];

    let chart = Chart::new(datasets)
        .x_axis(
            Axis::default()
                .style(Theme::label())
                .bounds([x_lo, x_hi])
                .labels(vec![
                    Line::from("-5m"),
                    Line::from("-2m30s"),
                    Line::from("agora"),
                ]),
        )
        .y_axis(
            Axis::default()
                .style(Theme::label())
                .bounds([y_lo, y_hi])
                .labels(vec![
                    Line::from(format!("{ymin}")),
                    Line::from(format!("{}", (ymin + ymax) / 2)),
                    Line::from(format!("{ymax}")),
                ]),
        );

    frame.render_widget(chart, inner);
}

// ── Painel direito (Fase 5) ──────────────────────────────────────

fn draw_right(frame: &mut Frame, area: Rect, app: &App, compact_v: bool) {
    let block = Theme::block()
        .border_style(Theme::status_border(app.crawler_status, app.frame_tick));
    let inner = block.inner(area);
    frame.render_widget(block, area);

    if compact_v {
        // Modo compacto: summary + gauges + progress, sem sparkline
        let [live_area, net_area, prog_area] = Layout::vertical([
            Constraint::Length(3),
            Constraint::Length(5),
            Constraint::Min(4),
        ])
        .areas(inner);
        draw_summary(frame, live_area, app);
        draw_network_monitor(frame, net_area, app);
        draw_collection_funnel(frame, prog_area, app);
    } else {
        let [live_area, net_area, funnel_area, pace_area, spark_area] = Layout::vertical([
            Constraint::Length(3),
            Constraint::Length(6),
            Constraint::Length(5),
            Constraint::Length(2),
            Constraint::Min(3),
        ])
        .areas(inner);
        draw_summary(frame, live_area, app);
        draw_network_monitor(frame, net_area, app);
        draw_collection_funnel(frame, funnel_area, app);
        draw_recent_pace(frame, pace_area, app);
        draw_spark(frame, spark_area, app);
    }
}

fn draw_summary(frame: &mut Frame, area: Rect, app: &App) {
    let s = &app.current;
    let prev = if app.history.len() >= 2 {
        &app.history[app.history.len() - 2]
    } else {
        s
    };
    let delta_players = s.players_total as i64 - prev.players_total as i64;
    let delta_dataset = s.dataset_total as i64 - prev.dataset_total as i64;

    let spinner = spinner_frame(app.frame_tick, app.unicode);

    frame.render_widget(
        Paragraph::new(vec![
            Line::from(vec![
                Span::styled(format!("{spinner} "), Style::default().fg(Theme::PRIMARY)),
                Span::styled(
                    format!("ciclo {} ", s.cycle),
                    Theme::value(),
                ),
                Span::styled(
                    format!("{}  ", phase_label(&s.phase)),
                    Theme::label(),
                ),
                Span::styled(&s.ts_hms, Theme::unit()),
            ]),
            Line::from(vec![
                Span::styled("jogadores=", Theme::label()),
                Span::styled(format!("{}", s.players_total), Theme::value()),
                Span::styled(format!("({delta_players:+}) "), Style::default().fg(if delta_players >= 0 { Theme::SUCCESS } else { Theme::DANGER })),
                Span::styled("base=", Theme::label()),
                Span::styled(format!("{}", s.dataset_total), Theme::value()),
                Span::styled(format!("({delta_dataset:+}) "), Style::default().fg(if delta_dataset >= 0 { Theme::SUCCESS } else { Theme::DANGER })),
                Span::styled("novos=", Theme::label()),
                Span::styled(format!("{}", s.players_new), Theme::value()),
                Span::styled("  falhas=", Theme::label()),
                Span::styled(format!("{}", s.failed_total), Style::default().fg(if s.failed_total > 0 { Theme::DANGER } else { Theme::SECONDARY })),
            ]),
        ])
        .wrap(Wrap { trim: true }),
        area,
    );
}

fn draw_network_monitor(frame: &mut Frame, area: Rect, app: &App) {
    let title_block = Theme::block_titled("Monitor de Rede");
    let inner = title_block.inner(area);
    frame.render_widget(title_block, area);

    if inner.height < 3 {
        return;
    }

    let s = &app.current;
    let status_score = net_health_score(s);
    let (status_label, status_color) = net_status_label(status_score);
    let lat_ratio = ratio_between(s.lat_ema_ms, 220.0, 1800.0);
    let err_ratio = ratio_between(s.err_seq as f64, 0.0, 8.0);
    let lat_color = gradient_green_red(lat_ratio);
    let err_color = gradient_green_red(err_ratio);

    let quality_color = if status_score >= 80 {
        Theme::SUCCESS
    } else if status_score < 30 {
        Theme::DANGER
    } else {
        status_color
    };
    let quality_ratio = (status_score as f64 / 100.0).clamp(0.0, 1.0);
    // 100% = dourado
    let quality_fill = if status_score == 100 {
        Theme::ACCENT
    } else {
        quality_color
    };

    let [g1, g2, g3] = Layout::vertical([
        Constraint::Length(1),
        Constraint::Length(1),
        Constraint::Length(1),
    ])
    .areas(inner);

    frame.render_widget(
        LineGauge::default()
            .filled_style(Style::default().fg(quality_fill))
            .unfilled_style(Style::default().fg(Color::DarkGray))
            .ratio(quality_ratio)
            .label(Line::from(vec![
                Span::styled(
                    format!("{status_label} {status_score}%"),
                    Style::default().fg(quality_fill).add_modifier(Modifier::BOLD),
                ),
            ])),
        g1,
    );
    frame.render_widget(
        LineGauge::default()
            .filled_style(Style::default().fg(lat_color))
            .unfilled_style(Style::default().fg(Color::DarkGray))
            .ratio(lat_ratio.clamp(0.0, 1.0))
            .label(Line::from(vec![
                Span::styled("lat ", Theme::label()),
                Span::styled(
                    format!("{}ms", s.lat_ema_ms.round() as u64),
                    Style::default().fg(lat_color).add_modifier(Modifier::BOLD),
                ),
                Span::styled(format!("  x{:.2}", s.delay_x), Theme::unit()),
            ])),
        g2,
    );
    frame.render_widget(
        LineGauge::default()
            .filled_style(Style::default().fg(err_color))
            .unfilled_style(Style::default().fg(Color::DarkGray))
            .ratio(err_ratio.clamp(0.0, 1.0))
            .label(Line::from(vec![
                Span::styled("err ", Theme::label()),
                Span::styled(
                    format!("{}", s.err_seq),
                    Style::default().fg(err_color).add_modifier(Modifier::BOLD),
                ),
                Span::styled("/8", Theme::unit()),
            ])),
        g3,
    );
}

fn draw_collection_funnel(frame: &mut Frame, area: Rect, app: &App) {
    let title_block = Theme::block_titled("Funil de Coleta");
    let inner = title_block.inner(area);
    frame.render_widget(title_block, area);

    if inner.height < 2 {
        return;
    }

    let s = &app.current;
    let details_ratio = ratio(s.details_done as f64, s.details_target as f64);
    let profile_ratio = ratio(s.profiles_ok as f64, s.profiles_try as f64);

    // Cores degradê: Primary (targets) -> Magenta (details) -> Accent (profiles)
    let targets_color = Theme::PRIMARY;
    let details_color = Color::Rgb(180, 100, 220); // entre Primary e Accent
    let profiles_color = Theme::ACCENT;

    let targets_ratio = if s.history_roots > 0 { 1.0 } else { 0.0 };
    let fail_label = if s.profiles_fail > 0 {
        format!(" err={}", s.profiles_fail)
    } else {
        String::new()
    };

    let gauges: Vec<(f64, &str, String, Color)> = vec![
        (
            targets_ratio,
            "alvos",
            format!("{} raizes", s.history_roots),
            targets_color,
        ),
        (
            details_ratio,
            "detalhes",
            format!("{}/{}", s.details_done, s.details_target),
            details_color,
        ),
        (
            profile_ratio,
            "perfis",
            format!("{}/{}{fail_label}", s.profiles_ok, s.profiles_try),
            profiles_color,
        ),
    ];

    let constraints: Vec<Constraint> = gauges.iter().map(|_| Constraint::Length(1)).collect();
    let areas = Layout::vertical(constraints).split(inner);

    for (i, (r, lbl, val, color)) in gauges.iter().enumerate() {
        if i >= areas.len() {
            break;
        }
        frame.render_widget(
            LineGauge::default()
                .filled_style(Style::default().fg(*color))
                .unfilled_style(Style::default().fg(Color::DarkGray))
                .ratio((*r).clamp(0.0, 1.0))
                .label(Line::from(vec![
                    Span::styled(format!("{lbl} "), Theme::label()),
                    Span::styled(
                        val.clone(),
                        Style::default().fg(*color).add_modifier(Modifier::BOLD),
                    ),
                ])),
            areas[i],
        );
    }
}

fn draw_recent_pace(frame: &mut Frame, area: Rect, app: &App) {
    let (avg_new, min_new, max_new) = stats_new_players(&app.history);
    frame.render_widget(
        Paragraph::new(Line::from(vec![
            Span::styled("RITMO ", Theme::group_title()),
            Span::styled("media=", Theme::label()),
            Span::styled(format!("{avg_new:.1}"), Theme::value()),
            Span::styled("  min=", Theme::label()),
            Span::styled(format!("{min_new}"), Theme::value()),
            Span::styled("  max=", Theme::label()),
            Span::styled(format!("{max_new}"), Theme::value()),
        ])),
        area,
    );
}

fn draw_spark(frame: &mut Frame, spark_area: Rect, app: &App) {
    let spark_data: Vec<u64> = app
        .history
        .iter()
        .rev()
        .take(48)
        .map(|h| h.players_new)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .collect();
    let spark_max = spark_data.iter().copied().max().unwrap_or(1).max(1);

    let activity = pulse_frame(app.frame_tick, app.unicode);
    frame.render_widget(
        Sparkline::default()
            .block(
                Block::default()
                    .borders(Borders::TOP)
                    .border_type(BorderType::Rounded)
                    .border_style(Style::default().fg(Theme::SECONDARY))
                    .title(Span::styled(
                        format!(" NOVOS/CICLO {activity}"),
                        Theme::title(),
                    )),
            )
            .data(&spark_data)
            .max(spark_max)
            .style(Style::default().fg(Theme::CHART_HI)),
        spark_area,
    );
}

// ── Footer contextual (Fase 3) ──────────────────────────────────

fn draw_footer(frame: &mut Frame, area: Rect, app: &App, _render_fps: u16, _data_interval: f64) {
    match app.active_tab {
        ActiveTab::Dashboard => draw_footer_dashboard(frame, area, app),
        ActiveTab::Config => draw_footer_config(frame, area, app),
    }
}

/// Helper: renderiza uma tecla como badge visual `[K]`
fn key_badge<'a>(key: &'a str, label: &'a str) -> Vec<Span<'a>> {
    vec![
        Span::styled(
            format!("[{key}]"),
            Style::default()
                .fg(Color::Black)
                .bg(Theme::SECONDARY)
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(format!(" {label}  "), Style::default().fg(Color::White)),
    ]
}

fn draw_footer_dashboard(frame: &mut Frame, area: Rect, app: &App) {
    let (status_label, _fg, status_bg) = Theme::status_badge(app.crawler_status);

    let mut spans: Vec<Span<'_>> = Vec::new();

    // Acoes de controle
    match app.crawler_status {
        CrawlerStatus::Running => {
            spans.extend(key_badge("S", "Pausar"));
            spans.extend(key_badge("X", "Cancelar"));
        }
        CrawlerStatus::Paused => {
            spans.extend(key_badge("S", "Retomar"));
            spans.extend(key_badge("X", "Cancelar"));
        }
        CrawlerStatus::Stopped | CrawlerStatus::Unknown => {
            spans.extend(key_badge("S", "Iniciar"));
        }
    }
    spans.extend(key_badge("R", "Revisita"));
    spans.push(Span::styled(
        " \u{2502} ",
        Style::default().fg(Theme::SECONDARY),
    ));
    spans.extend(key_badge("1/2", "Aba"));
    spans.extend(key_badge("Q+Q", "Sair"));

    // Mensagem temporaria de controle (5s)
    if let Some((at, msg)) = &app.control_msg {
        if at.elapsed() < std::time::Duration::from_secs(5) {
            spans.push(Span::styled(
                format!("  {msg}"),
                Style::default().fg(Theme::ACCENT),
            ));
        }
    }
    if let Some((at, msg)) = &app.recollect_msg {
        if at.elapsed() < std::time::Duration::from_secs(5) {
            spans.push(Span::styled(
                format!("  {msg}"),
                Style::default().fg(Theme::ACCENT),
            ));
        }
    }

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(status_bg))
        .title(Span::styled(
            format!(" {status_label} "),
            Style::default()
                .fg(Color::Black)
                .bg(status_bg)
                .add_modifier(Modifier::BOLD),
        ));

    let footer = Paragraph::new(Line::from(spans))
        .block(block)
        .alignment(Alignment::Left);
    frame.render_widget(footer, area);
}

fn draw_footer_config(frame: &mut Frame, area: Rect, app: &App) {
    let mut spans: Vec<Span<'_>> = Vec::new();

    spans.extend(key_badge("+/-", "Ajustar"));
    spans.extend(key_badge("Enter", "Aplicar"));
    spans.extend(key_badge("Esc", "Voltar"));
    spans.extend(key_badge("Espaco", "Toggle"));
    spans.push(Span::styled(
        " \u{2502} ",
        Style::default().fg(Theme::SECONDARY),
    ));
    spans.extend(key_badge("1/2", "Aba"));
    spans.extend(key_badge("Q+Q", "Sair"));

    if app.config_editor.dirty {
        spans.push(Span::styled(
            "  * Pendente",
            Style::default().fg(Theme::WARNING),
        ));
    }

    if !app.config_editor.status_msg.is_empty() {
        spans.push(Span::styled(
            format!("  [{}]", app.config_editor.status_msg),
            Style::default().fg(Theme::ACCENT),
        ));
    }

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(Theme::PRIMARY));

    let footer = Paragraph::new(Line::from(spans))
        .block(block)
        .alignment(Alignment::Left);
    frame.render_widget(footer, area);
}
