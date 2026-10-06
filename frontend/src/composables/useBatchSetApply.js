import { getPlatformByKey, DECLARATION_FIELD_MAP } from '@/config/platforms'

/**
 * 视频发布批量设 composable。
 * 把 payload (title/description/tags/scheduleTime) 写入 checkedPlatformKeys 中每个渠道的:
 *   1) platformConfigs[platformKey] (渠道级, 覆盖)
 *   2) 该渠道下已开 accountChecked 的账号 → accountOverrides[id] (账号级, 覆盖)
 *
 * 注：视频侧 enableTimer 在发布时由 scheduleTime 派生（PublishCenter.vue 构造 publishData 时
 *   enableTimer = scheduleTime ? 1 : 0），故此处只写 scheduleTime。
 *
 * @param {object} refs  { platformConfigs, accountOverrides, accountChecked, accountStore }
 * @returns {{ applyBatchSet: (checkedPlatformKeys: string[], payload: { title: string, description: string, tags: string[], scheduleTime: string }) => void }}
 */
export function useBatchSetApply({ platformConfigs, accountOverrides, accountChecked, accountStore }) {
  /**
   * targets 可选：不传 = 写入构造时绑定的活状态（当前视频）；
   * 传入 { platformConfigs, accountOverrides } = 就地写入指定对象
   * （「全视频应用」时对队列里每个快照的配置直接写入）。
   */
  function applyBatchSet(checkedPlatformKeys, payload, targets) {
    const pcs = targets?.platformConfigs || platformConfigs
    const aos = targets?.accountOverrides || accountOverrides
    const { title, description, tags, scheduleTime, isOriginal, declaration } = payload
    const mode = payload.mode || 'full'
    const tagsCopy = Array.isArray(tags) ? [...tags] : []
    const scheduleTimeValue = scheduleTime || ''

    // partial 模式：仅覆盖已填写（非空）字段，空值字段跳过保持原值
    const isPartial = mode === 'partial'
    const hasTitle = title !== undefined && title !== ''
    const hasDescription = description !== undefined && description !== ''
    const hasTags = tagsCopy.length > 0
    const hasScheduleTime = scheduleTimeValue !== ''
    // 作品声明/原创声明与 mode 无关：null = 未选择（跳过），选了就写
    const hasIsOriginal = isOriginal === true || isOriginal === false
    const hasDeclaration = declaration === 'none' || declaration === 'ai'

    for (const pk of checkedPlatformKeys) {
      // 1. 渠道级（覆盖）
      if (!pcs[pk]) pcs[pk] = {}
      if (!isPartial || hasTitle) pcs[pk].title = title
      if (!isPartial || hasDescription) pcs[pk].description = description
      if (!isPartial || hasTags) pcs[pk].tags = tagsCopy
      if (!isPartial || hasScheduleTime) pcs[pk].scheduleTime = scheduleTimeValue

      // 2. 作品声明（批量统一语义 → 各平台字段 key + 选项文案）
      if (hasDeclaration) {
        const mapping = DECLARATION_FIELD_MAP[pk]
        const value = mapping?.[declaration]
        if (mapping && value !== undefined) {
          pcs[pk][mapping.field] = value
        }
      }

      // 3. 原创声明：有 isOriginal 字段的平台直接写；微博用 videoType 承担原创/转载语义
      if (hasIsOriginal) {
        const platformCfg = getPlatformByKey(pk)
        const supportsIsOriginal = platformCfg?.settingsFields?.some(f => f.key === 'isOriginal')
        if (supportsIsOriginal) {
          pcs[pk].isOriginal = isOriginal
        } else if (pk === 'weibo') {
          pcs[pk].videoType = isOriginal ? '原创' : '转载'
        }
      }

      // 2. 该渠道下所有账号（覆盖）—— 不再用 accountChecked 筛选：
      //    五角星(账号级表单个性化)走的是 accountOverrides，与媒体开关 accountChecked 无关，
      //    故批量设置应替换该渠道下所有账号，无论是否已个性化。
      const platformCfg = getPlatformByKey(pk)
      if (!platformCfg) continue
      const accounts = (accountStore?.accounts || []).filter(a => a.platform === platformCfg.name)
      for (const acc of accounts) {
        if (!aos[acc.id]) aos[acc.id] = {}
        if (!isPartial || hasTitle) aos[acc.id].title = title
        if (!isPartial || hasDescription) aos[acc.id].description = description
        if (!isPartial || hasTags) aos[acc.id].tags = tagsCopy
        if (!isPartial || hasScheduleTime) aos[acc.id].scheduleTime = scheduleTimeValue
        if (hasDeclaration) {
          const mapping = DECLARATION_FIELD_MAP[pk]
          const value = mapping?.[declaration]
          if (mapping && value !== undefined) {
            aos[acc.id][mapping.field] = value
          }
        }
        if (hasIsOriginal) {
          const platformCfg = getPlatformByKey(pk)
          const supportsIsOriginal = platformCfg?.settingsFields?.some(f => f.key === 'isOriginal')
          if (supportsIsOriginal) {
            aos[acc.id].isOriginal = isOriginal
          } else if (pk === 'weibo') {
            aos[acc.id].videoType = isOriginal ? '原创' : '转载'
          }
        }
      }
    }
  }

  return { applyBatchSet }
}
