import os
import shutil

from flask import Blueprint, request, jsonify, send_file
from pathlib import Path

from conf import BASE_DIR
from services.ffmpeg_service import (
    start_frame_extraction,
    get_extraction_status,
    get_frame_list,
    get_frame_image_path,
    _extract_frames_sync,
)

frames_bp = Blueprint('frames', __name__)


def _resolve_video_path(video_path):
    full_path = os.path.join(str(BASE_DIR), 'videoFile', video_path)
    if os.path.isfile(full_path):
        return full_path
    if os.path.isfile(video_path):
        return video_path
    return None


@frames_bp.post('/api/extract-frames')
def extract_frames():
    data = request.get_json(force=True)
    video_path = data.get('video_path', '')
    if not video_path:
        return jsonify({"code": 400, "msg": "video_path is required"}), 400

    full_path = _resolve_video_path(video_path)
    if not full_path:
        return jsonify({"code": 404, "msg": "Video file not found"}), 404

    status = get_extraction_status(full_path)
    if status.get("status") == "done":
        result = get_frame_list(BASE_DIR, full_path)
        return jsonify({"code": 200, "data": result})

    _extract_frames_sync(BASE_DIR, full_path)
    result = get_frame_list(BASE_DIR, full_path)
    return jsonify({"code": 200, "data": result})


@frames_bp.get('/api/frames-status')
def frames_status():
    video_path = request.args.get('video_path', '')
    if not video_path:
        return jsonify({"code": 400, "msg": "video_path is required"}), 400

    full_path = _resolve_video_path(video_path)
    if not full_path:
        return jsonify({"code": 400, "msg": "video_path not found"}), 400

    status = get_extraction_status(full_path)
    return jsonify({"code": 200, "data": status})


@frames_bp.get('/api/frames')
def get_frames():
    video_path = request.args.get('video_path', '')
    if not video_path:
        return jsonify({"code": 400, "msg": "video_path is required"}), 400

    full_path = _resolve_video_path(video_path)
    if not full_path:
        return jsonify({"code": 400, "msg": "video_path not found"}), 400

    result = get_frame_list(BASE_DIR, full_path)
    return jsonify({"code": 200, "data": result})


@frames_bp.get('/api/frame-image')
def get_frame_image():
    video_path = request.args.get('video_path', '')
    seconds = request.args.get('seconds', '0')
    thumbnail = request.args.get('thumbnail', '0') == '1'

    if not video_path:
        return jsonify({"code": 400, "msg": "video_path is required"}), 400
    try:
        seconds = int(seconds)
    except ValueError:
        return jsonify({"code": 400, "msg": "seconds must be integer"}), 400

    full_path = _resolve_video_path(video_path)
    if not full_path:
        return jsonify({"code": 404, "msg": "Video file not found"}), 404

    image_path = get_frame_image_path(BASE_DIR, full_path, seconds, thumbnail=thumbnail)
    if not image_path or not os.path.isfile(image_path):
        return jsonify({"code": 404, "msg": "Frame not found"}), 404

    return send_file(image_path, mimetype='image/jpeg')


@frames_bp.post('/api/clear-cache')
def clear_cache():
    """Clear cached data: extracted frames, etc."""
    data = request.get_json(force=True) if request.is_json else {}
    targets = data.get('targets', ['frames'])

    results = {}

    if 'frames' in targets:
        frames_dir = os.path.join(str(BASE_DIR), 'frames')
        if os.path.isdir(frames_dir):
            file_count = sum(len(files) for _, _, files in os.walk(frames_dir))
            shutil.rmtree(frames_dir)
            os.makedirs(frames_dir, exist_ok=True)
            results['frames'] = {'cleared': file_count, 'unit': 'files'}
        else:
            results['frames'] = {'cleared': 0, 'unit': 'files'}

    return jsonify({"code": 200, "data": results})


@frames_bp.get('/api/system-info')
def system_info():
    """Return version and cache size info."""
    # Read version from versions file
    version = 'unknown'
    for candidate in [
        os.path.join(str(BASE_DIR), '..', 'versions'),
        os.path.join(str(BASE_DIR), 'versions'),
    ]:
        if os.path.isfile(candidate):
            with open(candidate, 'r') as f:
                version = f.read().strip()
            break

    # Calculate frames cache size
    frames_dir = os.path.join(str(BASE_DIR), 'frames')
    frames_size = 0
    frames_count = 0
    if os.path.isdir(frames_dir):
        for dirpath, _, filenames in os.walk(frames_dir):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    frames_size += os.path.getsize(fp)
                    frames_count += 1
                except OSError:
                    pass

    return jsonify({
        "code": 200,
        "data": {
            "version": version,
            "cache": {
                "frames": {"count": frames_count, "size": frames_size},
            },
        },
    })
