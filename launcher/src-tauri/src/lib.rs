#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;
use std::io::Cursor;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use tauri::menu::{Menu, MenuItem, Submenu};
use tauri::{AppHandle, Emitter, Manager, State};
use tauri_plugin_opener::OpenerExt;
use tokio::process::Child;

/// URL default dello ZIP. Può essere sovrascritto da config.json in PlanarAllyPlus/config.json
/// Formato GitHub: https://github.com/OWNER/REPO/archive/refs/heads/BRANCH.zip
const DEFAULT_ZIP_URL: &str =
    "https://github.com/mccoy88f/PlanarAllyPlus/archive/refs/heads/dev.zip";

fn get_zip_url() -> String {
    if let Some(base) = dirs::data_local_dir().or_else(dirs::home_dir) {
        let config_path = base.join("PlanarAllyPlus").join("config.json");
        if let Ok(content) = std::fs::read_to_string(&config_path) {
            if let Ok(json) = serde_json::from_str::<serde_json::Value>(&content) {
                if let Some(url) = json.get("zip_url").and_then(|v| v.as_str()) {
                    return url.to_string();
                }
            }
        }
    }
    DEFAULT_ZIP_URL.to_string()
}

struct ServerState(Mutex<Option<Child>>);

fn app_data_dir() -> Result<PathBuf, String> {
    dirs::data_local_dir()
        .or_else(dirs::home_dir)
        .map(|p| p.join("PlanarAllyPlus"))
        .ok_or_else(|| "Cannot determine data folder".to_string())
}

fn project_root_for_dev() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let dir = exe.parent()?;
    let dir_str = dir.to_string_lossy();
    if dir_str.contains("target") {
        dir.ancestors().nth(3)
    } else {
        dir.parent()
    }
    .map(PathBuf::from)
}

/// Paths to preserve during update (relative to project root). These contain user data.
const PRESERVE_PATHS: &[&str] = &[
    "server/static/assets",
    "server/static/thumbnails",
    "server/static/mods",
    "server/data",
    "server/save_backups",
    "extensions/compendium/db",
];

/// Recursively copy directory contents (files and subdirs) from src to dst.
fn copy_dir_all(src: &Path, dst: &Path) -> Result<(), String> {
    if !src.is_dir() {
        return Err(format!("Source is not a directory: {}", src.display()));
    }
    std::fs::create_dir_all(dst).map_err(|e| format!("{}", e))?;
    for entry in std::fs::read_dir(src).map_err(|e| format!("{}", e))? {
        let entry = entry.map_err(|e| format!("{}", e))?;
        let path = entry.path();
        let name = entry
            .file_name()
            .into_string()
            .map_err(|_| "Invalid filename")?;
        let dst_path = dst.join(&name);
        if path.is_dir() {
            copy_dir_all(&path, &dst_path)?;
        } else {
            std::fs::copy(&path, &dst_path).map_err(|e| {
                format!("Failed to copy {} to {}: {}", path.display(), dst_path.display(), e)
            })?;
        }
    }
    Ok(())
}

fn backup_user_data(base: &Path, project_root: &Path) -> Result<PathBuf, String> {
    let backup_dir = base.join("pa_update_backup");
    if backup_dir.exists() {
        std::fs::remove_dir_all(&backup_dir).map_err(|e| e.to_string())?;
    }
    std::fs::create_dir_all(&backup_dir).map_err(|e| e.to_string())?;
    for rel in PRESERVE_PATHS {
        let src = project_root.join(rel);
        if src.exists() && src.is_dir() {
            let dst = backup_dir.join(rel);
            std::fs::create_dir_all(dst.parent().unwrap()).map_err(|e| e.to_string())?;
            copy_dir_all(&src, &dst).map_err(|e| format!("Backup failed for {}: {}", rel, e))?;
        }
    }
    Ok(backup_dir)
}

