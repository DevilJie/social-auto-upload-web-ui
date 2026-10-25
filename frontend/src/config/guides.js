/**
 * 新手引导配置中心（全站唯一写入点：Lead 维护，各页面/弹窗只消费）
 *
 * 页面通过 GuideTour 组件消费本文件的步骤数组：
 *   import { xxxGuideSteps, GUIDE_KEYS, isGuideDone, markGuideDone } from '@/config/guides'
 *
 * 步骤字段：
 *   target        CSS 选择器（统一用 data-tour="xxx" 锚点），省略则气泡居中显示
 *   title         步骤标题
 *   content       气泡正文（面向第一次使用的用户）
 *   icon          标题前 emoji（可选）
 *   placement     气泡首选方位 bottom/top/left/right（可选，默认 bottom，空间不足自动换向）
 *   skipIfMissing 目标元素不存在/隐藏时自动跳过该步（条件渲染区块必加）
 *
 * 触发策略约定：
 *   页面引导      onMounted 首次自动播放（延时 600ms）
 *   独立工具弹窗  @opened 首次自动播放（延时 150ms）+ 标题栏「新手引导」重看按钮
 *   流程中弹窗    不自动播放，仅标题栏「新手引导」按钮按需查看（发布确认/进度/素材库/封面编辑器/草稿批量预览）
 */

// 每个引导的"已完成"持久化 key（localStorage，置 '1' 表示不再自动弹出）
export const GUIDE_KEYS = {
  account: 'guide_done_account_v1',          // 账号管理页
  batchTag: 'guide_done_batch_tag_v1',       // 批量设置标签弹窗
  login: 'guide_done_login_v1',              // 添加/重登账号弹窗（LoginDialog）
  import: 'guide_done_import_v1',            // 导入用户弹窗
  material: 'guide_done_material_v1',        // 素材管理页
  materialUpload: 'guide_done_material_upload_v1',   // 上传素材弹窗
  materialSelect: 'guide_done_material_select_v1',   // 素材库选择弹窗（按需）
  publish: 'guide_done_publish_v1',          // 视频发布页
  videoConfirm: 'guide_done_video_confirm_v1',       // 发布确认弹窗（按需）
  videoProgress: 'guide_done_video_progress_v1',     // 发布进度弹窗（按需）
  accountSelect: 'guide_done_account_select_v1',     // 账号设置弹窗（账号选择）
  coverEditor: 'guide_done_cover_editor_v1',         // 封面编辑器弹窗（按需）
  batchSet: 'guide_done_batch_set_v1',               // 批量设置弹窗
  oneClickFill: 'guide_done_one_click_fill_v1',      // 一键填写弹窗
  image: 'guide_done_image_v1',              // 图集发布页
  article: 'guide_done_article_v1',          // 文章发布页
  draft: 'guide_done_draft_v1',              // 草稿箱页
  draftBatch: 'guide_done_draft_batch_v1',   // 草稿批量发布预览弹窗（按需）
  settings: 'guide_done_settings_v1',        // 系统设置页
  blacklist: 'guide_done_blacklist_v1'       // 渠道黑名单弹窗
}

export function isGuideDone (key) {
  try { return localStorage.getItem(key) === '1' } catch { return true }
}

export function markGuideDone (key) {
  try { localStorage.setItem(key, '1') } catch { /* ignore */ }
}

// resetGuide：调试/演示用，在控制台执行后刷新即可重看
export function resetGuide (key) {
  try { localStorage.removeItem(key) } catch { /* ignore */ }
}

