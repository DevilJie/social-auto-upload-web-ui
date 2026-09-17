import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from '../client.js';
import { z } from 'zod';
import { formatErrorResult, translateError, ErrorCodes } from '../errors.js';

/** 任务终态（publish_details.status） */
const TERMINAL_STATUSES = new Set(['success', 'failed', 'cancelled']);

/** GET /getAccounts → 归一化账号对象列表（兼容数组行/对象两种返回） */
async function fetchAccounts(client: BackendClient): Promise<any[]> {
  const resp = await client.get('/getAccounts');
  const raw: any[] = resp?.data ?? [];
  return raw.map((row: any) => Array.isArray(row)
    ? { id: row[0], type: row[1], filePath: row[2], userName: row[3], status: row[4], avatar: row[5] }
    : row
  );
}

/** GET /api/v2/platforms → { idToKey: Map<number,string>, metaByKey: Map<string,any> } */
async function fetchPlatformMeta(client: BackendClient): Promise<{
  idToKey: Map<number, string>;
  metaByKey: Map<string, any>;
}> {
  const resp = await client.get('/api/v2/platforms');
  const platforms: any[] = resp?.data?.platforms ?? [];
  const idToKey = new Map<number, string>();
  const metaByKey = new Map<string, any>();
  for (const p of platforms) {
    idToKey.set(p.id, p.key);
    metaByKey.set(p.key, p);
  }
  return { idToKey, metaByKey };
}

/** GET /api/materials/<id> → 素材行（404 返回 null） */
async function fetchMaterial(client: BackendClient, id: string): Promise<any | null> {
  try {
    const resp = await client.get(`/api/materials/${id}`);
    return resp?.data ?? null;
  } catch {
    return null;
  }
}

/** 素材行 → 前端 _slimMaterial 同构对象（batch-publish 载荷里的媒体引用） */
function slimMaterial(m: any): any {
  if (!m) return null;
  return {
    id: m.id,
    name: m.original_filename ?? '',
    stored_path: m.stored_path ?? '',
    size: m.file_size ?? 0,
    type: m.file_type ?? '',
    duration: m.duration ?? 0,
    orientation: m.orientation ?? '',
  };
}

/** 封面对象（covers/crop、save-cover 返回）→ 前端 toCover 同构 slim 引用 */
function toSlimCover(c: any): any {
  if (!c) return null;
  return {
    id: c.id,
    name: c.original_filename ?? '',
    url: c.url ?? '',
    stored_path: c.stored_path ?? '',
    size: c.file_size ?? 0,
    type: c.mime_type ?? 'image/jpeg',
  };
}

/** {landscape_43, ...} 裁剪结果 → commonConfig 的 4 个封面字段 */
function coversToCommonConfig(d: any) {
  return {
    coverLandscape: toSlimCover(d.landscape_43),
    coverLandscape169: toSlimCover(d.landscape_169),
    coverPortrait: toSlimCover(d.portrait_34),
    coverPortrait916: toSlimCover(d.portrait_916),
  };
}

/**
 * 自动封面（与网页 fetchAutoCovers 完全同逻辑）：
 * 等抽帧完成 → 选「1~5 秒内最接近 3 秒」的帧（无则第一帧）→ save-cover 裁 4 比例。
 * preferredSeconds 指定时选最接近该秒数的帧。失败返回 null。
 */
