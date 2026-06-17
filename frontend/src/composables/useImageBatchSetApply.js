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
      if (!panel?.publicApi) continue

      // 1. 写 panel 内的 platformConfig（覆盖）
      panel.publicApi.setPlatformConfig({
        title,
        description,
        tags: tagsCopy,
      })

      // 2. 写该 panel 下已个性化账号（覆盖）
      const checkedIds = panel.publicApi.getCheckedAccountIds?.() || []
      for (const aid of checkedIds) {
        panel.publicApi.setAccountOverride(aid, {
          title,
          description,
          tags: tagsCopy,
        })
      }
    }
  }

  return { applyImageBatchSet }
}
