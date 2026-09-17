"""平台发布配置元数据（供 MCP / AI Agent 消费）。

`/api/v2/platforms` 端点把本模块与 impl.registry 的自动枚举结果合并返回：
- registry 注册新平台 → 端点自动出现该平台（id/key/name 来自平台实现类）
- 本模块补充发布配置细节：default_config（发布配置初始值）、fields（发布设置
  字段定义：类型/选项/联动规则）、schedule（定时发布约束）

数据来源与同步约定：
- default_config 与 frontend/src/views/PublishCenter.vue 的 DEFAULT_PLATFORM_CONFIGS 同构
- fields 与 frontend/src/config/platforms.js 的 settingsFields 对齐（只保留
  JSON 可序列化子集：key/label/type/required/placeholder/description/options/visible_when）
- 超长级联选项（微博 255 子分类、视频号 240 国地区树）只保留顶级选项，
  子级由发布页面实际交互兜底（Playwright 在真实页面逐级点选）
"""

from __future__ import annotations

# 通用最小发布配置（registry 有平台但此处无元数据时的兜底）
_MINIMAL_DEFAULT_CONFIG = {
    "title": "", "description": "", "tags": [], "scheduleTime": "",
}


def _opt(*values: str) -> list[dict]:
    return [{"label": v, "value": v} for v in values]