async function autoCoversFromFrames(
  client: BackendClient,
  materialId: string,
  preferredSeconds?: number,
): Promise<any | null> {
  let frames: any[] = [];
  for (let attempt = 0; attempt < 15; attempt++) {
    try {
      const resp = await client.get('/api/frames', { material_id: materialId });
      const data = resp?.data ?? {};
      frames = data.frames ?? [];
      if (data.status === 'done' && frames.length > 0) break;
    } catch { /* 抽帧中，触发后重试 */ }
    await client.post('/api/extract-frames', { material_id: materialId }).catch(() => undefined);
    await new Promise((r) => setTimeout(r, 2500));
  }
  if (!frames.length) return null;

  let pick: any;
  if (preferredSeconds !== undefined && preferredSeconds !== null) {
    pick = frames.reduce((b, f) => Math.abs(f.seconds - preferredSeconds) < Math.abs(b.seconds - preferredSeconds) ? f : b);
  } else {
    const inWindow = frames.filter((f: any) => f.seconds >= 1 && f.seconds <= 5);
    pick = inWindow.length
      ? inWindow.reduce((b, f) => Math.abs(f.seconds - 3) < Math.abs(b.seconds - 3) ? f : b)
      : frames[0];
  }
  if (!pick || pick.seconds === undefined || pick.seconds === null) return null;

  try {
    const resp = await client.post('/api/frames/save-cover', {
      material_id: materialId,
      seconds: Math.round(pick.seconds),
    });
    const d = resp?.data;
    return d?.landscape_43 ? d : null;
  } catch {
    return null;
  }
}

interface PublishVideoParams {
  account_ids: number[];
  material_id: string;
  title: string;
  description?: string;
  tags?: string[];
  cover_material_id?: string;
  cover_landscape_material_id?: string;
  cover_portrait_material_id?: string;
  cover_landscape_169_material_id?: string;
  cover_portrait_916_material_id?: string;
  cover_frame_seconds?: number;
  use_auto_cover?: boolean;
  platform_settings?: Record<string, Record<string, any>>;
  schedule_time?: string;
}

/**
 * 把 AI 友好的扁平参数构造成与网页发布页完全同构的 draft_data 快照：
 * commonConfig（媒体）+ platformConfigs（每平台发布配置，含标题/描述/标签与平台声明字段）。
 */
