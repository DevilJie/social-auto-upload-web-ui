<template>
  <div class="rich-editor" :class="{ 'is-disabled': disabled }" data-tour="rich-editor">
    <!-- ===== Toolbar ===== -->
    <div class="re-toolbar" v-if="!disabled">
      <div class="re-group">
        <button class="re-btn" title="撤销" @mousedown.prevent @click="cmd('undo')"><el-icon><RefreshLeft /></el-icon></button>
        <button class="re-btn" title="重做" @mousedown.prevent @click="cmd('redo')"><el-icon><RefreshRight /></el-icon></button>
      </div>
      <div class="re-group">
        <button class="re-btn re-btn-text" title="正文" @mousedown.prevent @click="block('p')">正文</button>
        <button class="re-btn re-btn-text" title="标题2" @mousedown.prevent @click="block('h2')">H2</button>
        <button class="re-btn re-btn-text" title="标题3" @mousedown.prevent @click="block('h3')">H3</button>
      </div>
      <div class="re-group">
        <button class="re-btn re-btn-text" title="加粗" @mousedown.prevent @click="cmd('bold')"><b>B</b></button>
        <button class="re-btn re-btn-text" title="斜体" @mousedown.prevent @click="cmd('italic')"><i>I</i></button>
        <button class="re-btn re-btn-text" title="下划线" @mousedown.prevent @click="cmd('underline')"><u>U</u></button>
        <button class="re-btn re-btn-text" title="删除线" @mousedown.prevent @click="cmd('strikeThrough')"><s>S</s></button>
      </div>
      <div class="re-group">
        <button class="re-btn" title="无序列表" @mousedown.prevent @click="cmd('insertUnorderedList')"><el-icon><List /></el-icon></button>
        <button class="re-btn" title="有序列表" @mousedown.prevent @click="cmd('insertOrderedList')"><el-icon><Tickets /></el-icon></button>
        <button class="re-btn" title="引用" @mousedown.prevent @click="block('blockquote')"><el-icon><ChatLineSquare /></el-icon></button>
        <button class="re-btn" title="分割线" @mousedown.prevent @click="cmd('insertHorizontalRule')"><el-icon><Minus /></el-icon></button>
      </div>
      <div class="re-group">
        <button class="re-btn" title="上传图片" :disabled="uploading" @mousedown.prevent @click="triggerFileSelect"><el-icon><Upload /></el-icon></button>
        <button class="re-btn" title="从素材库选择" :disabled="uploading" @mousedown.prevent @click="$emit('insert-image')"><el-icon><Picture /></el-icon></button>
        <button class="re-btn" title="清除格式" @mousedown.prevent @click="clearFormat"><el-icon><Brush /></el-icon></button>
      </div>
    </div>

    <!-- 隐藏的本地图片选择器(多选,选完由父组件上传后逐张插入) -->
    <input
      ref="fileInputRef"
      type="file"
      accept="image/gif,image/jpeg,image/jpg,image/png,image/webp"
      multiple
      style="display: none"
      @change="onFileChange"
    >

    <!-- ===== Editable Area ===== -->
    <div
      ref="editorRef"
      class="re-content"
      :style="{ minHeight: minHeight + 'px' }"
      contenteditable="true"
      :data-placeholder="placeholder"
      @input="onInput"
      @blur="onInput"
      @paste="onPaste"
      @drop.prevent
    ></div>
  </div>
</template>

<script setup>
/**
 * 轻量富文本编辑器(contenteditable + execCommand,零新依赖)。
 *
 * - v-model 为 HTML 字符串;段落分隔符固定为 <p>(回车输出规范段落)
 * - 工具栏按钮 mousedown.prevent 保持编辑器选区(execCommand 依赖 selection)
 * - 插图通过 emit('insert-image') 由父组件打开素材库/上传,
 *   拿到素材 URL 后调 exposed insertImage(url) 在光标处插入
 * - 输出的 HTML 由后端做 sanitize + 平台转换(公众号图片自动转存)
 */
import { ref, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  RefreshLeft, RefreshRight, List, Tickets, ChatLineSquare,
  Minus, Picture, Brush, Upload,
} from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: '请输入正文...' },
  minHeight: { type: Number, default: 360 },
  disabled: { type: Boolean, default: false },
  /** 本地图片上传中(禁用上传按钮防重复) */
  uploading: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'insert-image', 'upload-image'])

const editorRef = ref(null)
let syncingFromProp = false

onMounted(() => {
  try {
    document.execCommand('defaultParagraphSeparator', false, 'p')
  } catch (e) { /* 忽略,老内核兜底 */ }
  if (editorRef.value && props.modelValue) {
    editorRef.value.innerHTML = props.modelValue
  }
})

watch(() => props.modelValue, (val) => {
  // 外部重置(清空/载入草稿)时同步进编辑器;避免光标跳动只在内容不一致时写
  if (!editorRef.value) return
  if (editorRef.value.innerHTML !== val) {
    syncingFromProp = true
    editorRef.value.innerHTML = val || ''
    syncingFromProp = false
  }
})