// ========== 1. 账号管理页 ==========
export const accountGuideSteps = [
  {
    title: '欢迎使用「账号管理」',
    icon: '🎉',
    content: '发布内容前，需要先绑定你的平台账号，这一页就是账号的大本营。花一分钟认识各个功能，后面发布会上手很快～'
  },
  {
    target: '[data-tour="add-account"]',
    title: '添加账号',
    icon: '➕',
    placement: 'bottom',
    content: '点这里绑定平台账号：选择平台后会自动弹出浏览器，扫码登录即可；昵称、头像和运营数据都会自动同步进来。'
  },
  {
    target: '[data-tour="import-user"]',
    title: '导入用户',
    icon: '📥',
    placement: 'bottom',
    content: '已经有平台账号的 Cookie？粘贴过来无需重新扫码，一分钟把老账号批量搬进来。'
  },
  {
    target: '[data-tour="platform-tabs"]',
    title: '按平台筛选',
    icon: '🗂️',
    placement: 'bottom',
    content: '账号多了不用翻：点平台标签只看某一个平台的账号，标签上的数字就是已绑定的账号数量。'
  },
  {
    target: '[data-tour="search-bar"]',
    title: '搜索与批量维护',
    icon: '🔎',
    placement: 'bottom',
    content: '支持按昵称搜索账号。「刷新」拉取最新列表；「批量检查」一键体检所有账号，失效的会自动引导重登修复；「批量设置标签」方便分组管理。'
  },
  {
    target: '[data-tour="tag-filter"]',
    title: '标签筛选',
    icon: '🏷️',
    placement: 'bottom',
    skipIfMissing: true,
    content: '给账号打好标签后，点彩色标签就能快速筛出同一类账号，再点一下取消筛选。'
  },
  {
    target: '[data-tour="account-card-sample"]',
    title: '认识账号卡片',
    icon: '👤',
    placement: 'right',
    content: '每张卡片展示头像、昵称、状态灯（绿=正常）和运营数据。底部按钮：「检查」验证登录、「同步」更新资料、「创作中心」直达平台后台、「删除」移除账号。'
  },
  {
    title: '一切就绪！',
    icon: '🚀',
    content: '先点「添加账号」绑定第一个平台吧！绑定后即可前往「视频发布 / 图集发布 / 文章发布」开始创作。本引导可随时点右上角「新手引导」重新查看。'
  }
]

// ========== 2. 批量设置标签弹窗（账号管理页内） ==========
export const batchTagGuideSteps = [
  {
    title: '批量打标签，一次搞定',
    icon: '🏷️',
    content: '要给一堆账号打上同一组标签，用这个弹窗最省事：左边选账号，右边选标签，最后点「追加」即可。'
  },
  {
    target: '[data-tour="batch-accounts"]',
    title: '第一步：选账号',
    icon: '👥',
    placement: 'right',
    content: '点卡片勾选要打标签的账号（置灰的是异常账号，不可选）；右上角「一键全选」可以快速选中全部正常账号。'
  },
  {
    target: '[data-tour="batch-tags"]',
    title: '第二步：选标签',
    icon: '✨',
    placement: 'right',
    content: '在搜索框输入名称回车（或点「新建」）即可创建标签；点彩色标签勾选或取消；标签上的 × 可删除该标签（会从所有账号移除）。'
  },
  {
    target: '[data-tour="batch-apply"]',
    title: '第三步：追加',
    icon: '✅',
    placement: 'top',
    content: '点这里把勾选的标签追加给所选账号。放心，只是追加，不会清除账号已有的标签。'
  }
]

// ========== 3. 添加/重登账号弹窗（LoginDialog） ==========
export const loginGuideSteps = [
  {
    title: '添加账号，全程自动',
    icon: '🔐',
    content: '绑定账号只需两步：点一张平台卡片，工具会自动弹出浏览器打开登录页，你扫码就好。'
  },
  {
    target: '[data-tour="ld-grid"]',
    title: '第一步：选平台',
    icon: '🧭',
    placement: 'bottom',
    content: '点一张平台卡片即开始登录。可以连续点不同平台，一次绑多个账号；「取消」可中断登录中的卡片。'
  },
  {
    target: '[data-tour="ld-grid"]',
    title: '第二步：看状态',
    icon: '👀',
    placement: 'bottom',
    content: '卡片状态实时变化：转圈=登录中，绿勾=登录成功（已自动同步昵称头像），红字=失败可「重试」。完成后点「关闭」。'
  }
]