# 各平台发布设置字段元数据（key 与 registry platform_key 一致）
PLATFORM_META: dict[str, dict] = {
    "xiaohongshu": {
        "name": "小红书",
        "creator_url": "https://creator.xiaohongshu.com/",
        "fields": [
            {"key": "aiContent", "label": "内容类型声明", "type": "select", "required": True, "options": _opt(
                "虚构演绎，仅供娱乐", "笔记含AI合成内容", "内容包含营销广告", "内容来源声明")},
            {"key": "xhsSourceType", "label": "内容来源类型", "type": "radio", "visible_when": {"key": "aiContent", "value": "内容来源声明"},
             "options": [{"label": "自主拍摄", "value": "self"}, {"label": "来源转载", "value": "repost"}]},
            {"key": "xhsShootLocation", "label": "拍摄地点", "type": "poiSelect", "visible_when": {"key": "xhsSourceType", "value": "self"}},
            {"key": "xhsShootDate", "label": "拍摄日期", "type": "date", "visible_when": {"key": "xhsSourceType", "value": "self"},
             "placeholder": "YYYY-MM-DD"},
            {"key": "xhsRepostSource", "label": "转载来源", "type": "input", "visible_when": {"key": "xhsSourceType", "value": "repost"},
             "placeholder": "媒体名称"},
            {"key": "isOriginal", "label": "原创声明", "type": "radio", "options": [
                {"label": "原创", "value": True}, {"label": "非原创", "value": False}],
             "note": "选择来源转载时不可声明原创"},
            {"key": "collectionId", "label": "合集", "type": "collectionSelect"},
            {"key": "scheduleTime", "label": "定时发布", "type": "datetime", "placeholder": "yyyy-MM-dd HH:mm:ss"},
            {"key": "videoFormat", "label": "视频格式", "type": "radio", "options": _opt("landscape", "portrait")},
        ],
    },
    "channels": {
        "name": "视频号",
        "creator_url": "https://channels.weixin.qq.com/",
        "fields": [
            {"key": "channelsMarkTag", "label": "视频标注", "type": "select", "options": _opt(
                "无需标注", "含AI生成内容", "内容为虚构剧情，仅供娱乐", "个人观点，仅供参考",
                "内容包含营销广告", "内容为自行拍摄", "内容为转载"),
             "note": "所有选项（含无需标注）都会在发布页真正选中"},
            {"key": "channelsShootDate", "label": "拍摄时间", "type": "date", "visible_when": {"key": "channelsMarkTag", "value": "内容为自行拍摄"}},
            {"key": "channelsShootRegion", "label": "拍摄地点", "type": "cascader", "visible_when": {"key": "channelsMarkTag", "value": "内容为自行拍摄"},
             "placeholder": "[国家, 省, 市]，如 [\"中国\", \"北京市\", \"北京市\"]"},
            {"key": "channelsRepostSource", "label": "转载来源", "type": "input", "visible_when": {"key": "channelsMarkTag", "value": "内容为转载"},
             "required": False},
            {"key": "isOriginal", "label": "原创声明", "type": "radio", "options": [
                {"label": "原创", "value": True}, {"label": "非原创", "value": False}]},
            {"key": "channelsCollectionName", "label": "合集", "type": "collectionSelect"},
            {"key": "channelsLocationName", "label": "位置", "type": "poiSelect"},
            {"key": "channelsActivityName", "label": "活动", "type": "activitySelect"},
            {"key": "channelsDrama", "label": "关联剧集", "type": "dramaPicker"},
            {"key": "channelsLinkType", "label": "链接类型", "type": "select", "options": _opt("公众号文章", "红包封面")},
            {"key": "channelsLinkArticleUrl", "label": "公众号文章链接", "type": "input", "visible_when": {"key": "channelsLinkType", "value": "公众号文章"}},
            {"key": "channelsRedEnvelopeUrl", "label": "红包封面链接", "type": "input", "visible_when": {"key": "channelsLinkType", "value": "红包封面"}},
            {"key": "scheduleTime", "label": "定时发布", "type": "datetime", "placeholder": "yyyy-MM-dd HH:mm:ss"},
            {"key": "videoFormat", "label": "视频格式", "type": "radio", "options": _opt("landscape", "portrait")},
        ],
    },
    "douyin": {
        "name": "抖音",
        "creator_url": "https://creator.douyin.com/",
        "fields": [
            {"key": "aiContent", "label": "自主声明", "type": "select", "required": True, "options": _opt(
                "内容由AI生成", "内容为个人观点或见解", "内容为转载信息", "内容含营销推广信息",
                "虚构演绎，仅供娱乐", "无需添加自主声明")},
            {"key": "isOriginal", "label": "原创声明", "type": "radio", "options": [
                {"label": "原创", "value": True}, {"label": "非原创", "value": False}]},
            {"key": "activityId", "label": "官方活动", "type": "multiSelect", "note": "活动 ID 列表，可调 douyin_activity_list 获取"},
            {"key": "hotspotId", "label": "热点", "type": "hotspotSelect", "note": "热点 ID，可调 douyin_hotspot_search 搜索"},
            {"key": "tagType", "label": "标签类型", "type": "select", "options": [{"label": "小程序", "value": "miniapp"}]},
            {"key": "tagValue", "label": "标签值", "type": "input"},
            {"key": "mixId", "label": "合集", "type": "mixSelect", "note": "合集 ID，可调 douyin_mix_list 获取"},
            {"key": "scheduleTime", "label": "定时发布", "type": "datetime", "placeholder": "yyyy-MM-dd HH:mm:ss"},
        ],
        "note": "话题总数 ≤ 5（描述 #xxx + 活动 + 标签）",
    },
    "kuaishou": {
        "name": "快手",
        "creator_url": "https://k.kuaishou.com/",
        "fields": [
            {"key": "aiContent", "label": "作者声明", "type": "select", "required": True, "options": _opt(
                "内容为AI生成", "演绎情节，仅供娱乐", "个人观点，仅供参考", "素材来源于网络", "内容无需添加声明")},
            {"key": "isOriginal", "label": "原创声明", "type": "radio", "options": [
                {"label": "原创", "value": True}, {"label": "非原创", "value": False}]},
            {"key": "scheduleTime", "label": "定时发布", "type": "datetime", "placeholder": "yyyy-MM-dd HH:mm:ss"},
            {"key": "videoFormat", "label": "视频格式", "type": "radio", "options": _opt("landscape", "portrait")},
        ],
        "note": "标签最多 4 个",
    },
    "bilibili": {
        "name": "B站",
        "creator_url": "https://member.bilibili.com/",
        "fields": [
            {"key": "zone", "label": "分区", "type": "select", "options": _opt(
                "vlog", "影视", "娱乐", "音乐", "舞蹈", "动画", "绘画", "鬼畜", "游戏", "资讯",
                "知识", "人工智能", "科技数码", "汽车", "时尚美妆", "家装房产", "户外潮流", "健身",
                "体育运动", "手工", "美食", "小剧场", "旅游出行", "三农", "动物", "亲子", "健康",
                "情感", "生活兴趣", "生活经验")},
            {"key": "creationDeclaration", "label": "创作声明", "type": "select", "required": True, "options": _opt(
                "内容无需标注", "含AI生成内容", "含虚构演绎内容", "内容含营销信息", "个人观点，仅供参考", "内容为转载")},
            {"key": "biliRepostSource", "label": "转载来源", "type": "input", "required": True,
             "visible_when": {"key": "creationDeclaration", "value": "内容为转载"}, "placeholder": "例: 转自 https://xxx"},
            {"key": "isOriginal", "label": "原创声明", "type": "radio", "options": [
                {"label": "原创", "value": True}, {"label": "非原创", "value": False}]},
            {"key": "biliKeepSystemTags", "label": "保留系统生成标签", "type": "switch"},
            {"key": "biliCollectionName", "label": "合集", "type": "collectionSelect"},
            {"key": "scheduleTime", "label": "定时发布", "type": "datetime", "placeholder": "yyyy-MM-dd HH:mm:ss"},
            {"key": "videoFormat", "label": "视频格式", "type": "radio", "options": _opt("landscape", "portrait")},
        ],
    },
    "baijiahao": {
        "name": "百家号",
        "creator_url": "https://baijiahao.baidu.com/",
        "schedule": {"max_days": 7},
        "fields": [
            {"key": "isOriginal", "label": "原创声明", "type": "radio", "options": [
                {"label": "原创", "value": True}, {"label": "非原创", "value": False}]},
            {"key": "creationDeclaration", "label": "必选声明", "type": "select", "required": True, "options": _opt(
                "无需声明", "含AI生成内容", "内容为转载", "含虚构演绎内容", "内容含营销信息", "个人观点，仅供参考")},
            {"key": "supplementaryDeclaration", "label": "补充声明", "type": "select", "required": False, "options": _opt(
                "内容可能引人不适", "内容含有高危险行为", "请理性适度消费", "未成年人请在监护人指导下浏览")},
            {"key": "scheduleTime", "label": "定时发布", "type": "datetime", "placeholder": "yyyy-MM-dd HH:mm:ss",
             "note": "仅未来 7 天内可选，且需晚于当前时间"},
            {"key": "videoFormat", "label": "视频格式", "type": "radio", "options": _opt("landscape", "portrait")},
        ],
    },
    "tiktok": {
        "name": "TikTok",
        "creator_url": "https://www.tiktok.com/tiktokstudio/upload?lang=en",
        "fields": [
            {"key": "aiContent", "label": "AI生成内容", "type": "switch"},
            {"key": "isOriginal", "label": "原创声明", "type": "radio", "options": [
                {"label": "原创", "value": True}, {"label": "非原创", "value": False}]},
            {"key": "scheduleTime", "label": "定时发布", "type": "datetime", "placeholder": "yyyy-MM-dd HH:mm:ss"},
            {"key": "videoFormat", "label": "视频格式", "type": "radio", "options": _opt("landscape", "portrait")},
        ],
    },
    "youtube": {
        "name": "YouTube",
        "creator_url": "https://studio.youtube.com/",
        "fields": [
            {"key": "audience", "label": "观众", "type": "radio", "required": True, "options": [
                {"label": "面向儿童", "value": "kids"}, {"label": "非面向儿童", "value": "not_kids"}]},
            {"key": "alteredContent", "label": "加工的内容", "type": "radio", "required": True, "options": [
                {"label": "是", "value": True}, {"label": "否", "value": False}]},
            {"key": "scheduleTime", "label": "定时发布", "type": "datetime", "placeholder": "yyyy-MM-dd HH:mm:ss",
             "note": "视频在发布前处于私享状态"},
            {"key": "videoFormat", "label": "视频格式", "type": "radio", "options": _opt("landscape", "portrait")},
        ],
    },
    "tencent_video": {
        "name": "腾讯视频",
        "creator_url": "https://mp.v.qq.com/",
        "fields": [
            {"key": "creationDeclaration", "label": "创作声明", "type": "multiSelect", "required": True, "options": _opt(
                "剧情演绎，仅供娱乐", "取材网络，谨慎甄别", "个人观点，仅供参考", "未成年人请勿学习模仿", "内容由AI生成")},
            {"key": "scheduleTime", "label": "定时发布", "type": "datetime", "placeholder": "yyyy-MM-dd HH:mm:ss"},
            {"key": "videoFormat", "label": "视频格式", "type": "radio", "options": _opt("landscape", "portrait")},
        ],
    },
    "iqiyi": {
        "name": "爱奇艺",
        "creator_url": "https://creator.iqiyi.com/",
        "fields": [
            {"key": "creationDeclaration", "label": "创作声明", "type": "select", "required": True, "options": _opt(
                "含AI生成内容", "含虚构演绎内容", "内容含营销信息", "内容为转载", "个人观点，仅供参考", "内容无需标注")},
            {"key": "riskWarning", "label": "风险提示", "type": "select", "required": False, "options": _opt(
                "内容可能引人不适，请谨慎观看", "内容含有高危险行为，请勿模仿", "请理性适度消费", "未成年人请在监护人指导下浏览")},
            {"key": "enableCashActivity", "label": "参与打卡挑战赛", "type": "switch"},
            {"key": "scheduleTime", "label": "定时发布", "type": "datetime", "placeholder": "yyyy-MM-dd HH:mm:ss"},
            {"key": "videoFormat", "label": "视频格式", "type": "radio", "options": _opt("landscape", "portrait")},
        ],
    },
    "weibo": {
        "name": "微博",
        "creator_url": "https://weibo.com/set/index",
        "fields": [
            {"key": "videoType", "label": "类型", "type": "radio", "options": _opt("原创", "二创", "转载")},
            {"key": "weiboCategory", "label": "分类", "type": "cascader",
             "placeholder": "[频道, 子分类]，如 [\"VLOG\", \"旅行\"]",
             "options": _opt("VLOG", "生活", "好物分享", "视频播客", "游戏", "电竞", "知识", "美食",
                             "娱乐明星", "搞笑幽默", "美妆", "时尚", "综艺", "动漫", "体育", "音乐演出",
                             "电影", "电视剧", "人文艺术", "旅游", "科技数码", "汽车", "舞蹈", "社会资讯", "纪录片"),
             "note": "共 25 频道 255 子分类，此处仅列频道；子分类按用户指定传入"},
            {"key": "contentStatement", "label": "内容声明", "type": "select", "required": False, "options": _opt(
                "无", "内容为自主创作", "内容为转载", "内容由AI生成", "内容为虚构演绎")},
            {"key": "contentStatement2", "label": "内容声明2", "type": "select", "required": True, "options": _opt(
                "内容无需标注", "内容为转载", "含AI生成内容", "含虚构演绎内容", "个人观点，仅供参考", "内容含营销信息")},
            {"key": "contentStatement2Optional", "label": "内容声明2(可选)", "type": "select", "required": False, "options": _opt(
                "内容可能引人不适，请谨慎观看", "内容含有高危险行为，请勿模仿", "请理性适度消费", "未成年人请在监护人指导下浏览")},
            {"key": "weiboCollectionName", "label": "合集", "type": "collectionSelect"},
        ],
    },
    "alipay": {
        "name": "支付宝",
        "creator_url": "https://c.alipay.com/page/life-account/index",
        "fields": [
            {"key": "authorStatement", "label": "作者声明", "type": "select", "required": True, "options": _opt(
                "内容无需标注", "个人观点，仅供参考", "内容由AI生成", "内容虚构演绎，仅供娱乐",
                "内容含营销信息", "内容为转载")},
            {"key": "reprintUrl", "label": "转载来源", "type": "input", "required": True,
             "visible_when": {"key": "authorStatement", "value": "内容为转载"}, "placeholder": "https://xxx"},
            {"key": "compilation", "label": "加入合集", "type": "compilationSelect", "note": "可调 alipay_compilation_search 搜索合集"},
            {"key": "scheduleTime", "label": "定时发布", "type": "datetime", "placeholder": "yyyy-MM-dd HH:mm:ss"},
            {"key": "videoFormat", "label": "视频格式", "type": "radio", "options": _opt("landscape", "portrait")},
        ],
    },
    "toutiao": {
        "name": "今日头条",
        "creator_url": "https://mp.toutiao.com/profile_v4/index",
        "schedule": {"max_days": 7},
        "fields": [
            {"key": "creationDeclaration", "label": "作品声明", "type": "select", "required": True, "options": _opt(
                "取自站外", "引用站内", "自行拍摄", "AI生成", "虚构演绎，故事经历", "投资观点，仅供参考",
                "健康医疗分享，仅供参考")},
            {"key": "enableGenerateImage", "label": "视频生成图文", "type": "switch"},
            {"key": "collection", "label": "加入合集", "type": "compilationSelect", "note": "可调 toutiao_compilation_search 搜索合集"},
            {"key": "extendLink", "label": "扩展链接", "type": "switch"},
            {"key": "extendLinkUrl", "label": "链接地址", "type": "input", "visible_when": {"key": "extendLink", "value": True}},
            {"key": "scheduleTime", "label": "定时发布", "type": "datetime", "placeholder": "yyyy-MM-dd HH:mm:ss",
             "note": "仅未来 7 天内可选，且需晚于当前时间"},
            {"key": "videoFormat", "label": "视频格式", "type": "radio", "options": _opt("landscape", "portrait")},
        ],
    },
    "zhihu": {
        "name": "知乎",
        "creator_url": "https://www.zhihu.com/upload-video?entry=navPanel",
        "schedule": {"max_days": 31},
        "fields": [
            {"key": "creationDeclaration", "label": "视频标记", "type": "select", "options": _opt(
                "内容无需标注", "含 AI 生成内容", "含虚构演绎内容", "内容含营销信息", "内容为转载", "个人观点仅供参考")},
            {"key": "category", "label": "所属领域", "type": "select", "options": _opt(
                "人文", "体育竞技", "健康医学", "其他", "军事", "动漫", "娱乐", "宠物", "家居生活",
                "家用电器", "影视", "心理学", "情感", "故事", "教育", "数码", "旅行", "时尚穿搭",
                "母婴亲子", "汽车", "法律", "游戏电竞", "社会/时政", "社会学", "科学工程", "科技互联网",
                "经济与管理", "美妆个护", "美食", "职场", "艺术", "运动健身", "音乐")},
            {"key": "scheduleTime", "label": "定时发布", "type": "datetime", "placeholder": "yyyy-MM-dd HH:mm:ss"},
            {"key": "videoFormat", "label": "视频格式", "type": "radio", "options": _opt("landscape", "portrait")},
            {"key": "coverLandscape169", "label": "16:9 横版封面", "type": "material", "note": "横版视频建议提供 16:9 封面"},
            {"key": "coverPortrait916", "label": "9:16 竖版封面", "type": "material"},
        ],
    },
    "csdn": {
        "name": "CSDN",
        "creator_url": "https://mp.csdn.net/",
        "fields": [
            {"key": "recommend", "label": "是否推荐", "type": "switch"},
            {"key": "scheduleTime", "label": "定时发布", "type": "datetime", "placeholder": "yyyy-MM-dd HH:mm:ss"},
        ],
    },
    "vivo": {
        "name": "VIVO",
        "creator_url": "https://www.kaixinkan.com.cn/#/home",
        "fields": [
            {"key": "vivoLocationName", "label": "添加位置", "type": "poiSelect", "note": "可调 vivo_search_position 搜索"},
            {"key": "vivoDistribution", "label": "作品同步", "type": "switch", "description": "同时分发到 vivo 浏览器、i 视频、阅图"},
            {"key": "vivoDeclaration", "label": "自主声明", "type": "select", "options": _opt(
                "含AI生成内容", "含虚构演绎内容", "内容含营销信息", "内容为转载", "个人观点，仅供参考", "内容无需标注")},
            {"key": "vivoPrivacy", "label": "谁可以看", "type": "radio", "options": _opt("公开", "私密")},
            {"key": "vivoDownloadPermission", "label": "下载权限", "type": "radio", "options": _opt("允许", "不允许")},
            {"key": "scheduleTime", "label": "定时发布", "type": "datetime", "placeholder": "yyyy-MM-dd HH:mm:ss"},
        ],
    },
    "weixin_gzh": {
        "name": "微信公众号",
        "creator_url": "https://mp.weixin.qq.com/",
        "fields": [
            {"key": "isOriginal", "label": "原创声明", "type": "radio", "options": [
                {"label": "原创", "value": True}, {"label": "非原创", "value": False}]},
            {"key": "gzhClaimSource", "label": "创作来源", "type": "select", "required": False, "options": _opt(
                "内容由AI生成", "内容剧情演绎，仅供娱乐", "个人观点，仅供参考", "健康医疗分享，仅供参考",
                "投资观点，仅供参考", "无需声明")},
            {"key": "gzhCollectionName", "label": "合集", "type": "collectionSelect"},
            {"key": "scheduleTime", "label": "定时发布", "type": "datetime", "placeholder": "yyyy-MM-dd HH:mm:ss",
             "note": "最近 7 天，且需大于当前时间 1 小时"},
        ],
    },
    "taobao_guanghe": {
        "name": "淘宝光合",
        "creator_url": "https://creator.guanghe.taobao.com/",
        "fields": [
            {"key": "guangheClaim", "label": "创作者声明", "type": "select", "required": True, "options": _opt(
                "内容无需标注", "含AI生成内容", "含虚构演绎内容", "内容为转载", "个人观点，仅供参考", "内容含营销信息")},
            {"key": "guangheLinkType", "label": "关联类型", "type": "select", "options": _opt("商品", "店铺")},
            {"key": "guangheProducts", "label": "关联商品", "type": "multiSelect",
             "placeholder": "[{title, image}]，按名称在光合面板搜索匹配"},
            {"key": "guangheShops", "label": "关联店铺", "type": "multiSelect"},
            {"key": "scheduleTime", "label": "定时发布", "type": "datetime", "placeholder": "yyyy-MM-dd HH:mm:ss"},
        ],
    },
    "jingmai": {
        "name": "京东京麦",
        "creator_url": "https://dr.jd.com/jm/",
        "hide_fields": ["description", "tags"],
        "fields": [
            {"key": "jdRelatedType", "label": "关联类型", "type": "select", "options": _opt("商品", "小说")},
            {"key": "jdProducts", "label": "关联商品", "type": "multiSelect"},
            {"key": "jdNovel", "label": "关联小说", "type": "input", "note": "小说名称，发布时自动搜索匹配"},
            {"key": "jdDeclaration", "label": "创作声明", "type": "select", "options": _opt(
                "含AI生成内容", "含虚构演绎内容", "内容为转载", "内容含营销广告", "内容无需标注")},
            {"key": "scheduleTime", "label": "定时发布", "type": "datetime", "placeholder": "yyyy-MM-dd HH:mm:ss"},
        ],
    },
    "dayu": {
        "name": "大鱼号",
        "creator_url": "https://mp.dayu.com/dashboard/index",
        "schedule": {"max_days": 7, "minute_step": 5},
        "fields": [
            {"key": "creationDeclaration", "label": "信息来源", "type": "select", "required": True, "options": _opt(
                "无需标注", "AI生成", "虚构演绎", "营销信息", "转载", "个人观点", "不适宜未成年人")},
            {"key": "dayuRepostUrl", "label": "原文链接", "type": "input", "required": True,
             "visible_when": {"key": "creationDeclaration", "value": "转载"}},
            {"key": "category", "label": "视频分类", "type": "select", "required": True, "options": _opt(
                "其他", "社会", "国内", "国际", "体育", "科技", "娱乐", "军事", "财经", "汽车", "房产",
                "时尚", "健康", "两性情感", "游戏", "动漫", "旅游", "美食", "历史", "奇闻", "科学探索",
                "星座", "育儿", "教育", "美女", "搞笑", "演讲", "萌娃", "萌宠", "音乐", "语言类",
                "记录短片", "涨姿势", "劲爆体育", "幽默", "综艺", "电视剧", "电影", "纪录片", "少儿",
                "文化", "三农", "生活方式")},
            {"key": "scheduleTime", "label": "定时发布", "type": "datetime", "placeholder": "yyyy-MM-dd HH:mm:ss",
             "note": "7 天内，5 分钟间隔（分钟需是 5 的倍数）"},
            {"key": "videoFormat", "label": "视频格式", "type": "radio", "options": _opt("landscape", "portrait")},
        ],
    },
}


