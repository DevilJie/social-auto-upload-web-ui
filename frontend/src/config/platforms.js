/**
 * 统一平台配置 — 所有平台相关数据的唯一真实来源
 *
 * 使用方式：
 *   import { PLATFORMS, platformList, platformIdToName } from '@/config/platforms'
 */

// Logo 文件使用 Vite 的静态资源导入
import logoDouyin from '@/assets/logos/douyin.png'
import logoKuaishou from '@/assets/logos/kuaishou.png'
import logoXiaohongshu from '@/assets/logos/xiaohongshu.png'
import logoChannels from '@/assets/logos/shipinhao.png'
import logoBilibili from '@/assets/logos/bilibili.png'
import logoBaijiahao from '@/assets/logos/baijiahao.png'
import logoYoutube from '@/assets/logos/youtube.png'

export const PLATFORMS = {
  XIAOHONGSHU: {
    id: 1,
    key: 'xiaohongshu',
    name: '小红书',
    shortName: 'XHS',
    letter: 'X',
    logo: logoXiaohongshu,
    color: '#8b5cf6',
    bgColor: 'rgba(139, 92, 246, 0.15)',
    cssClass: 'xiaohongshu',
    creatorUrl: 'https://creator.xiaohongshu.com/',
    settingsFields: [
      { key: 'collection', label: '合集', type: 'select', placeholder: '请选择合集' },
      { key: 'groupChat', label: '群聊', type: 'select', placeholder: '请选择群聊' },
      { key: 'location', label: '位置', type: 'select', placeholder: '选择位置' },
      { key: 'aiContent', label: '内容类型声明', type: 'select', placeholder: '添加内容类型声明', options: [
        { label: '虚构演绎，仅供娱乐', value: '虚构演绎，仅供娱乐' },
        { label: '笔记含AI合成内容', value: '笔记含AI合成内容' },
        { label: '内容包含营销广告', value: '内容包含营销广告' },
        { label: '内容来源声明', value: '内容来源声明' },
      ] },
      { key: 'isOriginal', label: '原创声明', type: 'radio', options: [{ label: '原创', value: true }, { label: '非原创', value: false }] },
      { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间' },
      { key: 'videoFormat', label: '视频格式', type: 'radio', options: [{ label: '横版', value: 'landscape' }, { label: '竖版', value: 'portrait' }] },
    ],
    defaultSettings: { title: '', description: '', collection: '', groupChat: '', location: '', aiContent: '', isOriginal: false, scheduleTime: '', videoFormat: '' },
  },
  CHANNELS: {
    id: 2,
    key: 'channels',
    name: '视频号',
    shortName: 'SPH',
    letter: 'V',
    logo: logoChannels,
    color: '#3b82f6',
    bgColor: 'rgba(59, 130, 246, 0.15)',
    cssClass: 'channels',
    creatorUrl: 'https://channels.weixin.qq.com/',
    settingsFields: [
      { key: 'isDraft', label: '草稿模式', type: 'switch', description: '仅保存草稿（用手机发布）' },
      { key: 'location', label: '位置', type: 'select', placeholder: '选择位置' },
      { key: 'aiContent', label: 'AI生成内容', type: 'switch' },
      { key: 'isOriginal', label: '原创声明', type: 'radio', options: [{ label: '原创', value: true }, { label: '非原创', value: false }] },
      { key: 'videoFormat', label: '视频格式', type: 'radio', options: [{ label: '横版', value: 'landscape' }, { label: '竖版', value: 'portrait' }] },
    ],
    defaultSettings: { title: '', description: '', isDraft: false, location: '', aiContent: false, isOriginal: false, videoFormat: '' },
  },
  DOUYIN: {
    id: 3,
    key: 'douyin',
    name: '抖音',
    shortName: 'DY',
    letter: 'D',
    logo: logoDouyin,
    color: '#f43f5e',
    bgColor: 'rgba(244, 63, 94, 0.15)',
    cssClass: 'douyin',
    creatorUrl: 'https://creator.douyin.com/',
    settingsFields: [
      { key: 'productTitle', label: '商品名称', type: 'input', placeholder: '请输入商品名称' },
      { key: 'productLink', label: '商品链接', type: 'input', placeholder: '请输入商品链接' },
      { key: 'aiContent', label: '自主声明', type: 'select', placeholder: '请选择自主声明', options: [
        { label: '内容由AI生成', value: '内容由AI生成' },
        { label: '内容为个人观点或见解', value: '内容为个人观点或见解' },
        { label: '内容为转载信息', value: '内容为转载信息' },
        { label: '内容含营销推广信息', value: '内容含营销推广信息' },
        { label: '虚构演绎，仅供娱乐', value: '虚构演绎，仅供娱乐' },
        { label: '无需添加自主声明', value: '无需添加自主声明' },
      ] },
      { key: 'isOriginal', label: '原创声明', type: 'radio', options: [{ label: '原创', value: true }, { label: '非原创', value: false }] },
      { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间' },
      { key: 'visibility', label: '谁可以看', type: 'radio', options: [{ label: '公开', value: 'public' }, { label: '私密', value: 'private' }] },
      { key: 'allowDownload', label: '允许下载', type: 'switch' },
      { key: 'videoFormat', label: '视频格式', type: 'radio', options: [{ label: '横版', value: 'landscape' }, { label: '竖版', value: 'portrait' }] },
    ],
    defaultSettings: { title: '', description: '', productTitle: '', productLink: '', aiContent: '', isOriginal: false, scheduleTime: '', visibility: 'public', allowDownload: true, videoFormat: '' },
  },
  KUAISHOU: {
    id: 4,
    key: 'kuaishou',
    name: '快手',
    shortName: 'KS',
    letter: 'K',
    logo: logoKuaishou,
    color: '#f59e0b',
    bgColor: 'rgba(245, 158, 11, 0.15)',
    cssClass: 'kuaishou',
    creatorUrl: 'https://k.kuaishou.com/',
    settingsFields: [
      { key: 'productTitle', label: '商品名称', type: 'input', placeholder: '请输入商品名称' },
      { key: 'productLink', label: '商品链接', type: 'input', placeholder: '请输入商品链接' },
      { key: 'aiContent', label: '作者声明', type: 'select', placeholder: '请选择作者声明', options: [{ label: '内容为AI生成', value: '内容为AI生成' }, { label: '演绎情节，仅供娱乐', value: '演绎情节，仅供娱乐' }, { label: '个人观点，仅供参考', value: '个人观点，仅供参考' }, { label: '素材来源于网络', value: '素材来源于网络' }] },
      { key: 'isOriginal', label: '原创声明', type: 'radio', options: [{ label: '原创', value: true }, { label: '非原创', value: false }] },
      { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间' },
      { key: 'videoFormat', label: '视频格式', type: 'radio', options: [{ label: '横版', value: 'landscape' }, { label: '竖版', value: 'portrait' }] },
    ],
    defaultSettings: { title: '', description: '', productTitle: '', productLink: '', aiContent: false, isOriginal: false, scheduleTime: '', videoFormat: '' },
  },
  BILIBILI: {
    id: 5,
    key: 'bilibili',
    name: 'B站',
    shortName: 'BL',
    letter: 'B',
    logo: logoBilibili,
    color: '#00a1d6',
    bgColor: 'rgba(0, 161, 214, 0.15)',
    cssClass: 'bilibili',
    creatorUrl: 'https://member.bilibili.com/',
    settingsFields: [
      { key: 'zone', label: '分区', type: 'select', placeholder: '选择投稿分区', options: [
        { label: 'vlog', value: 'vlog' },
        { label: '影视', value: '影视' },
        { label: '娱乐', value: '娱乐' },
        { label: '音乐', value: '音乐' },
        { label: '舞蹈', value: '舞蹈' },
        { label: '动画', value: '动画' },
        { label: '绘画', value: '绘画' },
        { label: '鬼畜', value: '鬼畜' },
        { label: '游戏', value: '游戏' },
        { label: '资讯', value: '资讯' },
        { label: '知识', value: '知识' },
        { label: '人工智能', value: '人工智能' },
        { label: '科技数码', value: '科技数码' },
        { label: '汽车', value: '汽车' },
        { label: '时尚美妆', value: '时尚美妆' },
        { label: '家装房产', value: '家装房产' },
        { label: '户外潮流', value: '户外潮流' },
        { label: '健身', value: '健身' },
        { label: '体育运动', value: '体育运动' },
        { label: '手工', value: '手工' },
        { label: '美食', value: '美食' },
        { label: '小剧场', value: '小剧场' },
        { label: '旅游出行', value: '旅游出行' },
        { label: '三农', value: '三农' },
        { label: '动物', value: '动物' },
        { label: '亲子', value: '亲子' },
        { label: '健康', value: '健康' },
        { label: '情感', value: '情感' },
        { label: '生活兴趣', value: '生活兴趣' },
        { label: '生活经验', value: '生活经验' },
      ] },
      { key: 'tags', label: '标签', type: 'input', placeholder: '如：#标签1 #标签2 或 逗号分隔' },
      { key: 'topic', label: '话题', type: 'select', placeholder: '选择话题' },
      { key: 'aiContent', label: '声明与权益', type: 'select', placeholder: '选择声明与权益', options: [
        { label: '该视频使用人工智能合成技术', value: '该视频使用人工智能合成技术' },
        { label: '视频内含有危险行为，请勿轻易模仿', value: '视频内含有危险行为，请勿轻易模仿' },
        { label: '该内容仅供娱乐，请勿过分解读', value: '该内容仅供娱乐，请勿过分解读' },
        { label: '该内容可能引人不适，请谨慎选择观看', value: '该内容可能引人不适，请谨慎选择观看' },
        { label: '请理性适度消费', value: '请理性适度消费' },
        { label: '个人观点，仅供参考', value: '个人观点，仅供参考' },
      ] },
      { key: 'creationDeclaration', label: '创作声明', type: 'select', placeholder: '选择创作声明', options: [
        { label: '内容无需标注', value: '内容无需标注' },
        { label: '含AI生成内容', value: '含AI生成内容' },
        { label: '含虚构演绎内容', value: '含虚构演绎内容' },
        { label: '内容含营销信息', value: '内容含营销信息' },
        { label: '个人观点，仅供参考', value: '个人观点，仅供参考' },
        { label: '内容为转载', value: '内容为转载' },
      ] },
      { key: 'isOriginal', label: '原创声明', type: 'radio', options: [{ label: '原创', value: true }, { label: '非原创', value: false }] },
      { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间' },
      { key: 'videoFormat', label: '视频格式', type: 'radio', options: [{ label: '横版', value: 'landscape' }, { label: '竖版', value: 'portrait' }] },
    ],
    defaultSettings: { title: '', description: '', zone: '', tags: '', topic: '', aiContent: '', creationDeclaration: '', isOriginal: false, scheduleTime: '', videoFormat: '' },
  },
  BAIJIAHAO: {
    id: 6,
    key: 'baijiahao',
    name: '百家号',
    shortName: 'BJH',
    letter: 'J',
    logo: logoBaijiahao,
    color: '#e64e3a',
    bgColor: 'rgba(230, 78, 58, 0.15)',
    cssClass: 'baijiahao',
    creatorUrl: 'https://baijiahao.baidu.com/',
    settingsFields: [
      { key: 'aiContent', label: 'AI生成内容', type: 'switch' },
      { key: 'isOriginal', label: '原创声明', type: 'radio', options: [{ label: '原创', value: true }, { label: '非原创', value: false }] },
      { key: 'creationDeclaration', label: '必选声明', type: 'select', placeholder: '选择必选声明', options: [
        { label: '无需声明', value: '无需声明' },
        { label: '含AI生成内容', value: '含AI生成内容' },
        { label: '内容为转载', value: '内容为转载' },
        { label: '含虚构演绎内容', value: '含虚构演绎内容' },
        { label: '内容含营销信息', value: '内容含营销信息' },
        { label: '个人观点，仅供参考', value: '个人观点，仅供参考' },
      ] },
      { key: 'supplementaryDeclaration', label: '补充声明', type: 'select', placeholder: '选择补充声明（可选）', options: [
        { label: '不选择', value: '' },
        { label: '内容可能引人不适', value: '内容可能引人不适' },
        { label: '内容含有高危险行为', value: '内容含有高危险行为' },
        { label: '请理性适度消费', value: '请理性适度消费' },
        { label: '未成年人请在监护人指导下浏览', value: '未成年人请在监护人指导下浏览' },
      ] },
      { key: 'videoFormat', label: '视频格式', type: 'radio', options: [{ label: '横版', value: 'landscape' }, { label: '竖版', value: 'portrait' }] },
    ],
    defaultSettings: { title: '', description: '', aiContent: false, isOriginal: false, creationDeclaration: '', supplementaryDeclaration: '', videoFormat: '' },
  },
  TIKTOK: {
    id: 7,
    key: 'tiktok',
    name: 'TikTok',
    shortName: 'TT',
    letter: 'T',
    logo: null,
    color: '#000000',
    bgColor: 'rgba(0, 0, 0, 0.15)',
    cssClass: 'tiktok',
    creatorUrl: 'https://www.tiktok.com/tiktokstudio/upload?lang=en',
    settingsFields: [
      { key: 'aiContent', label: 'AI生成内容', type: 'switch' },
      { key: 'isOriginal', label: '原创声明', type: 'radio', options: [{ label: '原创', value: true }, { label: '非原创', value: false }] },
      { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间' },
      { key: 'videoFormat', label: '视频格式', type: 'radio', options: [{ label: '横版', value: 'landscape' }, { label: '竖版', value: 'portrait' }] },
    ],
    defaultSettings: { title: '', description: '', aiContent: false, isOriginal: false, scheduleTime: '', videoFormat: '' },
  },
  YOUTUBE: {
    id: 8,
    key: 'youtube',
    name: 'YouTube',
    shortName: 'YT',
    letter: 'Y',
    logo: logoYoutube,
    color: '#ff0000',
    bgColor: 'rgba(255, 0, 0, 0.15)',
    cssClass: 'youtube',
    creatorUrl: 'https://studio.youtube.com/',
    settingsFields: [
      { key: 'audience', label: '观众', type: 'radio',
        description: '根据法律要求，无论你身在何处，都必须遵守《儿童在线隐私保护法》(COPPA) 和/或其他法律。你必须指明自己的视频是否为面向儿童的内容。\n面向儿童的视频不支持个性化广告和通知等功能。',
        options: [{ label: '是，内容是面向儿童的', value: 'kids' }, { label: '否，内容不是面向儿童的', value: 'not_kids' }] },
      { key: 'alteredContent', label: '加工的内容', type: 'radio',
        description: '你的内容是否符合以下任何一项描述？\n• 呈现真实人物的言论或行为，但实际并非本人言行\n• 篡改有关真实事件或地点的视频片段\n• 生成逼真但与实情不符的场景\n\n按照 YouTube 的政策，如果你的内容看似真实，但实则经过加工或合成，则必须告知我们。其中包括使用 AI 或其他工具制作的逼真声音或画面。如果选择"是"，系统会为内容加上披露声明。',
        options: [{ label: '是', value: true }, { label: '否', value: false }] },
      { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间',
        description: '选择要将你的视频设为公开的日期和时间。视频在发布之前将处于私享状态。时区默认为 GMT+8（香港）。' },
      { key: 'videoFormat', label: '视频格式', type: 'radio', options: [{ label: '横版', value: 'landscape' }, { label: '竖版', value: 'portrait' }] },
    ],
    defaultSettings: { title: '', description: '', audience: 'not_kids', alteredContent: false, scheduleTime: '', videoFormat: '' },
  },
}

// 派生数据
export const platformList = Object.values(PLATFORMS)

export const platformIdToName = Object.fromEntries(
  platformList.map(p => [p.id, p.name])
)

export const platformNameToId = Object.fromEntries(
  platformList.map(p => [p.name, p.id])
)

export const platformCssMap = Object.fromEntries(
  platformList.map(p => [p.name, p.cssClass])
)

/**
 * 根据平台ID获取平台配置
 */
export function getPlatformById(id) {
  return platformList.find(p => p.id === id) || null
}

/**
 * 根据平台名称获取平台配置
 */
export function getPlatformByName(name) {
  return platformList.find(p => p.name === name) || null
}

/**
 * 根据 key 获取平台配置
 */
export function getPlatformByKey(key) {
  return platformList.find(p => p.key === key) || null
}

/**
 * 根据 key 获取平台 ID
 */
export const platformKeyToId = Object.fromEntries(
  platformList.map(p => [p.key, p.id])
)