// ========== 4. 导入用户弹窗（账号管理页内） ==========
export const importGuideSteps = [
  {
    title: '导入用户，免扫码搬家',
    icon: '📥',
    content: '已经在浏览器里登录过平台？把 Cookie 复制过来就能直接导入，不用重新扫码。'
  },
  {
    target: '[data-tour="ig-platform"]',
    title: '第一步：选平台',
    icon: '🧭',
    placement: 'right',
    content: '左侧点选要导入的平台，可搜索定位；只展示支持 Cookie 导入的平台。'
  },
  {
    target: '[data-tour="ig-cookie"]',
    title: '第二步：粘贴 Cookie',
    icon: '📋',
    placement: 'left',
    content: '浏览器按 F12 → Network → 点任意请求 → Request Headers → 把 Cookie 整段复制粘贴到这里。'
  },
  {
    target: '[data-tour="ig-submit"]',
    title: '第三步：开始导入',
    icon: '🚀',
    placement: 'top',
    content: '点「开始导入」，4 步进度全自动；成功后弹出账号预览卡，列表里立刻能看到。'
  }
]

// ========== 5. 素材管理页 ==========
export const materialGuideSteps = [
  {
    title: '欢迎使用「素材管理」',
    icon: '🎁',
    content: '这里是视频和图片的统一仓库，所有发布页取材都来自这里。花一分钟认识各个功能～'
  },
  {
    target: '[data-tour="material-upload"]',
    title: '一键上传素材',
    icon: '📤',
    placement: 'bottom',
    content: '点这里上传本地图片或视频：支持拖拽、一次最多 20 个，超大文件会自动分片断点续传。'
  },
  {
    target: '[data-tour="material-search"]',
    title: '按名字搜索',
    icon: '🔎',
    placement: 'bottom',
    content: '素材多了也不怕，输入文件名立刻筛选，点 × 一键清空。'
  },
  {
    target: '[data-tour="material-type-filter"]',
    title: '筛选类型',
    icon: '🎞️',
    placement: 'bottom',
    content: '只看图片或只看视频？点分段按钮切换，列表立刻更新。'
  },
  {
    target: '[data-tour="material-grid"]',
    title: '素材卡片墙',
    icon: '🖼️',
    placement: 'top',
    content: '每张卡片就是一个素材：缩略图、大小、上传时间一目了然（视频自动生成缩略图）。空库时，素材会显示在这里。'
  },
  {
    target: '[data-tour="material-batch"]',
    title: '批量整理',
    icon: '🧹',
    placement: 'bottom',
    content: '点「批量删除」进入勾选模式：全选本页一键清理，删除前还有二次确认，放心操作。'
  },
  {
    target: '[data-tour="material-pagination"]',
    title: '翻页与更多',
    icon: '📄',
    placement: 'bottom',
    skipIfMissing: true,
    content: '底部可切换每页数量和跳页。素材就绪后，去「视频发布」选用它们吧！'
  }
]

// ========== 6. 上传素材弹窗（MaterialUploader） ==========
export const materialUploadGuideSteps = [
  {
    title: '上传素材',
    icon: '📤',
    content: '把本地图片/视频拖进来或点击选择，一次最多 20 个，单文件不限大小。'
  },
  {
    target: '[data-tour="uploader-dragger"]',
    title: '选择文件',
    icon: '🗂️',
    placement: 'bottom',
    content: '把文件拖进虚线框，或点击选择；支持批量，选完先进列表再统一上传。'
  },
  {
    target: '[data-tour="uploader-list"]',
    title: '看进度',
    icon: '📊',
    placement: 'top',
    skipIfMissing: true,
    content: '每行一个文件：进度条 + 实时速度；失败可重试，点 × 移除，「继续添加」能追加文件。'
  },
  {
    target: '[data-tour="uploader-start"]',
    title: '开始上传',
    icon: '🚀',
    placement: 'top',
    content: '点「开始上传」批量上传；超过 100MB 的大文件自动分片断点续传，不怕网络抖动。'
  }
]

