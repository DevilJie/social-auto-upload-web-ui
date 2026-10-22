import { test } from 'node:test'
import assert from 'node:assert/strict'
import { limitTags, historyVideoSnapshot } from '../src/utils/publishPreferences.js'

test('ordered truncation and reserved topic slots without mutation', () => {
  const tags = Array.from({length: 12}, (_, i) => `tag${i}`)
  for (const [platform, count] of [['douyin', 5], ['kuaishou', 4], ['youtube', 10], ['bilibili', 10]]) {
    assert.deepEqual(limitTags(platform, {tags}), tags.slice(0, count))
  }
  assert.equal(limitTags('douyin', {tags, activityId: ['a']}, 2).length, 2)
  assert.equal(limitTags('xiaohongshu', {tags}, 3).length, 7)
  assert.equal(tags.length, 12)
})

test('history restores only failed account, clears timer, preserves false and content', () => {
  const batch = {type: 'video', items: [
    {id: 'ok', status: 'success', account_id: 1},
    {id: 'bad', status: 'failed', account_id: 7, account_configs: {
      title: 'Video', description: 'Body', tags: ['first'], alteredContent: false,
      videoLandscape: {id: 'v', stored_path: 'v.mp4'}, scheduleTime: '2020-01-01',
    }},
  ]}
  const args = [[{id: 7, platform: 'YouTube'}], {youtube: {alteredContent: true}}, {YouTube: 'youtube'}]
  const restored = historyVideoSnapshot(batch, 'bad', ...args)
  assert.deepEqual(restored.publishAccountIds, [7])
  assert.equal(restored.platformConfigs.youtube.alteredContent, false)
  assert.equal(restored.platformConfigs.youtube.scheduleTime, '')
  assert.equal(restored.platformConfigs.youtube.title, 'Video')
  assert.equal(batch.items[1].account_configs.scheduleTime, '2020-01-01')
  assert.throws(() => historyVideoSnapshot(batch, 'ok', ...args))
  assert.throws(() => historyVideoSnapshot(batch, 'bad', [], args[1], args[2]))
})