fn restore_user_data(backup_dir: &Path, project_root: &Path) -> Result<(), String> {
    for rel in PRESERVE_PATHS {
        let src = backup_dir.join(rel);
        let dst = project_root.join(rel);
        if src.exists() && src.is_dir() {
            if dst.exists() {
                std::fs::remove_dir_all(&dst).map_err(|e| e.to_string())?;
            }
            std::fs::create_dir_all(dst.parent().unwrap()).map_err(|e| e.to_string())?;
            copy_dir_all(&src, &dst).map_err(|e| format!("Restore failed for {}: {}", rel, e))?;
        }
    }
    std::fs::remove_dir_all(backup_dir).map_err(|e| e.to_string())?;
    Ok(())
}

fn get_project_root() -> Result<PathBuf, String> {
    if cfg!(debug_assertions) {
        if let Some(root) = project_root_for_dev() {
            if root.join("scripts").join("run.sh").exists()
                || root.join("scripts").join("run.bat").exists()
            {
                return Ok(root);
            }
        }
    }

    let base = app_data_dir()?;
    let app_dir = base.join("app");
    if !app_dir.exists() {
        return Err("App not downloaded. Click Start or Update.".to_string());
    }

    let entries: Vec<_> = std::fs::read_dir(&app_dir)
        .map_err(|e| e.to_string())?
        .filter_map(|e| e.ok())
        .collect();

    if entries.len() == 1 {
        let sub = entries[0].path();
        if sub.is_dir() && sub.join("scripts").exists() {
            return Ok(sub);
        }
    }

    if app_dir.join("scripts").exists() {
        Ok(app_dir)
    } else {
        Err("Invalid app structure. Click Update.".to_string())
    }
}

#[tauri::command]
async fn ensure_app_downloaded(app: AppHandle, force: bool) -> Result<String, String> {
    if cfg!(debug_assertions) {
        if let Some(root) = project_root_for_dev() {
            if root.join("scripts").exists() {
                return Ok(root.to_string_lossy().to_string());
            }
        }
    }

    let base = app_data_dir()?;
    let app_dir = base.join("app");
    let zip_path = base.join("planarally.zip");

    if !force && get_project_root().is_ok() {
        return Ok(get_project_root().unwrap().to_string_lossy().to_string());
    }

    let zip_url = get_zip_url();

    // Backup user data BEFORE download (if not first install)
    let backup_dir = if app_dir.exists() {
        if let Ok(project_root) = get_project_root() {
            app.emit("download-progress", "Creating user data backup...").ok();
            match backup_user_data(&base, &project_root) {
                Ok(b) => Some(b),
                Err(e) => return Err(e),
            }
        } else {
            None
        }
    } else {
        None
    };

    app.emit("download-progress", "Downloading app...").ok();

    let response = reqwest::get(&zip_url)
        .await
        .map_err(|e| format!("Download failed: {}", e))?;

    if !response.status().is_success() {
        return Err(format!("Server responded with {}", response.status()));
    }

    let bytes = response
        .bytes()
        .await
        .map_err(|e| format!("Reading response: {}", e))?;

    app.emit("download-progress", "Writing file...").ok();
    std::fs::create_dir_all(&base).map_err(|e| e.to_string())?;
    std::fs::write(&zip_path, &bytes).map_err(|e| e.to_string())?;

    app.emit("download-progress", "Extracting archive...").ok();

    if app_dir.exists() {
        std::fs::remove_dir_all(&app_dir).map_err(|e| e.to_string())?;
    }
    std::fs::create_dir_all(&app_dir).map_err(|e| e.to_string())?;

    let mut archive =
        zip::ZipArchive::new(Cursor::new(bytes)).map_err(|e| format!("Invalid ZIP: {}", e))?;

    archive
        .extract(&app_dir)
        .map_err(|e| format!("Extraction failed: {}", e))?;

    let _ = std::fs::remove_file(&zip_path);

    let root = get_project_root().map_err(|e| e.to_string())?;

    // Make scripts executable (ZIP extraction doesn't preserve Unix permissions)
    #[cfg(unix)]
    for script in ["scripts/run.sh", "scripts/start-server.sh"] {
        let p = root.join(script);
        if p.exists() {
            if let Ok(meta) = std::fs::metadata(&p) {
                let mut perms = meta.permissions();
                perms.set_mode(0o755);
                let _ = std::fs::set_permissions(&p, perms);
            }
        }
    }

    if let Some(ref b) = backup_dir {
        app.emit("download-progress", "Restoring user data backup...").ok();
        restore_user_data(b, &root).map_err(|e| e.to_string())?;
        // Verify key file exists
        let db_path = root.join("server/data/planar.sqlite");
        if !db_path.exists() {
            let _ = app.emit(
                "download-progress",
                "Warning: planar.sqlite not found after restore",
            );
        }
    }

    app.emit("download-progress", "Completed").ok();

    Ok(root.to_string_lossy().to_string())
}

