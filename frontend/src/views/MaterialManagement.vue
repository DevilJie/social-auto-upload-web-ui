<template>
  <div class="material-management">
    <!-- Page Header -->
    <div class="page-header">
      <h1>素材管理</h1>
      <p class="page-subtitle">上传和管理视频素材</p>
    </div>

    <!-- Toolbar -->
    <div class="toolbar-card">
      <el-input
        v-model="searchKeyword"
        placeholder="输入文件名搜索"
        prefix-icon="Search"
        clearable
        @clear="handleSearch"
        @input="handleSearch"
        class="search-input"
      />
      <div class="action-buttons">
        <el-button type="primary" class="btn-upload" @click="handleUploadMaterial">
          <el-icon><Upload /></el-icon>
          <span>上传素材</span>
        </el-button>
        <el-button class="btn-refresh" @click="fetchMaterials" :loading="false">
          <el-icon :class="{ 'is-loading': isRefreshing }"><Refresh /></el-icon>
          <span v-if="isRefreshing">刷新中</span>
        </el-button>
      </div>
    </div>

    <!-- Material Table -->
    <div class="table-card">
      <div v-if="filteredMaterials.length > 0" class="material-list">
        <el-table :data="filteredMaterials" style="width: 100%" class="material-table">
          <el-table-column label="缩略图" width="80" align="center">
            <template #default="scope">
              <div class="thumbnail-cell" v-if="isVideoFile(scope.row.filename)">
                <span class="play-icon">&#9654;</span>
              </div>
              <div class="thumbnail-cell thumbnail-image" v-else-if="isImageFile(scope.row.filename)">
                <img :src="getPreviewUrl(scope.row)" alt="" />
              </div>
              <div class="thumbnail-cell thumbnail-other" v-else>
                <el-icon><Document /></el-icon>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="filename" label="文件名" min-width="240" show-overflow-tooltip />
          <el-table-column prop="filesize" label="文件大小" width="120" align="center">
            <template #default="scope">
              {{ scope.row.filesize }} MB
            </template>
          </el-table-column>
          <el-table-column prop="upload_time" label="上传时间" width="180" align="center" />
          <el-table-column label="操作" width="160" align="center">
            <template #default="scope">
              <div class="action-cell">
                <button class="action-btn action-preview" @click="handlePreview(scope.row)" title="预览">
                  <el-icon><View /></el-icon>
                </button>
                <button class="action-btn action-delete" @click="handleDelete(scope.row)" title="删除">
                  <el-icon><Delete /></el-icon>
                </button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div v-else class="empty-data">
        <el-empty description="暂无素材数据" />
      </div>
    </div>

    <!-- Upload Dialog -->
    <el-dialog
      v-model="uploadDialogVisible"
      title="上传素材"
      width="40%"
      @close="handleUploadDialogClose"
      class="upload-dialog"
    >
      <div class="upload-form">
        <el-form label-width="80px">
          <el-form-item label="文件名称:">
            <el-input
              v-model="customFilename"
              placeholder="选填 (仅单个文件时生效)"
              :disabled="customFilenameDisabled"
              clearable
            />
          </el-form-item>
          <el-form-item label="选择文件">
            <el-upload
              class="upload-zone"
              drag
              multiple
              :auto-upload="false"
              :on-change="handleFileChange"
              :on-remove="handleFileRemove"
              :file-list="fileList"
            >
              <el-icon class="upload-zone-icon"><Upload /></el-icon>
              <div class="upload-zone-text">
                将文件拖到此处，或<em>点击上传</em>
              </div>
              <template #tip>
                <div class="upload-zone-tip">
                  支持视频、图片等格式文件，可一次选择多个文件
                </div>
              </template>
            </el-upload>
          </el-form-item>
          <el-form-item label="上传列表" v-if="fileList.length > 0">
            <div class="upload-file-list">
              <div v-for="file in fileList" :key="file.uid" class="upload-file-item">
                <div class="file-item-header">
                  <span class="file-name">{{ file.name }}</span>
                </div>
                <el-progress
                  :percentage="uploadProgress[file.uid]?.percentage || 0"
                  :text-inside="true"
                  :stroke-width="18"
                  class="upload-progress"
                >
                  <span>{{ uploadProgress[file.uid]?.speed || '' }}</span>
                </el-progress>
              </div>
            </div>
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="uploadDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitUpload" :loading="isUploading">
            {{ isUploading ? '上传中' : '确认上传' }}
          </el-button>
        </div>
      </template>
    </el-dialog>

    <!-- Preview Dialog -->
    <el-dialog
      v-model="previewDialogVisible"
      title="素材预览"
      width="50%"
      :top="'10vh'"
      class="preview-dialog"
    >
      <div class="preview-container" v-if="currentMaterial">
        <div class="preview-frame">
          <div v-if="isVideoFile(currentMaterial.filename)" class="video-preview">
            <video controls>
              <source :src="getPreviewUrl(currentMaterial)" type="video/mp4">
              您的浏览器不支持视频播放
            </video>
          </div>
          <div v-else-if="isImageFile(currentMaterial.filename)" class="image-preview">
            <img :src="getPreviewUrl(currentMaterial)" />
          </div>
          <div v-else class="file-info">
            <div class="file-info-icon">
              <el-icon :size="48"><Document /></el-icon>
            </div>
            <p>文件名: {{ currentMaterial.filename }}</p>
            <p>文件大小: {{ currentMaterial.filesize }} MB</p>
            <p>上传时间: {{ currentMaterial.upload_time }}</p>
            <el-button type="primary" @click="downloadFile(currentMaterial)">下载文件</el-button>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { Refresh, Upload, View, Delete, Document } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { materialApi } from '@/api/material'