// ========== 7. 素材库选择弹窗（MaterialSelectDialog，按需查看） ==========
export const materialSelectGuideSteps = [
  {
    title: '素材库',
    icon: '🗃️',
    content: '发布用的视频/图片都从这里选，支持搜索和类型筛选。'
  },
  {
    target: '[data-tour="msd-search"]',
    title: '搜索',
    icon: '🔎',
    placement: 'bottom',
    content: '按文件名快速筛选。'
  },
  {
    target: '[data-tour="msd-type-filter"]',
    title: '类型筛选',
    icon: '🎞️',
    placement: 'bottom',
    content: '只看图片或只看视频。'
  },
  {
    target: '[data-tour="msd-card"]',
    title: '点卡片选择',
    icon: '🖼️',
    placement: 'top',
    skipIfMissing: true,
    content: '多选时可跨页勾选；视频卡片能直接播放预览。'
  },
  {
    target: '[data-tour="msd-confirm"]',
    title: '确定',
    icon: '✅',
    placement: 'top',
    content: '点「确定（N 个）」把所选素材带回发布页。'
  }
]

// ========== 8. 视频发布页 ==========
export const publishGuideSteps = [
  {
    title: '欢迎使用「视频发布」',
    icon: '🎬',
    content: '这里能把一条视频同时发到多个平台的多个账号。口诀：选账号 → 加视频 → 填内容 → 批量发布。跟我走一遍～'
  },
  {
    target: '[data-tour="sidebar-add-account"]',
    title: '第一步：选账号',
    icon: '👥',
    placement: 'right',
    content: '发布前先告诉工具「发到哪」：点左下角「+ 账号设置」，勾选要用的平台账号。'
  },
  {
    target: '[data-tour="queue-add"]',
    title: '第二步：加视频',
    icon: '🎞️',
    placement: 'bottom',
    content: '点「+ 添加视频」从素材库多选或本地上传。多个视频排成队列单独设置；新视频自动继承当前配置和封面。'
  },
  {
    target: '.publish-center .phone-panel',
    title: '实时预览',
    icon: '📱',
    placement: 'left',
    content: '右侧手机就是发布效果预览，也能在这里本地上传或更换素材库视频。'
  },
  {
    target: '[data-tour="cover-grid"]',
    title: '检查封面',
    icon: '🖼️',
    placement: 'bottom',
    content: '上传后已自动生成 4 种比例封面；点封面可进编辑器，拖时间轴换帧重裁。'
  },
  {
    target: '[data-tour="platform-settings"]',
    title: '第三步：填内容',
    icon: '✏️',
    placement: 'bottom',
    content: '在这里填标题、描述、话题标签；描述里打 #话题 会自动变成标签。点左侧具体账号可为它单独配置（⭐）。'
  },
  {
    target: '.publish-center .settings-grid',
    title: '平台专属设置',
    icon: '⚙️',
    placement: 'bottom',
    skipIfMissing: true,
    content: '每个平台有自己的必选项（如创作声明），红字提示要看一眼，漏选会发布失败。'
  },
  {
    target: '[data-tour="field-scheduleTime"]',
    title: '定时发布',
    icon: '⏰',
    placement: 'bottom',
    skipIfMissing: true,
    content: '想错峰发布？在「定时发布」选未来时间（14 天内），到点自动发；不选就立即发。'
  },
  {
    target: '[data-tour="header-tools"]',
    title: '效率三件套',
    icon: '🧰',
    placement: 'bottom',
    content: '「保存草稿」随时存进度（还会自动保存）；「一键填写」套用历史配置；「批量设置」把标签声明铺到多渠道。'
  },
  {
    target: '.publish-center .header-btn--primary',
    title: '第四步：批量发布',
    icon: '🚀',
    placement: 'bottom',
    content: '点「批量发布」：自动体检 → Cookie 预检 → 确认弹窗（可设发布间隔防风控），之后逐账号自动发布，进度实时可见。'
  },
  {
    title: '一切就绪！',
    icon: '✅',
    content: '记住口诀：选账号 → 加视频 → 填内容 → 批量发布。发布后去「发布历史」回看结果，失败的可修复重发～'
  }
]

