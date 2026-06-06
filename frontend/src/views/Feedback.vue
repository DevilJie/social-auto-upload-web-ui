<template>
  <div class="feedback-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">一键反馈</h1>
        <p class="page-subtitle">查看、提交、投票反馈，与作者一起改进产品</p>
      </div>
      <el-button type="primary" :icon="Plus" @click="openSubmitDialog">提交反馈</el-button>
    </div>

    <div class="filter-bar">
      <span class="filter-label">状态</span>
      <el-select v-model="statusFilter" placeholder="选择状态" class="status-select" @change="handleStatusChange">
        <el-option label="全部" value="all" />
        <el-option label="待确认" :value="1" />
        <el-option label="处理中" :value="2" />
        <el-option label="已完成" :value="3" />
        <el-option label="已拒绝" :value="4" />
      </el-select>
      <el-button :icon="Refresh" @click="loadList" :loading="loading">刷新</el-button>
    </div>

    <div v-loading="loading" class="card-grid">
      <el-empty v-if="!loading && sortedList.length === 0" description="暂无反馈" />
      <div
        v-for="fb in sortedList"
        :key="fb.id"
        class="feedback-card"
        @click="openDrawer(fb)"
      >
        <div class="card-top">
          <el-tag :type="statusTagType(fb.status)" size="small">
            {{ statusLabel(fb.status) }}
          </el-tag>
          <button
            :class="['vote-btn', { voted: votedIds.has(fb.id) }]"
            :disabled="votedIds.has(fb.id)"
            @click.stop="handleVote(fb)"
          >
            <el-icon><CaretTop /></el-icon>
            <span>{{ votedIds.has(fb.id) ? '已支持' : '我也支持' }}</span>
            <span class="vote-num">{{ fb.vote_count || 0 }}</span>
          </button>
        </div>
        <div class="card-content">{{ truncate(fb.content, 80) }}</div>
        <div class="card-meta">
          <span class="meta-email">{{ maskEmail(fb.email) }}</span>
          <span class="meta-time">{{ formatTime(fb.created_at) }}</span>
        </div>
        <div v-if="fb.attachments && fb.attachments.length" class="card-attachments">
          <el-icon><Paperclip /></el-icon>
          {{ fb.attachments.length }} 个附件
        </div>
      </div>
    </div>

    <div v-if="total > 0" class="pagination-wrapper">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50]"
        :total="total"
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="loadList"
        @size-change="onSizeChange"
      />
    </div>

    <!-- 详情抽屉 -->
    <el-drawer
      v-model="drawerVisible"
      :title="`反馈 #${currentFb?.id || ''}`"
      size="500px"
      direction="rtl"
    >
      <div v-if="currentFb" class="drawer-content">
        <el-tag :type="statusTagType(currentFb.status)" size="small">
          {{ statusLabel(currentFb.status) }}
        </el-tag>
        <div v-if="currentFb.assignee" class="drawer-assignee">
          处理人：{{ currentFb.assignee }}
        </div>
        <div class="drawer-time">{{ formatTime(currentFb.created_at) }}</div>
        <div class="drawer-content-text">{{ currentFb.content }}</div>
        <div v-if="currentFb.attachments && currentFb.attachments.length" class="drawer-attachments">
          <h4>附件</h4>
          <el-image
            v-for="att in currentFb.attachments"
            :key="att.id"
            :src="att.file_url"
            :preview-src-list="currentFb.attachments.map(a => a.file_url)"
            :initial-index="0"
            fit="cover"
            class="attachment-img"
          />
        </div>
        <div class="drawer-vote">
          <button
            :class="['vote-btn', { voted: votedIds.has(currentFb.id) }]"
            :disabled="votedIds.has(currentFb.id)"
            @click="handleVote(currentFb)"
          >
            <el-icon><CaretTop /></el-icon>
            <span>{{ votedIds.has(currentFb.id) ? '已支持' : '我也支持' }}</span>
            <span class="vote-num">{{ currentFb.vote_count || 0 }}</span>
          </button>
        </div>
      </div>
    </el-drawer>

    <!-- 提交反馈对话框 -->
    <el-dialog v-model="submitVisible" title="提交反馈" width="500px">
      <el-form :model="submitForm" label-width="80px">
        <el-form-item label="邮箱" required>
          <el-input v-model="submitForm.email" placeholder="your@email.com" />
        </el-form-item>
        <el-form-item label="内容" required>
          <el-input v-model="submitForm.content" type="textarea" :rows="5" placeholder="详细描述您遇到的问题或建议" />
        </el-form-item>
        <el-form-item label="附件">
          <el-upload
            :auto-upload="false"
            :limit="1"
            :on-change="onFileChange"
            :on-exceed="onExceed"
            :on-remove="onFileRemove"
            accept=".png,.jpg,.jpeg,.gif,.bmp,.webp,.pdf,.doc,.docx,.xlsx,.xls,.pptx,.ppt"
            list-type="picture"
          >
            <el-button :icon="Upload">选择文件 (≤5MB)</el-button>
            <template #tip>
              <div class="el-upload__tip">支持图片、PDF、Office 文档，单文件不超过 5MB</div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="submitVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, CaretTop, Paperclip, Upload, Refresh } from '@element-plus/icons-vue'