import { useAppStore } from '@/stores/app'

// 获取应用状态管理
const appStore = useAppStore()

// 搜索和状态控制
const searchKeyword = ref('')
const isRefreshing = ref(false)
const isUploading = ref(false)

// 对话框控制
const uploadDialogVisible = ref(false)
const previewDialogVisible = ref(false)
const currentMaterial = ref(null)

// 文件上传
const fileList = ref([])
const customFilename = ref('')
const customFilenameDisabled = computed(() => fileList.value.length > 1)
const uploadProgress = ref({}); // { [uid]: { percentage: 0, speed: '' } }


watch(fileList, (newList) => {
  if (newList.length <= 1) {
    // If you want to clear the custom name when going back to single file, uncomment below
    // customFilename.value = ''
  }
});


// 获取素材列表
const fetchMaterials = async () => {
  isRefreshing.value = true
  try {
    const response = await materialApi.getAllMaterials()

    if (response.code === 200) {
      appStore.setMaterials(response.data)
      ElMessage.success('刷新成功')
    } else {
      ElMessage.error('获取素材列表失败')
    }
  } catch (error) {
    console.error('获取素材列表出错:', error)
    ElMessage.error('获取素材列表失败')
  } finally {
    isRefreshing.value = false
  }
}

// 过滤素材
const filteredMaterials = computed(() => {
  if (!searchKeyword.value) return appStore.materials

  const keyword = searchKeyword.value.toLowerCase()
  return appStore.materials.filter(material =>
    material.filename.toLowerCase().includes(keyword)
  )
})

// 搜索处理
const handleSearch = () => {
  // 搜索逻辑已通过计算属性实现
}

// 上传素材
const handleUploadMaterial = () => {
  // 清空变量
  fileList.value = []
  customFilename.value = ''
  uploadProgress.value = {};
  uploadDialogVisible.value = true
}

// 关闭上传对话框时清空变量
const handleUploadDialogClose = () => {
  fileList.value = []
  customFilename.value = ''
  uploadProgress.value = {};
}

// 文件选择变更
const handleFileChange = (file, uploadFileList) => {
  fileList.value = uploadFileList;
  const newProgress = {};
  for (const f of uploadFileList) {
    newProgress[f.uid] = { percentage: 0, speed: '' };
  }
  uploadProgress.value = newProgress;
}

const handleFileRemove = (file, uploadFileList) => {
  fileList.value = uploadFileList;
  const newProgress = { ...uploadProgress.value };
  delete newProgress[file.uid];
  uploadProgress.value = newProgress;
}