// ========== 9. 发布确认弹窗（VideoBatchConfirmDialog，按需查看） ==========
export const videoConfirmGuideSteps = [
  {
    title: '发布确认',
    icon: '📋',
    content: '出发前最后检查站：勾选要发的视频、设置发布间隔。'
  },
  {
    target: '[data-tour="vbc-stats"]',
    title: '统计与筛选',
    icon: '📊',
    placement: 'bottom',
    content: '按「全部 / 可发布 / 待处理」筛选；有问题的视频会内联列出原因和解决办法。'
  },
  {
    target: '[data-tour="vbc-video-card"]',
    title: '视频清单',
    icon: '🎞️',
    placement: 'top',
    skipIfMissing: true,
    content: '每行一个视频，勾选是否发布；点开能看具体问题。'
  },
  {
    target: '[data-tour="vbc-interval"]',
    title: '发布间隔',
    icon: '⏱️',
    placement: 'top',
    content: '默认间隔 30 分钟防平台风控，仅本次批量生效；0 表示连续执行。'
  },
  {
    target: '[data-tour="vbc-submit"]',
    title: '开跑',
    icon: '🚀',
    placement: 'top',
    content: '点「发布 N 个视频」正式开始！'
  }
]

// ========== 10. 发布进度弹窗（BatchTaskProgressDialog，按需查看） ==========
export const videoProgressGuideSteps = [
  {
    title: '发布进度',
    icon: '📡',
    content: '这里实时显示每个账号的发布状态；关掉弹窗不影响后台发布。'
  },
  {
    target: '[data-tour="btp-progress"]',
    title: '总进度',
    icon: '📈',
    placement: 'bottom',
    content: '总进度条 + 当前发布账号；有定时时会显示距下一条视频的倒计时。'
  },
  {
    target: '[data-tour="btp-video-card"]',
    title: '逐账号明细',
    icon: '🎞️',
    placement: 'top',
    skipIfMissing: true,
    content: '点开每个视频卡片：逐账号状态、失败原因、成功后的作品链接。'
  },
  {
    target: '[data-tour="btp-footer"]',
    title: '后台与取消',
    icon: '🎛️',
    placement: 'top',
    content: '进行中可「后台运行」或「取消所有剩余」；全部完成后可去发布历史。'
  }
]

// ========== 11. 账号设置弹窗（AccountSelectDialog） ==========
export const accountSelectGuideSteps = [
  {
    title: '选择发布账号',
    icon: '👥',
    content: '这一步决定内容发到哪里：按渠道筛、按标签筛，勾选账号后确认。'
  },
  {
    target: '[data-tour="asd-platform-list"]',
    title: '按渠道筛选',
    icon: '🧭',
    placement: 'right',
    content: '先勾平台缩小范围，已选数量实时显示。'
  },
  {
    target: '[data-tour="asd-account-grid"]',
    title: '选账号',
    icon: '✅',
    placement: 'bottom',
    content: '点卡片勾选账号（置灰的是异常账号）；「一键全选」作用于当前筛选结果。'
  },
  {
    target: '[data-tour="asd-tag-list"]',
    title: '按标签筛选',
    icon: '🏷️',
    placement: 'left',
    content: '账号多时，按标签快速锁定目标账号。'
  },
  {
    target: '[data-tour="asd-confirm"]',
    title: '确认设置',
    icon: '🚀',
    placement: 'top',
    content: '点「确认设置」完成选择，发布页左侧会按平台分组展示。'
  }
]

