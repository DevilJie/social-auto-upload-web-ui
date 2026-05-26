"""
FFmpeg service for video processing.

Provides utilities to locate ffmpeg/ffprobe binaries, extract video metadata,
and perform frame extraction (thumbnail and HD) for the video timeline feature.
"""

import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from loguru import logger


# ---------------------------------------------------------------------------
# Binary discovery
# ---------------------------------------------------------------------------

def _validate_binary(path: str) -> bool:
    """Check that a binary actually exists and is executable."""
    try:
        result = subprocess.run(
            [path, "-version"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _find_binary(name: str) -> str:
    """Locate a binary (ffmpeg or ffprobe).

    Priority order:
      1. System PATH via shutil.which (user's installed version)
      2. Local bundle: backend/bin/<name>
      3. PyInstaller bundle: sys._MEIPASS/bin/<name>

    Validates each candidate actually runs before accepting.
    """
    # 1. System PATH — prefer user's installed version
    found = shutil.which(name)
    if found and _validate_binary(found):
        logger.debug("Found {} on system PATH: {}", name, found)
        return found
    if found:
        logger.debug("{} on PATH ({}) is not a valid binary, skipping", name, found)

    # 2. Local bundle: backend/bin/
    #    On Windows, check both "name" and "name.exe"
    bin_dir = Path(__file__).resolve().parent.parent / "bin"
    for candidate in [bin_dir / name, bin_dir / f"{name}.exe"]:
        if candidate.exists() and _validate_binary(str(candidate)):
            logger.debug("Found {} in local bundle: {}", name, candidate)
            return str(candidate)

    # 3. PyInstaller bundle
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidate = os.path.join(meipass, "bin", name)
        if os.path.isfile(candidate) and _validate_binary(candidate):
            logger.debug("Found {} in PyInstaller bundle: {}", name, candidate)
            return candidate

    raise FileNotFoundError(
        f"{name} not found or not executable. "
        f"Install {name} system-wide or place the binary in backend/bin/"
    )


def _find_ffmpeg() -> str:
    return _find_binary("ffmpeg")


def _find_ffprobe() -> str | None:
    try:
        return _find_binary("ffprobe")
    except FileNotFoundError:
        logger.warning("ffprobe not found — duration detection will be unavailable")
        return None


# Lazy-initialized module-level constants.
# ffmpeg is optional — the app should still start without it (frame features will be disabled).
FFMPEG: str | None = None
FFPROBE: str | None = None


def _ensure_binaries():
    """Resolve ffmpeg/ffprobe paths on first use."""
    global FFMPEG, FFPROBE
    if FFMPEG is None:
        try:
            FFMPEG = _find_ffmpeg()
        except FileNotFoundError:
            logger.warning("ffmpeg not found — video frame features will be disabled")
        try:
            FFPROBE = _find_ffprobe()
        except FileNotFoundError:
            logger.warning("ffprobe not found — duration detection will be unavailable")


# ---------------------------------------------------------------------------
# Video metadata
# ---------------------------------------------------------------------------

def get_video_duration(video_path: str) -> float:
    """Return the duration of *video_path* in seconds."""
    _ensure_binaries()
    if FFPROBE is None:
        return 0.0
    cmd = [
        FFPROBE,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    logger.debug("Running ffprobe: {}", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    duration = float(result.stdout.strip())
    return duration


# ---------------------------------------------------------------------------
# Frame extraction task tracking
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_extraction_tasks: dict = {}
"""In-memory dict tracking extraction status per video_path.

Format::

    {
        "video_path": {
            "status": "processing" | "done" | "error",
            "total_frames": int,
            "duration": float,
        },
        ...
    }
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _frames_dir(base_dir: Path, video_path: str) -> Path:
    """Return the directory where extracted frames are stored.

    ``{base_dir}/frames/{video_stem}/``
    """
    stem = Path(video_path).stem
    return Path(base_dir) / "frames" / stem


def _extract_frames_sync(base_dir, video_path: str) -> None:
    """Extract 1-fps thumbnails in a background thread.

    Uses a single ffmpeg pass with ``fps=1`` filter for fast extraction.
    Outputs ``frame_1.jpg`` … ``frame_N.jpg`` (1-indexed, one per second).
    """
    try:
        _ensure_binaries()
        if FFMPEG is None:
            raise FileNotFoundError("ffmpeg not available")

        output_dir = _frames_dir(base_dir, video_path)
        output_dir.mkdir(parents=True, exist_ok=True)

        duration = get_video_duration(video_path)

        with _lock:
            _extraction_tasks[video_path] = {
                "status": "processing",
                "total_frames": 0,
                "duration": duration,
            }

        output_pattern = str(output_dir / "frame_%d.jpg")
        cmd = [
            FFMPEG,
            "-i", video_path,
            "-vf", "fps=1,scale=320:-1",
            "-q:v", "3",
            "-y",
            output_pattern,
        ]
        logger.info("Extracting frames: {}", " ".join(cmd))
        subprocess.run(cmd, capture_output=True, text=True, check=True)

        frame_files = sorted(
            output_dir.glob("frame_*.jpg"),
            key=lambda f: int(f.stem.split("_", 1)[1]),
        )
        total_frames = len(frame_files)

        with _lock:
            _extraction_tasks[video_path]["status"] = "done"
            _extraction_tasks[video_path]["total_frames"] = total_frames

        logger.info(
            "Frame extraction done for {}: {} frames", video_path, total_frames
        )

    except Exception as exc:
        logger.exception("Frame extraction failed for {}: {}", video_path, exc)
        with _lock:
            _extraction_tasks[video_path] = {
                "status": "error",
                "total_frames": 0,
                "duration": 0.0,
            }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_frame_extraction(base_dir, video_path: str) -> str:
    """Start frame extraction in a daemon thread.

    Idempotent: if extraction is already *done* or *processing* for
    *video_path*, returns immediately.

    Returns:
        The *video_path* string (used as the task identifier).
    """
    with _lock:
        task = _extraction_tasks.get(video_path)
        if task and task["status"] in ("processing", "done"):
            logger.debug(
                "Extraction already {} for {}, skipping",
                task["status"],
                video_path,
            )
            return video_path

    thread = threading.Thread(
        target=_extract_frames_sync,
        args=(base_dir, video_path),
        daemon=True,
        name=f"frame-extract-{Path(video_path).stem}",
    )
    thread.start()
    return video_path


def get_extraction_status(video_path: str) -> dict:
    """Return the current extraction status dict for *video_path*.

    Returns an empty dict if no extraction has been started.
    """
    with _lock:
        return dict(_extraction_tasks.get(video_path, {}))


def get_frame_list(base_dir, video_path: str) -> dict:
    """Return the list of extracted thumbnail frames for a video.

    Returns::

        {
            "frames": [
                {"url": "/api/frame-image?video_path=...&seconds=N&thumbnail=1", "seconds": N},
                ...
            ],
            "duration": float,
        }

    Frames are sorted by filename; ``seconds`` equals ``frame_number - 1``.
    """
    output_dir = _frames_dir(base_dir, video_path)
    frames = []

    with _lock:
        task = _extraction_tasks.get(video_path, {})
        duration = task.get("duration", 0.0)

    frame_files = sorted(
        output_dir.glob("frame_*.jpg"),
        key=lambda f: int(f.stem.split("_", 1)[1]),
    )
    for f in frame_files:
        # Extract the frame number from filename like "frame_5.jpg"
        stem = f.stem  # e.g. "frame_5"
        frame_number = int(stem.split("_", 1)[1])
        seconds = frame_number - 1
        frames.append(
            {
                "url": (
                    f"/api/frame-image?video_path="
                    f"{video_path}&seconds={seconds}&thumbnail=1"
                ),
                "seconds": seconds,
            }
        )

    return {"frames": frames, "duration": duration}


def get_frame_image_path(
    base_dir, video_path: str, seconds: int, thumbnail: bool = False
) -> str | None:
    """Return the file path for a specific frame.

    Args:
        base_dir: The data base directory.
        video_path: Path to the source video.
        seconds: The timestamp in seconds.
        thumbnail: If True, return the pre-extracted low-res thumbnail.
                   If False, return (or extract on-demand) an HD frame.

    Returns:
        The absolute file path to the frame image, or None on failure.
    """
    frames_root = _frames_dir(base_dir, video_path)

    if thumbnail:
        path = frames_root / f"frame_{seconds + 1}.jpg"
        return str(path) if path.is_file() else None

    # HD frame — check cache first
    frames_root.mkdir(parents=True, exist_ok=True)
    hd_path = frames_root / f"hd_{seconds}.jpg"
    if hd_path.is_file():
        logger.debug("HD frame cache hit: {}", hd_path)
        return str(hd_path)

    _ensure_binaries()
    if FFMPEG is None:
        return None

    # Extract on-demand using time-based seeking
    cmd = [
        FFMPEG,
        "-ss", str(seconds),
        "-i", video_path,
        "-frames:v", "1",
        "-q:v", "2",
        "-y",
        str(hd_path),
    ]
    logger.info("Extracting HD frame: {}", " ".join(cmd))
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return str(hd_path)
    except subprocess.CalledProcessError as exc:
        logger.error("Failed to extract HD frame at {}s: {}", seconds, exc)
        return None