function onInput() {
  if (syncingFromProp || props.disabled) return
  emit('update:modelValue', editorRef.value ? editorRef.value.innerHTML : '')
}

function onPaste(e) {
  // 富文本粘贴走浏览器默认(保留格式);纯文本粘贴转成 <p> 段落
  const text = e.clipboardData?.getData('text/plain')
  const html = e.clipboardData?.getData('text/html')
  if (html) return // 浏览器默认处理富文本
  if (text) {
    e.preventDefault()
    const paras = String(text).split(/\r?\n/).filter(l => l.trim())
    const safe = paras.map(p => `<p>${p.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</p>`).join('')
    document.execCommand('insertHTML', false, safe || `<p>${text.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</p>`)
    onInput()
  }
}

function focusEditor() {
  editorRef.value?.focus()
}

/** execCommand 前:focus(工具栏点击时选区可能已丢)→ 恢复最近选区 */
function cmd(command) {
  focusEditor()
  document.execCommand(command, false, null)
  onInput()
}

function block(tag) {
  focusEditor()
  // blockquote 先退出到 p 再进入,避免嵌套
  if (tag === 'blockquote') {
    document.execCommand('formatBlock', false, 'blockquote')
  } else {
    document.execCommand('formatBlock', false, tag)
  }
  onInput()
}

function clearFormat() {
  focusEditor()
  document.execCommand('removeFormat', false, null)
  onInput()
}

/** 在当前光标处插入图片(父组件拿到素材 URL 后调用) */
function insertImage(url, alt = '') {
  if (!url) return
  focusEditor()
  const safeUrl = String(url).replace(/"/g, '&quot;')
  const safeAlt = String(alt || '配图').replace(/"/g, '&quot;')
  document.execCommand('insertHTML', false,
    `<img src="${safeUrl}" alt="${safeAlt}" style="max-width:100%;">`)
  onInput()
}

// ===== 本地图片上传 =====
const fileInputRef = ref(null)

function triggerFileSelect() {
  fileInputRef.value?.click()
}

function onFileChange(e) {
  const files = [...(e.target.files || [])]
  e.target.value = '' // 清空以便可重复选择同一文件
  if (files.length === 0) return
  const bad = files.filter(f => f.size > 10 * 1024 * 1024)
  if (bad.length > 0) {
    ElMessage.warning(`以下图片超过 10MB 已跳过：${bad.map(f => f.name).join('、')}`)
  }
  const ok = files.filter(f => f.size <= 10 * 1024 * 1024)
  if (ok.length > 0) emit('upload-image', ok)
}

function getHTML() {
  return editorRef.value ? editorRef.value.innerHTML : ''
}

/** 纯文本长度(字数统计用) */
function getTextLength() {
  return (editorRef.value?.innerText || '').replace(/\s+/g, '').length
}

function isEmpty() {
  const html = getHTML().replace(/<br\s*\/?>/gi, '').replace(/&nbsp;/gi, '').trim()
  return !html || html === '<p></p>'
}

function clear() {
  if (editorRef.value) editorRef.value.innerHTML = ''
  emit('update:modelValue', '')
}

defineExpose({ insertImage, getHTML, getTextLength, isEmpty, clear, focusEditor })

defineOptions({ inheritAttrs: false })
</script>

<style scoped lang="scss">
.rich-editor {
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
  transition: border-color 0.2s;

  &:focus-within {
    border-color: #07C160;
  }

  &.is-disabled {
    opacity: 0.6;
    pointer-events: none;
  }
}

.re-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 2px;
  padding: 6px 8px;
  border-bottom: 1px solid #ebeef5;
  background: #f9fafc;
}

.re-group {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 0 6px;

  & + .re-group {
    border-left: 1px solid #e4e7ed;
  }
}

.re-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  height: 28px;
  padding: 0 6px;
  border: none;
  border-radius: 4px;
  background: transparent;
  cursor: pointer;
  color: #606266;
  font-size: 13px;

  &:hover {
    background: #eef1f6;
    color: #07C160;
  }
}

.re-btn-text {
  font-weight: 600;
}

.re-content {
  padding: 14px 16px;
  font-size: 15px;
  line-height: 1.8;
  color: #303133;
  outline: none;
  word-break: break-word;
  overflow-y: auto;
  max-height: 560px;

  :deep(img) {
    max-width: 100%;
    border-radius: 4px;
  }

  :deep(blockquote) {
    margin: 8px 0;
    padding: 6px 12px;
    border-left: 3px solid #d0d6e0;
    background: #f7f8fa;
    color: #606266;
  }

  :deep(h2), :deep(h3) {
    margin: 12px 0 8px;
  }

  :deep(p) {
    margin: 6px 0;
  }

  &:empty::before,
  &:has(> :only-child:is(br))::before {
    content: attr(data-placeholder);
    color: #c0c4cc;
    pointer-events: none;
  }
}
</style>
