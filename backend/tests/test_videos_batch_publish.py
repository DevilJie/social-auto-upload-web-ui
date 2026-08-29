"""POST /api/v2/videos/batch-publish 端点集成测试。"""
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# 平台名 → 整数平台 id（与 init_db.py 一致）
_PLATFORM_NAME_TO_TYPE = {
    'xiaohongshu': 1, 'channels': 2, 'douyin': 3, 'kuaishou': 4,
    'bilibili': 5, 'baijiahao': 6, 'tiktok': 7, 'youtube': 8,
    'tencent_video': 9, 'iqiyi': 10, 'weibo': 11, 'alipay': 12,
    'toutiao': 13, 'zhihu': 14, 'csdn': 15, 'vivo': 16,
    'weixin_gzh': 17, 'taobao_guanghe': 18, 'jingmai': 19,
}


def _setup_db(tmp_db):
    conn = sqlite3.connect(str(tmp_db))
    conn.executescript("""
        CREATE TABLE user_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type INTEGER NOT NULL,
            filePath TEXT NOT NULL DEFAULT '',
            userName TEXT NOT NULL DEFAULT '',
            status INTEGER DEFAULT 0,
            avatar TEXT DEFAULT ''
        );
        CREATE TABLE materials (
            id TEXT PRIMARY KEY,
            original_filename TEXT DEFAULT '',
            stored_path TEXT DEFAULT '',
            file_type TEXT DEFAULT '',
            mime_type TEXT DEFAULT '',
            file_size INTEGER DEFAULT 0,
            storage_type TEXT DEFAULT 'local',
            duration REAL DEFAULT 0,
            orientation TEXT DEFAULT ''
        );
        CREATE TABLE publish_batches (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            video_material_id TEXT DEFAULT '',
            image_material_ids TEXT DEFAULT '[]',
            landscape_cover_material_id TEXT DEFAULT '',
            portrait_cover_material_id TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            account_count INTEGER NOT NULL DEFAULT 0,
            success_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            schedule_time TEXT DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            draft_id INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            scheduled_at TEXT DEFAULT '',
            interval_minutes REAL DEFAULT 0,
            next_batch_id TEXT DEFAULT ''
        );
        CREATE TABLE publish_details (
            id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            account_id INTEGER,
            account_name TEXT NOT NULL DEFAULT '',
            platform TEXT NOT NULL DEFAULT '',
            account_configs TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending',
            retry_count INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 3,
            error_message TEXT NOT NULL DEFAULT '',
            publish_url TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            FOREIGN KEY (batch_id) REFERENCES publish_batches(id) ON DELETE CASCADE
        );
        CREATE TABLE settings (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT '',
            updated_at TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()


def _insert_user(conn, id, platform, file_path):
    conn.execute(
        "INSERT INTO user_info (id, type, filePath, userName) VALUES (?, ?, ?, ?)",
        (id, _PLATFORM_NAME_TO_TYPE[platform], file_path, platform)
    )
    conn.commit()


def _video_data(name='v.mp4'):
    """单个视频的完整 draft_data 快照（与前端 serializeVideoState 同构）。"""
    return {
        'commonConfig': {
            'videoLandscape': {'id': 'm1', 'stored_path': '/abs/v.mp4',
                               'name': name, 'url': '/x', 'size': 100, 'type': 'video/mp4'},
            'videoPortrait': None,
            'coverLandscape': {'id': 'c1', 'stored_path': '/abs/c.jpg',
                               'name': 'c.jpg', 'url': '/x', 'size': 10, 'type': 'image/jpeg'},
            'coverPortrait': None,
        },
        'platformConfigs': {
            'xiaohongshu': {'title': 'T', 'aiContent': '内容由AI生成',
                            'description': '', 'tags': [], 'scheduleTime': ''},
        },
        'platformOverrides': {},
        'accountOverrides': {},
        'publishAccountIds': [1],
    }


def _patch_common(monkeypatch, db_path):
    monkeypatch.setattr('services.draft_merge.DB_PATH', db_path)
    monkeypatch.setattr('ext_api.DB_PATH', db_path)
    monkeypatch.setattr('storage.resolve_material_path', lambda p: p)
    monkeypatch.setattr('app._get_db_path', lambda: db_path)
    monkeypatch.setattr('app._ensure_db', lambda: None)


def test_batch_publish_2videos_2accounts(tmp_path, monkeypatch):
    """2 视频 × 各 1 账号 → 2 batch；链头视频立即入队，第二个视频暂存待排程。"""
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        _insert_user(conn, 1, 'xiaohongshu', '/cookies/x1')

    added_tasks = []

    def fake_add_task(task):
        added_tasks.append(task)

    from ext_api import task_queue as tq
    queue_mock = MagicMock(add_task=fake_add_task)
    monkeypatch.setattr(tq, 'get_task_queue', lambda: queue_mock)
    _patch_common(monkeypatch, db_path)

    from app import app
    client = app.test_client()
    resp = client.post('/api/v2/videos/batch-publish',
                       json={'videos': [_video_data('a.mp4'), _video_data('b.mp4')]})

    assert resp.status_code == 200
    data = resp.get_json()['data'] if 'data' in resp.get_json() else resp.get_json()
    assert len(data['task_ids']) == 2
    assert len(set(data['batch_ids'])) == 2   # 每视频独立 batch
    assert data['failed'] == []
    # 发布链：只有链头（第一个视频）的任务立即入队执行
    assert len(added_tasks) == 1
    assert added_tasks[0].source == 'batch'
    assert added_tasks[0].max_retries == 0
    assert added_tasks[0].platform == '小红书'
    assert added_tasks[0].title == 'T'
    # 第二个视频：只写库（details=pending）+ 暂存待排程，不立即入队
    queue_mock._insert_db.assert_called_once()
    queue_mock.add_pending_batch.assert_called_once()
    pending_bid, pending_tasks = queue_mock.add_pending_batch.call_args[0]
    assert len(pending_tasks) == 1
    assert pending_bid in data['batch_ids']
    assert pending_bid != added_tasks[0].batch_id


def test_batch_publish_invalid_video_reports_failure(tmp_path, monkeypatch):
    """缺封面视频 → 该视频 failed，不入队。"""
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        _insert_user(conn, 1, 'xiaohongshu', '/cookies/x1')

    added_tasks = []
    from ext_api import task_queue as tq
    monkeypatch.setattr(tq, 'get_task_queue',
                        lambda: MagicMock(add_task=added_tasks.append))
    _patch_common(monkeypatch, db_path)

    bad = _video_data()
    bad['commonConfig']['coverLandscape'] = None   # 去掉封面 → 校验失败

    from app import app
    client = app.test_client()
    resp = client.post('/api/v2/videos/batch-publish',
                       json={'videos': [bad, _video_data('ok.mp4')]})

    assert resp.status_code == 200
    body = resp.get_json()
    data = body.get('data', body)
    assert len(data['task_ids']) == 1
    assert len(data['failed']) == 1
    assert data['failed'][0]['video'] == 0
    assert '封面' in data['failed'][0]['reason']
    assert len(added_tasks) == 1


def test_batch_publish_video_limit_validation(tmp_path, monkeypatch):
    """素材表有 duration 时，超时长视频被拦截（xiaohongshu 上限 14400s）。"""
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        _insert_user(conn, 1, 'xiaohongshu', '/cookies/x1')
        conn.execute(
            "INSERT INTO materials (id, stored_path, duration, file_size) "
            "VALUES ('m1', '/abs/v.mp4', 99999, 100)")
        conn.commit()

    added_tasks = []
    from ext_api import task_queue as tq
    monkeypatch.setattr(tq, 'get_task_queue',
                        lambda: MagicMock(add_task=added_tasks.append))
    _patch_common(monkeypatch, db_path)

    from app import app
    client = app.test_client()
    resp = client.post('/api/v2/videos/batch-publish',
                       json={'videos': [_video_data()]})

    assert resp.status_code == 200
    body = resp.get_json()
    data = body.get('data', body)
    assert data['task_ids'] == []
    assert len(data['failed']) == 1
    assert '小红书' in data['failed'][0]['reason'] or '时长' in data['failed'][0]['reason']
    assert added_tasks == []


def test_batch_publish_title_length_validation(tmp_path, monkeypatch):
    """小红书标题 > 20 字 → 逐账号校验拦截。"""
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        _insert_user(conn, 1, 'xiaohongshu', '/cookies/x1')

    added_tasks = []
    from ext_api import task_queue as tq
    monkeypatch.setattr(tq, 'get_task_queue',
                        lambda: MagicMock(add_task=added_tasks.append))
    _patch_common(monkeypatch, db_path)

    vd = _video_data()
    vd['platformConfigs']['xiaohongshu']['title'] = '这是一个非常非常非常非常长的标题超过二十个字'

    from app import app
    client = app.test_client()
    resp = client.post('/api/v2/videos/batch-publish', json={'videos': [vd]})

    assert resp.status_code == 200
    body = resp.get_json()
    data = body.get('data', body)
    assert data['task_ids'] == []
    assert len(data['failed']) == 1
    assert '标题' in data['failed'][0]['reason']
    assert added_tasks == []


def test_batch_publish_payload_platform_fields(tmp_path, monkeypatch):
    """payload 含全量平台字段（以 weibo/guanghe 为代表校验映射）。"""
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        _insert_user(conn, 1, 'weibo', '/cookies/w1')

    added_tasks = []
    from ext_api import task_queue as tq
    monkeypatch.setattr(tq, 'get_task_queue',
                        lambda: MagicMock(add_task=added_tasks.append))
    _patch_common(monkeypatch, db_path)

    vd = _video_data()
    vd['platformConfigs'] = {
        'weibo': {
            'title': '微博标题', 'description': '正文', 'tags': [],
            'videoType': '原创',
            'weiboCategory': ['搞笑', '沙雕日常'],
            'contentStatement': '包含虚构创作',
            'scheduleTime': '',
        },
    }

    from app import app
    client = app.test_client()
    resp = client.post('/api/v2/videos/batch-publish', json={'videos': [vd]})

    assert resp.status_code == 200
    body = resp.get_json()
    data = body.get('data', body)
    assert data['failed'] == []
    assert len(added_tasks) == 1
    p = added_tasks[0].payload
    # weibo：类型走 ai_content，category 是级联数组
    assert p['ai_content'] == '原创'
    assert p['category'] == ['搞笑', '沙雕日常']
    assert p['content_statement'] == '包含虚构创作'
    # 封面互备：只有横版封面时竖版用同图
    assert p['thumbnail_landscape_path'] == '/abs/c.jpg'
    assert p['thumbnail_portrait_path'] == '/abs/c.jpg'


def test_batch_publish_propagates_interval_minutes(tmp_path, monkeypatch):
    """发布页 interval_minutes 被写入每个任务的 batch_interval_minutes。

    覆盖三种语义：
      - 正数（30）→ 透传，worker 会等待 30 分钟
      - 0        → 写入 0.0（= 不等待）
      - 缺省     → 写入 0.0（与旧行为一致，向后兼容）
    """
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        _insert_user(conn, 1, 'xiaohongshu', '/cookies/x1')

    added_tasks = []
    from ext_api import task_queue as tq
    monkeypatch.setattr(tq, 'get_task_queue',
                        lambda: MagicMock(add_task=added_tasks.append))
    _patch_common(monkeypatch, db_path)

    from app import app
    client = app.test_client()

    # 1) 显式传 30 → task.batch_interval_minutes == 30.0
    resp = client.post(
        '/api/v2/videos/batch-publish',
        json={'videos': [_video_data('a.mp4')], 'interval_minutes': 30},
    )
    assert resp.status_code == 200
    assert added_tasks[-1].batch_interval_minutes == 30.0

    # 2) 显式传 0 → task.batch_interval_minutes == 0.0（不等待）
    resp = client.post(
        '/api/v2/videos/batch-publish',
        json={'videos': [_video_data('b.mp4')], 'interval_minutes': 0},
    )
    assert resp.status_code == 200
    assert added_tasks[-1].batch_interval_minutes == 0.0

    # 3) 缺省/非法/负数 → 统一规整为 0.0，向后兼容
    for bad in (None, 'abc', -5, -0.001):
        added_tasks.clear()
        body = {'videos': [_video_data('c.mp4')]}
        if bad is not None:
            body['interval_minutes'] = bad
        resp = client.post('/api/v2/videos/batch-publish', json=body)
        assert resp.status_code == 200
        assert added_tasks[-1].batch_interval_minutes == 0.0, (
            f"interval_minutes={bad!r} should normalize to 0.0"
        )


def test_batch_publish_empty_videos_rejected(tmp_path, monkeypatch):
    """videos 缺失/空数组 → 400。"""
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    _patch_common(monkeypatch, db_path)

    from app import app
    client = app.test_client()
    resp = client.post('/api/v2/videos/batch-publish', json={'videos': []})
    assert resp.status_code == 400
    resp = client.post('/api/v2/videos/batch-publish', json={})
    assert resp.status_code == 400