// ========== 12. 封面编辑器弹窗（CoverEditorDialog，按需查看） ==========
export const coverEditorGuideSteps = [
  {
    title: '封面编辑器',
    icon: '🎨',
    content: '裁出各平台完美封面：缩放、拖动、换帧、传图都支持。'
  },
  {
    target: '[data-tour="ce-canvas"]',
    title: '裁剪画布',
    icon: '✂️',
    placement: 'right',
    content: '滚轮缩放、拖动移动画面，比例框固定，调到满意为止。'
  },
  {
    target: '[data-tour="ce-ratio-tabs"]',
    title: '封面尺寸',
    icon: '📐',
    placement: 'bottom',
    content: '横版 4:3 / 16:9、竖版 3:4 / 9:16 逐个设置，每个比例独立保存。'
  },
  {
    target: '[data-tour="ce-timeline"]',
    title: '时间轴选帧',
    icon: '🎞️',
    placement: 'bottom',
    skipIfMissing: true,
    content: '视频封面可拖时间轴换帧，点缩略图即选中；也能上传图片或从素材库选。'
  },
  {
    target: '[data-tour="ce-upload"]',
    title: '用图片当封面',
    icon: '🖼️',
    placement: 'bottom',
    skipIfMissing: true,
    content: '不用视频帧？直接上传图片或从素材库挑一张。'
  }
]

// ========== 13. 批量设置弹窗（BatchSetDialog） ==========
export const batchSetGuideSteps = [
  {
    title: '批量设置',
    icon: '🧰',
    content: '一次把标题、标签、声明等铺到多个渠道，多平台发布的提效神器。'
  },
  {
    target: '[data-tour="bs-fields"]',
    title: '第一步：填字段',
    icon: '📝',
    placement: 'right',
    content: '在左侧填要统一的字段；选「仅覆盖已填项」时，留空的字段不会动原有配置。'
  },
  {
    target: '[data-tour="bs-platforms"]',
    title: '第二步：选渠道',
    icon: '🎯',
    placement: 'bottom',
    content: '勾选要应用的渠道卡片，注意覆盖模式：仅填项 / 全量覆盖当前视频 / 所有视频全量替换。'
  },
  {
    target: '[data-tour="bs-apply"]',
    title: '第三步：应用',
    icon: '✅',
    placement: 'top',
    content: '点「全量应用」把所填内容铺到选中的渠道，完成批量设置。'
  }
]

// ========== 14. 一键填写弹窗（OneClickFillDialog） ==========
export const oneClickFillGuideSteps = [
  {
    title: '一键填写',
    icon: '⚡',
    content: '从发布历史套用成功过的配置：自动勾选账号、回填标题标签封面。'
  },
  {
    target: '[data-tour="ocf-cards"]',
    title: '选一条历史',
    icon: '🗂️',
    placement: 'bottom',
    skipIfMissing: true,
    content: '每张卡片是一次历史发布，点选即套用；还没有历史时，先手动发一次再来。'
  }
]

// ========== 15. 图集发布页 ==========
export const imageGuideSteps = [
  {
    title: '欢迎使用「图集发布」',
    icon: '🖼️',
    content: '一组图片同时发到小红书、抖音、快手等 6 个平台。流程：选账号 → 传图 → 填内容 → 一键发布～'
  },
  {
    target: '[data-tour="sidebar-add-account"]',
    title: '第一步：选账号',
    icon: '👥',
    placement: 'right',
    content: '点左下角「+ 账号设置」勾选要发布的账号；点分组展开，再点某个账号可单独为它配置。'
  },
  {
    target: '[data-tour="media-section"]',
    title: '第二步：传图片',
    icon: '📸',
    placement: 'bottom',
    content: '点虚线卡上传或直接拖图进来，最多 35 张；拖左上角手柄可排序，也能从素材库选。'
  },
  {
    target: '[data-tour="cover-section"]',
    title: '设置封面',
    icon: '🎨',
    placement: 'bottom',
    content: '封面可本地上传或从素材库挑一张；不设也行，发布时默认用图片。'
  },
  {
    target: '[data-tour="platform-panel"]',
    title: '第三步：填平台内容',
    icon: '🧩',
    placement: 'bottom',
    content: '当前平台的专属设置：标题必填、描述里 #话题 自动变标签；选中具体账号后改的只对它生效。'
  },
  {
    target: '.image-publish .phone-mockup',
    title: '实时预览',
    icon: '📱',
    placement: 'left',
    content: '右侧手机实时预览翻页效果；点「放大预览」能缩放旋转看大图。'
  },
  {
    target: '[data-tour="header-tools"]',
    title: '效率三件套',
    icon: '🧰',
    placement: 'bottom',
    content: '「保存草稿」防丢失；「一键填写」套历史；「批量设置」多平台统一文案。'
  },
  {
    target: '.image-publish .header-btn--primary',
    title: '第四步：一键发布',
    icon: '🚀',
    placement: 'bottom',
    content: '万事俱备点这里！逐账号自动发布，进度和结果实时可见，可随时取消。'
  },
  {
    title: '一切就绪！',
    icon: '✅',
    content: '小贴士：上限 35 张图；小红书 / 快手 / 公众号支持定时发布。去发第一组图吧～'
  }
]

