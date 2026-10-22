export function limitTags(platform, config, descriptionTopics = 0) {
  let limit = { douyin: 5, kuaishou: 4 }[platform] ?? 10
  if (platform === 'douyin' || platform === 'xiaohongshu') limit -= descriptionTopics
  if (platform === 'douyin') limit -= (config.activityId || []).length
  return (config.tags || []).slice(0, Math.max(0, limit))
}

// Restore persisted history, never enqueue or include successful peers.
export function historyVideoSnapshot(batch, itemId, accounts, defaults, platformKeys) {
  const item = batch?.items?.find(it => it.id === itemId)
  if (batch?.type !== 'video' || item?.status !== 'failed') throw new Error('只能重新发布失败的视频记录')
  const account = accounts.find(a => a.id === item.account_id)
  const platform = account && platformKeys[account.platform]
  if (!platform) throw new Error('原账号已删除或平台不可用，请重新选择账号')
  const cfg = JSON.parse(JSON.stringify(item.account_configs || {}))
  const merged = { ...defaults[platform], ...cfg, scheduleTime: '', enableTimer: false }
  for (const [key, value] of Object.entries(defaults[platform] || {})) {
    if (merged[key] == null || (merged[key] === '' && typeof value === 'string' && value.includes('无需'))) merged[key] = value
  }
  const commonConfig = {}
  for (const key of ['videoLandscape', 'videoPortrait', 'coverLandscape', 'coverPortrait', 'coverLandscape169', 'coverPortrait916']) {
    commonConfig[key] = cfg[key] || null
  }
  if (!commonConfig.videoLandscape && !commonConfig.videoPortrait) {
    throw new Error('该旧记录未保存视频素材，请在视频发布页重新选择原视频')
  }
  return {
    commonConfig, platformConfigs: { [platform]: merged }, platformOverrides: {}, accountOverrides: {},
    publishAccountIds: [item.account_id], selectedPlatform: platform, selectedAccountId: item.account_id,
    expandedGroups: [platform],
  }
}