async function buildVideoSnapshot(
  client: BackendClient,
  params: PublishVideoParams,
  accounts: any[],
  idToKey: Map<number, string>,
  metaByKey: Map<string, any>,
): Promise<{ video?: any; error?: ReturnType<typeof formatErrorResult> }> {
  const {
    account_ids, material_id, title, description, tags,
    cover_material_id, cover_landscape_material_id, cover_portrait_material_id,
    cover_landscape_169_material_id, cover_portrait_916_material_id,
    cover_frame_seconds, use_auto_cover,
    platform_settings, schedule_time,
  } = params;

  // 0. 发布要素确认守卫：网页端用户「看着表单里的空字段点发布」= 显式确认过；
  //    MCP 里「没传」≠「确认不要」——描述/标签缺席时拒绝发布，强制 agent 先问用户。
  //    用户明确不需要时须显式传空（description="" / tags=[]）。
  if (description === undefined || tags === undefined) {
    const missing: string[] = [];
    if (description === undefined) missing.push('description（描述）');
    if (tags === undefined) missing.push('tags（标签）');
    return { error: formatErrorResult({
      code: ErrorCodes.MISSING_REQUIRED_FIELD, error: 'MISSING_REQUIRED_FIELD',
      message: `发布要素未确认：${missing.join('、')} 缺失。发布前必须逐项向用户确认标题/描述/标签/封面/声明/定时，不允许跳过询问直接发布`,
      suggestion: '先向用户确认缺失项的内容后重试；用户明确不需要时显式传空（description 传空字符串、tags 传空数组）',
      retryable: false,
    }) };
  }

  // 1. 账号 → 平台 key 集合
  const platformKeys = new Set<string>();
  for (const aid of account_ids) {
    const acc = accounts.find((a: any) => String(a.id) === String(aid));
    if (!acc) {
      return { error: formatErrorResult({
        code: ErrorCodes.ACCOUNT_NOT_FOUND, error: 'ACCOUNT_NOT_FOUND',
        message: `账号 ${aid} 不存在`, suggestion: '调 account_list 查可用账号 ID', retryable: false,
      }) };
    }
    const key = idToKey.get(Number(acc.type));
    if (!key) {
      return { error: formatErrorResult({
        code: ErrorCodes.INVALID_PLATFORM_TYPE, error: 'INVALID_PLATFORM_TYPE',
        message: `账号 ${aid} 的平台类型 ${acc.type} 未注册`, suggestion: '调 platform_list 查支持的平台', retryable: false,
      }) };
    }
    platformKeys.add(key);
  }

  // 2. 视频素材 → slim（按 orientation 决定放 videoLandscape/videoPortrait，与前端一致）
  const videoMat = await fetchMaterial(client, material_id);
  if (!videoMat) {
    return { error: formatErrorResult({
      code: ErrorCodes.MATERIAL_NOT_FOUND, error: 'MATERIAL_NOT_FOUND',
      message: `视频素材 ${material_id} 不存在`, suggestion: '调 material_list 查可用素材 ID', retryable: false,
    }) };
  }
  const slimVideo = slimMaterial(videoMat);
  const isPortrait = (videoMat.orientation === 'vertical');
  const commonConfig: Record<string, any> = {
    videoLandscape: isPortrait ? null : slimVideo,
    videoPortrait: isPortrait ? slimVideo : null,
    coverLandscape: null,
    coverPortrait: null,
    coverLandscape169: null,
    coverPortrait916: null,
  };

  // 3. 封面——封面方式必须由用户显式抉择（抽帧自动 or 用户封面图）：
  //    未传任何封面参数且未显式确认自动封面 → 拒绝发布，防止 AI 静默用抽帧封面。
  //    确定方式后保证与网页相同的「4 比例齐备且比例正确」不变量：
  //    各平台取用不同比例（如 B 站 4:3、知乎横版 16:9、竖版平台 3:4/9:16），
  //    commonConfig 里 4 个封面字段必须是按比例中心裁剪好的图。
  //    - 用户封面图 → /covers/crop 以它裁出 4 张；其他显式指定的比例字段按各自源图单独裁剪覆盖
  //    - 确认自动封面（use_auto_cover=true 或指定了 cover_frame_seconds）→ 抽帧选 3 秒附近帧裁 4 张
  const primaryCoverId = cover_material_id
    ?? cover_landscape_material_id ?? cover_portrait_material_id
    ?? cover_landscape_169_material_id ?? cover_portrait_916_material_id
    ?? null;

  const autoCoverConfirmed = use_auto_cover === true || cover_frame_seconds !== undefined;
  if (!primaryCoverId && !autoCoverConfirmed) {
    return { error: formatErrorResult({
      code: ErrorCodes.MISSING_REQUIRED_FIELD, error: 'MISSING_REQUIRED_FIELD',
      message: '封面方式未确认：发布前必须让用户在「视频抽帧自动封面」与「用户自己的封面图」之间做出选择，不允许默认使用抽帧封面直接发布',
      suggestion: '用户选抽帧自动封面 → 传 use_auto_cover=true（可用 cover_frame_seconds 指定帧，默认选 3 秒附近）；用户提供封面图 → 传 cover_material_id',
      retryable: false,
    }) };
  }

  let coversDict: any = null;
  if (primaryCoverId) {
    try {
      const resp = await client.post('/api/materials/covers/crop', { material_id: primaryCoverId });
      coversDict = resp?.data ?? null;
    } catch { coversDict = null; }
    if (!coversDict?.landscape_43) {
      return { error: formatErrorResult({
        code: ErrorCodes.MATERIAL_NOT_FOUND, error: 'MATERIAL_NOT_FOUND',
        message: `封面源图 ${primaryCoverId} 不存在或裁剪失败`,
        suggestion: '调 material_list 选一张有效图片素材，或让用户确认后改用抽帧自动封面（use_auto_cover=true）',
        retryable: false,
      }) };
    }
  } else {
    coversDict = await autoCoversFromFrames(client, material_id, cover_frame_seconds);
    if (!coversDict) {
      return { error: formatErrorResult({
        code: ErrorCodes.MISSING_REQUIRED_FIELD, error: 'MISSING_REQUIRED_FIELD',
        message: '自动封面生成失败（视频抽帧超时或无可用帧）',
        suggestion: '传 cover_material_id 指定封面源图，或传 cover_frame_seconds 指定选帧时间点',
        retryable: false,
      }) };
    }
  }
  const coverFields: Record<string, any> = coversToCommonConfig(coversDict);

  // 显式指定且与主源不同的比例字段：按各自源图单独裁剪该比例后覆盖
  const explicitCoverFields: [string, string | undefined, string][] = [
    ['coverLandscape', cover_landscape_material_id, 'landscape_43'],
    ['coverPortrait', cover_portrait_material_id, 'portrait_34'],
    ['coverLandscape169', cover_landscape_169_material_id, 'landscape_169'],
    ['coverPortrait916', cover_portrait_916_material_id, 'portrait_916'],
  ];
  for (const [field, matId, ratio] of explicitCoverFields) {
    if (!matId || matId === primaryCoverId) continue;
    let cropped: any = null;
    try {
      const resp = await client.post('/api/materials/covers/crop', { material_id: matId, ratios: [ratio] });
      cropped = resp?.data?.[ratio] ?? null;
    } catch { cropped = null; }
    if (!cropped) {
      return { error: formatErrorResult({
        code: ErrorCodes.MATERIAL_NOT_FOUND, error: 'MATERIAL_NOT_FOUND',
        message: `封面素材 ${matId} 不存在或按 ${ratio} 裁剪失败`,
        suggestion: '调 material_list 换一张有效图片素材',
        retryable: false,
      }) };
    }
    coverFields[field] = toSlimCover(cropped);
  }
  Object.assign(commonConfig, coverFields);

  // 4. 每平台配置 = default_config（与网页一致）+ 公共字段 + platform_settings 覆盖
  const platformConfigs: Record<string, any> = {};
  for (const key of platformKeys) {
    const base = metaByKey.get(key)?.default_config
      ?? { title: '', description: '', tags: [], scheduleTime: '' };
    platformConfigs[key] = {
      ...JSON.parse(JSON.stringify(base)),
      title,
      ...(description !== undefined ? { description } : {}),
      ...(tags !== undefined ? { tags } : {}),
      ...(schedule_time ? { scheduleTime: schedule_time } : {}),
      ...(platform_settings?.[key] ?? {}),
    };
  }

  return {
    video: {
      commonConfig,
      platformConfigs,
      platformOverrides: {},
      accountOverrides: {},
      publishAccountIds: [...account_ids],
    },
  };
}