// ========== 16. 文章发布页 ==========
export const articleGuideSteps = [
  {
    title: '欢迎使用「文章发布」',
    icon: '✍️',
    content: '一篇文章同时发到公众号、知乎、CSDN 等 7 个平台。标题正文全局共用，右侧手机实时预览～'
  },
  {
    target: '[data-tour="sidebar-add-account"]',
    title: '第一步：选账号',
    icon: '👥',
    placement: 'right',
    content: '先点左下角「+ 账号设置」勾选要发布的平台账号。'
  },
  {
    target: '[data-tour="title-input"]',
    title: '第二步：写标题',
    icon: '📝',
    placement: 'bottom',
    content: '起个吸引人的标题（必填，最多 64 字），所有平台共用这一个。'
  },
  {
    target: '[data-tour="rich-editor"]',
    title: '第三步：写正文',
    icon: '📄',
    placement: 'bottom',
    content: '像写文档一样排版：加粗、标题、列表都能用；支持本地上传或从素材库插图。'
  },
  {
    target: '[data-tour="cover-grid"]',
    title: '设置封面',
    icon: '🎨',
    placement: 'bottom',
    content: '横竖版封面各两种比例，可裁剪；不设也没关系，自动抓正文第一张图。'
  },
  {
    target: '[data-tour="platform-settings"]',
    title: '平台专属设置',
    icon: '🧩',
    placement: 'bottom',
    content: '点左侧平台后，这里变成该平台专属设置：摘要、原创声明、话题、定时等，按平台要求填好。'
  },
  {
    target: '.article-publish .publish-mode-radio',
    title: '选发布方式',
    icon: '📮',
    placement: 'bottom',
    content: '默认「存草稿箱」更安全，后台确认再群发；「直接发表」立即推送，公众号需要扫码验证。'
  },
  {
    target: '[data-tour="btn-save-draft"]',
    title: '保存草稿',
    icon: '💾',
    placement: 'bottom',
    content: '写一半点这里保存；开启自动保存后更不怕丢，下次从草稿箱接着写。'
  },
  {
    target: '.article-publish .header-btn--primary',
    title: '第四步：一键发表',
    icon: '🚀',
    placement: 'bottom',
    content: '标题、正文、账号就绪后点这里！逐账号发布，进度和结果弹窗实时看。'
  },
  {
    title: '一切就绪！',
    icon: '✅',
    content: '支持平台：公众号 / 知乎 / CSDN / 微博 / 百家号 / 大鱼号 / 头条。去写第一篇吧～'
  }
]

// ========== 17. 草稿箱页 ==========
export const draftGuideSteps = [
  {
    title: '欢迎使用「草稿箱」',
    icon: '📥',
    content: '你在各发布页保存的草稿都会躺在这里，随时回来继续编辑或一键发布。'
  },
  {
    target: '[data-tour="draft-tabs"]',
    title: '三类草稿',
    icon: '🗂️',
    placement: 'bottom',
    content: '视频、图集、文章分开放；标签上有数量，点一下切换。'
  },
  {
    target: '[data-tour="draft-card"]',
    title: '认识草稿卡片',
    icon: '🃏',
    placement: 'bottom',
    skipIfMissing: true,
    content: '每张卡片是一条草稿：封面、标题、要发的平台和保存时间一目了然。'
  },
  {
    target: '[data-tour="card-edit"]',
    title: '编辑与删除',
    icon: '✏️',
    placement: 'bottom',
    skipIfMissing: true,
    content: '「编辑」回发布页恢复全部内容继续做；「删除」有二次确认，放心点。'
  },
  {
    target: '[data-tour="draft-toolbar"]',
    title: '批量操作',
    icon: '☑️',
    placement: 'bottom',
    content: '草稿多？点「多选」勾选一批，批量发布或批量删除，一次搞定几十条。'
  },
  {
    title: '会用草稿箱了！',
    icon: '✅',
    content: '小贴士：发布页开启「自动保存草稿」后更安心；空列表时可直接点「去发布」开始创作～'
  }
]

