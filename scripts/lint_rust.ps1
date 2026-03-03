Param(
    [string]$ManifestPath = "tui_rs/Cargo.toml"
)

$ErrorActionPreference = "Stop"

cargo fmt --manifest-path $ManifestPath -- --check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
cargo clippy --manifest-path $ManifestPath --all-targets -- -D warnings -D clippy::unwrap_used -D clippy::expect_used -D clippy::panic -D clippy::todo -D clippy::unimplemented -D clippy::dbg_macro -W clippy::all
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
