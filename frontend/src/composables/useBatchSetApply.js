import { getPlatformByKey } from '@/config/platforms'

/**
 * 视频发布批量设 composable。
 * 把 payload (title/description/tags) 写入 checkedPlatformKeys 中每个渠道的:
 *   1) platformConfigs[platformKey] (渠道级, 覆盖)
 *   2) 该渠道下已开 accountChecked 的账号 → accountOverrides[id] (账号级, 覆盖)
 *
 * @param {object} refs  { platformConfigs, accountOverrides, accountChecked, accountStore }
 * @returns {{ applyBatchSet: (checkedPlatformKeys: string[], payload: { title: string, description: string, tags: string[] }) => void }}
 */
export function useBatchSetApply({ platformConfigs, accountOverrides, accountChecked, accountStore }) {
  function applyBatchSet(checkedPlatformKeys, payload) {
    const { title, description, tags } = payload
    for (const pk of checkedPlatformKeys) {
      // 1. 渠道级（覆盖）
      if (!platformConfigs[pk]) platformConfigs[pk] = {}
      platformConfigs[pk].title = title
      platformConfigs[pk].description = description
      platformConfigs[pk].tags = Array.isArray(tags) ? [...tags] : []

      // 2. 该渠道下已开 accountChecked 的账号（覆盖）
      const platformCfg = getPlatformByKey(pk)
      if (!platformCfg) continue
      const accounts = (accountStore?.accounts || []).filter(a => a.platform === platformCfg.name)
      for (const acc of accounts) {
        if (accountChecked[acc.id]) {
          if (!accountOverrides[acc.id]) accountOverrides[acc.id] = {}
          accountOverrides[acc.id].title = title
          accountOverrides[acc.id].description = description
          accountOverrides[acc.id].tags = Array.isArray(tags) ? [...tags] : []
        }
      }
    }
  }

  return { applyBatchSet }
}