#[tauri::command]
fn get_launcher_version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}

#[tauri::command]
fn get_app_version_info() -> serde_json::Value {
    // Try to read version info from the installed app.
    // Looks for version.txt, COMMIT, .commit, server/version.txt in project root.
    let root = match get_project_root() {
        Ok(r) => r,
        Err(_) => return serde_json::json!({ "commit": null, "date": null }),
    };

    // Candidate files that may contain "commit hash [date]" or just a commit hash.
    let candidates = [
        "version.txt",
        "COMMIT",
        ".commit",
        "server/version.txt",
    ];

    for candidate in &candidates {
        let p = root.join(candidate);
        if p.exists() {
            if let Ok(content) = std::fs::read_to_string(&p) {
                let content = content.trim().to_string();
                if content.is_empty() {
                    continue;
                }
                // Try to parse "COMMIT DATE" format (space-separated)
                let mut parts = content.splitn(2, ' ');
                let commit = parts.next().unwrap_or("").trim().to_string();
                let date = parts.next().map(|s| s.trim().to_string());
                if !commit.is_empty() {
                    return serde_json::json!({ "commit": commit, "date": date });
                }
            }
        }
    }

    // Fallback: try git log in the project root
    let output = std::process::Command::new("git")
        .args(["log", "-1", "--format=%h %ad", "--date=short"])
        .current_dir(&root)
        .output();
    if let Ok(out) = output {
        if out.status.success() {
            let s = String::from_utf8_lossy(&out.stdout).trim().to_string();
            if !s.is_empty() {
                let mut parts = s.splitn(2, ' ');
                let commit = parts.next().unwrap_or("").trim().to_string();
                let date = parts.next().map(|d| d.trim().to_string());
                return serde_json::json!({ "commit": commit, "date": date });
            }
        }
    }

    serde_json::json!({ "commit": null, "date": null })
}

#[tauri::command]
fn reset_app() -> Result<(), String> {
    let base = app_data_dir()?;
    let app_dir = base.join("app");
    if app_dir.exists() {
        std::fs::remove_dir_all(&app_dir)
            .map_err(|e| format!("Failed to remove app dir: {}", e))?;
    }
    Ok(())
}

#[tauri::command]
async fn get_app_status() -> Result<serde_json::Value, String> {
    let root_result = get_project_root();
    let (ready, path) = match root_result {
        Ok(p) => (true, p.to_string_lossy().to_string()),
        Err(e) => (false, e),
    };
    Ok(serde_json::json!({
        "ready": ready,
        "path": path,
        "zip_url": get_zip_url()
    }))
}

/// Kill any process listening on the given port (macOS/Linux).
/// Kill any process listening on the given port.
fn kill_process_on_port(port: u16) {
    let port_str = port.to_string();
    let _ = if cfg!(target_os = "windows") {
        std::process::Command::new("powershell")
            .args([
                "-NoProfile",
                "-Command",
                &format!("Get-NetTCPConnection -LocalPort {} -ErrorAction SilentlyContinue | ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}", port_str),
            ])
            .output()
    } else {
        std::process::Command::new("sh")
            .args([
                "-c",
                &format!("lsof -ti :{} | xargs kill 2>/dev/null || true", port_str),
            ])
            .output()
    };
}