/** 轮询任务到终态；返回摘要（超时返回当前状态 + timed_out 标记） */
async function waitTasksTerminal(
  client: BackendClient,
  taskIds: string[],
  timeoutSeconds: number,
): Promise<any[]> {
  const deadline = Date.now() + timeoutSeconds * 1000;
  const results = new Map<string, any>();

  for (;;) {
    const pending = taskIds.filter((id) => !results.has(id));
    await Promise.all(pending.map(async (id) => {
      try {
        const resp = await client.get(`/api/v2/tasks/${id}`);
        const task = resp?.data;
        if (task && TERMINAL_STATUSES.has(String(task.status))) {
          results.set(id, {
            task_id: id,
            platform: task.platform,
            account_name: task.account_name,
            status: task.status,
            error_message: task.error_message || '',
          });
        }
      } catch {
        // 单次查询失败（后端重启等）不中断等待，下轮重试
      }
    }));
    if (results.size === taskIds.length) break;
    if (Date.now() > deadline) {
      for (const id of taskIds) {
        if (!results.has(id)) {
          try {
            const resp = await client.get(`/api/v2/tasks/${id}`);
            const task = resp?.data;
            results.set(id, {
              task_id: id,
              platform: task?.platform,
              account_name: task?.account_name,
              status: task?.status ?? 'unknown',
              error_message: task?.error_message || '',
              timed_out: true,
            });
          } catch {
            results.set(id, { task_id: id, status: 'unknown', timed_out: true });
          }
        }
      }
      break;
    }
    await new Promise((r) => setTimeout(r, 3000));
  }

  return taskIds.map((id) => results.get(id)).filter(Boolean);
}

