import { ref, reactive, watch } from 'vue'

/**
 * 渠道表单数据管理 composable。
 * 封装两级配置（渠道默认 + 账号覆盖）的创建、切换、同步、序列化逻辑。
 *
 * @param {object}    defaults         渠道默认字段（含 tags: []）
 * @param {object}    props           组件 props { accountId, disabled }
 * @param {object}    emit            组件 emit
 * @param {function}  publishFn       (accountId, accountName, commonData, merged, extra) => Promise
 * @param {function}  validateFn       (accountId) => { valid, errors }
 */
export function useChannelForm(defaults, { props, emit }, { publishFn, validateFn } = {}) {
  // ===== 内部状态 =====
  const platformConfig = reactive({ ...defaults })
  const accountOverrides = reactive({})
  const form = reactive({ ...platformConfig })

  let syncing = false

  // ===== 工具函数 =====
  function hasValues(v) {
    if (v === undefined || v === '' || v === false) return false
    if (Array.isArray(v)) return v.length > 0
    return true
  }

  function hasMeaningfulOverride(override) {
    return override && Object.values(override).some(hasValues)
  }

  function getMergedConfig(accountId) {
    const override = accountOverrides[accountId] || {}
    const merged = {}
    // 深拷贝 platformConfig，数组字段必须断开引用，否则 form 和 platformConfig 共享同一数组
    for (const [k, v] of Object.entries(platformConfig)) {
      merged[k] = Array.isArray(v) ? [...v] : v
    }
    for (const [k, v] of Object.entries(override)) {
      if (hasValues(v)) merged[k] = Array.isArray(v) ? [...v] : v
    }
    return merged
  }

  function applyToForm(source) {
    syncing = true
    // 清除 form 中存在但 source 不存在的动态字段（如 mixData, selectedMusicData 等），
    // 这些是账号级专属字段，不存在于 platformConfig 默认值中，切换账号时必须清空
    for (const key of Object.keys(form)) {
      if (!(key in source)) delete form[key]
    }
    Object.assign(form, source)
    syncing = false
  }

  // ===== 账号/平台切换 → 切表单 =====
  watch(() => props.accountId, (newId) => {
    applyToForm(newId ? getMergedConfig(newId) : { ...platformConfig })
  }, { immediate: true })

  // ===== 表单变更 → 同步到 platformConfig / accountOverrides =====
  watch(form, () => {
    if (syncing) return
    if (!props.accountId) {
      for (const key of Object.keys(form)) {
        if (Array.isArray(form[key])) {
          platformConfig[key] = [...form[key]]
        } else {
          platformConfig[key] = form[key]
        }
      }
    } else {
      const diff = {}
      for (const key of Object.keys(form)) {
        const cur = form[key]
        const fallback = platformConfig[key]
        if (typeof cur === 'object' && cur !== null) {
          if (JSON.stringify(cur) !== JSON.stringify(fallback)) {
            diff[key] = Array.isArray(cur) ? [...cur] : { ...cur }
          }
        } else if (cur !== fallback) {
          diff[key] = cur
        }
      }
      if (Object.entries(diff).some(([, v]) => hasValues(v))) {
        const existing = accountOverrides[props.accountId] || {}
        accountOverrides[props.accountId] = { ...existing, ...diff }
      } else {
        delete accountOverrides[props.accountId]
      }
    }
    emit('config-changed')
  }, { deep: true })

  // ===== 模板辅助函数 =====
  function hasAccountOverride(accountId) {
    return hasMeaningfulOverride(accountOverrides[accountId])
  }

  function resetOverride() {
    if (props.accountId) {
      delete accountOverrides[props.accountId]
      applyToForm({ ...platformConfig })
      emit('config-changed')
    }
  }

  // ===== 暴露给父组件的接口 =====
  const publicApi = {
    async publish(accountId, accountName, commonData, extra) {
      if (publishFn) {
        await publishFn(accountId, accountName, commonData, getMergedConfig(accountId), extra)
      }
    },

    getConfigs() {
      return {
        platformConfig: JSON.parse(JSON.stringify(platformConfig)),
        accountOverrides: JSON.parse(JSON.stringify(accountOverrides)),
      }
    },

    restoreConfigs(config, overrides) {
      Object.keys(platformConfig).forEach(k => delete platformConfig[k])
      Object.assign(platformConfig, defaults, config)
      Object.keys(accountOverrides).forEach(k => delete accountOverrides[k])
      if (overrides) Object.assign(accountOverrides, overrides)
      applyToForm(props.accountId ? getMergedConfig(props.accountId) : { ...platformConfig })
    },

    syncTitle(title) {
      if (!props.accountId) { platformConfig.title = title; form.title = title }
      emit('config-changed')
    },

    syncDescription(desc) {
      if (!props.accountId) { platformConfig.description = desc; form.description = desc }
      emit('config-changed')
    },

    syncTags(tags) {
      if (!props.accountId) { platformConfig.tags = [...tags]; form.tags = [...tags] }
      emit('config-changed')
    },

    validate(accountId) {
      if (validateFn) return validateFn(accountId, getMergedConfig(accountId))
      const merged = getMergedConfig(accountId)
      const errors = []
      if (!merged.title || !merged.title.trim()) errors.push('标题不能为空')
      return { valid: errors.length === 0, errors }
    },

    hasAccountOverride,
  }

  return {
    // 响应式状态
    form,
    platformConfig,
    accountOverrides,
    // 模板方法
    hasAccountOverride,
    resetOverride,
    getMergedConfig,
    // 暴露接口
    publicApi,
  }
}
