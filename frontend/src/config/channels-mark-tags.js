/**
 * 视频号「视频标注」静态数据源
 *
 * 数据来自视频号创作者平台返回的标注配置(2026-07-17 抓取):
 *   - 7 个标注选项(tagType: 0/1/3/8/2/5/7)
 *   - 「内容为自行拍摄」(tagType=5) 自带 国家->省->市 三级树,
 *     共 240 个国家, 仅「中国」有 34 省 / 361 市, 其余 239 国为叶子节点。
 *   - 「内容为转载」(tagType=7) regionInfos 为空, 转载来源由用户输入。
 *
 * cascader value 用【中文文本】而非 code:
 *   后端 Playwright 按文本在视频号级联菜单(.weui-desktop-dropdown__list-ele__text)
 *   逐级匹配点击, code 在页面 DOM 里不存在, 必须用文本才能选中。
 *
 * 注意: 视频号所有标注选项(含「无需标注」)在发布时都会去页面下拉里
 * 真正选中对应项, 不因默认值跳过。
 */

export const CHANNELS_MARK_TAGS = [
  {
    "tagType": 0,
    "tagName": "无需标注",
    "needShootInfo": false,
    "needRepostSource": false
  },
  {
    "tagType": 1,
    "tagName": "含AI生成内容",
    "needShootInfo": false,
    "needRepostSource": false
  },
  {
    "tagType": 3,
    "tagName": "内容为虚构剧情，仅供娱乐",
    "needShootInfo": false,
    "needRepostSource": false
  },
  {
    "tagType": 8,
    "tagName": "个人观点，仅供参考",
    "needShootInfo": false,
    "needRepostSource": false
  },
  {
    "tagType": 2,
    "tagName": "内容包含营销广告",
    "needShootInfo": false,
    "needRepostSource": false
  },
  {
    "tagType": 5,
    "tagName": "内容为自行拍摄",
    "needShootInfo": true,
    "needRepostSource": false
  },
  {
    "tagType": 7,
    "tagName": "内容为转载",
    "needShootInfo": false,
    "needRepostSource": true
  }
]

