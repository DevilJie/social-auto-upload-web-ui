# Settings Page Design

> **Route:** `/settings`
> **Purpose:** Configure application behavior, publishing preferences, and system settings

---

## Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Page Header                                                     │
│  "Settings"                                                      │
│  "Configure your application preferences"                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [General] [Publishing] [Browser] [Storage] [About]              │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  General Settings                                         │   │
│  │                                                          │   │
│  │  Theme                                                    │   │
│  │  (●) Dark Mode (default)                                 │   │
│  │  ( ) Light Mode                                          │   │
│  │  ( ) System                                              │   │
│  │                                                          │   │
│  │  Language                                                 │   │
│  │  [Simplified Chinese ▼]                                  │   │
│  │                                                          │   │
│  │  Auto-start on boot                                      │   │
│  │  [Toggle Off]                                            │   │
│  │                                                          │   │
│  │  Minimize to system tray                                 │   │
│  │  [Toggle On]                                             │   │
│  │                                                          │   │
│  │  Notifications                                           │   │
│  │  Sound on task complete  [Toggle On]                     │   │
│  │  Sound on task failure   [Toggle On]                     │   │
│  │  Desktop notification    [Toggle On]                     │   │
│  │                                                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  [Save Settings]                                                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Tab Navigation

- Horizontal tabs at top: General / Publishing / Browser / Storage / About
- Active tab: underline `var(--color-cta)`, text white
- Inactive tab: text `var(--color-text-secondary)`, hover text primary
- No card border around tabs (cleaner look)

## Tab: General

### Theme Selection
- Radio group with 3 options
- Dark: default and recommended
- Switching theme applies immediately (no save needed)
- Store in localStorage

### Language
- `el-select`: Simplified Chinese (default), English
- Changes apply on next page load

### Startup & System Tray
- `el-switch` toggles
- Auto-start: registers with OS (Tauri/Electron feature)
- System tray: minimize to tray instead of closing

### Notifications
- `el-switch` toggles for each notification type
- Sound files: use system sounds, not custom audio
- Desktop notifications: use OS notification API

## Tab: Publishing

