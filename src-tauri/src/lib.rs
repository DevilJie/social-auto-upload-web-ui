use std::path::PathBuf;

#[cfg(windows)]
pub fn check_webview2() -> Result<(), String> {
    use winreg::enums::*;
    use winreg::RegKey;

    // Try multiple registry locations
    let paths = [
        "SOFTWARE\\Microsoft\\EdgeUpdate\\Clients\\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        "SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        "SOFTWARE\\Microsoft\\EdgeUpdate\\Clients\\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
    ];

    for path in &paths {
        let hkcu = RegKey::predef(HKEY_CURRENT_USER);
        if let Ok(key) = hkcu.open_subkey(path) {
            if let Ok(version) = key.get_value::<String, _>("pv") {
                if !version.is_empty() {
                    return Ok(());
                }
            }
        }
        let hklm = RegKey::predef(HKEY_LOCAL_MACHINE);
        if let Ok(key) = hklm.open_subkey(path) {
            if let Ok(version) = key.get_value::<String, _>("pv") {
                if !version.is_empty() {
                    return Ok(());
                }
            }
        }
    }
    Err("WebView2 not installed".to_string())
}

#[cfg(not(windows))]
pub fn check_webview2() -> Result<(), String> {
    Ok(())
}

pub fn get_data_dir() -> PathBuf {
    #[cfg(windows)]
    {
        std::env::var("LOCALAPPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from("."))
            .join("AI Social Auto Upload Web UI")
    }
    #[cfg(not(windows))]
    {
        std::env::var("HOME").map(|h| PathBuf::from(h)).unwrap_or_else(|_| PathBuf::from("."))
            .join(".local/share/social-auto-upload-web-ui")
    }
}

pub fn create_data_dirs(data_dir: &PathBuf) -> std::io::Result<()> {
    std::fs::create_dir_all(data_dir.join("db"))?;
    std::fs::create_dir_all(data_dir.join("cookies"))?;
    std::fs::create_dir_all(data_dir.join("cookiesFile"))?;
    std::fs::create_dir_all(data_dir.join("videoFile"))?;
    std::fs::create_dir_all(data_dir.join("data").join("logs"))?;
    Ok(())
}