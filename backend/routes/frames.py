import os

from flask import Blueprint, request, jsonify, send_file

from conf import BASE_DIR
from services.ffmpeg_service import (
    start_frame_extraction,
    get_extraction_status,
    get_frame_list,
    get_frame_image_path,
)

frames_bp = Blueprint('frames', __name__)


@frames_bp.post('/api/extract-frames')
def extract_frames():
    data = request.get_json(force=True)
    video_path = data.get('video_path', '')
    if not video_path:
        return jsonify({"code": 400, "msg": "video_path is required"}), 400

    # Resolve actual file path on disk
    full_path = os.path.join(str(BASE_DIR), 'videoFile', video_path)
    if not os.path.isfile(full_path):
        full_path = video_path
    if not os.path.isfile(full_path):
        return jsonify({"code": 404, "msg": "Video file not found"}), 404

    task_id = start_frame_extraction(BASE_DIR, full_path)
    return jsonify({"code": 200, "data": {"task_id": task_id}})


@frames_bp.get('/api/frames-status')
def frames_status():
    video_path = request.args.get('video_path', '')
    if not video_path:
        return jsonify({"code": 400, "msg": "video_path is required"}), 400

    full_path = os.path.join(str(BASE_DIR), 'videoFile', video_path)
    if not os.path.isfile(full_path):
        full_path = video_path

    status = get_extraction_status(full_path)
    return jsonify({"code": 200, "data": status})


@frames_bp.get('/api/frames')
def get_frames():
    video_path = request.args.get('video_path', '')
    if not video_path:
        return jsonify({"code": 400, "msg": "video_path is required"}), 400

    full_path = os.path.join(str(BASE_DIR), 'videoFile', video_path)
    if not os.path.isfile(full_path):
        full_path = video_path

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

    full_path = os.path.join(str(BASE_DIR), 'videoFile', video_path)
    if not os.path.isfile(full_path):
        full_path = video_path

    image_path = get_frame_image_path(BASE_DIR, full_path, seconds, thumbnail=thumbnail)
    if not image_path or not os.path.isfile(image_path):
        return jsonify({"code": 404, "msg": "Frame not found"}), 404

    return send_file(image_path, mimetype='image/jpeg')
