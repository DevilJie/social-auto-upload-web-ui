#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader, Write};
use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::SystemTime;
use ai_social_auto_upload_lib::{create_data_dirs, get_data_dir};
use tauri::{Manager, WindowEvent};

fn main() {
    let exe_dir = std::env::current_exe()
        .unwrap()
        .parent()
        .unwrap()
        .to_path_buf();
    let log_path = exe_dir.join("app.log");

    let mut log_file = std::fs::File::create(&log_path).unwrap();
    writeln!(log_file, "[{}] INFO: Starting AI Social Auto Upload", unix_ts()).unwrap();
    writeln!(log_file, "[{}] INFO: Log file: {:?}", unix_ts(), log_path).unwrap();

    // NOTE: WebView2 check removed - Tauri will auto-install via embedBootstrapper when window opens
    writeln!(log_file, "[{}] INFO: WebView2 will be installed by Tauri if needed", unix_ts()).unwrap();

    let data_dir = get_data_dir();
    writeln!(log_file, "[{}] INFO: Data directory: {:?}", unix_ts(), data_dir).unwrap();

    // Create data directories
    if let Err(e) = create_data_dirs(&data_dir) {
        writeln!(log_file, "[{}] ERROR: Could not create data directory: {}", unix_ts(), e).unwrap();
        std::process::exit(1);
    }

    // Find available port
    let port = find_available_port(5409);
    writeln!(log_file, "[{}] INFO: Using backend port: {}", unix_ts(), port).unwrap();

    // Python path — must be the embedded distribution's python.exe (NOT Scripts/python.exe which is a venv launcher)
    let python_path = exe_dir.join("python").join("python.exe");
    let backend_path = exe_dir.join("backend").join("app.py");

    // CloakBrowser stealth Chromium — bundled with the app
    let cloakbrowser_binary_path = exe_dir.join("cloakbrowser").join("chrome.exe");

    writeln!(log_file, "[{}] INFO: exe_dir: {:?}", unix_ts(), exe_dir).unwrap();
    writeln!(log_file, "[{}] INFO: Python path: {:?}", unix_ts(), python_path).unwrap();
    writeln!(log_file, "[{}] INFO: Backend path: {:?}", unix_ts(), backend_path).unwrap();
    writeln!(log_file, "[{}] INFO: CloakBrowser binary: {:?}", unix_ts(), cloakbrowser_binary_path).unwrap();

    if !python_path.exists() {
        let msg = format!("Python not found at {:?}. The embedded Python distribution is missing.", python_path);
        writeln!(log_file, "[{}] ERROR: {}", unix_ts(), msg).unwrap();
        eprintln!("ERROR: {}", msg);
        std::process::exit(1);
    }

    // Spawn Python backend
    // PYTHONUNBUFFERED=1 ensures stdout/stderr are flushed immediately so logs appear in real-time
    let child = match Command::new(&python_path)
        .arg(&backend_path)
        .env("SAU_PORT", port.to_string())
        .env("SAU_DATA_DIR", data_dir.to_str().unwrap())
        .env("CLOAKBROWSER_BINARY_PATH", cloakbrowser_binary_path.to_str().unwrap())
        .env("PYTHONUNBUFFERED", "1")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
    {
        Ok(c) => Arc::new(Mutex::new(c)),
        Err(e) => {
            writeln!(log_file, "[{}] ERROR: Failed to start backend: {}", unix_ts(), e).unwrap();
            eprintln!("ERROR: Failed to start backend: {}", e);
            std::process::exit(1);
        }
    };

    // Log backend output in background
    let mut log_file2 = log_file.try_clone().unwrap();
    if let Ok(mut child_guard) = child.lock() {
        if let Some(stdout) = child_guard.stdout.take() {
            std::thread::spawn(move || {
                for line in BufReader::new(stdout).lines().map_while(Result::ok) {
                    writeln!(log_file2, "[{}] [backend] {}", unix_ts(), line).unwrap();
                }
            });
        }
        if let Some(stderr) = child_guard.stderr.take() {
            let mut log_file3 = log_file.try_clone().unwrap();
            std::thread::spawn(move || {
                for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                    writeln!(log_file3, "[{}] [backend error] {}", unix_ts(), line).unwrap();
                }
            });
        }
    }

    drop(log_file); // Release lock before waiting

    // Wait for backend to be ready
    let backend_url = format!("http://localhost:{}", port);
    let health_check_addr = format!("localhost:{}", port);
    let mut log_file = std::fs::OpenOptions::new().create(true).append(true).open(&log_path).unwrap();
    writeln!(log_file, "[{}] INFO: Waiting for backend at {}", unix_ts(), backend_url).unwrap();
    drop(log_file);

    let max_wait = 30;
    for i in 0..max_wait {
        // Check if the Python process has already exited (crash)
        if let Ok(mut c) = child.lock() {
            match c.try_wait() {
                Ok(Some(status)) => {
                    let mut log_file = std::fs::OpenOptions::new().create(true).append(true).open(&log_path).unwrap();
                    writeln!(log_file, "[{}] ERROR: Backend process exited prematurely with status: {}", unix_ts(), status).unwrap();
                    std::thread::sleep(std::time::Duration::from_millis(500));
                    // Dump the log file contents for diagnosis
                    if let Ok(contents) = std::fs::read_to_string(&log_path) {
                        eprintln!("=== app.log ===\n{}", contents);
                    }
                    std::process::exit(1);
                }
                Ok(None) => { /* still running, good */ }
                Err(e) => {
                    let mut log_file = std::fs::OpenOptions::new().create(true).append(true).open(&log_path).unwrap();
                    writeln!(log_file, "[{}] ERROR: Failed to check backend process: {}", unix_ts(), e).unwrap();
                }
            }
        }
        // NOTE: TcpStream::connect expects "host:port" format, NOT "http://host:port"
        if std::net::TcpStream::connect(&health_check_addr[..]).is_ok() {
            let mut log_file = std::fs::OpenOptions::new().create(true).append(true).open(&log_path).unwrap();
            writeln!(log_file, "[{}] INFO: Backend ready after {} seconds", unix_ts(), i).unwrap();
            break;
        }
        if i == max_wait - 1 {
            let mut log_file = std::fs::OpenOptions::new().create(true).append(true).open(&log_path).unwrap();
            writeln!(log_file, "[{}] ERROR: Backend did not start within {} seconds", unix_ts(), max_wait).unwrap();
            if let Ok(mut c) = child.lock() {
                c.kill().ok();
            }
            std::process::exit(1);
        }
        std::thread::sleep(std::time::Duration::from_secs(1));
    }

    // Clone for use in on_window_event
    let child_for_close = child.clone();

    // Create Tauri app
    tauri::Builder::default()
        .setup(move |app| {
            let window = app.get_webview_window("main").unwrap();
            window.eval(&format!(
                "window.location.replace('{}')",
                backend_url
            )).unwrap();
            Ok(())
        })
        .on_window_event(move |_window, event| {
            if let WindowEvent::CloseRequested { .. } = event {
                if let Ok(mut c) = child_for_close.lock() {
                    c.kill().ok();
                }
                std::process::exit(0);
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

fn unix_ts() -> u64 {
    SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH).unwrap()
        .as_secs()
}

fn find_available_port(start: u16) -> u16 {
    use std::net::TcpListener;
    for port in start..start + 100 {
        if TcpListener::bind(("127.0.0.1", port)).is_ok() {
            return port;
        }
    }
    start
}
