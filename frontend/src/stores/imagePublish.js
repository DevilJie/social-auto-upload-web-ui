import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { imagePublishApi } from '@/api/imagePublish'
import { ElMessage } from 'element-plus'

export const useImagePublishStore = defineStore('imagePublish', () => {
  // ========== 状态 ==========

  // 图片列表，每项: { url, name, file, progress }
  const images = ref([])

  // 已选账号 ID 列表
  const selectedAccounts = ref([])

  // 每个账号的独立配置 { [accountId]: { title, description } }
  const accountConfigs = ref({})

  // 当前草稿 ID（null 表示新建）
  const currentDraftId = ref(null)

  // 是否正在发布
  const publishing = ref(false)

  // 批量标题/描述（用于同步到所有账号）
  const batchTitle = ref('')
  const batchDescription = ref('')

  // ========== 计算属性 ==========

  const imageCount = computed(() => images.value.length)

  const canUpload = computed(() => images.value.length < 35)

  const canPublish = computed(() => {
    return images.value.length > 0 && selectedAccounts.value.length > 0
  })

  // ========== 方法 ==========

  /**
   * 上传单张图片
   * @param {File} file - 图片文件
   * @returns {Promise<object>} 上传结果，包含 url 等信息
   */
  async function upload(file) {
    const entry = {
      url: '',
      name: file.name,
      file,
      progress: 0
    }
    const index = images.value.length
    images.value.push(entry)

    try {
      const res = await imagePublishApi.uploadImage(file, (percent) => {
        if (images.value[index]) {
          images.value[index].progress = percent
        }
      })
      // 后端返回上传后的图片信息
      const url = res?.data?.url || res?.url || ''
      if (images.value[index]) {
        images.value[index].url = url
        images.value[index].progress = 100
      }
      return res
    } catch (error) {
      // 上传失败，移除占位项
      images.value.splice(index, 1)
      ElMessage.error(`图片 ${file.name} 上传失败`)
      throw error
    }
  }

  /**
   * 移除指定位置的图片
   * @param {number} index - 图片索引
   */
  function removeImage(index) {
    if (index >= 0 && index < images.value.length) {
      images.value.splice(index, 1)
    }
  }

  /**
   * 重排图片顺序
   * @param {number} fromIndex - 原位置
   * @param {number} toIndex - 目标位置
   */
  function reorder(fromIndex, toIndex) {
    if (
      fromIndex < 0 || fromIndex >= images.value.length ||
      toIndex < 0 || toIndex >= images.value.length ||
      fromIndex === toIndex
    ) {
      return
    }
    const [moved] = images.value.splice(fromIndex, 1)
    images.value.splice(toIndex, 0, moved)
  }

  /**
   * 替换指定位置的图片
   * @param {number} index - 要替换的图片索引
   * @param {File} file - 新图片文件
   * @returns {Promise<object>} 上传结果
   */
  async function replaceImage(index, file) {
    if (index < 0 || index >= images.value.length) {
      throw new Error('无效的图片索引')
    }

    const oldEntry = images.value[index]
    images.value[index] = {
      url: '',
      name: file.name,
      file,
      progress: 0
    }

    try {
      const res = await imagePublishApi.uploadImage(file, (percent) => {
        if (images.value[index]) {
          images.value[index].progress = percent
        }
      })
      const url = res?.data?.url || res?.url || ''
      if (images.value[index]) {
        images.value[index].url = url
        images.value[index].progress = 100
      }
      return res
    } catch (error) {
      // 上传失败，恢复原图
      images.value[index] = oldEntry
      ElMessage.error(`图片 ${file.name} 上传失败`)
      throw error
    }
  }

  /**
   * 更新指定账号的配置
   * @param {string|number} accountId - 账号 ID
   * @param {object} config - 配置对象 { title, description }
   */
  function updateAccountConfig(accountId, config) {
    accountConfigs.value = {
      ...accountConfigs.value,
      [accountId]: {
        ...accountConfigs.value[accountId],
        ...config
      }
    }
  }

  /**
   * 将批量标题/描述同步到所有已选账号
   */
  function syncBatchToAll() {
    const newConfigs = {}
    for (const accountId of selectedAccounts.value) {
      newConfigs[accountId] = {
        ...accountConfigs.value[accountId],
        title: batchTitle.value,
        description: batchDescription.value
      }
    }
    accountConfigs.value = newConfigs
  }

  /**
   * 保存草稿
   * @returns {Promise<object>} 保存结果
   */
  async function save() {
    const payload = {
      images: images.value.map(img => ({ url: img.url, name: img.name })),
      selectedAccounts: selectedAccounts.value,
      accountConfigs: accountConfigs.value,
      batchTitle: batchTitle.value,
      batchDescription: batchDescription.value,
      draftId: currentDraftId.value
    }

    try {
      const res = await imagePublishApi.saveDraft(payload)
      if (res?.data?.id) {
        currentDraftId.value = res.data.id
      }
      ElMessage.success('草稿已保存')
      return res
    } catch (error) {
      ElMessage.error('保存草稿失败')
      throw error
    }
  }

  /**
   * 发布图文
   * @param {string|null} scheduledAt - 定时发布时间，null 表示立即发布
   * @returns {Promise<object>} 发布结果
   */
  async function publish(scheduledAt = null) {
    if (!canPublish.value) {
      ElMessage.warning('请至少上传一张图片并选择一个账号')
      return
    }

    publishing.value = true

    try {
      const payload = {
        images: images.value.map(img => ({ url: img.url, name: img.name })),
        selectedAccounts: selectedAccounts.value,
        accountConfigs: accountConfigs.value,
        scheduledAt
      }

      const res = await imagePublishApi.publishImage(payload)
      ElMessage.success(scheduledAt ? '已设置定时发布' : '发布任务已提交')
      return res
    } catch (error) {
      ElMessage.error('发布失败')
      throw error
    } finally {
      publishing.value = false
    }
  }

  /**
   * 重置所有状态
   */
  function reset() {
    images.value = []
    selectedAccounts.value = []
    accountConfigs.value = {}
    currentDraftId.value = null
    publishing.value = false
    batchTitle.value = ''
    batchDescription.value = ''
  }

  // ========== 导出 ==========

  return {
    // 状态
    images,
    selectedAccounts,
    accountConfigs,
    currentDraftId,
    publishing,
    batchTitle,
    batchDescription,
    // 计算属性
    imageCount,
    canUpload,
    canPublish,
    // 方法
    upload,
    removeImage,
    reorder,
    replaceImage,
    updateAccountConfig,
    syncBatchToAll,
    save,
    publish,
    reset
  }
})