/** 提交批量发布并按需等待终态 */
async function submitBatchPublish(
  client: BackendClient,
  videos: any[],
  intervalMinutes: number,
  wait: boolean,
  waitTimeoutSeconds: number,
) {
  const resp = await client.post('/api/v2/videos/batch-publish', {
    videos,
    interval_minutes: Math.max(0, Number(intervalMinutes) || 0),
  }, 120000);
  const data = resp?.data ?? {};
  const taskIds: string[] = data.task_ids ?? [];
  const failed: any[] = data.failed ?? [];

  if (!wait || taskIds.length === 0) {
    return {
      batch_ids: data.batch_ids ?? [],
      task_ids: taskIds,
      submit_failed: failed,
      hint: taskIds.length
        ? '任务已提交。调 task_get_status 轮询各任务，或调 task_list / publish_history 查看结果'
        : undefined,
    };
  }

  const tasks = await waitTasksTerminal(client, taskIds, waitTimeoutSeconds);
  const allSuccess = tasks.every((t) => t.status === 'success');
  return {
    batch_ids: data.batch_ids ?? [],
    task_ids: taskIds,
    submit_failed: failed,
    tasks,
    all_success: allSuccess,
  };
}

// 单视频参数 schema（video_publish 与 video_batch_publish 的 videos[] 共用）
const videoParamsSchema = {
  account_ids: z.array(z.number()).min(1).describe('发布账号 ID 列表（多账号 = 多平台/同平台多号一次性发布）。调 account_list 获取'),
  material_id: z.string().describe('视频素材 ID。调 material_list 获取'),
  title: z.string().describe('视频标题（各平台标题长度限制不同，超限会被后端校验拦截）'),
  description: z.string().optional().describe('视频描述/简介（发布前必须与用户确认；用户明确不需要时显式传空字符串）'),
  tags: z.array(z.string()).optional().describe('标签列表（发布前必须与用户确认；用户明确不需要时显式传空数组）'),
  cover_material_id: z.string().optional().describe('封面源图素材 ID：按网页同款规格中心裁剪出 4 个比例（横版 4:3/16:9 + 竖版 3:4/9:16），各平台按需取用。推荐提供'),
  cover_landscape_material_id: z.string().optional().describe('横版封面（4:3）源图素材 ID——若与 cover_material_id 不同则单独按 4:3 裁剪'),
  cover_portrait_material_id: z.string().optional().describe('竖版封面（3:4）源图素材 ID——若与 cover_material_id 不同则单独按 3:4 裁剪'),
  cover_landscape_169_material_id: z.string().optional().describe('16:9 横版封面源图素材 ID（知乎等平台用）'),
  cover_portrait_916_material_id: z.string().optional().describe('9:16 竖版封面源图素材 ID'),
  cover_frame_seconds: z.number().optional().describe('抽帧自动封面的选帧时间点（秒），默认自动选 1~5 秒内最接近 3 秒的帧。传本参数即视为用户已确认使用抽帧封面'),
  use_auto_cover: z.boolean().optional().describe('用户确认使用「视频抽帧自动封面」时传 true（否则须提供 cover_material_id 由用户封面图裁剪）'),
  platform_settings: z.record(z.string(), z.record(z.string(), z.any())).optional().describe(
    `按平台 key 覆盖发布设置（各平台必填声明字段选项不同，先调 platform_list 查 fields 再填）。
示例: {"bilibili": {"zone": "vlog", "creationDeclaration": "内容无需标注"}, "dayu": {"creationDeclaration": "无需标注", "category": "社会"}}
- key 用平台英文标识（xiaohongshu/channels/douyin/kuaishou/bilibili/baijiahao/tiktok/youtube/tencent_video/iqiyi/weibo/alipay/toutiao/zhihu/csdn/vivo/weixin_gzh/taobao_guanghe/jingmai/dayu）
- 各平台声明字段（aiContent/creationDeclaration/authorStatement/...）的合法值以 platform_list 返回为准`),
  schedule_time: z.string().optional().describe('定时发布时间，格式 yyyy-MM-dd HH:mm:ss（对全部所选平台生效；部分平台有天数/粒度限制，见 platform_list 的 schedule）'),
};

