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