#[tauri::command]
async fn start_server(app: AppHandle, mode: String) -> Result<(), String> {
    // Free port 8000 if already in use (e.g. previous server instance)
    kill_process_on_port(8000);
    tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;

    ensure_app_downloaded(app.clone(), false).await?;
    let root = get_project_root()?;
    let scripts = root.join("scripts");

    // Ensure scripts are executable (fixes existing installs from ZIP without execute bits)
    #[cfg(unix)]
    for script in ["run.sh", "start-server.sh"] {
        let p = scripts.join(script);
        if p.exists() {
            if let Ok(meta) = std::fs::metadata(&p) {
                let mut perms = meta.permissions();
                perms.set_mode(0o755);
                let _ = std::fs::set_permissions(&p, perms);
            }
        }
    }

    let (cmd, args): (std::ffi::OsString, Vec<std::ffi::OsString>) = if cfg!(target_os = "windows")
    {
        let batch = if mode == "full" {
            "run.bat"
        } else {
            "start-server.bat"
        };
        let path = scripts.join(batch);
        ("cmd.exe".into(), vec!["/c".into(), path.into_os_string()])
    } else {
        let sh = if mode == "full" {
            "run.sh"
        } else {
            "start-server.sh"
        };
        let path = scripts.join(sh);
        let shell = if cfg!(target_os = "macos") {
            "/bin/zsh"
        } else {
            "/bin/bash"
        };
        // Path tra apici singoli (spazi tipo "Application Support" altrimenti spezzano il comando)
        let path_arg = format!("'{}'", path.to_string_lossy().replace('\'', "'\\''"));
        // "script" crea un PTY: output in tempo reale (npm/python bufferizzano senza TTY)
        let (cmd, args) = if cfg!(target_os = "macos") {
            (
                "script".into(),
                vec![
                    "-q".into(),
                    "/dev/stdout".into(),
                    shell.into(),
                    "-l".into(),
                    "-c".into(),
                    path_arg.clone().into(),
                ],
            )
        } else {
            (
                shell.into(),
                vec!["-l".into(), "-c".into(), path_arg.into()],
            )
        };
        (cmd, args)
    };

    let mut child = tokio::process::Command::new(&cmd)
        .args(&args)
        .current_dir(&root)
        .env("PYTHONUNBUFFERED", "1")
        .env("NO_COLOR", "1")
        .env("FORCE_COLOR", "0")
        .env("TERM", "dumb")
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .map_err(|e| format!("Start failed: {}", e))?;

    let stdout = child.stdout.take().ok_or("cannot capture stdout")?;
    let stderr = child.stderr.take().ok_or("cannot capture stderr")?;

    let app_stdout = app.clone();
    let app_stderr = app.clone();
    let server_ready_emitted = std::sync::Arc::new(AtomicBool::new(false));

    fn sanitize_log(s: &str) -> String {
        let mut out = String::with_capacity(s.len());
        let mut chars = s.chars().peekable();
        while let Some(c) = chars.next() {
            if c == '\x1b' {
                // Salta sequenze ANSI: ESC [ ... lettera
                if chars.peek() == Some(&'[') {
                    chars.next();
                    while let Some(x) = chars.next() {
                        if x >= '@' && x <= '~' {
                            break;
                        }
                    }
                }
                continue;
            }
            // Salta ^D e altri control eccetto \n \t
            if c.is_control() && c != '\n' && c != '\t' {
                continue;
            }
            // Salta caratteri Braille spinner (⠙⠹⠸ ecc.)
            if ('\u{2800}'..='\u{28ff}').contains(&c) {
                continue;
            }
            out.push(c);
        }
        out
    }

    let server_ready_out = server_ready_emitted.clone();
    tokio::spawn(async move {
        use tokio::io::AsyncBufReadExt;
        let reader = tokio::io::BufReader::new(stdout);
        let mut lines = reader.lines();
        while let Ok(Some(line)) = lines.next_line().await {
            let clean = sanitize_log(&line);
            if !clean.is_empty() {
                let _ = app_stdout.emit("server-log", &clean);
                // Emit server-started only when server prints it's listening (not during npm/uv install)
                if clean.contains("Starting Webserver")
                {
                    if !server_ready_out.swap(true, Ordering::SeqCst) {
                        let _ = app_stdout.emit("server-started", ());
                    }
                }
            }
        }
    });

    tokio::spawn(async move {
        use tokio::io::AsyncBufReadExt;
        let reader = tokio::io::BufReader::new(stderr);
        let mut lines = reader.lines();
        while let Ok(Some(line)) = lines.next_line().await {
            let clean = sanitize_log(&line);
            if !clean.is_empty() {
                let _ = app_stderr.emit("server-log-err", &clean);
            }
        }
    });

    let state: State<ServerState> = app.state();
    *state.0.lock().unwrap() = Some(child);
    // server-started is emitted when we see "Starting Webserver" in the log (not at spawn time)
    Ok(())
}