```
┌──────────────────────────────────────────────────────────┐
│  Publishing Settings                                      │
│                                                          │
│  Publish Interval (between tasks)                        │
│  Min: [30] seconds    Max: [60] seconds                  │
│  ℹ Random interval prevents platform rate limiting       │
│                                                          │
│  Max Concurrent Tasks                                    │
│  [2] tasks simultaneously                                │
│  ℹ Too many concurrent tasks may slow down your PC       │
│                                                          │
│  Auto-retry Failed Tasks                                 │
│  [Toggle On]                                             │
│  Max retries: [3]                                        │
│  Retry delay: exponential backoff                        │
│                                                          │
│  Default Publish Mode                                    │
│  (●) Publish immediately                                 │
│  ( ) Always schedule                                     │
│                                                          │
│  Default Tag Template                                    │
│  [#________] [+ Add]                                     │
│  ℹ These tags are auto-filled in Publish Center          │
│                                                          │
│  Platform Account Defaults                               │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Douyin:  [Select default account ▼]               │  │
│  │  XHS:     [Select default account ▼]               │  │
│  │  Bilibili:[Select default account ▼]               │  │
│  │  Kuaishou:[Select default account ▼]               │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### Key Settings

- **Publish Interval:** Two number inputs (min/max), generates random delay between tasks
- **Max Concurrent:** Slider or number input, range 1-5, default 2
- **Auto-retry:** Toggle + max retry count + delay strategy
- **Default tags:** Tag input for frequently used hashtags
- **Account defaults:** Per-platform default account selector

## Tab: Browser

```
┌──────────────────────────────────────────────────────────┐
│  Browser Settings                                         │
│                                                          │
│  Browser Mode                                            │
│  ( ) Headless (faster, no visible browser)               │
│  (●) Headed (visible browser window, for debugging)      │
│                                                          │
│  ℹ Headed mode is recommended for first-time setup       │
│  to verify the automation works correctly.               │
│                                                          │
│  Browser Path (optional)                                 │
│  [________________________] [Browse]                     │
│  ℹ Leave empty to use built-in Chromium                  │
│                                                          │
│  Proxy Settings                                          │
│  [Toggle Off] Enable proxy                               │
│  Type: [HTTP ▼]                                          │
│  Address: [http://127.0.0.1:7890]                        │
│                                                          │
│  User Data Directory                                     │
│  [~/.social-auto-upload/browser-data] [Browse]           │
│  ℹ Stores browser session data separately                │
│                                                          │
│  Actions                                                 │
│  [Clear Browser Cache]   [Reinstall Chromium]            │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### Key Settings

- **Browser mode:** Headed recommended for debugging, headless for production
- **Custom browser path:** Allow using system Chrome/Edge instead of bundled Chromium
- **Proxy:** HTTP/SOCKS5 support, for users behind firewall
- **Clear cache:** Button with confirmation dialog
- **Reinstall Chromium:** Downloads fresh browser binary

## Tab: Storage

```
┌──────────────────────────────────────────────────────────┐
│  Storage Settings                                         │
│                                                          │
│  Data Directory                                           │
│  [~/.social-auto-upload/]  [Open in File Manager]        │
│                                                          │
│  Storage Usage                                            │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Database (SQLite)     12.5 MB                     │  │
│  │  Cookies               2.3 MB                      │  │
│  │  Materials (videos)    8.2 GB                      │  │
│  │  Browser Data          560 MB                      │  │
│  │  ─────────────────────────────────────             │  │
│  │  Total                 8.8 GB                      │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  Cleanup                                                  │
│  [ ] Auto-delete materials after publishing               │
│  [ ] Auto-delete browser cache on exit                    │
│  Keep logs for: [90 days ▼]                              │
│                                                          │
│  Actions                                                  │
│  [Clean Old Logs]  [Export All Data]  [Reset Database]    │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### Storage Actions

- **Clean Old Logs:** Deletes logs older than retention period
- **Export All Data:** Exports database as JSON backup
- **Reset Database:** Destructive! Requires typing "RESET" to confirm

## Tab: About

```
┌──────────────────────────────────────────────────────────┐
│  About                                                    │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │                                                    │  │
│  │         [App Logo - 80px]                          │  │
│  │                                                    │  │
│  │      Social Auto Upload                            │  │
│  │      Version 1.0.0                                 │  │
│  │                                                    │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  Components                                               │
│  Vue Frontend     v3.5.x          ✓ Up to date          │
│  Flask Backend    v3.1.x          ✓ Up to date          │
│  CloakBrowser     v0.3.x          ✓ Up to date         │
│  Chromium         v125.x          ✓ Up to date          │
│                                                          │
│  [Check for Updates]                                     │
│                                                          │
│  ─────────────────────────────────────────────────       │
│                                                          │
│  Links                                                    │
│  GitHub: dreammis/social-auto-upload                     │
│  License: MIT                                            │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

- Component versions: read from package.json and Python requirements
- "Check for Updates": checks GitHub releases for new version
- Links: open in external browser via `shell.openExternal()`

## Save Behavior

- Settings auto-save on change (debounced 500ms)
- Show subtle "Saved" toast notification (bottom-right, fades after 2s)
- No explicit "Save" button needed, but show for user comfort
- Store in: `localStorage` for UI settings, `config.json` file for backend settings

## Form Design Patterns

- All inputs: dark themed per global spec
- Info tooltips (`ℹ`): `el-tooltip` with description text
- Toggle switches: `el-switch`, green when on, gray when off
- Number inputs: `el-input-number` with min/max bounds
- Path inputs: text input + "Browse" button (`el-button`)

## Empty State

- N/A (settings page always has content)