import { listFeedback, submitFeedback as apiSubmit, voteFeedback as apiVote } from '@/api/feedback'
import { http } from '@/utils/request'

const router = useRouter()

const statusFilter = ref('all')
const loading = ref(false)
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)

const drawerVisible = ref(false)
const currentFb = ref(null)

const submitVisible = ref(false)
const submitting = ref(false)
const submitForm = ref({ email: '', content: '' })
const submitFile = ref(null)

const VOTED_LS_KEY = 'feedback_voted_ids'
const votedIds = ref(new Set(JSON.parse(localStorage.getItem(VOTED_LS_KEY) || '[]')))

function persistVotedIds() {
  localStorage.setItem(VOTED_LS_KEY, JSON.stringify([...votedIds.value]))
}

const sortedList = computed(() => {
  return [...list.value].sort((a, b) => {
    if ((b.vote_count || 0) !== (a.vote_count || 0)) {
      return (b.vote_count || 0) - (a.vote_count || 0)
    }
    return new Date(b.created_at) - new Date(a.created_at)
  })
})

function statusLabel(s) {
  return { 1: '待确认', 2: '处理中', 3: '已完成', 4: '已拒绝' }[s] || '未知'
}
function statusTagType(s) {
  return { 1: 'warning', 2: 'primary', 3: 'success', 4: 'info' }[s] || 'info'
}
function truncate(text, n) {
  if (!text) return ''
  return text.length > n ? text.slice(0, n) + '…' : text
}
function maskEmail(email) {
  if (!email) return ''
  const [user, domain] = email.split('@')
  if (!domain) return email
  return user.slice(0, 2) + '***@' + domain
}
function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { hour12: false })
}