#[tauri::command]
async fn stop_server(app: AppHandle) -> Result<(), String> {
    let child = app.state::<ServerState>().0.lock().unwrap().take();
    if let Some(mut c) = child {
        let _ = c.kill().await;
        let exit = c
            .wait()
            .await
            .unwrap_or(std::process::ExitStatus::default());
        let code = exit.code().unwrap_or(-1);
        let _ = app.emit("server-stopped", code);
    }
    Ok(())
}

#[tauri::command]
async fn restart_server(app: AppHandle) -> Result<(), String> {
    stop_server(app.clone()).await?;
    tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;
    start_server(app, "quick".to_string()).await
}

#[tauri::command]
async fn get_local_ip() -> Result<String, String> {
    local_ip_address::list_afinet_netifas()
        .map_err(|e| e.to_string())?
        .into_iter()
        .find(|(_, ip)| !ip.is_loopback() && matches!(ip, std::net::IpAddr::V4(_)))
        .map(|(_, ip)| ip.to_string())
        .ok_or_else(|| "No local IP found".to_string())
}

#[tauri::command]
fn open_browser_url(app: AppHandle, url: String) -> Result<(), String> {
    if !url.starts_with("http://") && !url.starts_with("https://") {
        return Err("Invalid URL scheme".to_string());
    }
    app.opener().open_url(&url, None::<&str>).map_err(|e| e.to_string())
}

#[tauri::command]
async fn exit_app(app: AppHandle) -> Result<(), String> {
    // Stop server first, then exit
    let child = app.state::<ServerState>().0.lock().unwrap().take();
    if let Some(mut c) = child {
        let _ = c.kill().await;
        let _ = c.wait().await;
    }
    app.exit(0);
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(ServerState(Mutex::new(None)))
        .setup(|app| {
            // Menu with "Show Window" so user can reopen after closing via X (window hides)
            let lang = std::env::var("LANG").unwrap_or_default();
            let (show_text, submenu_text) = if lang.starts_with("it") {
                ("Mostra finestra", "PlanarAlly Plus Launcher")
            } else {
                ("Show Window", "PlanarAlly Plus Launcher")
            };
            let show_item = MenuItem::with_id(app, "show-window", show_text, true, None::<&str>)?;
            let submenu = Submenu::with_id_and_items(app, "main", submenu_text, true, &[&show_item])?;
            let menu = Menu::with_items(app, &[&submenu])?;
            app.set_menu(menu)?;
            Ok(())
        })
        .on_menu_event(|app, event| {
            if event.id.as_ref() == "show-window" {
                if let Some(win) = app.get_webview_window("main") {
                    let _ = win.show();
                    let _ = win.set_focus();
                }
            }
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                window.hide().ok();
                api.prevent_close();
            }
        })
        .invoke_handler(tauri::generate_handler![
            ensure_app_downloaded,
            get_app_status,
            get_app_version_info,
            reset_app,
            get_launcher_version,
            start_server,
            stop_server,
            restart_server,
            get_local_ip,
            open_browser_url,
            exit_app,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        // macOS: show window when user clicks dock icon (Reopen with no visible windows)
        if let tauri::RunEvent::Reopen { has_visible_windows, .. } = event {
            if !has_visible_windows {
                if let Some(win) = app_handle.get_webview_window("main") {
                    let _ = win.show();
                    let _ = win.set_focus();
                }
            }
        }
    });
}