// 提交上传
const submitUpload = async () => {
  if (fileList.value.length === 0) {
    ElMessage.warning('请选择要上传的文件')
    return
  }

  isUploading.value = true

  for (const file of fileList.value) {
    try {
      // 确保文件对象存在
      if (!file || !file.raw) {
        ElMessage.warning(`文件 ${file.name} 对象无效，已跳过`)
        continue
      }

      const formData = new FormData()
      formData.append('file', file.raw)

      // 只有当只有一个文件时，自定义文件名才生效
      if (fileList.value.length === 1 && customFilename.value.trim()) {
        formData.append('filename', customFilename.value.trim())
      }

      let lastLoaded = 0;
      let lastTime = Date.now();

      const response = await materialApi.uploadMaterial(formData, (progressEvent) => {
        const progressData = uploadProgress.value[file.uid];
        if (!progressData) return;

        const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total)
        progressData.percentage = progress;

        const currentTime = Date.now();
        const timeDiff = (currentTime - lastTime) / 1000; // in seconds
        const loadedDiff = progressEvent.loaded - lastLoaded;

        if (timeDiff > 0.5) { // Update speed every 0.5 seconds
          const speed = loadedDiff / timeDiff; // bytes per second
          if (speed > 1024 * 1024) {
            progressData.speed = (speed / (1024 * 1024)).toFixed(2) + ' MB/s';
          } else {
            progressData.speed = (speed / 1024).toFixed(2) + ' KB/s';
          }
          lastLoaded = progressEvent.loaded;
          lastTime = currentTime;
        }
      })

      if (response.code === 200) {
        ElMessage.success(`文件 ${file.name} 上传成功`)
        const progressData = uploadProgress.value[file.uid];
        if(progressData) progressData.speed = '完成';
      } else {
        ElMessage.error(`文件 ${file.name} 上传失败: ${response.msg || '未知错误'}`)
      }
    } catch (error) {
      console.error(`上传文件 ${file.name} 出错:`, error)
      ElMessage.error(`文件 ${file.name} 上传失败: ${error.message || '未知错误'}`)
    }
  }

  isUploading.value = false
  // Keep dialog open to show results
  // uploadDialogVisible.value = false
  await fetchMaterials()
}

// 预览素材
const handlePreview = async (material) => {
  currentMaterial.value = null
  previewDialogVisible.value = true
  ElMessage.info('加载中...')
  try {
    // 等待一小段时间以确保对话框已打开
    await new Promise(resolve => setTimeout(resolve, 100))
    currentMaterial.value = material
  } catch (error) {
    console.error('预览素材出错:', error)
    ElMessage.error('预览加载失败')
    previewDialogVisible.value = false
  }
}

// 删除素材
const handleDelete = (material) => {
  ElMessageBox.confirm(
    `确定要删除素材 ${material.filename} 吗？`,
    '警告',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    }
  )
    .then(async () => {
      try {
        const response = await materialApi.deleteMaterial(material.id)

        if (response.code === 200) {
          appStore.removeMaterial(material.id)
          ElMessage.success('删除成功')
        } else {
          ElMessage.error(response.msg || '删除失败')
        }
      } catch (error) {
        console.error('删除素材出错:', error)
        ElMessage.error('删除失败')
      }
    })
    .catch(() => {
      // 取消删除
    })
}

// 获取预览URL
const getPreviewUrl = (material) => {
  // 如果有完整的 url 字段，直接使用
  if (material.url) {
    if (material.url.startsWith('/')) {
      const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5409'
      return `${baseUrl}${material.url}`
    }
    return material.url
  }
  // 兼容旧格式
  const filePath = material.file_path || ''
  const filename = filePath.split('/').pop()
  return materialApi.getMaterialPreviewUrl(filename)
}

// 下载文件
const downloadFile = (material) => {
  const url = materialApi.downloadMaterial(material.file_path)
  window.open(url, '_blank')
}

// 判断文件类型
const isVideoFile = (filename) => {
  const videoExtensions = ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv']
  return videoExtensions.some(ext => filename.toLowerCase().endsWith(ext))
}

const isImageFile = (filename) => {
  const imageExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
  return imageExtensions.some(ext => filename.toLowerCase().endsWith(ext))
}

