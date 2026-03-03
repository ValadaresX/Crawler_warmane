use ratatui::prelude::{Color, Modifier, Style};
use ratatui::widgets::{Block, BorderType, Borders};

use crate::CrawlerStatus;

pub struct Theme;

impl Theme {
    // Paleta principal WotLK "The Frozen Throne"
    pub const PRIMARY: Color = Color::Rgb(0, 180, 216);       // #00B4D8 Ice Blue
    pub const SECONDARY: Color = Color::Rgb(144, 159, 166);   // #909FA6 Plate Gray
    pub const ACCENT: Color = Color::Rgb(255, 215, 0);        // #FFD700 Legendary Gold
    pub const SUCCESS: Color = Color::Rgb(46, 204, 113);      // #2ECC71 Fel Green
    pub const DANGER: Color = Color::Rgb(231, 76, 60);        // #E74C3C Blood Red
    pub const WARNING: Color = Color::Yellow;
    pub const CHART_HI: Color = Color::Rgb(144, 224, 239);    // #90E0EF

    // Tipografia
    pub fn title() -> Style {
        Style::default()
            .fg(Self::PRIMARY)
            .add_modifier(Modifier::BOLD)
    }

    pub fn value() -> Style {
        Style::default()
            .fg(Color::White)
            .add_modifier(Modifier::BOLD)
    }

    pub fn label() -> Style {
        Style::default().fg(Self::SECONDARY)
    }

    pub fn unit() -> Style {
        Style::default()
            .fg(Self::SECONDARY)
            .add_modifier(Modifier::DIM)
    }

    pub fn group_title() -> Style {
        Style::default()
            .fg(Self::PRIMARY)
            .add_modifier(Modifier::BOLD)
    }

    /// Cor de borda contextual pelo status do crawler.
    /// Paused pulsa entre WARNING e DarkGray a cada ~0.8s.
    pub fn status_border(status: CrawlerStatus, frame_tick: u64) -> Style {
        let color = match status {
            CrawlerStatus::Running => Self::PRIMARY,
            CrawlerStatus::Paused => {
                if (frame_tick / 6).is_multiple_of(2) {
                    Self::WARNING
                } else {
                    Color::DarkGray
                }
            }
            CrawlerStatus::Stopped => Self::DANGER,
            CrawlerStatus::Unknown => Self::SECONDARY,
        };
        Style::default().fg(color)
    }

    /// Status badge: (label, fg, bg)
    pub fn status_badge(status: CrawlerStatus) -> (&'static str, Color, Color) {
        match status {
            CrawlerStatus::Running => ("COLETANDO", Color::Black, Self::SUCCESS),
            CrawlerStatus::Paused => ("PAUSADO", Color::Black, Self::WARNING),
            CrawlerStatus::Stopped => ("PARADO", Color::White, Self::DANGER),
            CrawlerStatus::Unknown => ("AGUARDANDO", Self::SECONDARY, Color::DarkGray),
        }
    }

    /// Bloco padrão temático com bordas arredondadas.
    pub fn block() -> Block<'static> {
        Block::default()
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(Style::default().fg(Self::SECONDARY))
    }

    /// Bloco temático com título em UPPERCASE + PRIMARY Bold.
    pub fn block_titled(title: &str) -> Block<'_> {
        Self::block().title(title.to_uppercase()).title_style(Self::title())
    }
}
