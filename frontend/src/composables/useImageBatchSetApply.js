/**
 * 图集发布批量设 composable。
 * 通过 panel.publicApi 调 useChannelForm 扩展的 setPlatformConfig / setAccountOverride。
 *
 * @param {object} refs  { panels: Map<string, panelRef> } — panels 用 platformKey 索引
 * @returns {{ applyImageBatchSet: (checkedPlatformKeys: string[], payload: { title: string, description: string, tags: string[] }) => void }}
 */
export function useImageBatchSetApply({ panels }) {
  function applyImageBatchSet(checkedPlatformKeys, payload) {
    const { title, description, tags } = payload
    const tagsCopy = Array.isArray(tags) ? [...tags] : []
    for (const pk of checkedPlatformKeys) {
      const panel = panels.get?.(pk) || panels[pk]
      // panel 组件用 defineExpose(publicApi) 直接展开方法,所以方法在 panel 上而非 panel.publicApi 下
      // 但保留 panel.publicApi 兼容 (未来如果 wrap 一下)
      const api = panel?.publicApi || panel
      if (!api?.setPlatformConfig) continue

      // 1. 写 panel 内的 platformConfig（覆盖）
      api.setPlatformConfig({
        title,
        description,
        tags: tagsCopy,
      })

      // 2. 写该 panel 下已个性化账号（覆盖）
      const checkedIds = api.getCheckedAccountIds?.() || []
      for (const aid of checkedIds) {
        api.setAccountOverride(aid, {
          title,
          description,
          tags: tagsCopy,
        })
      }
    }
  }

  return { applyImageBatchSet }
}