// ========== 18. 草稿批量发布预览弹窗（BatchDraftPublishDialog，按需查看） ==========
export const draftBatchGuideSteps = [
  {
    title: '批量发布预览',
    icon: '📦',
    content: '确认哪些草稿可以发：通过项已默认勾选，失败项悬停可看原因。'
  },
  {
    target: '[data-tour="bdp-table"]',
    title: '核对清单',
    icon: '🧾',
    placement: 'bottom',
    content: '逐条列出标题、目标平台和校验状态；失败行不可勾选。'
  },
  {
    target: '[data-tour="bdp-confirm"]',
    title: '确认发布',
    icon: '🚀',
    placement: 'top',
    content: '点「确认发布 N 项」开跑；视频草稿会入队异步执行，其他类型同步处理。'
  }
]

// ========== 19. 系统设置页 ==========
export const settingsGuideSteps = [
  {
    title: '欢迎使用「系统设置」',
    icon: '⚙️',
    content: '代理、发布、存储等偏好都在这里。记住一条：改完任何设置，都要点底部「保存设置」才生效！'
  },
  {
    target: '[data-tour="card-proxy"]',
    title: '海外平台代理',
    icon: '🌐',
    placement: 'right',
    content: '只有发 YouTube / TikTok 才需要填代理地址；只玩国内平台，留空跳过即可。'
  },
  {
    target: '[data-tour="card-publish"]',
    title: '发布偏好',
    icon: '🤖',
    placement: 'bottom',
    content: '自动填充标题、自动保存草稿默认已开，很省心；「批量任务间隔」可防平台风控。'
  },
  {
    target: '[data-tour="check-mode"]',
    title: '账号检查时机',
    icon: '🩺',
    placement: 'bottom',
    content: '默认发布前检测 Cookie 有效性；改「启动时检测」则打开软件就后台体检。'
  },
  {
    target: '[data-tour="blacklist-add"]',
    title: '渠道黑名单',
    icon: '🚫',
    placement: 'bottom',
    content: '不想用的渠道拉进黑名单，发布和登录时不再出现，界面更清爽。'
  },
  {
    target: '[data-tour="storage-type"]',
    title: '文件存储',
    icon: '💾',
    placement: 'right',
    content: '默认本地存储开箱即用；用 MinIO / OSS 才切 S3，填完记得点「测试连接」。'
  },
  {
    target: '.save-btn',
    title: '别忘了保存',
    icon: '✅',
    placement: 'top',
    content: '任何修改都要点这里保存，看到「设置已保存」提示才算生效！'
  }
]

// ========== 20. 渠道黑名单弹窗（PlatformBlacklistDialog） ==========
export const blacklistGuideSteps = [
  {
    title: '渠道黑名单',
    icon: '🚫',
    content: '不想看到的平台可以被屏蔽：发布、登录、添加账号时都不再出现。'
  },
  {
    target: '[data-tour="pb-list"]',
    title: '选渠道',
    icon: '🧲',
    placement: 'bottom',
    content: '点平台卡片多选（已添加的置灰不可选）；确认后立即生效，随时可移除。'
  },
  {
    target: '[data-tour="pb-confirm"]',
    title: '确认添加',
    icon: '✅',
    placement: 'top',
    content: '点「确认添加(N)」完成拉黑；回到设置页 hover 渠道 chip 可点 × 移除。'
  }
]