export function registerPublishTools(server: McpServer, client: BackendClient): void {
  // 视频发布（与网页发布页完全同链路：/api/v2/videos/batch-publish）
  server.tool(
    'video_publish',
    `发布视频到所选账号的各平台（多平台/多账号一次性发布）。与网页发布页完全相同的链路与校验。

【发布前必须逐项向用户确认——任何一项未确认就调用本工具发布都是错误用法，服务端会拒绝】
1. 发布账号（account_ids）：哪些账号要发
2. 标题（title）
3. 描述（description）：即使不需要也要用户确认后显式传空字符串
4. 标签（tags）：即使不需要也要用户确认后显式传空数组
5. 封面方式（必须让用户二选一，默认抽帧直接发布会被拒绝）：
   a) 用户自己的封面图 → cover_material_id（自动按网页同款规格裁出 4 个比例：4:3/16:9/3:4/9:16）
   b) 视频抽帧自动封面 → use_auto_cover=true（可用 cover_frame_seconds 指定帧，默认选 3 秒附近）
6. 作品声明：各平台必填的声明字段选项不同 —— 先调 platform_list 查该平台 fields 的合法值，向用户确认后填入 platform_settings
7. 是否定时发布（schedule_time）

【流程建议】material_list 选视频 → account_list 选账号 → platform_list 查平台声明字段 → 与用户逐项确认上述清单 → 发布。

默认等待全部任务终态后返回（wait=true）；wait=false 立即返回 task_ids，配合 task_get_status 轮询。`,
    {
      ...videoParamsSchema,
      interval_minutes: z.number().optional().describe('发布间隔分钟数（单视频发布时无意义，可忽略）'),
      wait: z.boolean().optional().describe('是否等待发布任务终态（默认 true）'),
      wait_timeout_seconds: z.number().optional().describe('等待超时秒数（默认 600，超时返回当前状态）'),
    },
    async (params) => {
      try {
        const [accounts, platformMeta] = await Promise.all([
          fetchAccounts(client),
          fetchPlatformMeta(client),
        ]);
        const { video, error } = await buildVideoSnapshot(
          client, params, accounts, platformMeta.idToKey, platformMeta.metaByKey,
        );
        if (error) return error;

        const result = await submitBatchPublish(
          client, [video], params.interval_minutes ?? 0,
          params.wait !== false, params.wait_timeout_seconds ?? 600,
        );
        return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  // 批量视频发布（发布页视频队列等价物）
  server.tool(
    'video_batch_publish',
    `批量发布多个视频（网页「批量发布」的等价物）：每个视频可指定各自的账号/素材/标题/平台设置，
按 videos 数组顺序排队执行，interval_minutes 为相邻视频的发布间隔（0 = 立即接着发）。

【发布前必须逐视频向用户确认（与 video_publish 相同的清单，未确认会被服务端拒绝）】
每个视频的：账号、标题、描述（确认为空须显式传 ""）、标签（确认为空须显式传 []）、
封面方式（用户封面图 cover_material_id 或抽帧自动封面 use_auto_cover=true，二选一）、
各平台作品声明（platform_settings，选项调 platform_list 查）、是否定时。`,
    {
      videos: z.array(z.object(videoParamsSchema)).min(1).max(30).describe('视频列表（按发布顺序）'),
      interval_minutes: z.number().optional().describe('相邻视频发布间隔（分钟，0=立即，默认 0）'),
      wait: z.boolean().optional().describe('是否等待全部任务终态（默认 true）'),
      wait_timeout_seconds: z.number().optional().describe('等待超时秒数（默认 600）'),
    },
    async (params) => {
      try {
        const [accounts, platformMeta] = await Promise.all([
          fetchAccounts(client),
          fetchPlatformMeta(client),
        ]);
        const videos: any[] = [];
        for (const vp of params.videos) {
          const { video, error } = await buildVideoSnapshot(
            client, vp as PublishVideoParams, accounts, platformMeta.idToKey, platformMeta.metaByKey,
          );
          if (error) return error;
          videos.push(video);
        }

        const result = await submitBatchPublish(
          client, videos, params.interval_minutes ?? 0,
          params.wait !== false, params.wait_timeout_seconds ?? 600,
        );
        return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  // 图文发布（与网页 /api/image-publish/publish 同链路）
  server.tool(
    'image_publish',
    `发布图文内容到指定平台（与网页图文发布同链路）。支持全部平台（key 列表见 platform_list）。

【发布前必须逐项向用户确认——未确认就发布是错误用法】
1. 发布账号与各账号的标题（title）
2. 描述（description）与标签（tags）：即使不需要也要用户确认后再留空
3. 图片素材（image_ids）与封面（cover_material_id）
4. 各平台作品声明（先调 platform_list 查合法值）
5. 是否定时发布（scheduleTime，格式 yyyy-MM-dd HH:mm:ss）`,
    {
      image_ids: z.array(z.string()).describe('图片素材 ID 列表'),
      cover_material_id: z.string().optional().describe('封面图素材 ID（默认取第一张图）'),
      account_configs: z.array(z.object({
        account_id: z.number().describe('账号 ID（cookie 路径由 MCP 自动解析，无需提供）'),
        title: z.string().optional().describe('标题'),
        description: z.string().optional().describe('描述'),
        tags: z.array(z.string()).optional().describe('标签列表'),
        mix_id: z.string().optional().describe('合集/合集 ID'),
        music_name: z.string().optional().describe('音乐名称'),
        hotspot: z.string().optional().describe('热点'),
        tag_type: z.string().optional().describe('标签类型'),
        tag_value: z.string().optional().describe('标签值'),
        mini_link: z.string().optional().describe('小程序链接'),
        scheduleTime: z.string().optional().describe('定时发布时间，格式 yyyy-MM-dd HH:mm:ss'),
        platform_settings: z.record(z.string(), z.any()).optional().describe(
          '该账号平台的发布设置（声明字段等，合法值调 platform_list 查；如 {"aiContent": "内容由AI生成", "isOriginal": true}）'),
      })).min(1).describe('账号配置列表（每个账号一份发布设置）'),
    },
    async (params) => {
      try {
        const { cover_material_id, account_configs } = params;

        // 账号 → platform key + filePath（自动解析，AI 无需知道 cookie 路径）
        const [accounts, platformMeta] = await Promise.all([
          fetchAccounts(client),
          fetchPlatformMeta(client),
        ]);
        const idToKey = platformMeta.idToKey;

        // 封面素材 → stored_path（未指定时由后端用第一张图，传空串）
        let coverPath = '';
        if (cover_material_id) {
          const mat = await fetchMaterial(client, cover_material_id);
          if (!mat) {
            return formatErrorResult({
              code: ErrorCodes.MATERIAL_NOT_FOUND, error: 'MATERIAL_NOT_FOUND',
              message: `封面素材 ${cover_material_id} 不存在`, suggestion: '调 material_list 查可用素材 ID', retryable: false,
            });
          }
          coverPath = mat.stored_path;
        }

        const builtConfigs = account_configs.map((cfg: any) => {
          const { platform_settings, account_id, ...rest } = cfg;
          const acc = accounts.find((a: any) => String(a.id) === String(account_id));
          if (!acc) {
            throw Object.assign(new Error(`账号 ${account_id} 不存在（调 account_list 查可用账号）`), { code: 'ACCOUNT_NOT_FOUND' });
          }
          const platformKey = idToKey.get(Number(acc.type)) ?? '';
          return {
            ...rest,
            account_id,
            platform: platformKey,
            filePath: acc.filePath,
            cover_path: coverPath,
            dry_run: false,
            ...(platform_settings ?? {}),
          };
        });

        const response = await client.post('/api/image-publish/publish', {
          image_ids: params.image_ids,
          account_configs: builtConfigs,
        }, 600000);

        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify(response, null, 2)
          }]
        };
      } catch (error: any) {
        if (error?.code === 'ACCOUNT_NOT_FOUND') {
          return formatErrorResult({
            code: ErrorCodes.ACCOUNT_NOT_FOUND, error: 'ACCOUNT_NOT_FOUND',
            message: error.message, suggestion: '调 account_list 查可用账号 ID', retryable: false,
          });
        }
        return formatErrorResult(translateError(null, error));
      }
    }
  );
}
