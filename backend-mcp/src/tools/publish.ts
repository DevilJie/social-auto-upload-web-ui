import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from '../client.js';
import { z } from 'zod';
import { formatErrorResult, translateError, ErrorCodes } from '../errors.js';

export function registerPublishTools(server: McpServer, client: BackendClient): void {
  // 视频发布
  server.tool(
    'video_publish',
    `发布视频到指定平台。优先用 material_id（从素材库选），也兼容本地 fileList。

【重要】发布前必须向用户确认以下事项：
1. 作品声明（各平台选项不同，见下方各字段说明）
2. 是否定时发布，如需要则询问定时时间（格式 yyyy-MM-dd HH:mm:ss，如 2026-06-05 18:00:00）
3. 封面图：需要提供横版封面和竖版封面（从素材库选或提供本地路径）

【各平台声明字段对照表】
- 小红书(1): aiContent（下拉选择）+ isOriginal（是否原创）
- 视频号(2): aiContent（布尔开关）+ isOriginal（是否原创）
- 抖音(3): aiContent（下拉选择）+ isOriginal（是否原创）
- 快手(4): aiContent（下拉选择）+ isOriginal（是否原创）
- B站(5): creationDeclaration（下拉选择）+ isOriginal（是否原创）
- 百家号(6): creationDeclaration（下拉）+ supplementaryDeclaration（补充声明）+ aiContent（布尔）+ isOriginal（是否原创）
- TikTok(7): aiContent（布尔开关）+ isOriginal（是否原创）
- YouTube(8): audience（观众）+ alteredContent（是否加工内容）
- 腾讯视频(9): creationDeclaration（多选，传数组如 "剧情演绎，仅供娱乐,取材网络，谨慎甄别"）
- 爱奇艺(10): creationDeclaration（下拉）+ riskWarning（风险提示）+ enableCashActivity（是否参与打卡）`,
    {
      type: z.number().min(1).max(10).describe('平台类型: 1=小红书, 2=视频号, 3=抖音, 4=快手, 5=B站, 6=百家号, 7=TikTok, 8=YouTube, 9=腾讯视频, 10=爱奇艺'),
      title: z.string().describe('视频标题'),
      material_id: z.string().optional().describe('视频素材 ID（推荐，从素材库选择）'),
      fileList: z.array(z.string()).optional().describe('视频文件路径列表（兼容旧用法，与 material_id 互斥）'),
      accountList: z.array(z.string()).optional().describe('账号 cookie 文件路径列表'),
      account_id: z.union([z.string(), z.number()]).optional().describe('账号 ID（推荐；MCP 会查 list 拿 cookie 路径填到 accountList）'),
      tags: z.array(z.string()).optional().describe('标签列表'),
      description: z.string().optional().describe('视频描述/简介'),
      category: z.string().optional().describe('分类'),
      // 封面相关（必须询问用户提供封面图）
      thumbnail_material_id: z.string().optional().describe('【必问】封面图素材 ID，请从素材库中选择，或让用户提供本地封面图路径'),
      thumbnail: z.string().optional().describe('封面图本地路径（与 thumbnail_material_id 二选一）'),
      thumbnailLandscape_material_id: z.string().optional().describe('【必问】横版封面素材 ID，请从素材库中选择，或让用户提供本地封面图路径'),
      thumbnailLandscape: z.string().optional().describe('横版封面本地路径（与 thumbnailLandscape_material_id 二选一）'),
      thumbnailPortrait_material_id: z.string().optional().describe('【必问】竖版封面素材 ID，请从素材库中选择，或让用户提供本地封面图路径'),
      thumbnailPortrait: z.string().optional().describe('竖版封面本地路径（与 thumbnailPortrait_material_id 二选一）'),
      // 定时发布
      enableTimer: z.boolean().optional().describe('是否定时发布（如需定时发布设为 true）'),
      scheduleTime: z.string().optional().describe('定时发布时间，格式 yyyy-MM-dd HH:mm:ss，如 2026-06-05 18:00:00'),
      // 声明相关
      aiContent: z.string().optional().describe(`AI/内容声明（根据平台不同选择不同值）：
- 小红书(1): "虚构演绎，仅供娱乐" | "笔记含AI合成内容" | "内容包含营销广告" | "内容来源声明"
- 视频号(2): 传 "true"/"false"（布尔开关）
- 抖音(3): "内容由AI生成" | "内容为个人观点或见解" | "内容为转载信息" | "内容含营销推广信息" | "虚构演绎，仅供娱乐" | "无需添加自主声明"
- 快手(4): "内容为AI生成" | "演绎情节，仅供娱乐" | "个人观点，仅供参考" | "素材来源于网络"
- 百家号(6): 传 "true"/"false"（布尔开关）
- TikTok(7): 传 "true"/"false"（布尔开关）`),
      isOriginal: z.boolean().optional().describe('是否原创（小红书/视频号/抖音/快手/B站/百家号/TikTok 适用）'),
      creationDeclaration: z.string().optional().describe(`创作声明（根据平台不同选择不同值）：
- B站(5): "内容无需标注" | "含AI生成内容" | "含虚构演绎内容" | "内容含营销信息" | "个人观点，仅供参考" | "内容为转载"
- 百家号(6): "无需声明" | "含AI生成内容" | "内容为转载" | "含虚构演绎内容" | "内容含营销信息" | "个人观点，仅供参考"
- 腾讯视频(9): 可多选，逗号分隔: "剧情演绎，仅供娱乐" | "取材网络，谨慎甄别" | "个人观点，仅供参考" | "未成年人请勿学习模仿" | "内容由AI生成"
- 爱奇艺(10): "含AI生成内容" | "含虚构演绎内容" | "内容含营销信息" | "内容为转载" | "个人观点，仅供参考" | "内容无需标注"`),
      supplementaryDeclaration: z.string().optional().describe('补充声明（仅百家号）: "内容可能引人不适" | "内容含有高危险行为" | "请理性适度消费" | "未成年人请在监护人指导下浏览"'),
      riskWarning: z.string().optional().describe('风险提示（仅爱奇艺）: "内容可能引人不适，请谨慎观看" | "内容含有高危险行为，请勿模仿" | "请理性适度消费" | "未成年人请在监护人指导下浏览"'),
      enableCashActivity: z.boolean().optional().describe('是否参与打卡挑战赛（仅爱奇艺）'),
      audience: z.string().optional().describe('观众设定（仅YouTube）: "kids"=面向儿童 | "not_kids"=非面向儿童'),
      alteredContent: z.boolean().optional().describe('是否为加工的内容（仅YouTube）'),
      // 其他
      videosPerDay: z.number().optional(),
      dailyTimes: z.array(z.string()).optional(),
      startDays: z.number().optional(),
      productLink: z.string().optional(),
      productTitle: z.string().optional(),
      isDraft: z.boolean().optional().describe('是否存为草稿（不立即发布）'),
      hotspot: z.string().optional().describe('热点话题'),
      tag_type: z.string().optional(),
      tag_value: z.string().optional(),
      mini_link: z.string().optional().describe('小程序链接'),
      mix_id: z.string().optional().describe('合集ID'),
      activities: z.array(z.any()).optional().describe('活动列表'),
    },
    async (params) => {
      try {
        const {
          material_id, fileList, account_id, accountList,
          thumbnail_material_id, thumbnail,
          thumbnailLandscape_material_id, thumbnailLandscape,
          thumbnailPortrait_material_id, thumbnailPortrait,
          ...rest
        } = params;

        // 互斥校验
        if (!material_id && !fileList?.length) {
          return formatErrorResult({
            code: ErrorCodes.MISSING_REQUIRED_FIELD,
            error: 'MISSING_REQUIRED_FIELD',
            message: 'material_id 或 fileList 至少二选一',
            suggestion: '调 material_list 选素材传 material_id，或直接传 fileList',
            retryable: false,
          });
        }

        // 并发拉取需要的素材/账号数据
        const needsVideoList = !!material_id && !fileList?.length;
        const needsAccountList = !!account_id && !accountList?.length;
        const needsImageList = !!thumbnail_material_id || !!thumbnailLandscape_material_id || !!thumbnailPortrait_material_id;

        const [videoListResp, accountListResp, imageListResp] = await Promise.all([
          needsVideoList ? client.get('/api/materials/list', { type: 'video', page: '1', page_size: '100' }) : Promise.resolve(null),
          needsAccountList ? client.get('/getAccounts') : Promise.resolve(null),
          needsImageList ? client.get('/api/materials/list', { type: 'image', page: '1', page_size: '100' }) : Promise.resolve(null),
        ]);

        // material_id → fileList
        let resolvedFileList = fileList;
        if (needsVideoList) {
          const items = videoListResp?.data?.items ?? [];
          const mat = items.find((m: any) => m.id === material_id);
          if (!mat) {
            return formatErrorResult({
              code: ErrorCodes.MATERIAL_NOT_FOUND,
              error: 'MATERIAL_NOT_FOUND',
              message: `素材 ${material_id} 不存在或不在前 100 条之内`,
              suggestion: '调 material_list 翻页查找，或用 keyword 过滤',
              retryable: false,
            });
          }
          resolvedFileList = [mat.stored_path];
        }

        // account_id → accountList
        let resolvedAccountList = accountList;
        if (needsAccountList) {
          const rawAccs: any[] = accountListResp?.data ?? [];
          const accs = rawAccs.map((row: any) => Array.isArray(row)
            ? { id: row[0], type: row[1], filePath: row[2], userName: row[3], status: row[4], avatar: row[5] }
            : row
          );
          const acc = accs.find((a: any) => String(a.id) === String(account_id));
          if (!acc) {
            return formatErrorResult({
              code: ErrorCodes.ACCOUNT_NOT_FOUND,
              error: 'ACCOUNT_NOT_FOUND',
              message: `账号 ${account_id} 不存在`,
              suggestion: '调 account_list 查可用账号 ID',
              retryable: false,
            });
          }
          resolvedAccountList = [acc.filePath ?? acc.cookie_path ?? acc.cookiePath];
        }

        // 素材 ID → 本地路径（封面、横版封面、竖版封面）
        const imageItems: any[] = imageListResp?.data?.items ?? [];
        const resolveImageMaterial = (matId: string | undefined, fallback: string | undefined): string | undefined => {
          if (!matId) return fallback;
          const mat = imageItems.find((m: any) => m.id === matId);
          return mat ? mat.stored_path : fallback;
        };

        const resolvedThumbnail = resolveImageMaterial(thumbnail_material_id, thumbnail);
        const resolvedLandscape = resolveImageMaterial(thumbnailLandscape_material_id, thumbnailLandscape);
        const resolvedPortrait = resolveImageMaterial(thumbnailPortrait_material_id, thumbnailPortrait);

        const response = await client.post('/postVideo', {
          ...rest,
          fileList: resolvedFileList,
          accountList: resolvedAccountList,
          thumbnail: resolvedThumbnail,
          thumbnailLandscape: resolvedLandscape,
          thumbnailPortrait: resolvedPortrait,
        }, 600000);

        return {
          content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }],
        };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  // 图文发布
  server.tool(
    'image_publish',
    `发布图文内容到指定平台。优先用 cover_material_id（从素材库选封面），也兼容 cover_path。

【重要】发布前必须向用户确认以下事项：
1. 封面图：需要提供一张封面图片（从素材库选或提供本地路径）
2. 作品声明（各平台选项不同，见下方各字段说明）
3. 是否定时发布，如需要则询问定时时间（格式 yyyy-MM-dd HH:mm:ss，如 2026-06-05 18:00:00）

【各平台声明字段对照表】
- 小红书(xiaohongshu): aiContent（下拉选择）+ isOriginal（是否原创）
- 视频号(channels): aiContent（布尔开关）+ isOriginal（是否原创）
- 抖音(douyin): aiContent（下拉选择）+ isOriginal（是否原创）
- 快手(kuaishou): aiContent（下拉选择）+ isOriginal（是否原创）
- B站(bilibili): creationDeclaration（下拉选择）+ isOriginal（是否原创）
- 百家号(baijiahao): creationDeclaration（下拉）+ supplementaryDeclaration（补充声明）+ aiContent（布尔）+ isOriginal（是否原创）
- TikTok(tiktok): aiContent（布尔开关）+ isOriginal（是否原创）
- YouTube(youtube): audience（观众）+ alteredContent（是否加工内容）
- 腾讯视频(tencent_video): creationDeclaration（多选）
- 爱奇艺(iqiyi): creationDeclaration（下拉）+ riskWarning（风险提示）+ enableCashActivity（是否参与打卡）`,
    {
      image_ids: z.array(z.string()).describe('图片素材ID列表'),
      cover_material_id: z.string().optional().describe('【必问】封面图素材 ID，请从素材库中选择一张封面图，或让用户提供本地封面图路径'),
      cover_path: z.string().optional().describe('封面图本地路径（与 cover_material_id 二选一）'),
      account_configs: z.array(z.object({
        account_id: z.number().describe('账号ID'),
        platform: z.string().describe('平台类型: xiaohongshu/channels/douyin/kuaishou/bilibili/baijiahao/tiktok/youtube/tencent_video/iqiyi'),
        filePath: z.string().describe('cookie文件路径'),
        title: z.string().optional().describe('标题'),
        description: z.string().optional().describe('描述'),
        tags: z.array(z.string()).optional().describe('标签列表'),
        mix_id: z.string().optional().describe('合集ID'),
        music_name: z.string().optional().describe('音乐名称'),
        hotspot: z.string().optional().describe('热点'),
        tag_type: z.string().optional().describe('标签类型'),
        tag_value: z.string().optional().describe('标签值'),
        mini_link: z.string().optional().describe('小程序链接'),
        scheduleTime: z.string().optional().describe('定时发布时间，格式 yyyy-MM-dd HH:mm:ss，如 2026-06-05 18:00:00'),
        aiContent: z.string().optional().describe(`AI/内容声明（根据平台选择）：
- 小红书: "虚构演绎，仅供娱乐" | "笔记含AI合成内容" | "内容包含营销广告" | "内容来源声明"
- 视频号: "true"/"false"（布尔开关）
- 抖音: "内容由AI生成" | "内容为个人观点或见解" | "内容为转载信息" | "内容含营销推广信息" | "虚构演绎，仅供娱乐" | "无需添加自主声明"
- 快手: "内容为AI生成" | "演绎情节，仅供娱乐" | "个人观点，仅供参考" | "素材来源于网络"
- 百家号: "true"/"false"（布尔开关）
- TikTok: "true"/"false"（布尔开关）`),
        isOriginal: z.boolean().optional().describe('是否原创'),
        creationDeclaration: z.string().optional().describe(`创作声明（根据平台选择）：
- B站: "内容无需标注" | "含AI生成内容" | "含虚构演绎内容" | "内容含营销信息" | "个人观点，仅供参考" | "内容为转载"
- 百家号: "无需声明" | "含AI生成内容" | "内容为转载" | "含虚构演绎内容" | "内容含营销信息" | "个人观点，仅供参考"
- 腾讯视频: 多选逗号分隔: "剧情演绎，仅供娱乐" | "取材网络，谨慎甄别" | "个人观点，仅供参考" | "未成年人请勿学习模仿" | "内容由AI生成"
- 爱奇艺: "含AI生成内容" | "含虚构演绎内容" | "内容含营销信息" | "内容为转载" | "个人观点，仅供参考" | "内容无需标注"`),
        supplementaryDeclaration: z.string().optional().describe('补充声明（仅百家号）: "内容可能引人不适" | "内容含有高危险行为" | "请理性适度消费" | "未成年人请在监护人指导下浏览"'),
        riskWarning: z.string().optional().describe('风险提示（仅爱奇艺）: "内容可能引人不适，请谨慎观看" | "内容含有高危险行为，请勿模仿" | "请理性适度消费" | "未成年人请在监护人指导下浏览"'),
        enableCashActivity: z.boolean().optional().describe('是否参与打卡挑战赛（仅爱奇艺）'),
        audience: z.string().optional().describe('观众设定（仅YouTube）: "kids"=面向儿童 | "not_kids"=非面向儿童'),
        alteredContent: z.boolean().optional().describe('是否为加工的内容（仅YouTube）'),
        activities: z.array(z.any()).optional().describe('活动列表'),
        music_id: z.string().optional().describe('音乐ID'),
        music_title: z.string().optional().describe('音乐标题'),
      })).describe('账号配置列表'),
    },
    async (params) => {
      try {
        const { cover_material_id, cover_path, ...rest } = params;

        // 解析封面素材 ID → stored_path
        let resolvedCoverPath = cover_path;
        if (cover_material_id && !cover_path) {
          const imageListResp = await client.get('/api/materials/list', { type: 'image', page: '1', page_size: '100' });
          const items = imageListResp?.data?.items ?? [];
          const mat = items.find((m: any) => m.id === cover_material_id);
          if (!mat) {
            return formatErrorResult({
              code: ErrorCodes.MATERIAL_NOT_FOUND,
              error: 'MATERIAL_NOT_FOUND',
              message: `封面素材 ${cover_material_id} 不存在或不在前 100 条之内`,
              suggestion: '调 material_list 翻页查找，或用 keyword 过滤',
              retryable: false,
            });
          }
          resolvedCoverPath = mat.stored_path;
        }

        // 将 cover_path 注入每个 account_config，默认 dry_run=false 真实发布
        const account_configs = rest.account_configs.map((cfg: any) => ({
          ...cfg,
          cover_path: resolvedCoverPath || cfg.cover_path || '',
          dry_run: false,
        }));

        const response = await client.post('/api/image-publish/publish', {
          ...rest,
          account_configs,
        }, 600000);

        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify(response, null, 2)
          }]
        };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );
}
