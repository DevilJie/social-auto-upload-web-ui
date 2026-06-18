import sqlite3
import pytest
from app import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def test_create_and_list_tags(client):
    r = client.post('/api/tags', json={'name': '测试标签', 'color': '#ff0000'})
    assert r.status_code == 200
    tag_id = r.get_json()['data']['id']

    r = client.get('/api/tags')
    assert r.status_code == 200
    tags = r.get_json()['data']
    assert any(t['name'] == '测试标签' for t in tags)

    client.delete(f'/api/tags/{tag_id}')


def test_duplicate_tag_name(client):
    client.post('/api/tags', json={'name': '唯一标签'})
    r = client.post('/api/tags', json={'name': '唯一标签'})
    assert r.status_code == 409
    # cleanup
    tags = client.get('/api/tags').get_json()['data']
    for t in tags:
        if t['name'] == '唯一标签':
            client.delete(f'/api/tags/{t["id"]}')


def test_account_tags_crud(client):
    r = client.get('/getAccounts')
    accounts = r.get_json().get('data', [])
    if not accounts:
        pytest.skip('No accounts in test DB')

    account_id = accounts[0][0]
    tag = client.post('/api/tags', json={'name': '账号标签测试'}).get_json()['data']

    r = client.put(f'/api/accounts/{account_id}/tags', json={'tag_ids': [tag['id']]})
    assert r.status_code == 200

    r = client.get(f'/api/accounts/{account_id}/tags')
    assert r.status_code == 200
    assert any(t['id'] == tag['id'] for t in r.get_json()['data'])

    client.put(f'/api/accounts/{account_id}/tags', json={'tag_ids': []})
    client.delete(f'/api/tags/{tag["id"]}')


def test_batch_set_account_tags(client):
    """批量设置应追加,不清除账号已有标签"""
    accounts = client.get('/getAccounts').get_json().get('data', [])
    if len(accounts) < 2:
        pytest.skip('Need at least 2 accounts')

    tag_a = client.post('/api/tags', json={'name': '批量标签A'}).get_json()['data']
    tag_b = client.post('/api/tags', json={'name': '批量标签B'}).get_json()['data']
    tag_existing = client.post('/api/tags', json={'name': '已有标签'}).get_json()['data']

    ids = [accounts[0][0], accounts[1][0]]

    # 先清空,避免测试间状态污染
    for aid in ids:
        client.put(f'/api/accounts/{aid}/tags', json={'tag_ids': []})

    # 先给账号 0 设一个「已有标签」,验证批量不会清除它
    client.put(f'/api/accounts/{ids[0]}/tags', json={'tag_ids': [tag_existing['id']]})

    r = client.put('/api/accounts/batch/tags', json={
        'account_ids': ids,
        'tag_ids': [tag_a['id'], tag_b['id']],
    })
    assert r.status_code == 200
    assert r.get_json()['data']['updated'] == 2

    # 账号 0:追加后应有 3 个标签(已有 + A + B)
    tags0 = client.get(f'/api/accounts/{ids[0]}/tags').get_json()['data']
    assert {t['id'] for t in tags0} == {tag_existing['id'], tag_a['id'], tag_b['id']}

    # 账号 1:只有 A + B
    tags1 = client.get(f'/api/accounts/{ids[1]}/tags').get_json()['data']
    assert {t['id'] for t in tags1} == {tag_a['id'], tag_b['id']}

    # cleanup
    for aid in ids:
        client.put(f'/api/accounts/{aid}/tags', json={'tag_ids': []})
    client.delete(f'/api/tags/{tag_a["id"]}')
    client.delete(f'/api/tags/{tag_b["id"]}')
    client.delete(f'/api/tags/{tag_existing["id"]}')


def test_batch_empty_account_ids(client):
    r = client.put('/api/accounts/batch/tags', json={'account_ids': [], 'tag_ids': []})
    assert r.status_code == 400


def test_delete_tag_cascades_account_tags(client):
    """删除标签应同时清理 account_tags 中所有关联行,不留孤儿"""
    import sqlite3 as _sqlite3
    from conf import BASE_DIR as _BASE

    accounts = client.get('/getAccounts').get_json().get('data', [])
    if not accounts:
        pytest.skip('No accounts in test DB')

    account_id = accounts[0][0]
    tag = client.post('/api/tags', json={'name': '__cascade_test'}).get_json()['data']
    client.put(f'/api/accounts/{account_id}/tags', json={'tag_ids': [tag['id']]})

    _DB = _BASE / 'db' / 'database.db'
    conn = _sqlite3.connect(str(_DB))
    before = conn.execute('SELECT COUNT(*) FROM account_tags WHERE tag_id = ?', (tag['id'],)).fetchone()[0]
    conn.close()
    assert before == 1

    r = client.delete(f'/api/tags/{tag["id"]}')
    assert r.status_code == 200

    conn = _sqlite3.connect(str(_DB))
    after = conn.execute('SELECT COUNT(*) FROM account_tags WHERE tag_id = ?', (tag['id'],)).fetchone()[0]
    conn.close()
    assert after == 0
