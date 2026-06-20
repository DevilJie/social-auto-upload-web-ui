/**
 * 图集发布批量设 composable。
 * 通过 panel.publicApi 调 useChannelForm 扩展的 setPlatformConfig / setAccountOverride。
 *
 * 注：定时发布同时写 scheduleTime 和 enableTimer（enableTimer 由 scheduleTime 是否非空派生）。
 *   小红书 panel 的 publishFn 用 `enableTimer ? scheduleTime : ''` 门控，故必须同步写 enableTimer，
 *   否则批量设的 scheduleTime 会被小红书的开关（默认 false）清空。
 *
 * @param {object} refs  { panels: Map<string, panelRef> } — panels 用 platformKey 索引
 * @returns {{ applyImageBatchSet: (checkedPlatformKeys: string[], payload: { title: string, description: string, tags: string[], scheduleTime: string }) => void }}
 */
export function useImageBatchSetApply({ panels }) {
  function applyImageBatchSet(checkedPlatformKeys, payload) {
    const { title, description, tags, scheduleTime } = payload
    const mode = payload.mode || 'full'
    const tagsCopy = Array.isArray(tags) ? [...tags] : []
    const scheduleTimeValue = scheduleTime || ''
    // 定时开关由 scheduleTime 是否非空派生：选了时间→true，留空→false（立即发布）
    const enableTimerValue = !!scheduleTimeValue

    // partial 模式：仅覆盖已填写（非空）字段；未填写的字段不传（setPlatformConfig
    // / setAccountOverride 遇到 undefined 会自动跳过，保持 panel 原值）
    const isPartial = mode === 'partial'
    const hasTitle = title !== undefined && title !== ''
    const hasDescription = description !== undefined && description !== ''
    const hasTags = tagsCopy.length > 0
    const hasScheduleTime = scheduleTimeValue !== ''

    // 构造要写入的字段集合：full 模式全量，partial 模式仅含已填写字段
    function buildFields() {
      return {
        ...(isPartial ? (hasTitle ? { title } : {}) : { title }),
        ...(isPartial ? (hasDescription ? { description } : {}) : { description }),
        ...(isPartial ? (hasTags ? { tags: tagsCopy } : {}) : { tags: tagsCopy }),
        ...(isPartial
          ? (hasScheduleTime ? { scheduleTime: scheduleTimeValue, enableTimer: enableTimerValue } : {})
          : { scheduleTime: scheduleTimeValue, enableTimer: enableTimerValue }),
      }
    }

    for (const pk of checkedPlatformKeys) {
      const panel = panels.get?.(pk) || panels[pk]
      // panel 组件用 defineExpose(publicApi) 直接展开方法,所以方法在 panel 上而非 panel.publicApi 下
      // 但保留 panel.publicApi 兼容 (未来如果 wrap 一下)
      const api = panel?.publicApi || panel
      if (!api?.setPlatformConfig) continue

      const fields = buildFields()
      // partial 模式下用户可能一个字段都没填，此时 fields 为空，跳过该渠道
      // （避免 setAccountOverride({}) 误删已有 override）
      if (isPartial && Object.keys(fields).length === 0) continue

      // 1. 写 panel 内的 platformConfig（覆盖）
      api.setPlatformConfig(fields)

      // 2. 写该 panel 下已个性化账号（覆盖）
      const checkedIds = api.getCheckedAccountIds?.() || []
      for (const aid of checkedIds) {
        api.setAccountOverride(aid, fields)
      }
    }
  }

  return { applyImageBatchSet }
}