async function loadList() {
  loading.value = true
  try {
    const params = { page: page.value, pageSize: pageSize.value }
    if (statusFilter.value === 'all') {
      params.includeAll = true
    } else {
      params.status = statusFilter.value
    }
    const res = await listFeedback(params)
    list.value = res.data?.list || []
    total.value = res.data?.total || 0
  } catch (e) {
    list.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function handleStatusChange() {
  page.value = 1
  loadList()
}
function onSizeChange(s) {
  pageSize.value = s
  page.value = 1
  loadList()
}

function openDrawer(fb) {
  currentFb.value = fb
  drawerVisible.value = true
}

async function handleVote(fb) {
  // 后端从 settings 表读 email；前端不再传。前端只用来判断是否需要引导去设置。
  const localEmail = localStorage.getItem('global_user_email') || ''
  if (!localEmail) {
    await promptForEmail()
    return
  }
  if (votedIds.value.has(fb.id)) return
  try {
    await apiVote({ id: fb.id })
    votedIds.value.add(fb.id)
    persistVotedIds()
    fb.vote_count = (fb.vote_count || 0) + 1
    ElMessage.success('+1 成功')
  } catch (e) {
    // 400 您已经为该反馈 +1 过了
    if (e.message && e.message.includes('+1 过了')) {
      votedIds.value.add(fb.id)
      persistVotedIds()
      ElMessage.warning('您已为此反馈投过票')
    }
    // 其他错误已被 request.js 拦截器处理
  }
}

async function promptForEmail() {
  try {
    await ElMessageBox.confirm(
      '请前往设置页填写反馈邮箱',
      '需要邮箱',
      { confirmButtonText: '去设置', cancelButtonText: '取消', type: 'warning' }
    )
    router.push('/settings')
  } catch (_) {
    // 用户取消，不操作
  }
}

function openSubmitDialog() {
  submitForm.value = {
    email: localStorage.getItem('global_user_email') || '',
    content: ''
  }
  submitFile.value = null
  submitVisible.value = true
}
function onFileChange(file) {
  if (file.size > 5 * 1024 * 1024) {
    ElMessage.error('文件超过 5MB')
    submitFile.value = null
    return false
  }
  submitFile.value = file.raw
}
function onExceed() {
  ElMessage.warning('只能上传 1 个文件')
}
function onFileRemove() {
  submitFile.value = null
}

async function handleSubmit() {
  const email = submitForm.value.email.trim()
  const content = submitForm.value.content.trim()
  if (!email || !content) {
    ElMessage.error('邮箱和内容必填')
    return
  }
  // 用户在对话框里可能改了 email，把它同步回 settings + localStorage
  const globalEmail = localStorage.getItem('global_user_email') || ''
  if (email !== globalEmail) {
    localStorage.setItem('global_user_email', email)
    // 同步回后端 settings（让下次 list/vote 也能用上）
    try {
      await http.put('/api/v2/settings', { feedbackEmail: email })
    } catch (_) { /* 后端同步失败不影响本次提交 */ }
  }

  submitting.value = true
  try {
    const fd = new FormData()
    // 后端优先用 settings 里的 email，这里也传作为覆盖（保持兼容性）
    fd.append('email', email)
    fd.append('content', content)
    if (submitFile.value) {
      fd.append('files', submitFile.value)
    }
    await apiSubmit(fd)
    ElMessage.success('提交成功')
    submitVisible.value = false
    await loadList()
  } catch (e) {
    // 错误已由 request.js 拦截器处理
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  const email = localStorage.getItem('global_user_email')
  if (!email) {
    await promptForEmail()
  }
  await loadList()
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.feedback-page {
  padding: 24px;
  width: 100%;
  max-width: none;
  margin: 0;
  box-sizing: border-box;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 24px;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  color: $text-primary;
  margin-bottom: 4px;
}

.page-subtitle {
  font-size: 13px;
  color: $text-muted;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;

  .filter-label {
    color: $text-secondary;
    font-size: 14px;
  }

  .status-select {
    width: 160px;
  }
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 20px;
  min-height: 200px;
}

.feedback-card {
  padding: 16px;
  border-radius: 12px;
  background: $bg-elevated;
  border: 1px solid $border;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    border-color: $brand-start;
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
  }
}

.card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.vote-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid $border;
  background: rgba(255, 255, 255, 0.04);
  color: $text-primary;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;

  &:hover:not(:disabled) {
    border-color: $brand-start;
    color: $brand-start;
    background: rgba($brand-start, 0.1);
    transform: translateY(-1px);
  }

  &:disabled,
  &.voted {
    border-color: $brand-start;
    background: linear-gradient(135deg, $brand-start, $brand-end);
    color: #fff;
    cursor: default;
  }

  .vote-num {
    padding: 0 6px;
    background: rgba(0, 0, 0, 0.15);
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
    min-width: 18px;
    text-align: center;
  }

  &:not(.voted) .vote-num {
    background: rgba(255, 255, 255, 0.08);
  }
}

.card-content {
  font-size: 14px;
  line-height: 1.6;
  color: $text-primary;
  margin-bottom: 12px;
  word-break: break-word;
}

.card-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: $text-muted;
  margin-bottom: 8px;
}

.card-attachments {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: $text-muted;
}

.pagination-wrapper {
  display: flex;
  justify-content: center;
  padding: 24px 0;
}

.drawer-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.drawer-assignee {
  font-size: 13px;
  color: $text-secondary;
}

.drawer-time {
  font-size: 12px;
  color: $text-muted;
}

.drawer-content-text {
  padding: 12px;
  background: $bg-surface;
  border-radius: 8px;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 14px;
  line-height: 1.6;
}

.drawer-attachments {
  h4 {
    font-size: 14px;
    margin-bottom: 8px;
    color: $text-primary;
  }
  .attachment-img {
    width: 100px;
    height: 100px;
    border-radius: 6px;
    margin-right: 8px;
    margin-bottom: 8px;
  }
}

.drawer-vote {
  padding-top: 12px;
  border-top: 1px solid $border;

  .vote-btn {
    padding: 8px 16px;
    font-size: 13px;
  }
}
</style>