# 各平台发布配置初始值（与 PublishCenter.vue DEFAULT_PLATFORM_CONFIGS 保持同步）
DEFAULT_CONFIGS: dict[str, dict] = {
    "douyin": {"title": "", "description": "", "tags": [], "aiContent": "", "isOriginal": False, "scheduleTime": "", "activityId": [], "hotspotId": "", "hotspotData": None, "selectedTag": None, "tagType": "", "tagValue": "", "mixId": "", "mixData": None},
    "xiaohongshu": {"title": "", "description": "", "aiContent": "", "isOriginal": False, "scheduleTime": "", "tags": [], "collectionId": "", "collectionName": "", "collectionData": None},
    "kuaishou": {"title": "", "description": "", "aiContent": "", "isOriginal": False, "scheduleTime": "", "tags": []},
    "bilibili": {"title": "", "description": "", "zone": "", "tags": [], "creationDeclaration": "", "biliRepostSource": "", "biliKeepSystemTags": True, "isOriginal": False, "scheduleTime": "", "biliCollectionName": "", "biliCollectionData": None},
    "channels": {"title": "", "description": "", "isOriginal": False, "scheduleTime": "", "tags": [], "channelsCollectionName": "", "channelsCollectionData": None, "channelsLocationName": "", "channelsLocationData": None, "channelsActivityName": "", "channelsActivityData": None, "channelsMarkTag": "无需标注", "channelsShootDate": "", "channelsShootRegion": [], "channelsRepostSource": "", "channelsDrama": [], "channelsLinkType": "", "channelsLinkArticleUrl": "", "channelsRedEnvelopeUrl": ""},
    "baijiahao": {"title": "", "description": "", "isOriginal": False, "scheduleTime": "", "tags": []},
    "tiktok": {"title": "", "description": "", "aiContent": False, "isOriginal": False, "scheduleTime": "", "tags": []},
    "youtube": {"title": "", "description": "", "audience": "not_kids", "alteredContent": False, "scheduleTime": "", "tags": []},
    "iqiyi": {"title": "", "description": "", "creationDeclaration": "", "riskWarning": "", "enableCashActivity": False, "scheduleTime": "", "tags": []},
    "tencent_video": {"title": "", "description": "", "creationDeclaration": [], "scheduleTime": "", "tags": []},
    "weibo": {"title": "", "description": "", "videoType": "", "weiboCategory": [], "contentStatement": "", "contentStatement2": "", "contentStatement2Optional": "", "tags": [], "weiboCollectionName": "", "weiboCollectionData": None},
    "alipay": {"title": "", "description": "", "authorStatement": "", "reprintUrl": "", "compilation": "", "scheduleTime": "", "tags": []},
    "toutiao": {"title": "", "description": "", "creationDeclaration": [], "enableGenerateImage": True, "collection": "", "extendLink": False, "extendLinkUrl": "", "scheduleTime": "", "tags": []},
    "zhihu": {"title": "", "description": "", "creationDeclaration": "内容无需标注", "category": "", "scheduleTime": "", "tags": []},
    "csdn": {"title": "", "description": "", "recommend": False, "scheduleTime": "", "tags": []},
    "vivo": {"title": "", "description": "", "vivoLocationName": "", "vivoLocationData": None,
             "vivoDistribution": False, "vivoDeclaration": "", "vivoPrivacy": "公开",
             "vivoDownloadPermission": "允许", "scheduleTime": "", "tags": []},
    "weixin_gzh": {"title": "", "description": "", "isOriginal": False, "gzhClaimSource": "", "gzhCollectionName": "", "gzhCollectionData": None, "scheduleTime": "", "tags": []},
    "taobao_guanghe": {"title": "", "description": "", "guangheClaim": "", "guangheLinkType": "", "guangheProducts": [], "guangheShops": [], "scheduleTime": "", "tags": []},
    "jingmai": {"title": "", "description": "", "jdRelatedType": "", "jdProducts": [], "jdNovel": "", "jdNovelData": None, "jdDeclaration": "", "scheduleTime": "", "tags": []},
    "dayu": {"title": "", "description": "", "creationDeclaration": "", "dayuRepostUrl": "", "category": "", "scheduleTime": "", "tags": []},
}


def get_platform_meta(platform_key: str) -> dict:
    """返回平台元数据（可变副本）。未知平台返回空 dict。"""
    meta = PLATFORM_META.get(platform_key)
    return dict(meta) if meta else {}


def build_platform_entry(platform_id: int, platform_key: str, platform_name: str) -> dict:
    """registry 枚举项 + 元数据 → /api/v2/platforms 单项。"""
    meta = PLATFORM_META.get(platform_key, {})
    default_config = DEFAULT_CONFIGS.get(platform_key) or dict(_MINIMAL_DEFAULT_CONFIG)
    return {
        "id": platform_id,
        "key": platform_key,
        "name": meta.get("name") or platform_name or platform_key,
        "creator_url": meta.get("creator_url", ""),
        "hide_fields": meta.get("hide_fields", []),
        "schedule": meta.get("schedule", {}),
        "note": meta.get("note", ""),
        "default_config": default_config,
        "fields": meta.get("fields", []),
    }