// 组件挂载时获取素材列表
onMounted(() => {
  // 只有store中没有数据时才获取
  if (appStore.materials.length === 0) {
    fetchMaterials()
  }
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

// ========== Page Layout ==========
.material-management {
  padding: 0 28px;

  .page-header {
    margin-bottom: $spacing-lg;

    h1 {
      font-size: 26px;
      font-weight: 700;
      color: $text-primary;
      margin: 0 0 4px 0;
      letter-spacing: -0.5px;
    }

    .page-subtitle {
      font-size: 14px;
      color: $text-muted;
      margin: 0;
    }
  }
}

// ========== Toolbar Card ==========
.toolbar-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: $spacing-md $spacing-lg;
  margin-bottom: $spacing-lg;
  background: $bg-elevated;
  border: 1px solid $border;
  border-radius: $radius-card;

  .search-input {
    width: 280px;
  }

  .action-buttons {
    display: flex;
    gap: 10px;

    .is-loading {
      animation: rotate 1s linear infinite;
    }
  }

  .btn-upload {
    background: $gradient-brand;
    border: none;
    display: flex;
    align-items: center;
    gap: 6px;
    font-weight: 500;

    &:hover {
      opacity: 0.9;
    }
  }

  .btn-refresh {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid $border;
    color: $text-secondary;

    &:hover {
      border-color: $border-active;
      color: $text-primary;
    }
  }
}

// ========== Table Card ==========
.table-card {
  background: $bg-elevated;
  border: 1px solid $border;
  border-radius: $radius-card;
  padding: $spacing-lg;

  .material-list {
    // table wrapper
  }

  .empty-data {
    padding: 60px 0;
  }
}

// ========== Thumbnail Cell ==========
.thumbnail-cell {
  width: 40px;
  height: 40px;
  border-radius: $radius-sm;
  background: $gradient-brand-subtle;
  display: flex;
  align-items: center;
  justify-content: center;
  color: $brand-start;
  font-size: 16px;
  overflow: hidden;
  margin: 0 auto;

  .play-icon {
    font-size: 14px;
    line-height: 1;
  }

  &.thumbnail-image {
    img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      border-radius: $radius-sm;
    }
  }

  &.thumbnail-other {
    .el-icon {
      font-size: 18px;
      color: $text-muted;
    }
  }
}

// ========== Action Buttons ==========
.action-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: $radius-sm;
  border: 1px solid $border;
  background: transparent;
  cursor: pointer;
  transition: all $transition-base;

  .el-icon {
    font-size: 14px;
  }

  &.action-preview {
    color: $brand-end;

    &:hover {
      background: rgba($brand-end, 0.1);
      border-color: rgba($brand-end, 0.3);
    }
  }

  &.action-delete {
    color: $danger-color;

    &:hover {
      background: rgba($danger-color, 0.1);
      border-color: rgba($danger-color, 0.3);
    }
  }
}

// ========== Table Styles ==========
.material-table {
  :deep(thead) th {
    background: rgba(255, 255, 255, 0.02) !important;
    color: $text-secondary !important;
    font-weight: 500;
    border-bottom: 1px solid $border !important;
  }

  :deep(tbody) td {
    border-bottom: 1px solid $border !important;
  }

  :deep(.el-table__row:hover > td) {
    background: rgba($brand-start, 0.04) !important;
  }

  :deep(.el-table__empty-block) {
    background: transparent;
  }

  // Transparent table background
  :deep(.el-table__inner-wrapper),
  :deep(.el-table__body-wrapper),
  :deep(tr) {
    background: transparent !important;
  }

  :deep(.el-table) {
    --el-table-bg-color: transparent;
    --el-table-tr-bg-color: transparent;
    --el-table-header-bg-color: transparent;
    --el-table-row-hover-bg-color: transparent;
  }
}

// ========== Upload Dialog ==========
.upload-dialog {
  :deep(.el-dialog) {
    background: $bg-elevated;
    border: 1px solid $border;
    border-radius: $radius-dialog;
  }

  :deep(.el-dialog__header) {
    border-bottom: 1px solid $border;
    padding-bottom: 16px;
  }

  :deep(.el-dialog__title) {
    color: $text-primary;
    font-weight: 600;
  }

  :deep(.el-dialog__body) {
    color: $text-secondary;
  }

  :deep(.el-form-item__label) {
    color: $text-secondary;
  }
}

