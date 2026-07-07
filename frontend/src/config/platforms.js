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
import logoTencentVideo from '@/assets/logos/tengxunshipin.png'
import logoIqiyi from '@/assets/logos/aiqiyi.png'
import logoWeibo from '@/assets/logos/weibo.png'
import logoAlipay from '@/assets/logos/alipay.png'
import logoToutiao from '@/assets/logos/toutiao.png'
import logoZhihu from '@/assets/logos/zhihu.png'
import logoCsdn from '@/assets/logos/csdn.png'

import { WEIBO_CATEGORIES } from './weibo-categories'

/**
 * 特殊作者声明值：表示「无需添加声明」。
 * 后端(impl/kuaishou/platform.py)识别到此值(或空)时会跳过作者声明设置，
 * 不去快手发布页查找下拉选项。视频和图集发布共用此约定。
 */
export const DECLARATION_NONE = '内容无需添加声明'

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
      { key: 'aiContent', label: '内容类型声明', type: 'select', required: true, placeholder: '添加内容类型声明', options: [
        { label: '虚构演绎，仅供娱乐', value: '虚构演绎，仅供娱乐' },
        { label: '笔记含AI合成内容', value: '笔记含AI合成内容' },
        { label: '内容包含营销广告', value: '内容包含营销广告' },
        { label: '内容来源声明', value: '内容来源声明' },
      ] },
      // 内容来源声明联动字段(aiContent === '内容来源声明' 时显示)
      { key: 'xhsSourceType', label: '内容来源类型', type: 'radio', options: [{ label: '自主拍摄', value: 'self' }, { label: '来源转载', value: 'repost' }], visibleWhen: { key: 'aiContent', value: '内容来源声明' } },
      { key: 'xhsShootLocation', label: '拍摄地点', type: 'poiSelect', placeholder: '搜索拍摄地点', visibleWhen: { key: 'xhsSourceType', value: 'self' } },
      { key: 'xhsShootDate', label: '拍摄日期', type: 'date', placeholder: '选择拍摄日期', visibleWhen: { key: 'xhsSourceType', value: 'self' } },
      { key: 'xhsRepostSource', label: '转载来源', type: 'input', placeholder: '请输入媒体名称', visibleWhen: { key: 'xhsSourceType', value: 'repost' } },
      // 原创声明:选择了「来源转载」时禁用(转载内容不能声明原创),并自动还原为非原创。
      // disabledWhen 条件命中时单选项灰掉不可勾。
      { key: 'isOriginal', label: '原创声明', type: 'radio', options: [{ label: '原创', value: true }, { label: '非原创', value: false }], disabledWhen: { key: 'xhsSourceType', value: 'repost' } },
      { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间' },
      { key: 'videoFormat', label: '视频格式', type: 'radio', options: [{ label: '横版', value: 'landscape' }, { label: '竖版', value: 'portrait' }] },
    ],
    defaultSettings: { title: '', description: '', aiContent: '', isOriginal: false, scheduleTime: '', videoFormat: '', enableTimer: false, xhsSourceType: '', xhsShootLocation: '', xhsShootDate: '', xhsRepostSource: '' },
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
      { key: 'isOriginal', label: '原创声明', type: 'radio', options: [{ label: '原创', value: true }, { label: '非原创', value: false }] },
      { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间' },
      { key: 'videoFormat', label: '视频格式', type: 'radio', options: [{ label: '横版', value: 'landscape' }, { label: '竖版', value: 'portrait' }] },
    ],
    defaultSettings: { title: '', description: '', isOriginal: false, scheduleTime: '', videoFormat: '' },
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
      { key: 'aiContent', label: '自主声明', type: 'select', required: true, placeholder: '请选择自主声明', options: [
        { label: '内容由AI生成', value: '内容由AI生成' },
        { label: '内容为个人观点或见解', value: '内容为个人观点或见解' },
        { label: '内容为转载信息', value: '内容为转载信息' },
        { label: '内容含营销推广信息', value: '内容含营销推广信息' },
        { label: '虚构演绎，仅供娱乐', value: '虚构演绎，仅供娱乐' },
        { label: '无需添加自主声明', value: '无需添加自主声明' },
      ] },
      { key: 'isOriginal', label: '原创声明', type: 'radio', options: [{ label: '原创', value: true }, { label: '非原创', value: false }] },
      { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间' },
    ],
    defaultSettings: { title: '', description: '', tags: [], aiContent: '', isOriginal: false, scheduleTime: '', videoFormat: '' },
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
      { key: 'aiContent', label: '作者声明', type: 'select', required: true, placeholder: '请选择作者声明', options: [{ label: '内容为AI生成', value: '内容为AI生成' }, { label: '演绎情节，仅供娱乐', value: '演绎情节，仅供娱乐' }, { label: '个人观点，仅供参考', value: '个人观点，仅供参考' }, { label: '素材来源于网络', value: '素材来源于网络' }, { label: DECLARATION_NONE, value: DECLARATION_NONE }] },
      { key: 'isOriginal', label: '原创声明', type: 'radio', options: [{ label: '原创', value: true }, { label: '非原创', value: false }] },
      { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间' },
      { key: 'videoFormat', label: '视频格式', type: 'radio', options: [{ label: '横版', value: 'landscape' }, { label: '竖版', value: 'portrait' }] },
    ],
    defaultSettings: { title: '', description: '', aiContent: false, isOriginal: false, scheduleTime: '', videoFormat: '' },
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
      { key: 'creationDeclaration', label: '创作声明', type: 'select', required: true, placeholder: '选择创作声明', options: [
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
    defaultSettings: { title: '', description: '', zone: '', creationDeclaration: '', isOriginal: false, scheduleTime: '', videoFormat: '' },
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
      { key: 'isOriginal', label: '原创声明', type: 'radio', options: [{ label: '原创', value: true }, { label: '非原创', value: false }] },
      { key: 'creationDeclaration', label: '必选声明', type: 'select', required: true, placeholder: '选择必选声明', options: [
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
      { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间',
        disabledDate: (time) => {
          const today = new Date();
          today.setHours(0, 0, 0, 0);
          const maxDate = new Date(today);
          maxDate.setDate(maxDate.getDate() + 7);
          return time.getTime() < today.getTime() || time.getTime() > maxDate.getTime();
        },
        disabledHours: (_role, comparingDate) => {
          if (!comparingDate) return [];
          const now = new Date();
          const d = comparingDate.toDate ? comparingDate.toDate() : comparingDate;
          const isToday = d.getFullYear() === now.getFullYear()
            && d.getMonth() === now.getMonth()
            && d.getDate() === now.getDate();
          if (!isToday) return [];
          return Array.from({ length: now.getHours() + 1 }, (_, i) => i);
        },
        disabledMinutes: (hour, _role, comparingDate) => {
          if (!comparingDate) return [];
          const now = new Date();
          const d = comparingDate.toDate ? comparingDate.toDate() : comparingDate;
          const isToday = d.getFullYear() === now.getFullYear()
            && d.getMonth() === now.getMonth()
            && d.getDate() === now.getDate();
          if (isToday && hour === now.getHours()) {
            return Array.from({ length: now.getMinutes() + 1 }, (_, i) => i);
          }
          return [];
        },
      },
      { key: 'videoFormat', label: '视频格式', type: 'radio', options: [{ label: '横版', value: 'landscape' }, { label: '竖版', value: 'portrait' }] },
    ],
    defaultSettings: { title: '', description: '', isOriginal: false, creationDeclaration: '', supplementaryDeclaration: '', scheduleTime: '', videoFormat: '' },
  },
  TIKTOK: {
    id: 7,
    key: 'tiktok',
    name: 'TikTok',
    shortName: 'TT',
    letter: 'T',
    logo: new URL('../assets/logos/tiktok.png', import.meta.url).href,
    color: '#FE2C55',
    bgColor: 'rgba(254, 44, 85, 0.15)',
    cssClass: 'tiktok',
    creatorUrl: 'https://www.tiktok.com/tiktokstudio/upload?lang=en',
    settingsFields: [
      { key: 'aiContent', label: 'AI生成内容', type: 'switch', required: true },
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
      { key: 'audience', label: '观众', type: 'radio', required: true,
        description: '根据法律要求，无论你身在何处，都必须遵守《儿童在线隐私保护法》(COPPA) 和/或其他法律。你必须指明自己的视频是否为面向儿童的内容。\n面向儿童的视频不支持个性化广告和通知等功能。',
        options: [{ label: '是，内容是面向儿童的', value: 'kids' }, { label: '否，内容不是面向儿童的', value: 'not_kids' }] },
      { key: 'alteredContent', label: '加工的内容', type: 'radio', required: true,
        description: '你的内容是否符合以下任何一项描述？\n• 呈现真实人物的言论或行为，但实际并非本人言行\n• 篡改有关真实事件或地点的视频片段\n• 生成逼真但与实情不符的场景\n\n按照 YouTube 的政策，如果你的内容看似真实，但实则经过加工或合成，则必须告知我们。其中包括使用 AI 或其他工具制作的逼真声音或画面。如果选择"是"，系统会为内容加上披露声明。',
        options: [{ label: '是', value: true }, { label: '否', value: false }] },
      { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间',
        description: '选择要将你的视频设为公开的日期和时间。视频在发布之前将处于私享状态。时区默认为 GMT+8（香港）。' },
      { key: 'videoFormat', label: '视频格式', type: 'radio', options: [{ label: '横版', value: 'landscape' }, { label: '竖版', value: 'portrait' }] },
    ],
    defaultSettings: { title: '', description: '', audience: 'not_kids', alteredContent: false, scheduleTime: '', videoFormat: '' },
  },
  TENCENT_VIDEO: {
    id: 9,
    key: 'tencent_video',
    name: '腾讯视频',
    shortName: 'TX',
    letter: 'Q',
    logo: logoTencentVideo,
    color: '#FF6A00',
    bgColor: 'rgba(255, 106, 0, 0.15)',
    cssClass: 'tencent-video',
    creatorUrl: 'https://mp.v.qq.com/',
    settingsFields: [
      { key: 'creationDeclaration', label: '创作声明', type: 'multiSelect', required: true, placeholder: '请选择创作声明（可多选）', options: [
        { label: '剧情演绎，仅供娱乐', value: '剧情演绎，仅供娱乐' },
        { label: '取材网络，谨慎甄别', value: '取材网络，谨慎甄别' },
        { label: '个人观点，仅供参考', value: '个人观点，仅供参考' },
        { label: '未成年人请勿学习模仿', value: '未成年人请勿学习模仿' },
        { label: '内容由AI生成', value: '内容由AI生成' },
      ] },
      { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间' },
      { key: 'videoFormat', label: '视频格式', type: 'radio', options: [{ label: '横版', value: 'landscape' }, { label: '竖版', value: 'portrait' }] },
    ],
    defaultSettings: { title: '', description: '', creationDeclaration: '', scheduleTime: '', videoFormat: '' },
  },
  IQIYI: {
    id: 10,
    key: 'iqiyi',
    name: '爱奇艺',
    shortName: 'IQY',
    letter: 'i',
    logo: logoIqiyi,
    color: '#00d442',
    bgColor: 'rgba(0, 212, 66, 0.15)',
    cssClass: 'iqiyi',
    creatorUrl: 'https://creator.iqiyi.com/',
    settingsFields: [
      { key: 'creationDeclaration', label: '创作声明（必填）', type: 'select', required: true, placeholder: '请选择创作声明', options: [
        { label: '含AI生成内容', value: '含AI生成内容' },
        { label: '含虚构演绎内容', value: '含虚构演绎内容' },
        { label: '内容含营销信息', value: '内容含营销信息' },
        { label: '内容为转载', value: '内容为转载' },
        { label: '个人观点，仅供参考', value: '个人观点，仅供参考' },
        { label: '内容无需标注', value: '内容无需标注' },
      ] },
      { key: 'riskWarning', label: '风险提示（选填）', type: 'select', placeholder: '选择风险提示', options: [
        { label: '内容可能引人不适，请谨慎观看', value: '内容可能引人不适，请谨慎观看' },
        { label: '内容含有高危险行为，请勿模仿', value: '内容含有高危险行为，请勿模仿' },
        { label: '请理性适度消费', value: '请理性适度消费' },
        { label: '未成年人请在监护人指导下浏览', value: '未成年人请在监护人指导下浏览' },
      ] },
      { key: 'enableCashActivity', label: '参与打卡挑战赛', type: 'switch', description: '参与当月打卡挑战赛获取奖励' },
      { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间' },
      { key: 'videoFormat', label: '视频格式', type: 'radio', options: [{ label: '横版', value: 'landscape' }, { label: '竖版', value: 'portrait' }] },
    ],
    defaultSettings: { title: '', description: '', creationDeclaration: '', riskWarning: '', enableCashActivity: false, scheduleTime: '', videoFormat: '' },
  },
  WEIBO: {
    id: 11,
    key: 'weibo',
    name: '微博',
    shortName: 'WB',
    letter: 'W',
    logo: logoWeibo,
    color: '#E6162D',
    bgColor: 'rgba(230, 22, 45, 0.15)',
    cssClass: 'weibo',
    creatorUrl: 'https://weibo.com/set/index',
    settingsFields: [
      { key: 'videoType', label: '类型', type: 'radio', options: [
        { label: '原创', value: '原创' },
        { label: '二创', value: '二创' },
        { label: '转载', value: '转载' },
      ] },
      { key: 'weiboCategory', label: '分类', type: 'cascader',
        placeholder: '选择频道 / 子分类',
        options: WEIBO_CATEGORIES,
        props: { expandTrigger: 'hover' } },
      { key: 'contentStatement', label: '内容声明', type: 'select', required: true,
        placeholder: '请选择内容声明（可选）',
        options: [
          { label: '无', value: '无' },
          { label: '内容为自主创作', value: '内容为自主创作' },
          { label: '内容为转载', value: '内容为转载' },
          { label: '内容由AI生成', value: '内容由AI生成' },
          { label: '内容为虚构演绎', value: '内容为虚构演绎' },
        ] },
    ],
    defaultSettings: { title: '', description: '', videoType: '', weiboCategory: [], contentStatement: '' },
  },
  ALIPAY: {
    id: 12,
    key: 'alipay',
    name: '支付宝',
    shortName: 'ZFB',
    letter: 'Z',
    logo: logoAlipay,
    color: '#1677FF',
    bgColor: 'rgba(22, 119, 255, 0.15)',
    cssClass: 'alipay',
    creatorUrl: 'https://c.alipay.com/page/life-account/index',
    settingsFields: [
      { key: 'authorStatement', label: '作者声明', type: 'select', required: true, placeholder: '请选择作者声明（必填）', options: [
        { label: '内容无需标注', value: '内容无需标注' },
        { label: '个人观点，仅供参考', value: '个人观点，仅供参考' },
        { label: '内容由AI生成', value: '内容由AI生成' },
        { label: '内容虚构演绎，仅供娱乐', value: '内容虚构演绎，仅供娱乐' },
        { label: '内容含营销信息', value: '内容含营销信息' },
        { label: '内容为转载', value: '内容为转载' },
      ] },
      { key: 'compilation', label: '加入合集', type: 'compilationSelect', placeholder: '输入合集名称搜索' },
      { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间' },
      { key: 'videoFormat', label: '视频格式', type: 'radio', options: [{ label: '横版', value: 'landscape' }, { label: '竖版', value: 'portrait' }] },
    ],
    defaultSettings: { title: '', description: '', authorStatement: '', compilation: '', scheduleTime: '', videoFormat: '' },
  },
  TOUTIAO: {
    id: 13,
    key: 'toutiao',
    name: '今日头条',
    shortName: 'TT',
    letter: 'T',
    logo: logoToutiao,
    color: '#FF0000',
    bgColor: 'rgba(255, 0, 0, 0.15)',
    cssClass: 'toutiao',
    creatorUrl: 'https://mp.toutiao.com/profile_v4/index',
    settingsFields: [
      { key: 'creationDeclaration', label: '作品声明', type: 'select', required: true, placeholder: '请选择作品声明', options: [
        { label: '取自站外', value: '取自站外' },
        { label: '引用站内', value: '引用站内' },
        { label: '自行拍摄', value: '自行拍摄' },
        { label: 'AI生成', value: 'AI生成' },
        { label: '虚构演绎，故事经历', value: '虚构演绎，故事经历' },
        { label: '投资观点，仅供参考', value: '投资观点，仅供参考' },
        { label: '健康医疗分享，仅供参考', value: '健康医疗分享，仅供参考' },
      ] },
      { key: 'enableGenerateImage', label: '视频生成图文', type: 'switch', description: '勾选后额外得图文创作收益' },
      { key: 'collection', label: '加入合集', type: 'compilationSelect', placeholder: '输入合集名称搜索' },
      { key: 'extendLink', label: '扩展链接', type: 'switch', description: '在今日头条APP的固定位置插入链接', linkField: 'extendLinkUrl' },
      { key: 'extendLinkUrl', label: '链接地址', type: 'input', placeholder: '请输入扩展链接地址', visibleWhen: { key: 'extendLink', value: true } },
      { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间',
        disabledDate: (time) => {
          const today = new Date();
          today.setHours(0, 0, 0, 0);
          const maxDate = new Date(today);
          maxDate.setDate(maxDate.getDate() + 7);
          return time.getTime() < today.getTime() || time.getTime() > maxDate.getTime();
        },
        disabledHours: (_role, comparingDate) => {
          if (!comparingDate) return [];
          const now = new Date();
          const d = comparingDate.toDate ? comparingDate.toDate() : comparingDate;
          const isToday = d.getFullYear() === now.getFullYear()
            && d.getMonth() === now.getMonth()
            && d.getDate() === now.getDate();
          if (!isToday) return [];
          return Array.from({ length: now.getHours() + 1 }, (_, i) => i);
        },
        disabledMinutes: (hour, _role, comparingDate) => {
          if (!comparingDate) return [];
          const now = new Date();
          const d = comparingDate.toDate ? comparingDate.toDate() : comparingDate;
          const isToday = d.getFullYear() === now.getFullYear()
            && d.getMonth() === now.getMonth()
            && d.getDate() === now.getDate();
          if (isToday && hour === now.getHours()) {
            return Array.from({ length: now.getMinutes() + 1 }, (_, i) => i);
          }
          return [];
        },
      },
      { key: 'videoFormat', label: '视频格式', type: 'radio', options: [{ label: '横版', value: 'landscape' }, { label: '竖版', value: 'portrait' }] },
    ],
    defaultSettings: { title: '', description: '', creationDeclaration: [], enableGenerateImage: true, collection: '', extendLink: false, extendLinkUrl: '', scheduleTime: '', videoFormat: '' },
  },
  ZHIHU: {
    id: 14,
    key: 'zhihu',
    name: '知乎',
    shortName: 'ZH',
    letter: 'Z',
    logo: logoZhihu,
    color: '#0084FF',
    bgColor: 'rgba(0, 132, 255, 0.15)',
    cssClass: 'zhihu',
    creatorUrl: 'https://www.zhihu.com/upload-video?entry=navPanel',
    settingsFields: [
      { key: 'creationDeclaration', label: '视频标记', type: 'select', placeholder: '请选择视频标记', options: [
        { label: '内容无需标注', value: '内容无需标注' },
        { label: '含 AI 生成内容', value: '含 AI 生成内容' },
        { label: '含虚构演绎内容', value: '含虚构演绎内容' },
        { label: '内容含营销信息', value: '内容含营销信息' },
        { label: '内容为转载', value: '内容为转载' },
        { label: '个人观点仅供参考', value: '个人观点仅供参考' },
      ] },
      { key: 'category', label: '所属领域', type: 'select', placeholder: '选择领域', options: [
        { label: '人文', value: '人文' },
        { label: '体育竞技', value: '体育竞技' },
        { label: '健康医学', value: '健康医学' },
        { label: '其他', value: '其他' },
        { label: '军事', value: '军事' },
        { label: '动漫', value: '动漫' },
        { label: '娱乐', value: '娱乐' },
        { label: '宠物', value: '宠物' },
        { label: '家居生活', value: '家居生活' },
        { label: '家用电器', value: '家用电器' },
        { label: '影视', value: '影视' },
        { label: '心理学', value: '心理学' },
        { label: '情感', value: '情感' },
        { label: '故事', value: '故事' },
        { label: '教育', value: '教育' },
        { label: '数码', value: '数码' },
        { label: '旅行', value: '旅行' },
        { label: '时尚穿搭', value: '时尚穿搭' },
        { label: '母婴亲子', value: '母婴亲子' },
        { label: '汽车', value: '汽车' },
        { label: '法律', value: '法律' },
        { label: '游戏电竞', value: '游戏电竞' },
        { label: '社会/时政', value: '社会/时政' },
        { label: '社会学', value: '社会学' },
        { label: '科学工程', value: '科学工程' },
        { label: '科技互联网', value: '科技互联网' },
        { label: '经济与管理', value: '经济与管理' },
        { label: '美妆个护', value: '美妆个护' },
        { label: '美食', value: '美食' },
        { label: '职场', value: '职场' },
        { label: '艺术', value: '艺术' },
        { label: '运动健身', value: '运动健身' },
        { label: '音乐', value: '音乐' },
      ] },
      { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间',
        disabledDate: (time) => {
          const today = new Date();
          today.setHours(0, 0, 0, 0);
          const maxDate = new Date(today);
          maxDate.setMonth(maxDate.getMonth() + 1);
          return time.getTime() < today.getTime() || time.getTime() > maxDate.getTime();
        },
        disabledHours: (_role, comparingDate) => {
          if (!comparingDate) return [];
          const now = new Date();
          const d = comparingDate.toDate ? comparingDate.toDate() : comparingDate;
          const isToday = d.getFullYear() === now.getFullYear()
            && d.getMonth() === now.getMonth()
            && d.getDate() === now.getDate();
          if (!isToday) return [];
          return Array.from({ length: now.getHours() + 1 }, (_, i) => i);
        },
        disabledMinutes: (hour, _role, comparingDate) => {
          if (!comparingDate) return [];
          const now = new Date();
          const d = comparingDate.toDate ? comparingDate.toDate() : comparingDate;
          const isToday = d.getFullYear() === now.getFullYear()
            && d.getMonth() === now.getMonth()
            && d.getDate() === now.getDate();
          if (isToday && hour === now.getHours()) {
            return Array.from({ length: now.getMinutes() + 1 }, (_, i) => i);
          }
          return [];
        },
      },
      { key: 'videoFormat', label: '视频格式', type: 'radio', options: [{ label: '横版', value: 'landscape' }, { label: '竖版', value: 'portrait' }] },
    ],
    defaultSettings: { title: '', description: '', creationDeclaration: '内容无需标注', category: '', scheduleTime: '', videoFormat: '' },
  },
  CSDN: {
    id: 15,
    key: 'csdn',
    name: 'CSDN',
    shortName: 'CSDN',
    letter: 'C',
    logo: logoCsdn,
    color: '#FC5531',
    bgColor: 'rgba(252, 85, 49, 0.15)',
    cssClass: 'csdn',
    creatorUrl: 'https://mp.csdn.net/',
    settingsFields: [
      { key: 'recommend', label: '是否推荐', type: 'switch', description: '勾选后发布的视频将被推荐' },
    ],
    defaultSettings: { title: '', description: '', recommend: false, scheduleTime: '' },
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

export const platformNameToKey = Object.fromEntries(
  platformList.map(p => [p.name, p.key])
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
