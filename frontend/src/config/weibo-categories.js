/**
 * 微博视频分类(频道 → 子分类)树形数据,供 el-cascader 使用。
 *
 * 数据源: 微博 https://weibo.com/upload/channel 的 /ajax/contribution
 * 接口,2026-06-15 抓取。共 25 频道 / 255 子分类。
 *
 * 注意: value 是分类名称(字符串),后端会按 [channel_name, sub_name]
 * 查表换算成 channel_id / sub_channel_id。
 */

export const WEIBO_CATEGORIES = [
  {
    "value": "VLOG",
    "label": "VLOG",
    "children": [
      {
        "value": "旅行",
        "label": "旅行"
      },
      {
        "value": "美食",
        "label": "美食"
      },
      {
        "value": "时尚美妆",
        "label": "时尚美妆"
      },
      {
        "value": "评测",
        "label": "评测"
      },
      {
        "value": "日常",
        "label": "日常"
      },
      {
        "value": "运动",
        "label": "运动"
      },
      {
        "value": "探店看展",
        "label": "探店看展"
      }
    ]
  },
  {
    "value": "生活",
    "label": "生活",
    "children": [
      {
        "value": "日常",
        "label": "日常"
      },
      {
        "value": "校园",
        "label": "校园"
      },
      {
        "value": "健身",
        "label": "健身"
      },
      {
        "value": "运动",
        "label": "运动"
      },
      {
        "value": "星座命理",
        "label": "星座命理"
      },
      {
        "value": "极限运动",
        "label": "极限运动"
      },
      {
        "value": "家居设计",
        "label": "家居设计"
      },
      {
        "value": "手工",
        "label": "手工"
      },
      {
        "value": "公益",
        "label": "公益"
      },
      {
        "value": "生活百科",
        "label": "生活百科"
      },
      {
        "value": "健康医疗",
        "label": "健康医疗"
      },
      {
        "value": "健康养生",
        "label": "健康养生"
      },
      {
        "value": "少儿萌宝",
        "label": "少儿萌宝"
      },
      {
        "value": "母婴育儿",
        "label": "母婴育儿"
      },
      {
        "value": "交通出行",
        "label": "交通出行"
      },
      {
        "value": "航空",
        "label": "航空"
      },
      {
        "value": "职场",
        "label": "职场"
      },
      {
        "value": "情感",
        "label": "情感"
      },
      {
        "value": "美女帅哥",
        "label": "美女帅哥"
      },
      {
        "value": "正能量",
        "label": "正能量"
      },
      {
        "value": "卡点变装",
        "label": "卡点变装"
      },
      {
        "value": "相片记忆",
        "label": "相片记忆"
      },
      {
        "value": "摄影拍照",
        "label": "摄影拍照"
      }
    ]
  },
  {
    "value": "好物分享",
    "label": "好物分享",
    "children": [
      {
        "value": "数码测评",
        "label": "数码测评"
      },
      {
        "value": "美妆个护",
        "label": "美妆个护"
      },
      {
        "value": "穿搭必备",
        "label": "穿搭必备"
      },
      {
        "value": "居家好物",
        "label": "居家好物"
      },
      {
        "value": "美食测评",
        "label": "美食测评"
      },
      {
        "value": "购车攻略",
        "label": "购车攻略"
      },
      {
        "value": "潮玩手办",
        "label": "潮玩手办"
      },
      {
        "value": "文创好物",
        "label": "文创好物"
      },
      {
        "value": "运动装备",
        "label": "运动装备"
      },
      {
        "value": "母婴好物",
        "label": "母婴好物"
      },
      {
        "value": "万物测评",
        "label": "万物测评"
      }
    ]
  },
  {
    "value": "视频播客",
    "label": "视频播客",
    "children": [
      {
        "value": "视频播客",
        "label": "视频播客"
      }
    ]
  },
  {
    "value": "游戏",
    "label": "游戏",
    "children": [
      {
        "value": "崩坏星穹铁道",
        "label": "崩坏星穹铁道"
      },
      {
        "value": "开心消消乐",
        "label": "开心消消乐"
      },
      {
        "value": "无限暖暖",
        "label": "无限暖暖"
      },
      {
        "value": "DOTA2",
        "label": "DOTA2"
      },
      {
        "value": "恋与深空",
        "label": "恋与深空"
      },
      {
        "value": "原神",
        "label": "原神"
      },
      {
        "value": "超自然行动组",
        "label": "超自然行动组"
      },
      {
        "value": "英雄联盟",
        "label": "英雄联盟"
      },
      {
        "value": "王者荣耀",
        "label": "王者荣耀"
      },
      {
        "value": "王者荣耀世界",
        "label": "王者荣耀世界"
      },
      {
        "value": "王者万象棋",
        "label": "王者万象棋"
      },
      {
        "value": "和平精英",
        "label": "和平精英"
      },
      {
        "value": "第五人格",
        "label": "第五人格"
      },
      {
        "value": "阴阳师",
        "label": "阴阳师"
      },
      {
        "value": "光遇",
        "label": "光遇"
      },
      {
        "value": "如鸢",
        "label": "如鸢"
      },
      {
        "value": "光与夜之恋",
        "label": "光与夜之恋"
      },
      {
        "value": "黑神话悟空",
        "label": "黑神话悟空"
      },
      {
        "value": "竞技游戏",
        "label": "竞技游戏"
      },
      {
        "value": "女性向游戏",
        "label": "女性向游戏"
      },
      {
        "value": "射击类游戏",
        "label": "射击类游戏"
      },
      {
        "value": "休闲益智",
        "label": "休闲益智"
      },
      {
        "value": "二次元游戏",
        "label": "二次元游戏"
      },
      {
        "value": "主机游戏",
        "label": "主机游戏"
      },
      {
        "value": "游戏红人资讯",
        "label": "游戏红人资讯"
      },
      {
        "value": "游戏资讯",
        "label": "游戏资讯"
      },
      {
        "value": "游戏二创",
        "label": "游戏二创"
      },
      {
        "value": "游戏攻略",
        "label": "游戏攻略"
      }
    ]
  },
  {
    "value": "电竞",
    "label": "电竞",
    "children": [
      {
        "value": "电竞赛事",
        "label": "电竞赛事"
      },
      {
        "value": "战队选手",
        "label": "战队选手"
      },
      {
        "value": "电竞衍生",
        "label": "电竞衍生"
      }
    ]
  },
  {
    "value": "知识",
    "label": "知识",
    "children": [
      {
        "value": "公开课",
        "label": "公开课"
      },
      {
        "value": "学习教程",
        "label": "学习教程"
      },
      {
        "value": "语言学习",
        "label": "语言学习"
      },
      {
        "value": "科学科普",
        "label": "科学科普"
      },
      {
        "value": "亲子育儿",
        "label": "亲子育儿"
      },
      {
        "value": "财经",
        "label": "财经"
      },
      {
        "value": "法律",
        "label": "法律"
      },
      {
        "value": "读书",
        "label": "读书"
      },
      {
        "value": "军事",
        "label": "军事"
      },
      {
        "value": "房地产",
        "label": "房地产"
      },
      {
        "value": "三农",
        "label": "三农"
      },
      {
        "value": "互联网",
        "label": "互联网"
      },
      {
        "value": "教育",
        "label": "教育"
      }
    ]
  },
  {
    "value": "美食",
    "label": "美食",
    "children": [
      {
        "value": "真香现场",
        "label": "真香现场"
      },
      {
        "value": "美食侦探",
        "label": "美食侦探"
      },
      {
        "value": "烹饪教程",
        "label": "烹饪教程"
      },
      {
        "value": "测评种草",
        "label": "测评种草"
      }
    ]
  },
  {
    "value": "娱乐明星",
    "label": "娱乐明星",
    "children": [
      {
        "value": "明星日常",
        "label": "明星日常"
      },
      {
        "value": "明星资讯",
        "label": "明星资讯"
      },
      {
        "value": "粉丝剪辑",
        "label": "粉丝剪辑"
      },
      {
        "value": "明星直拍",
        "label": "明星直拍"
      },
      {
        "value": "娱乐趣闻",
        "label": "娱乐趣闻"
      },
      {
        "value": "粉丝应援",
        "label": "粉丝应援"
      },
      {
        "value": "明星资讯",
        "label": "明星资讯"
      },
      {
        "value": "明星路透",
        "label": "明星路透"
      },
      {
        "value": "明星饭拍",
        "label": "明星饭拍"
      },
      {
        "value": "采访花絮",
        "label": "采访花絮"
      },
      {
        "value": "发布会",
        "label": "发布会"
      },
      {
        "value": "明星饭拍",
        "label": "明星饭拍"
      },
      {
        "value": "媒体专访",
        "label": "媒体专访"
      },
      {
        "value": "日娱",
        "label": "日娱"
      },
      {
        "value": "韩娱",
        "label": "韩娱"
      },
      {
        "value": "泰娱",
        "label": "泰娱"
      },
      {
        "value": "娱乐综合",
        "label": "娱乐综合"
      }
    ]
  },
  {
    "value": "搞笑幽默",
    "label": "搞笑幽默",
    "children": [
      {
        "value": "生活趣事",
        "label": "生活趣事"
      },
      {
        "value": "爆笑吐槽",
        "label": "爆笑吐槽"
      },
      {
        "value": "搞笑演绎",
        "label": "搞笑演绎"
      },
      {
        "value": "搞笑动漫",
        "label": "搞笑动漫"
      },
      {
        "value": "二创剪辑",
        "label": "二创剪辑"
      },
      {
        "value": "外国人系列",
        "label": "外国人系列"
      },
      {
        "value": "搞笑配音",
        "label": "搞笑配音"
      },
      {
        "value": "热点热梗",
        "label": "热点热梗"
      },
      {
        "value": "新闻趣事",
        "label": "新闻趣事"
      },
      {
        "value": "搞笑评测",
        "label": "搞笑评测"
      },
      {
        "value": "萌娃趣事",
        "label": "萌娃趣事"
      },
      {
        "value": "动物奇趣",
        "label": "动物奇趣"
      },
      {
        "value": "奇葩猎奇",
        "label": "奇葩猎奇"
      },
      {
        "value": "喜剧演出",
        "label": "喜剧演出"
      },
      {
        "value": "喜剧综艺",
        "label": "喜剧综艺"
      },
      {
        "value": "喜剧剧情",
        "label": "喜剧剧情"
      },
      {
        "value": "搞笑神评",
        "label": "搞笑神评"
      },
      {
        "value": "搞笑冷知识",
        "label": "搞笑冷知识"
      },
      {
        "value": "爆笑整蛊",
        "label": "爆笑整蛊"
      }
    ]
  },
  {
    "value": "美妆",
    "label": "美妆",
    "children": [
      {
        "value": "美妆教程",
        "label": "美妆教程"
      },
      {
        "value": "日常护肤",
        "label": "日常护肤"
      },
      {
        "value": "种草拔草",
        "label": "种草拔草"
      },
      {
        "value": "产品测评",
        "label": "产品测评"
      },
      {
        "value": "妆容点评",
        "label": "妆容点评"
      },
      {
        "value": "购物开箱",
        "label": "购物开箱"
      },
      {
        "value": "美容综合",
        "label": "美容综合"
      }
    ]
  },
  {
    "value": "时尚",
    "label": "时尚",
    "children": [
      {
        "value": "每日穿搭",
        "label": "每日穿搭"
      },
      {
        "value": "时尚秀场",
        "label": "时尚秀场"
      },
      {
        "value": "时尚买手",
        "label": "时尚买手"
      },
      {
        "value": "测评分享",
        "label": "测评分享"
      },
      {
        "value": "时尚资讯",
        "label": "时尚资讯"
      },
      {
        "value": "明星时尚",
        "label": "明星时尚"
      }
    ]
  },
  {
    "value": "综艺",
    "label": "综艺",
    "children": [
      {
        "value": "综艺资讯",
        "label": "综艺资讯"
      },
      {
        "value": "综艺剪辑",
        "label": "综艺剪辑"
      },
      {
        "value": "综艺路透",
        "label": "综艺路透"
      },
      {
        "value": "海外综艺",
        "label": "海外综艺"
      },
      {
        "value": "综艺解说",
        "label": "综艺解说"
      }
    ]
  },
  {
    "value": "动漫",
    "label": "动漫",
    "children": [
      {
        "value": "动画短片",
        "label": "动画短片"
      },
      {
        "value": "动画配音",
        "label": "动画配音"
      },
      {
        "value": "国创番剧",
        "label": "国创番剧"
      },
      {
        "value": "手办绘画",
        "label": "手办绘画"
      },
      {
        "value": "MMD",
        "label": "MMD"
      },
      {
        "value": "动漫PV",
        "label": "动漫PV"
      },
      {
        "value": "二次元装扮",
        "label": "二次元装扮"
      },
      {
        "value": "动漫综合",
        "label": "动漫综合"
      }
    ]
  },
  {
    "value": "体育",
    "label": "体育",
    "children": [
      {
        "value": "NBA",
        "label": "NBA"
      },
      {
        "value": "CBA",
        "label": "CBA"
      },
      {
        "value": "中超",
        "label": "中超"
      },
      {
        "value": "西甲",
        "label": "西甲"
      },
      {
        "value": "英超",
        "label": "英超"
      },
      {
        "value": "欧冠",
        "label": "欧冠"
      },
      {
        "value": "中国足球",
        "label": "中国足球"
      },
      {
        "value": "运动教学",
        "label": "运动教学"
      },
      {
        "value": "运动装备",
        "label": "运动装备"
      },
      {
        "value": "爆笑体育",
        "label": "爆笑体育"
      },
      {
        "value": "中国篮球",
        "label": "中国篮球"
      },
      {
        "value": "国际足球",
        "label": "国际足球"
      },
      {
        "value": "体育综合",
        "label": "体育综合"
      },
      {
        "value": "极限户外",
        "label": "极限户外"
      },
      {
        "value": "潮流运动",
        "label": "潮流运动"
      },
      {
        "value": "户外运动",
        "label": "户外运动"
      }
    ]
  },
  {
    "value": "音乐演出",
    "label": "音乐演出",
    "children": [
      {
        "value": "原创音乐",
        "label": "原创音乐"
      },
      {
        "value": "音乐现场",
        "label": "音乐现场"
      },
      {
        "value": "混剪二创",
        "label": "混剪二创"
      },
      {
        "value": "音乐资讯",
        "label": "音乐资讯"
      },
      {
        "value": "翻唱",
        "label": "翻唱"
      },
      {
        "value": "演奏",
        "label": "演奏"
      },
      {
        "value": "乐评盘点",
        "label": "乐评盘点"
      },
      {
        "value": "MV",
        "label": "MV"
      },
      {
        "value": "粉丝饭拍",
        "label": "粉丝饭拍"
      },
      {
        "value": "AI音乐",
        "label": "AI音乐"
      },
      {
        "value": "电台",
        "label": "电台"
      },
      {
        "value": "音乐教学",
        "label": "音乐教学"
      },
      {
        "value": "音乐综合",
        "label": "音乐综合"
      },
      {
        "value": "戏剧",
        "label": "戏剧"
      }
    ]
  },
  {
    "value": "电影",
    "label": "电影",
    "children": [
      {
        "value": "电影剪辑",
        "label": "电影剪辑"
      },
      {
        "value": "电影解说",
        "label": "电影解说"
      },
      {
        "value": "电影资讯",
        "label": "电影资讯"
      },
      {
        "value": "电影花絮",
        "label": "电影花絮"
      },
      {
        "value": "国产电影",
        "label": "国产电影"
      },
      {
        "value": "海外电影",
        "label": "海外电影"
      },
      {
        "value": "电影题材",
        "label": "电影题材"
      },
      {
        "value": "电影短片",
        "label": "电影短片"
      },
      {
        "value": "电影点评",
        "label": "电影点评"
      },
      {
        "value": "电影综合",
        "label": "电影综合"
      }
    ]
  },
  {
    "value": "电视剧",
    "label": "电视剧",
    "children": [
      {
        "value": "电视剧片段",
        "label": "电视剧片段"
      },
      {
        "value": "电视剧剪辑",
        "label": "电视剧剪辑"
      },
      {
        "value": "电视剧解说",
        "label": "电视剧解说"
      },
      {
        "value": "电视剧资讯",
        "label": "电视剧资讯"
      },
      {
        "value": "电视剧花絮",
        "label": "电视剧花絮"
      },
      {
        "value": "海外剧集",
        "label": "海外剧集"
      },
      {
        "value": "原创短剧/短片",
        "label": "原创短剧/短片"
      },
      {
        "value": "电视剧综合",
        "label": "电视剧综合"
      }
    ]
  },
  {
    "value": "人文艺术",
    "label": "人文艺术",
    "children": [
      {
        "value": "手绘",
        "label": "手绘"
      },
      {
        "value": "手写",
        "label": "手写"
      },
      {
        "value": "手工艺",
        "label": "手工艺"
      },
      {
        "value": "文化",
        "label": "文化"
      },
      {
        "value": "历史",
        "label": "历史"
      },
      {
        "value": "文学",
        "label": "文学"
      },
      {
        "value": "艺术",
        "label": "艺术"
      },
      {
        "value": "哲学",
        "label": "哲学"
      },
      {
        "value": "非遗",
        "label": "非遗"
      },
      {
        "value": "人文综合",
        "label": "人文综合"
      }
    ]
  },
  {
    "value": "旅游",
    "label": "旅游",
    "children": [
      {
        "value": "旅行攻略",
        "label": "旅行攻略"
      },
      {
        "value": "旅行种草",
        "label": "旅行种草"
      },
      {
        "value": "风景旅拍",
        "label": "风景旅拍"
      },
      {
        "value": "城市探索",
        "label": "城市探索"
      },
      {
        "value": "旅游综合",
        "label": "旅游综合"
      }
    ]
  },
  {
    "value": "科技数码",
    "label": "科技数码",
    "children": [
      {
        "value": "评测开箱",
        "label": "评测开箱"
      },
      {
        "value": "手机平板",
        "label": "手机平板"
      },
      {
        "value": "电脑装机",
        "label": "电脑装机"
      },
      {
        "value": "摄影摄像",
        "label": "摄影摄像"
      },
      {
        "value": "影音智能",
        "label": "影音智能"
      },
      {
        "value": "科技",
        "label": "科技"
      },
      {
        "value": "数码综合",
        "label": "数码综合"
      }
    ]
  },
  {
    "value": "汽车",
    "label": "汽车",
    "children": [
      {
        "value": "汽车评测",
        "label": "汽车评测"
      },
      {
        "value": "二手车",
        "label": "二手车"
      },
      {
        "value": "新车上市",
        "label": "新车上市"
      },
      {
        "value": "越野自驾",
        "label": "越野自驾"
      },
      {
        "value": "新能源汽车",
        "label": "新能源汽车"
      },
      {
        "value": "改装",
        "label": "改装"
      },
      {
        "value": "摩托车",
        "label": "摩托车"
      },
      {
        "value": "汽车综合",
        "label": "汽车综合"
      }
    ]
  },
  {
    "value": "舞蹈",
    "label": "舞蹈",
    "children": [
      {
        "value": "街舞",
        "label": "街舞"
      },
      {
        "value": "中国舞",
        "label": "中国舞"
      },
      {
        "value": "现代舞",
        "label": "现代舞"
      },
      {
        "value": "芭蕾",
        "label": "芭蕾"
      },
      {
        "value": "爵士舞",
        "label": "爵士舞"
      },
      {
        "value": "国标舞",
        "label": "国标舞"
      },
      {
        "value": "宅舞",
        "label": "宅舞"
      },
      {
        "value": "广场舞",
        "label": "广场舞"
      },
      {
        "value": "少儿舞蹈",
        "label": "少儿舞蹈"
      },
      {
        "value": "舞蹈教程",
        "label": "舞蹈教程"
      },
      {
        "value": "舞蹈综合",
        "label": "舞蹈综合"
      }
    ]
  },
  {
    "value": "社会资讯",
    "label": "社会资讯",
    "children": [
      {
        "value": "正能量",
        "label": "正能量"
      },
      {
        "value": "深度报道",
        "label": "深度报道"
      },
      {
        "value": "时事评论",
        "label": "时事评论"
      },
      {
        "value": "奇闻轶事",
        "label": "奇闻轶事"
      },
      {
        "value": "当事人发声",
        "label": "当事人发声"
      },
      {
        "value": "社会综合",
        "label": "社会综合"
      }
    ]
  },
  {
    "value": "纪录片",
    "label": "纪录片",
    "children": [
      {
        "value": "美食",
        "label": "美食"
      },
      {
        "value": "自然",
        "label": "自然"
      },
      {
        "value": "社会",
        "label": "社会"
      },
      {
        "value": "科普",
        "label": "科普"
      },
      {
        "value": "历史",
        "label": "历史"
      },
      {
        "value": "军事",
        "label": "军事"
      },
      {
        "value": "探险",
        "label": "探险"
      },
      {
        "value": "纪录片综合",
        "label": "纪录片综合"
      }
    ]
  }
]