// 自行拍摄拍摄地点级联树(el-cascader 格式): 国家 -> 省 -> 市
// value 为中文文本(后端按文本匹配视频号页面), 叶子国家只选到国家级即止。
export const CHANNELS_SHOOT_REGIONS = [
  {
    "value": "中国",
    "label": "中国",
    "leaf": false,
    "children": [
      {
        "value": "安徽",
        "label": "安徽",
        "leaf": false,
        "children": [
          {
            "value": "安庆",
            "label": "安庆",
            "leaf": true
          },
          {
            "value": "蚌埠",
            "label": "蚌埠",
            "leaf": true
          },
          {
            "value": "亳州",
            "label": "亳州",
            "leaf": true
          },
          {
            "value": "巢湖",
            "label": "巢湖",
            "leaf": true
          },
          {
            "value": "池州",
            "label": "池州",
            "leaf": true
          },
          {
            "value": "滁州",
            "label": "滁州",
            "leaf": true
          },
          {
            "value": "阜阳",
            "label": "阜阳",
            "leaf": true
          },
          {
            "value": "合肥",
            "label": "合肥",
            "leaf": true
          },
          {
            "value": "淮北",
            "label": "淮北",
            "leaf": true
          },
          {
            "value": "淮南",
            "label": "淮南",
            "leaf": true
          },
          {
            "value": "黄山",
            "label": "黄山",
            "leaf": true
          },
          {
            "value": "六安",
            "label": "六安",
            "leaf": true
          },
          {
            "value": "马鞍山",
            "label": "马鞍山",
            "leaf": true
          },
          {
            "value": "宿州",
            "label": "宿州",
            "leaf": true
          },
          {
            "value": "铜陵",
            "label": "铜陵",
            "leaf": true
          },
          {
            "value": "芜湖",
            "label": "芜湖",
            "leaf": true
          },
          {
            "value": "宣城",
            "label": "宣城",
            "leaf": true
          }
        ]
      },
      {
        "value": "北京",
        "label": "北京",
        "leaf": true
      },
      {
        "value": "重庆",
        "label": "重庆",
        "leaf": true
      },
      {
        "value": "福建",
        "label": "福建",
        "leaf": false,
        "children": [
          {
            "value": "福州",
            "label": "福州",
            "leaf": true
          },
          {
            "value": "龙岩",
            "label": "龙岩",
            "leaf": true
          },
          {
            "value": "南平",
            "label": "南平",
            "leaf": true
          },
          {
            "value": "宁德",
            "label": "宁德",
            "leaf": true
          },
          {
            "value": "莆田",
            "label": "莆田",
            "leaf": true
          },
          {
            "value": "泉州",
            "label": "泉州",
            "leaf": true
          },
          {
            "value": "三明",
            "label": "三明",
            "leaf": true
          },
          {
            "value": "厦门",
            "label": "厦门",
            "leaf": true
          },
          {
            "value": "漳州",
            "label": "漳州",
            "leaf": true
          }
        ]
      },
      {
        "value": "甘肃",
        "label": "甘肃",
        "leaf": false,
        "children": [
          {
            "value": "定西",
            "label": "定西",
            "leaf": true
          },
          {
            "value": "甘南",
            "label": "甘南",
            "leaf": true
          },
          {
            "value": "嘉峪关",
            "label": "嘉峪关",
            "leaf": true
          },
          {
            "value": "金昌",
            "label": "金昌",
            "leaf": true
          },
          {
            "value": "酒泉",
            "label": "酒泉",
            "leaf": true
          },
          {
            "value": "兰州市",
            "label": "兰州市",
            "leaf": true
          },
          {
            "value": "临夏",
            "label": "临夏",
            "leaf": true
          },
          {
            "value": "陇南",
            "label": "陇南",
            "leaf": true
          },
          {
            "value": "平凉",
            "label": "平凉",
            "leaf": true
          },
          {
            "value": "庆阳",
            "label": "庆阳",
            "leaf": true
          },
          {
            "value": "白银",
            "label": "白银",
            "leaf": true
          },
          {
            "value": "天水",
            "label": "天水",
            "leaf": true
          },
          {
            "value": "武威",
            "label": "武威",
            "leaf": true
          },
          {
            "value": "张掖",
            "label": "张掖",
            "leaf": true
          }
        ]
      },
      {
        "value": "广东",
        "label": "广东",
        "leaf": false,
        "children": [
          {
            "value": "潮州",
            "label": "潮州",
            "leaf": true
          },
          {
            "value": "东莞",
            "label": "东莞",
            "leaf": true
          },
          {
            "value": "佛山",
            "label": "佛山",
            "leaf": true
          },
          {
            "value": "广州",
            "label": "广州",
            "leaf": true
          },
          {
            "value": "河源",
            "label": "河源",
            "leaf": true
          },
          {
            "value": "惠州",
            "label": "惠州",
            "leaf": true
          },
          {
            "value": "江门",
            "label": "江门",
            "leaf": true
          },
          {
            "value": "揭阳",
            "label": "揭阳",
            "leaf": true
          },
          {
            "value": "茂名",
            "label": "茂名",
            "leaf": true
          },
          {
            "value": "梅州",
            "label": "梅州",
            "leaf": true
          },
          {
            "value": "清远",
            "label": "清远",
            "leaf": true
          },
          {
            "value": "汕头",
            "label": "汕头",
            "leaf": true
          },
          {
            "value": "汕尾",
            "label": "汕尾",
            "leaf": true
          },
          {
            "value": "韶关",
            "label": "韶关",
            "leaf": true
          },
          {
            "value": "深圳",
            "label": "深圳",
            "leaf": true
          },
          {
            "value": "阳江",
            "label": "阳江",
            "leaf": true
          },
          {
            "value": "云浮",
            "label": "云浮",
            "leaf": true
          },
          {
            "value": "湛江",
            "label": "湛江",
            "leaf": true
          },
          {
            "value": "肇庆",
            "label": "肇庆",
            "leaf": true
          },
          {
            "value": "中山",
            "label": "中山",
            "leaf": true
          },
          {
            "value": "珠海",
            "label": "珠海",
            "leaf": true
          }
        ]
      },
      {
        "value": "广西",
        "label": "广西",
        "leaf": false,
        "children": [
          {
            "value": "百色",
            "label": "百色",
            "leaf": true
          },
          {
            "value": "北海",
            "label": "北海",
            "leaf": true
          },
          {
            "value": "崇左",
            "label": "崇左",
            "leaf": true
          },
          {
            "value": "钦州",
            "label": "钦州",
            "leaf": true
          },
          {
            "value": "防城港",
            "label": "防城港",
            "leaf": true
          },
          {
            "value": "来宾",
            "label": "来宾",
            "leaf": true
          },
          {
            "value": "贵港",
            "label": "贵港",
            "leaf": true
          },
          {
            "value": "桂林",
            "label": "桂林",
            "leaf": true
          },
          {
            "value": "河池",
            "label": "河池",
            "leaf": true
          },
          {
            "value": "贺州",
            "label": "贺州",
            "leaf": true
          },
          {
            "value": "柳州",
            "label": "柳州",
            "leaf": true
          },
          {
            "value": "南宁",
            "label": "南宁",
            "leaf": true
          },
          {
            "value": "梧州",
            "label": "梧州",
            "leaf": true
          },
          {
            "value": "玉林",
            "label": "玉林",
            "leaf": true
          }
        ]
      },
      {
        "value": "贵州",
        "label": "贵州",
        "leaf": false,
        "children": [
          {
            "value": "安顺",
            "label": "安顺",
            "leaf": true
          },
          {
            "value": "毕节",
            "label": "毕节",
            "leaf": true
          },
          {
            "value": "贵阳",
            "label": "贵阳",
            "leaf": true
          },
          {
            "value": "遵义",
            "label": "遵义",
            "leaf": true
          },
          {
            "value": "六盘水",
            "label": "六盘水",
            "leaf": true
          },
          {
            "value": "黔东南",
            "label": "黔东南",
            "leaf": true
          },
          {
            "value": "黔南",
            "label": "黔南",
            "leaf": true
          },
          {
            "value": "黔西南",
            "label": "黔西南",
            "leaf": true
          },
          {
            "value": "铜仁",
            "label": "铜仁",
            "leaf": true
          }
        ]
      },
      {
        "value": "海南",
        "label": "海南",
        "leaf": false,
        "children": [
          {
            "value": "保亭",
            "label": "保亭",
            "leaf": true
          },
          {
            "value": "昌江",
            "label": "昌江",
            "leaf": true
          },
          {
            "value": "澄迈",
            "label": "澄迈",
            "leaf": true
          },
          {
            "value": "儋州",
            "label": "儋州",
            "leaf": true
          },
          {
            "value": "东方",
            "label": "东方",
            "leaf": true
          },
          {
            "value": "五指山",
            "label": "五指山",
            "leaf": true
          },
          {
            "value": "海口",
            "label": "海口",
            "leaf": true
          },
          {
            "value": "定安",
            "label": "定安",
            "leaf": true
          },
          {
            "value": "中沙",
            "label": "中沙",
            "leaf": true
          },
          {
            "value": "陵水",
            "label": "陵水",
            "leaf": true
          },
          {
            "value": "万宁",
            "label": "万宁",
            "leaf": true
          },
          {
            "value": "乐东",
            "label": "乐东",
            "leaf": true
          },
          {
            "value": "南沙",
            "label": "南沙",
            "leaf": true
          },
          {
            "value": "临高",
            "label": "临高",
            "leaf": true
          },
          {
            "value": "琼海",
            "label": "琼海",
            "leaf": true
          },
          {
            "value": "琼中",
            "label": "琼中",
            "leaf": true
          },
          {
            "value": "三亚",
            "label": "三亚",
            "leaf": true
          },
          {
            "value": "屯昌",
            "label": "屯昌",
            "leaf": true
          },
          {
            "value": "文昌",
            "label": "文昌",
            "leaf": true
          },
          {
            "value": "白沙",
            "label": "白沙",
            "leaf": true
          },
          {
            "value": "西沙",
            "label": "西沙",
            "leaf": true
          }
        ]
      },
      {
        "value": "河北",
        "label": "河北",
        "leaf": false,
        "children": [
          {
            "value": "保定",
            "label": "保定",
            "leaf": true
          },
          {
            "value": "沧州",
            "label": "沧州",
            "leaf": true
          },
          {
            "value": "承德",
            "label": "承德",
            "leaf": true
          },
          {
            "value": "邯郸",
            "label": "邯郸",
            "leaf": true
          },
          {
            "value": "衡水",
            "label": "衡水",
            "leaf": true
          },
          {
            "value": "廊坊",
            "label": "廊坊",
            "leaf": true
          },
          {
            "value": "秦皇岛",
            "label": "秦皇岛",
            "leaf": true
          },
          {
            "value": "石家庄",
            "label": "石家庄",
            "leaf": true
          },
          {
            "value": "唐山",
            "label": "唐山",
            "leaf": true
          },
          {
            "value": "邢台",
            "label": "邢台",
            "leaf": true
          },
          {
            "value": "张家口",
            "label": "张家口",
            "leaf": true
          }
        ]
      },
      {
        "value": "河南",
        "label": "河南",
        "leaf": false,
        "children": [
          {
            "value": "安阳",
            "label": "安阳",
            "leaf": true
          },
          {
            "value": "鹤壁",
            "label": "鹤壁",
            "leaf": true
          },
          {
            "value": "焦作",
            "label": "焦作",
            "leaf": true
          },
          {
            "value": "济源",
            "label": "济源",
            "leaf": true
          },
          {
            "value": "开封",
            "label": "开封",
            "leaf": true
          },
          {
            "value": "漯河",
            "label": "漯河",
            "leaf": true
          },
          {
            "value": "洛阳",
            "label": "洛阳",
            "leaf": true
          },
          {
            "value": "平顶山",
            "label": "平顶山",
            "leaf": true
          },
          {
            "value": "南阳",
            "label": "南阳",
            "leaf": true
          },
          {
            "value": "濮阳",
            "label": "濮阳",
            "leaf": true
          },
          {
            "value": "三门峡",
            "label": "三门峡",
            "leaf": true
          },
          {
            "value": "商丘",
            "label": "商丘",
            "leaf": true
          },
          {
            "value": "新乡",
            "label": "新乡",
            "leaf": true
          },
          {
            "value": "信阳",
            "label": "信阳",
            "leaf": true
          },
          {
            "value": "许昌",
            "label": "许昌",
            "leaf": true
          },
          {
            "value": "郑州",
            "label": "郑州",
            "leaf": true
          },
          {
            "value": "周口",
            "label": "周口",
            "leaf": true
          },
          {
            "value": "驻马店",
            "label": "驻马店",
            "leaf": true
          }
        ]
      },
      {
        "value": "黑龙江",
        "label": "黑龙江",
        "leaf": false,
        "children": [
          {
            "value": "大庆",
            "label": "大庆",
            "leaf": true
          },
          {
            "value": "哈尔滨",
            "label": "哈尔滨",
            "leaf": true
          },
          {
            "value": "鹤岗",
            "label": "鹤岗",
            "leaf": true
          },
          {
            "value": "黑河",
            "label": "黑河",
            "leaf": true
          },
          {
            "value": "佳木斯",
            "label": "佳木斯",
            "leaf": true
          },
          {
            "value": "鸡西",
            "label": "鸡西",
            "leaf": true
          },
          {
            "value": "大兴安岭",
            "label": "大兴安岭",
            "leaf": true
          },
          {
            "value": "牡丹江",
            "label": "牡丹江",
            "leaf": true
          },
          {
            "value": "齐齐哈尔",
            "label": "齐齐哈尔",
            "leaf": true
          },
          {
            "value": "七台河",
            "label": "七台河",
            "leaf": true
          },
          {
            "value": "双鸭山",
            "label": "双鸭山",
            "leaf": true
          },
          {
            "value": "绥化",
            "label": "绥化",
            "leaf": true
          },
          {
            "value": "伊春",
            "label": "伊春",
            "leaf": true
          }
        ]
      },
      {
        "value": "湖北",
        "label": "湖北",
        "leaf": false,
        "children": [
          {
            "value": "仙桃",
            "label": "仙桃",
            "leaf": true
          },
          {
            "value": "恩施",
            "label": "恩施",
            "leaf": true
          },
          {
            "value": "鄂州",
            "label": "鄂州",
            "leaf": true
          },
          {
            "value": "黄冈",
            "label": "黄冈",
            "leaf": true
          },
          {
            "value": "荆门",
            "label": "荆门",
            "leaf": true
          },
          {
            "value": "荆州",
            "label": "荆州",
            "leaf": true
          },
          {
            "value": "潜江",
            "label": "潜江",
            "leaf": true
          },
          {
            "value": "神农架",
            "label": "神农架",
            "leaf": true
          },
          {
            "value": "十堰",
            "label": "十堰",
            "leaf": true
          },
          {
            "value": "随州",
            "label": "随州",
            "leaf": true
          },
          {
            "value": "天门",
            "label": "天门",
            "leaf": true
          },
          {
            "value": "武汉",
            "label": "武汉",
            "leaf": true
          },
          {
            "value": "咸宁",
            "label": "咸宁",
            "leaf": true
          },
          {
            "value": "孝感",
            "label": "孝感",
            "leaf": true
          },
          {
            "value": "襄阳",
            "label": "襄阳",
            "leaf": true
          },
          {
            "value": "黄石",
            "label": "黄石",
            "leaf": true
          },
          {
            "value": "宜昌",
            "label": "宜昌",
            "leaf": true
          }
        ]
      },
      {
        "value": "湖南",
        "label": "湖南",
        "leaf": false,
        "children": [
          {
            "value": "常德",
            "label": "常德",
            "leaf": true
          },
          {
            "value": "长沙",
            "label": "长沙",
            "leaf": true
          },
          {
            "value": "郴州",
            "label": "郴州",
            "leaf": true
          },
          {
            "value": "衡阳",
            "label": "衡阳",
            "leaf": true
          },
          {
            "value": "怀化",
            "label": "怀化",
            "leaf": true
          },
          {
            "value": "娄底",
            "label": "娄底",
            "leaf": true
          },
          {
            "value": "邵阳",
            "label": "邵阳",
            "leaf": true
          },
          {
            "value": "湘潭",
            "label": "湘潭",
            "leaf": true
          },
          {
            "value": "湘西",
            "label": "湘西",
            "leaf": true
          },
          {
            "value": "益阳",
            "label": "益阳",
            "leaf": true
          },
          {
            "value": "永州",
            "label": "永州",
            "leaf": true
          },
          {
            "value": "岳阳",
            "label": "岳阳",
            "leaf": true
          },
          {
            "value": "张家界",
            "label": "张家界",
            "leaf": true
          },
          {
            "value": "株洲",
            "label": "株洲",
            "leaf": true
          }
        ]
      },
      {
        "value": "吉林",
        "label": "吉林",
        "leaf": false,
        "children": [
          {
            "value": "长春",
            "label": "长春",
            "leaf": true
          },
          {
            "value": "吉林",
            "label": "吉林",
            "leaf": true
          },
          {
            "value": "辽源",
            "label": "辽源",
            "leaf": true
          },
          {
            "value": "松原",
            "label": "松原",
            "leaf": true
          },
          {
            "value": "四平",
            "label": "四平",
            "leaf": true
          },
          {
            "value": "通化",
            "label": "通化",
            "leaf": true
          },
          {
            "value": "白城",
            "label": "白城",
            "leaf": true
          },
          {
            "value": "白山",
            "label": "白山",
            "leaf": true
          },
          {
            "value": "延边",
            "label": "延边",
            "leaf": true
          }
        ]
      },
      {
        "value": "江苏",
        "label": "江苏",
        "leaf": false,
        "children": [
          {
            "value": "常州",
            "label": "常州",
            "leaf": true
          },
          {
            "value": "淮安",
            "label": "淮安",
            "leaf": true
          },
          {
            "value": "连云港",
            "label": "连云港",
            "leaf": true
          },
          {
            "value": "南京",
            "label": "南京",
            "leaf": true
          },
          {
            "value": "南通",
            "label": "南通",
            "leaf": true
          },
          {
            "value": "宿迁",
            "label": "宿迁",
            "leaf": true
          },
          {
            "value": "苏州",
            "label": "苏州",
            "leaf": true
          },
          {
            "value": "泰州",
            "label": "泰州",
            "leaf": true
          },
          {
            "value": "无锡",
            "label": "无锡",
            "leaf": true
          },
          {
            "value": "徐州",
            "label": "徐州",
            "leaf": true
          },
          {
            "value": "盐城",
            "label": "盐城",
            "leaf": true
          },
          {
            "value": "扬州",
            "label": "扬州",
            "leaf": true
          },
          {
            "value": "镇江",
            "label": "镇江",
            "leaf": true
          }
        ]
      },
      {
        "value": "江西",
        "label": "江西",
        "leaf": false,
        "children": [
          {
            "value": "抚州",
            "label": "抚州",
            "leaf": true
          },
          {
            "value": "赣州",
            "label": "赣州",
            "leaf": true
          },
          {
            "value": "吉安",
            "label": "吉安",
            "leaf": true
          },
          {
            "value": "景德镇",
            "label": "景德镇",
            "leaf": true
          },
          {
            "value": "九江",
            "label": "九江",
            "leaf": true
          },
          {
            "value": "南昌",
            "label": "南昌",
            "leaf": true
          },
          {
            "value": "萍乡",
            "label": "萍乡",
            "leaf": true
          },
          {
            "value": "上饶",
            "label": "上饶",
            "leaf": true
          },
          {
            "value": "新余",
            "label": "新余",
            "leaf": true
          },
          {
            "value": "宜春",
            "label": "宜春",
            "leaf": true
          },
          {
            "value": "鹰潭",
            "label": "鹰潭",
            "leaf": true
          }
        ]
      },
      {
        "value": "辽宁",
        "label": "辽宁",
        "leaf": false,
        "children": [
          {
            "value": "鞍山",
            "label": "鞍山",
            "leaf": true
          },
          {
            "value": "本溪",
            "label": "本溪",
            "leaf": true
          },
          {
            "value": "朝阳",
            "label": "朝阳",
            "leaf": true
          },
          {
            "value": "大连",
            "label": "大连",
            "leaf": true
          },
          {
            "value": "丹东",
            "label": "丹东",
            "leaf": true
          },
          {
            "value": "抚顺",
            "label": "抚顺",
            "leaf": true
          },
          {
            "value": "阜新",
            "label": "阜新",
            "leaf": true
          },
          {
            "value": "葫芦岛",
            "label": "葫芦岛",
            "leaf": true
          },
          {
            "value": "锦州",
            "label": "锦州",
            "leaf": true
          },
          {
            "value": "辽阳",
            "label": "辽阳",
            "leaf": true
          },
          {
            "value": "盘锦",
            "label": "盘锦",
            "leaf": true
          },
          {
            "value": "沈阳",
            "label": "沈阳",
            "leaf": true
          },
          {
            "value": "铁岭",
            "label": "铁岭",
            "leaf": true
          },
          {
            "value": "营口",
            "label": "营口",
            "leaf": true
          }
        ]
      },
      {
        "value": "内蒙古",
        "label": "内蒙古",
        "leaf": false,
        "children": [
          {
            "value": "阿拉善",
            "label": "阿拉善",
            "leaf": true
          },
          {
            "value": "包头",
            "label": "包头",
            "leaf": true
          },
          {
            "value": "巴彦淖尔",
            "label": "巴彦淖尔",
            "leaf": true
          },
          {
            "value": "乌兰察布",
            "label": "乌兰察布",
            "leaf": true
          },
          {
            "value": "赤峰",
            "label": "赤峰",
            "leaf": true
          },
          {
            "value": "鄂尔多斯",
            "label": "鄂尔多斯",
            "leaf": true
          },
          {
            "value": "锡林郭勒",
            "label": "锡林郭勒",
            "leaf": true
          },
          {
            "value": "呼和浩特",
            "label": "呼和浩特",
            "leaf": true
          },
          {
            "value": "呼伦贝尔",
            "label": "呼伦贝尔",
            "leaf": true
          },
          {
            "value": "通辽",
            "label": "通辽",
            "leaf": true
          },
          {
            "value": "乌海",
            "label": "乌海",
            "leaf": true
          },
          {
            "value": "兴安",
            "label": "兴安",
            "leaf": true
          }
        ]
      },
      {
        "value": "宁夏",
        "label": "宁夏",
        "leaf": false,
        "children": [
          {
            "value": "固原",
            "label": "固原",
            "leaf": true
          },
          {
            "value": "石嘴山",
            "label": "石嘴山",
            "leaf": true
          },
          {
            "value": "吴忠",
            "label": "吴忠",
            "leaf": true
          },
          {
            "value": "银川",
            "label": "银川",
            "leaf": true
          },
          {
            "value": "中卫",
            "label": "中卫",
            "leaf": true
          }
        ]
      },
      {
        "value": "青海",
        "label": "青海",
        "leaf": false,
        "children": [
          {
            "value": "果洛",
            "label": "果洛",
            "leaf": true
          },
          {
            "value": "海东",
            "label": "海东",
            "leaf": true
          },
          {
            "value": "海南",
            "label": "海南",
            "leaf": true
          },
          {
            "value": "海西",
            "label": "海西",
            "leaf": true
          },
          {
            "value": "黄南",
            "label": "黄南",
            "leaf": true
          },
          {
            "value": "海北",
            "label": "海北",
            "leaf": true
          },
          {
            "value": "西宁",
            "label": "西宁",
            "leaf": true
          },
          {
            "value": "玉树",
            "label": "玉树",
            "leaf": true
          }
        ]
      },
      {
        "value": "山东",
        "label": "山东",
        "leaf": false,
        "children": [
          {
            "value": "滨州",
            "label": "滨州",
            "leaf": true
          },
          {
            "value": "东营",
            "label": "东营",
            "leaf": true
          },
          {
            "value": "菏泽",
            "label": "菏泽",
            "leaf": true
          },
          {
            "value": "济南",
            "label": "济南",
            "leaf": true
          },
          {
            "value": "济宁",
            "label": "济宁",
            "leaf": true
          },
          {
            "value": "莱芜",
            "label": "莱芜",
            "leaf": true
          },
          {
            "value": "聊城",
            "label": "聊城",
            "leaf": true
          },
          {
            "value": "临沂",
            "label": "临沂",
            "leaf": true
          },
          {
            "value": "青岛",
            "label": "青岛",
            "leaf": true
          },
          {
            "value": "日照",
            "label": "日照",
            "leaf": true
          },
          {
            "value": "泰安",
            "label": "泰安",
            "leaf": true
          },
          {
            "value": "德州",
            "label": "德州",
            "leaf": true
          },
          {
            "value": "潍坊",
            "label": "潍坊",
            "leaf": true
          },
          {
            "value": "威海",
            "label": "威海",
            "leaf": true
          },
          {
            "value": "烟台",
            "label": "烟台",
            "leaf": true
          },
          {
            "value": "枣庄",
            "label": "枣庄",
            "leaf": true
          },
          {
            "value": "淄博",
            "label": "淄博",
            "leaf": true
          }
        ]
      },
      {
        "value": "山西",
        "label": "山西",
        "leaf": false,
        "children": [
          {
            "value": "长治",
            "label": "长治",
            "leaf": true
          },
          {
            "value": "大同",
            "label": "大同",
            "leaf": true
          },
          {
            "value": "晋城",
            "label": "晋城",
            "leaf": true
          },
          {
            "value": "晋中",
            "label": "晋中",
            "leaf": true
          },
          {
            "value": "临汾",
            "label": "临汾",
            "leaf": true
          },
          {
            "value": "吕梁",
            "label": "吕梁",
            "leaf": true
          },
          {
            "value": "朔州",
            "label": "朔州",
            "leaf": true
          },
          {
            "value": "太原",
            "label": "太原",
            "leaf": true
          },
          {
            "value": "忻州",
            "label": "忻州",
            "leaf": true
          },
          {
            "value": "阳泉",
            "label": "阳泉",
            "leaf": true
          },
          {
            "value": "运城",
            "label": "运城",
            "leaf": true
          }
        ]
      },
      {
        "value": "陕西",
        "label": "陕西",
        "leaf": false,
        "children": [
          {
            "value": "安康",
            "label": "安康",
            "leaf": true
          },
          {
            "value": "宝鸡",
            "label": "宝鸡",
            "leaf": true
          },
          {
            "value": "汉中",
            "label": "汉中",
            "leaf": true
          },
          {
            "value": "商洛",
            "label": "商洛",
            "leaf": true
          },
          {
            "value": "铜川",
            "label": "铜川",
            "leaf": true
          },
          {
            "value": "渭南",
            "label": "渭南",
            "leaf": true
          },
          {
            "value": "西安",
            "label": "西安",
            "leaf": true
          },
          {
            "value": "咸阳",
            "label": "咸阳",
            "leaf": true
          },
          {
            "value": "延安",
            "label": "延安",
            "leaf": true
          },
          {
            "value": "榆林",
            "label": "榆林",
            "leaf": true
          }
        ]
      },
      {
        "value": "上海",
        "label": "上海",
        "leaf": true
      },
      {
        "value": "四川",
        "label": "四川",
        "leaf": false,
        "children": [
          {
            "value": "阿坝",
            "label": "阿坝",
            "leaf": true
          },
          {
            "value": "成都",
            "label": "成都",
            "leaf": true
          },
          {
            "value": "德阳",
            "label": "德阳",
            "leaf": true
          },
          {
            "value": "达州",
            "label": "达州",
            "leaf": true
          },
          {
            "value": "甘孜",
            "label": "甘孜",
            "leaf": true
          },
          {
            "value": "广元",
            "label": "广元",
            "leaf": true
          },
          {
            "value": "广安",
            "label": "广安",
            "leaf": true
          },
          {
            "value": "乐山",
            "label": "乐山",
            "leaf": true
          },
          {
            "value": "凉山",
            "label": "凉山",
            "leaf": true
          },
          {
            "value": "泸州",
            "label": "泸州",
            "leaf": true
          },
          {
            "value": "眉山",
            "label": "眉山",
            "leaf": true
          },
          {
            "value": "绵阳",
            "label": "绵阳",
            "leaf": true
          },
          {
            "value": "南充",
            "label": "南充",
            "leaf": true
          },
          {
            "value": "内江",
            "label": "内江",
            "leaf": true
          },
          {
            "value": "巴中",
            "label": "巴中",
            "leaf": true
          },
          {
            "value": "攀枝花",
            "label": "攀枝花",
            "leaf": true
          },
          {
            "value": "遂宁",
            "label": "遂宁",
            "leaf": true
          },
          {
            "value": "雅安",
            "label": "雅安",
            "leaf": true
          },
          {
            "value": "宜宾",
            "label": "宜宾",
            "leaf": true
          },
          {
            "value": "自贡",
            "label": "自贡",
            "leaf": true
          },
          {
            "value": "资阳",
            "label": "资阳",
            "leaf": true
          }
        ]
      },
      {
        "value": "天津",
        "label": "天津",
        "leaf": true
      },
      {
        "value": "西藏",
        "label": "西藏",
        "leaf": false,
        "children": [
          {
            "value": "阿里",
            "label": "阿里",
            "leaf": true
          },
          {
            "value": "拉萨",
            "label": "拉萨",
            "leaf": true
          },
          {
            "value": "那曲",
            "label": "那曲",
            "leaf": true
          },
          {
            "value": "林芝",
            "label": "林芝",
            "leaf": true
          },
          {
            "value": "昌都",
            "label": "昌都",
            "leaf": true
          },
          {
            "value": "山南",
            "label": "山南",
            "leaf": true
          },
          {
            "value": "日喀则",
            "label": "日喀则",
            "leaf": true
          }
        ]
      },
      {
        "value": "新疆",
        "label": "新疆",
        "leaf": false,
        "children": [
          {
            "value": "阿克苏",
            "label": "阿克苏",
            "leaf": true
          },
          {
            "value": "阿勒泰",
            "label": "阿勒泰",
            "leaf": true
          },
          {
            "value": "阿拉尔",
            "label": "阿拉尔",
            "leaf": true
          },
          {
            "value": "巴音郭楞",
            "label": "巴音郭楞",
            "leaf": true
          },
          {
            "value": "博尔塔拉",
            "label": "博尔塔拉",
            "leaf": true
          },
          {
            "value": "昌吉",
            "label": "昌吉",
            "leaf": true
          },
          {
            "value": "图木舒克",
            "label": "图木舒克",
            "leaf": true
          },
          {
            "value": "哈密",
            "label": "哈密",
            "leaf": true
          },
          {
            "value": "和田",
            "label": "和田",
            "leaf": true
          },
          {
            "value": "伊犁",
            "label": "伊犁",
            "leaf": true
          },
          {
            "value": "克拉玛依",
            "label": "克拉玛依",
            "leaf": true
          },
          {
            "value": "喀什",
            "label": "喀什",
            "leaf": true
          },
          {
            "value": "克孜勒苏",
            "label": "克孜勒苏",
            "leaf": true
          },
          {
            "value": "石河子",
            "label": "石河子",
            "leaf": true
          },
          {
            "value": "塔城",
            "label": "塔城",
            "leaf": true
          },
          {
            "value": "吐鲁番",
            "label": "吐鲁番",
            "leaf": true
          },
          {
            "value": "乌鲁木齐",
            "label": "乌鲁木齐",
            "leaf": true
          },
          {
            "value": "五家渠",
            "label": "五家渠",
            "leaf": true
          }
        ]
      },
      {
        "value": "云南",
        "label": "云南",
        "leaf": false,
        "children": [
          {
            "value": "保山",
            "label": "保山",
            "leaf": true
          },
          {
            "value": "楚雄",
            "label": "楚雄",
            "leaf": true
          },
          {
            "value": "大理",
            "label": "大理",
            "leaf": true
          },
          {
            "value": "德宏",
            "label": "德宏",
            "leaf": true
          },
          {
            "value": "迪庆",
            "label": "迪庆",
            "leaf": true
          },
          {
            "value": "昆明",
            "label": "昆明",
            "leaf": true
          },
          {
            "value": "丽江",
            "label": "丽江",
            "leaf": true
          },
          {
            "value": "临沧",
            "label": "临沧",
            "leaf": true
          },
          {
            "value": "怒江",
            "label": "怒江",
            "leaf": true
          },
          {
            "value": "普洱",
            "label": "普洱",
            "leaf": true
          },
          {
            "value": "曲靖",
            "label": "曲靖",
            "leaf": true
          },
          {
            "value": "红河",
            "label": "红河",
            "leaf": true
          },
          {
            "value": "文山",
            "label": "文山",
            "leaf": true
          },
          {
            "value": "西双版纳",
            "label": "西双版纳",
            "leaf": true
          },
          {
            "value": "玉溪",
            "label": "玉溪",
            "leaf": true
          },
          {
            "value": "昭通",
            "label": "昭通",
            "leaf": true
          }
        ]
      },
      {
        "value": "浙江",
        "label": "浙江",
        "leaf": false,
        "children": [
          {
            "value": "杭州",
            "label": "杭州",
            "leaf": true
          },
          {
            "value": "湖州",
            "label": "湖州",
            "leaf": true
          },
          {
            "value": "嘉兴",
            "label": "嘉兴",
            "leaf": true
          },
          {
            "value": "金华",
            "label": "金华",
            "leaf": true
          },
          {
            "value": "丽水",
            "label": "丽水",
            "leaf": true
          },
          {
            "value": "宁波",
            "label": "宁波",
            "leaf": true
          },
          {
            "value": "衢州",
            "label": "衢州",
            "leaf": true
          },
          {
            "value": "绍兴",
            "label": "绍兴",
            "leaf": true
          },
          {
            "value": "台州",
            "label": "台州",
            "leaf": true
          },
          {
            "value": "温州",
            "label": "温州",
            "leaf": true
          },
          {
            "value": "舟山",
            "label": "舟山",
            "leaf": true
          }
        ]
      },
      {
        "value": "中国澳门",
        "label": "中国澳门",
        "leaf": true
      },
      {
        "value": "中国台湾",
        "label": "中国台湾",
        "leaf": true
      },
      {
        "value": "中国香港",
        "label": "中国香港",
        "leaf": true
      }
    ]
  },
  {
    "value": "不丹",
    "label": "不丹",
    "leaf": true
  },
  {
    "value": "东帝汶",
    "label": "东帝汶",
    "leaf": true
  },
  {
    "value": "中非共和国",
    "label": "中非共和国",
    "leaf": true
  },
  {
    "value": "丹麦",
    "label": "丹麦",
    "leaf": true
  },
  {
    "value": "乌克兰",
    "label": "乌克兰",
    "leaf": true
  },
  {
    "value": "乌兹别克斯坦",
    "label": "乌兹别克斯坦",
    "leaf": true
  },
  {
    "value": "乌干达",
    "label": "乌干达",
    "leaf": true
  },
  {
    "value": "乌拉圭",
    "label": "乌拉圭",
    "leaf": true
  },
  {
    "value": "乍得",
    "label": "乍得",
    "leaf": true
  },
  {
    "value": "乔治亚",
    "label": "乔治亚",
    "leaf": true
  },
  {
    "value": "也门",
    "label": "也门",
    "leaf": true
  },
  {
    "value": "亚美尼亚",
    "label": "亚美尼亚",
    "leaf": true
  },
  {
    "value": "以色列",
    "label": "以色列",
    "leaf": true
  },
  {
    "value": "伊拉克",
    "label": "伊拉克",
    "leaf": true
  },
  {
    "value": "伊朗",
    "label": "伊朗",
    "leaf": true
  },
  {
    "value": "伯利兹",
    "label": "伯利兹",
    "leaf": true
  },
  {
    "value": "佛得角",
    "label": "佛得角",
    "leaf": true
  },
  {
    "value": "俄罗斯",
    "label": "俄罗斯",
    "leaf": true
  },
  {
    "value": "保加利亚",
    "label": "保加利亚",
    "leaf": true
  },
  {
    "value": "克罗地亚",
    "label": "克罗地亚",
    "leaf": true
  },
  {
    "value": "关岛",
    "label": "关岛",
    "leaf": true
  },
  {
    "value": "冈比亚",
    "label": "冈比亚",
    "leaf": true
  },
  {
    "value": "冰岛",
    "label": "冰岛",
    "leaf": true
  },
  {
    "value": "几内亚",
    "label": "几内亚",
    "leaf": true
  },
  {
    "value": "几内亚比绍",
    "label": "几内亚比绍",
    "leaf": true
  },
  {
    "value": "列支敦士登",
    "label": "列支敦士登",
    "leaf": true
  },
  {
    "value": "刚果民主共和国",
    "label": "刚果民主共和国",
    "leaf": true
  },
  {
    "value": "刚果（布）",
    "label": "刚果（布）",
    "leaf": true
  },
  {
    "value": "利比亚",
    "label": "利比亚",
    "leaf": true
  },
  {
    "value": "利比里亚",
    "label": "利比里亚",
    "leaf": true
  },
  {
    "value": "加拿大",
    "label": "加拿大",
    "leaf": true
  },
  {
    "value": "加纳",
    "label": "加纳",
    "leaf": true
  },
  {
    "value": "加蓬",
    "label": "加蓬",
    "leaf": true
  },
  {
    "value": "匈牙利",
    "label": "匈牙利",
    "leaf": true
  },
  {
    "value": "北马里亚纳群岛",
    "label": "北马里亚纳群岛",
    "leaf": true
  },
  {
    "value": "南乔治亚岛和南桑德韦奇岛",
    "label": "南乔治亚岛和南桑德韦奇岛",
    "leaf": true
  },
  {
    "value": "南极洲",
    "label": "南极洲",
    "leaf": true
  },
  {
    "value": "南非",
    "label": "南非",
    "leaf": true
  },
  {
    "value": "博茨瓦纳",
    "label": "博茨瓦纳",
    "leaf": true
  },
  {
    "value": "卡塔尔",
    "label": "卡塔尔",
    "leaf": true
  },
  {
    "value": "卢旺达",
    "label": "卢旺达",
    "leaf": true
  },
  {
    "value": "卢森堡",
    "label": "卢森堡",
    "leaf": true
  },
  {
    "value": "印度",
    "label": "印度",
    "leaf": true
  },
  {
    "value": "印度尼西亚",
    "label": "印度尼西亚",
    "leaf": true
  },
  {
    "value": "危地马拉",
    "label": "危地马拉",
    "leaf": true
  },
  {
    "value": "厄瓜多尔",
    "label": "厄瓜多尔",
    "leaf": true
  },
  {
    "value": "厄立特里亚",
    "label": "厄立特里亚",
    "leaf": true
  },
  {
    "value": "叙利亚",
    "label": "叙利亚",
    "leaf": true
  },
  {
    "value": "古巴",
    "label": "古巴",
    "leaf": true
  },
  {
    "value": "吉尔吉斯斯坦",
    "label": "吉尔吉斯斯坦",
    "leaf": true
  },
  {
    "value": "吉布提",
    "label": "吉布提",
    "leaf": true
  },
  {
    "value": "哈萨克斯坦",
    "label": "哈萨克斯坦",
    "leaf": true
  },
  {
    "value": "哥伦比亚",
    "label": "哥伦比亚",
    "leaf": true
  },
  {
    "value": "哥斯达黎加",
    "label": "哥斯达黎加",
    "leaf": true
  },
  {
    "value": "喀麦隆",
    "label": "喀麦隆",
    "leaf": true
  },
  {
    "value": "图瓦卢",
    "label": "图瓦卢",
    "leaf": true
  },
  {
    "value": "土库曼斯坦",
    "label": "土库曼斯坦",
    "leaf": true
  },
  {
    "value": "土耳其",
    "label": "土耳其",
    "leaf": true
  },
  {
    "value": "圣卢西亚",
    "label": "圣卢西亚",
    "leaf": true
  },
  {
    "value": "圣基茨和尼维斯",
    "label": "圣基茨和尼维斯",
    "leaf": true
  },
  {
    "value": "圣多美和普林西比",
    "label": "圣多美和普林西比",
    "leaf": true
  },
  {
    "value": "圣文森特和格林纳丁斯",
    "label": "圣文森特和格林纳丁斯",
    "leaf": true
  },
  {
    "value": "圣皮埃尔和密克隆",
    "label": "圣皮埃尔和密克隆",
    "leaf": true
  },
  {
    "value": "圣诞岛",
    "label": "圣诞岛",
    "leaf": true
  },
  {
    "value": "圣赫勒拿",
    "label": "圣赫勒拿",
    "leaf": true
  },
  {
    "value": "圣马力诺",
    "label": "圣马力诺",
    "leaf": true
  },
  {
    "value": "圭亚那",
    "label": "圭亚那",
    "leaf": true
  },
  {
    "value": "坦桑尼亚",
    "label": "坦桑尼亚",
    "leaf": true
  },
  {
    "value": "埃及",
    "label": "埃及",
    "leaf": true
  },
  {
    "value": "埃塞俄比亚",
    "label": "埃塞俄比亚",
    "leaf": true
  },
  {
    "value": "基里巴斯",
    "label": "基里巴斯",
    "leaf": true
  },
  {
    "value": "塔吉克斯坦",
    "label": "塔吉克斯坦",
    "leaf": true
  },
  {
    "value": "塞内加尔",
    "label": "塞内加尔",
    "leaf": true
  },
  {
    "value": "塞尔维亚,黑山",
    "label": "塞尔维亚,黑山",
    "leaf": true
  },
  {
    "value": "塞拉利昂",
    "label": "塞拉利昂",
    "leaf": true
  },
  {
    "value": "塞浦路斯",
    "label": "塞浦路斯",
    "leaf": true
  },
  {
    "value": "塞舌尔",
    "label": "塞舌尔",
    "leaf": true
  },
  {
    "value": "墨西哥",
    "label": "墨西哥",
    "leaf": true
  },
  {
    "value": "多哥",
    "label": "多哥",
    "leaf": true
  },
  {
    "value": "多米尼克",
    "label": "多米尼克",
    "leaf": true
  },
  {
    "value": "多米尼加共和国",
    "label": "多米尼加共和国",
    "leaf": true
  },
  {
    "value": "奥兰群岛",
    "label": "奥兰群岛",
    "leaf": true
  },
  {
    "value": "奥地利",
    "label": "奥地利",
    "leaf": true
  },
  {
    "value": "委内瑞拉",
    "label": "委内瑞拉",
    "leaf": true
  },
  {
    "value": "孟加拉",
    "label": "孟加拉",
    "leaf": true
  },
  {
    "value": "安哥拉",
    "label": "安哥拉",
    "leaf": true
  },
  {
    "value": "安圭拉",
    "label": "安圭拉",
    "leaf": true
  },
  {
    "value": "安提瓜岛和巴布达",
    "label": "安提瓜岛和巴布达",
    "leaf": true
  },
  {
    "value": "安道尔",
    "label": "安道尔",
    "leaf": true
  },
  {
    "value": "密克罗尼西亚联邦",
    "label": "密克罗尼西亚联邦",
    "leaf": true
  },
  {
    "value": "尼加拉瓜",
    "label": "尼加拉瓜",
    "leaf": true
  },
  {
    "value": "尼日利亚",
    "label": "尼日利亚",
    "leaf": true
  },
  {
    "value": "尼日尔",
    "label": "尼日尔",
    "leaf": true
  },
  {
    "value": "尼泊尔",
    "label": "尼泊尔",
    "leaf": true
  },
  {
    "value": "巴勒斯坦",
    "label": "巴勒斯坦",
    "leaf": true
  },
  {
    "value": "巴哈马",
    "label": "巴哈马",
    "leaf": true
  },
  {
    "value": "巴基斯坦",
    "label": "巴基斯坦",
    "leaf": true
  },
  {
    "value": "巴巴多斯岛",
    "label": "巴巴多斯岛",
    "leaf": true
  },
  {
    "value": "巴布亚新几内亚",
    "label": "巴布亚新几内亚",
    "leaf": true
  },
  {
    "value": "巴拉圭",
    "label": "巴拉圭",
    "leaf": true
  },
  {
    "value": "巴拿马",
    "label": "巴拿马",
    "leaf": true
  },
  {
    "value": "巴林",
    "label": "巴林",
    "leaf": true
  },
  {
    "value": "巴西",
    "label": "巴西",
    "leaf": true
  },
  {
    "value": "布基纳法索",
    "label": "布基纳法索",
    "leaf": true
  },
  {
    "value": "布维岛",
    "label": "布维岛",
    "leaf": true
  },
  {
    "value": "布隆迪",
    "label": "布隆迪",
    "leaf": true
  },
  {
    "value": "希腊",
    "label": "希腊",
    "leaf": true
  },
  {
    "value": "帕劳群岛",
    "label": "帕劳群岛",
    "leaf": true
  },
  {
    "value": "库克群岛",
    "label": "库克群岛",
    "leaf": true
  },
  {
    "value": "开曼群岛",
    "label": "开曼群岛",
    "leaf": true
  },
  {
    "value": "德国",
    "label": "德国",
    "leaf": true
  },
  {
    "value": "意大利",
    "label": "意大利",
    "leaf": true
  },
  {
    "value": "所罗门群岛",
    "label": "所罗门群岛",
    "leaf": true
  },
  {
    "value": "托克劳",
    "label": "托克劳",
    "leaf": true
  },
  {
    "value": "拉脱维亚",
    "label": "拉脱维亚",
    "leaf": true
  },
  {
    "value": "挪威",
    "label": "挪威",
    "leaf": true
  },
  {
    "value": "捷克共和国",
    "label": "捷克共和国",
    "leaf": true
  },
  {
    "value": "摩尔多瓦",
    "label": "摩尔多瓦",
    "leaf": true
  },
  {
    "value": "摩洛哥",
    "label": "摩洛哥",
    "leaf": true
  },
  {
    "value": "摩纳哥",
    "label": "摩纳哥",
    "leaf": true
  },
  {
    "value": "文莱",
    "label": "文莱",
    "leaf": true
  },
  {
    "value": "斐济",
    "label": "斐济",
    "leaf": true
  },
  {
    "value": "斯威士兰",
    "label": "斯威士兰",
    "leaf": true
  },
  {
    "value": "斯洛伐克",
    "label": "斯洛伐克",
    "leaf": true
  },
  {
    "value": "斯洛文尼亚",
    "label": "斯洛文尼亚",
    "leaf": true
  },
  {
    "value": "斯瓦尔巴岛和扬马延岛",
    "label": "斯瓦尔巴岛和扬马延岛",
    "leaf": true
  },
  {
    "value": "斯里兰卡",
    "label": "斯里兰卡",
    "leaf": true
  },
  {
    "value": "新加坡",
    "label": "新加坡",
    "leaf": true
  },
  {
    "value": "新喀里多尼亚",
    "label": "新喀里多尼亚",
    "leaf": true
  },
  {
    "value": "新西兰",
    "label": "新西兰",
    "leaf": true
  },
  {
    "value": "日本",
    "label": "日本",
    "leaf": true
  },
  {
    "value": "智利",
    "label": "智利",
    "leaf": true
  },
  {
    "value": "朝鲜",
    "label": "朝鲜",
    "leaf": true
  },
  {
    "value": "柬埔寨",
    "label": "柬埔寨",
    "leaf": true
  },
  {
    "value": "格恩西岛",
    "label": "格恩西岛",
    "leaf": true
  },
  {
    "value": "格林纳达",
    "label": "格林纳达",
    "leaf": true
  },
  {
    "value": "格陵兰",
    "label": "格陵兰",
    "leaf": true
  },
  {
    "value": "梵蒂冈",
    "label": "梵蒂冈",
    "leaf": true
  },
  {
    "value": "比利时",
    "label": "比利时",
    "leaf": true
  },
  {
    "value": "毛里塔尼亚",
    "label": "毛里塔尼亚",
    "leaf": true
  },
  {
    "value": "毛里求斯",
    "label": "毛里求斯",
    "leaf": true
  },
  {
    "value": "汤加",
    "label": "汤加",
    "leaf": true
  },
  {
    "value": "沙特阿拉伯",
    "label": "沙特阿拉伯",
    "leaf": true
  },
  {
    "value": "法国",
    "label": "法国",
    "leaf": true
  },
  {
    "value": "法属南部领地",
    "label": "法属南部领地",
    "leaf": true
  },
  {
    "value": "法属圭亚那",
    "label": "法属圭亚那",
    "leaf": true
  },
  {
    "value": "法属波利尼西亚",
    "label": "法属波利尼西亚",
    "leaf": true
  },
  {
    "value": "法罗群岛",
    "label": "法罗群岛",
    "leaf": true
  },
  {
    "value": "波兰",
    "label": "波兰",
    "leaf": true
  },
  {
    "value": "波多黎各",
    "label": "波多黎各",
    "leaf": true
  },
  {
    "value": "波黑",
    "label": "波黑",
    "leaf": true
  },
  {
    "value": "泰国",
    "label": "泰国",
    "leaf": true
  },
  {
    "value": "泽西岛",
    "label": "泽西岛",
    "leaf": true
  },
  {
    "value": "津巴布韦",
    "label": "津巴布韦",
    "leaf": true
  },
  {
    "value": "洪都拉斯",
    "label": "洪都拉斯",
    "leaf": true
  },
  {
    "value": "海地",
    "label": "海地",
    "leaf": true
  },
  {
    "value": "澳大利亚",
    "label": "澳大利亚",
    "leaf": true
  },
  {
    "value": "爱尔兰",
    "label": "爱尔兰",
    "leaf": true
  },
  {
    "value": "爱沙尼亚",
    "label": "爱沙尼亚",
    "leaf": true
  },
  {
    "value": "牙买加",
    "label": "牙买加",
    "leaf": true
  },
  {
    "value": "特克斯和凯科斯群岛",
    "label": "特克斯和凯科斯群岛",
    "leaf": true
  },
  {
    "value": "特立尼达和多巴哥",
    "label": "特立尼达和多巴哥",
    "leaf": true
  },
  {
    "value": "玻利维亚",
    "label": "玻利维亚",
    "leaf": true
  },
  {
    "value": "瑙鲁",
    "label": "瑙鲁",
    "leaf": true
  },
  {
    "value": "瑞典",
    "label": "瑞典",
    "leaf": true
  },
  {
    "value": "瑞士",
    "label": "瑞士",
    "leaf": true
  },
  {
    "value": "瓜德罗普",
    "label": "瓜德罗普",
    "leaf": true
  },
  {
    "value": "瓦利斯和富图纳",
    "label": "瓦利斯和富图纳",
    "leaf": true
  },
  {
    "value": "瓦努阿图",
    "label": "瓦努阿图",
    "leaf": true
  },
  {
    "value": "留尼旺岛",
    "label": "留尼旺岛",
    "leaf": true
  },
  {
    "value": "白俄罗斯",
    "label": "白俄罗斯",
    "leaf": true
  },
  {
    "value": "百慕大",
    "label": "百慕大",
    "leaf": true
  },
  {
    "value": "皮特凯恩",
    "label": "皮特凯恩",
    "leaf": true
  },
  {
    "value": "直布罗陀",
    "label": "直布罗陀",
    "leaf": true
  },
  {
    "value": "福克兰群岛（马尔维纳斯）",
    "label": "福克兰群岛（马尔维纳斯）",
    "leaf": true
  },
  {
    "value": "科威特",
    "label": "科威特",
    "leaf": true
  },
  {
    "value": "科摩罗",
    "label": "科摩罗",
    "leaf": true
  },
  {
    "value": "科特迪瓦",
    "label": "科特迪瓦",
    "leaf": true
  },
  {
    "value": "科科斯（基林）群岛",
    "label": "科科斯（基林）群岛",
    "leaf": true
  },
  {
    "value": "秘鲁",
    "label": "秘鲁",
    "leaf": true
  },
  {
    "value": "突尼斯",
    "label": "突尼斯",
    "leaf": true
  },
  {
    "value": "立陶宛",
    "label": "立陶宛",
    "leaf": true
  },
  {
    "value": "索马里",
    "label": "索马里",
    "leaf": true
  },
  {
    "value": "约旦",
    "label": "约旦",
    "leaf": true
  },
  {
    "value": "纳米比亚",
    "label": "纳米比亚",
    "leaf": true
  },
  {
    "value": "纽埃",
    "label": "纽埃",
    "leaf": true
  },
  {
    "value": "缅甸",
    "label": "缅甸",
    "leaf": true
  },
  {
    "value": "罗马尼亚",
    "label": "罗马尼亚",
    "leaf": true
  },
  {
    "value": "美国",
    "label": "美国",
    "leaf": true
  },
  {
    "value": "美国本土外小岛屿",
    "label": "美国本土外小岛屿",
    "leaf": true
  },
  {
    "value": "美属维尔京群岛",
    "label": "美属维尔京群岛",
    "leaf": true
  },
  {
    "value": "美属萨摩亚",
    "label": "美属萨摩亚",
    "leaf": true
  },
  {
    "value": "老挝",
    "label": "老挝",
    "leaf": true
  },
  {
    "value": "肯尼亚",
    "label": "肯尼亚",
    "leaf": true
  },
  {
    "value": "芬兰",
    "label": "芬兰",
    "leaf": true
  },
  {
    "value": "苏丹",
    "label": "苏丹",
    "leaf": true
  },
  {
    "value": "苏里南",
    "label": "苏里南",
    "leaf": true
  },
  {
    "value": "英国",
    "label": "英国",
    "leaf": true
  },
  {
    "value": "英国属地曼岛",
    "label": "英国属地曼岛",
    "leaf": true
  },
  {
    "value": "英属印度洋领地",
    "label": "英属印度洋领地",
    "leaf": true
  },
  {
    "value": "英属维尔京群岛",
    "label": "英属维尔京群岛",
    "leaf": true
  },
  {
    "value": "荷兰",
    "label": "荷兰",
    "leaf": true
  },
  {
    "value": "荷属安的列斯",
    "label": "荷属安的列斯",
    "leaf": true
  },
  {
    "value": "莫桑比克",
    "label": "莫桑比克",
    "leaf": true
  },
  {
    "value": "莱索托",
    "label": "莱索托",
    "leaf": true
  },
  {
    "value": "菲律宾",
    "label": "菲律宾",
    "leaf": true
  },
  {
    "value": "萨尔瓦多",
    "label": "萨尔瓦多",
    "leaf": true
  },
  {
    "value": "萨摩亚",
    "label": "萨摩亚",
    "leaf": true
  },
  {
    "value": "葡萄牙",
    "label": "葡萄牙",
    "leaf": true
  },
  {
    "value": "蒙古",
    "label": "蒙古",
    "leaf": true
  },
  {
    "value": "西撒哈拉",
    "label": "西撒哈拉",
    "leaf": true
  },
  {
    "value": "西班牙",
    "label": "西班牙",
    "leaf": true
  },
  {
    "value": "诺福克岛",
    "label": "诺福克岛",
    "leaf": true
  },
  {
    "value": "贝宁",
    "label": "贝宁",
    "leaf": true
  },
  {
    "value": "赞比亚",
    "label": "赞比亚",
    "leaf": true
  },
  {
    "value": "赤道几内亚",
    "label": "赤道几内亚",
    "leaf": true
  },
  {
    "value": "赫德岛和麦克唐纳岛",
    "label": "赫德岛和麦克唐纳岛",
    "leaf": true
  },
  {
    "value": "越南",
    "label": "越南",
    "leaf": true
  },
  {
    "value": "阿塞拜疆",
    "label": "阿塞拜疆",
    "leaf": true
  },
  {
    "value": "阿富汗",
    "label": "阿富汗",
    "leaf": true
  },
  {
    "value": "阿尔及利亚",
    "label": "阿尔及利亚",
    "leaf": true
  },
  {
    "value": "阿尔巴尼亚",
    "label": "阿尔巴尼亚",
    "leaf": true
  },
  {
    "value": "阿拉伯联合酋长国",
    "label": "阿拉伯联合酋长国",
    "leaf": true
  },
  {
    "value": "阿曼",
    "label": "阿曼",
    "leaf": true
  },
  {
    "value": "阿根廷",
    "label": "阿根廷",
    "leaf": true
  },
  {
    "value": "阿鲁巴",
    "label": "阿鲁巴",
    "leaf": true
  },
  {
    "value": "韩国",
    "label": "韩国",
    "leaf": true
  },
  {
    "value": "马其顿",
    "label": "马其顿",
    "leaf": true
  },
  {
    "value": "马尔代夫",
    "label": "马尔代夫",
    "leaf": true
  },
  {
    "value": "马拉维",
    "label": "马拉维",
    "leaf": true
  },
  {
    "value": "马提尼克",
    "label": "马提尼克",
    "leaf": true
  },
  {
    "value": "马来西亚",
    "label": "马来西亚",
    "leaf": true
  },
  {
    "value": "马约特",
    "label": "马约特",
    "leaf": true
  },
  {
    "value": "马绍尔群岛",
    "label": "马绍尔群岛",
    "leaf": true
  },
  {
    "value": "马耳他",
    "label": "马耳他",
    "leaf": true
  },
  {
    "value": "马达加斯加",
    "label": "马达加斯加",
    "leaf": true
  },
  {
    "value": "马里",
    "label": "马里",
    "leaf": true
  },
  {
    "value": "黎巴嫩",
    "label": "黎巴嫩",
    "leaf": true
  },
  {
    "value": "黑山",
    "label": "黑山",
    "leaf": true
  }
]