.upload-form {
  .upload-zone {
    width: 100%;

    :deep(.el-upload) {
      width: 100%;
    }

    :deep(.el-upload-dragger) {
      background: rgba(255, 255, 255, 0.02);
      border: 2px dashed rgba($brand-start, 0.3);
      border-radius: $radius-card;
      padding: 40px 20px;
      transition: all $transition-base;

      &:hover {
        border-color: rgba($brand-start, 0.6);
        background: rgba($brand-start, 0.03);
      }
    }

    .upload-zone-icon {
      font-size: 48px;
      color: $brand-start;
      margin-bottom: 12px;
    }

    .upload-zone-text {
      color: $text-secondary;
      font-size: 14px;

      em {
        color: $brand-start;
        font-style: normal;
      }
    }

    .upload-zone-tip {
      color: $text-muted;
      font-size: 12px;
      margin-top: 8px;
      text-align: center;
    }
  }
}

// ========== Upload File List ==========
.upload-file-list {
  width: 100%;
}

.upload-file-item {
  border: 1px solid $border;
  border-radius: $radius-base;
  padding: 12px 16px;
  margin-bottom: 10px;
  background: $bg-elevated;
  transition: border-color $transition-base;

  &:hover {
    border-color: $border-active;
  }

  .file-item-header {
    margin-bottom: 8px;
  }

  .file-name {
    font-size: 14px;
    color: $text-primary;
    font-weight: 500;
  }

  .upload-progress {
    :deep(.el-progress-bar__outer) {
      background: rgba(255, 255, 255, 0.06);
      border-radius: 9px;
    }

    :deep(.el-progress-bar__inner) {
      background: $gradient-brand;
      border-radius: 9px;
    }
  }
}

:deep(.el-progress__text) {
  color: $text-secondary !important;
  font-size: 12px !important;
}

:deep(.el-progress--line) {
  margin-bottom: 10px;
}

// ========== Dialog Footer ==========
.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

// ========== Preview Dialog ==========
.preview-dialog {
  :deep(.el-dialog) {
    background: $bg-elevated;
    border: 1px solid $border;
    border-radius: $radius-dialog;
  }

  :deep(.el-dialog__header) {
    border-bottom: 1px solid $border;
    padding-bottom: 16px;
  }

  :deep(.el-dialog__title) {
    color: $text-primary;
    font-weight: 600;
  }

  :deep(.el-dialog__body) {
    background: rgba(0, 0, 0, 0.2);
    border-radius: 0 0 $radius-dialog $radius-dialog;
  }
}

.preview-container {
  display: flex;
  justify-content: center;
  align-items: center;
  flex-direction: column;
  padding: 20px;

  .preview-frame {
    border: 1px solid rgba($brand-start, 0.2);
    border-radius: $radius-card;
    padding: 16px;
    background: rgba(0, 0, 0, 0.3);
    width: 100%;
    display: flex;
    justify-content: center;
    align-items: center;
    position: relative;

    &::before {
      content: '';
      position: absolute;
      inset: -1px;
      border-radius: $radius-card;
      padding: 1px;
      background: linear-gradient(135deg, rgba($brand-start, 0.3), rgba($brand-end, 0.1), transparent);
      -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
      -webkit-mask-composite: xor;
      mask-composite: exclude;
      pointer-events: none;
    }
  }

  .video-preview,
  .image-preview {
    display: flex;
    justify-content: center;
    align-items: center;

    video, img {
      max-width: 100%;
      max-height: 60vh;
      border-radius: $radius-sm;
    }
  }

  .file-info {
    text-align: center;
    padding: 20px;
    color: $text-secondary;

    .file-info-icon {
      margin-bottom: 16px;
      color: $brand-start;
    }

    p {
      margin-bottom: 8px;
      font-size: 14px;
    }

    .el-button {
      margin-top: 16px;
    }
  }
}
</style>
