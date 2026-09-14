import { describe, it, expect, vi } from 'vitest';
import { registerPublishTools } from '../../src/tools/publish';
import { BackendClient } from '../../src/client';

function makeMockServer(tools: any[]) {
  return {
    tool: (name: string, description: string, schema: any, handler: Function) => {
      tools.push({ name, description, schema, handler });
    },
  } as any;
}

/** 模拟后端：1 个抖音账号 + 抖音平台元数据 + 视频素材 + 成功任务 */
function makeMockClient(overrides: Record<string, any> = {}) {
  return {
    get: vi.fn(async (path: string) => {
      if (path === '/getAccounts') {
        return { data: [[7, 3, '/cookies/dy.json', '抖音号', 1, '']] };
      }
      if (path === '/api/v2/platforms') {
        return { data: { platforms: [{
          id: 3, key: 'douyin', name: '抖音',
          default_config: { title: '', description: '', tags: [], aiContent: '', scheduleTime: '' },
        }] } };
      }
      if (path.startsWith('/api/materials/')) {
        return { data: {
          id: 'mat-1', original_filename: 'v.mp4', stored_path: 'materials/v.mp4',
          file_type: 'video', file_size: 1, duration: 10, orientation: 'horizontal',
        } };
      }
      if (path.startsWith('/api/v2/tasks/')) {
        return { data: { id: 'task-1', status: 'success', platform: '抖音', account_name: '抖音号', error_message: '' } };
      }
      return { data: null };
    }),
    post: vi.fn(async (path: string) => {
      if (path === '/api/v2/videos/batch-publish') {
        return { code: 200, data: { task_ids: ['task-1'], batch_ids: ['batch-1'], failed: [] } };
      }
      return { code: 200, data: {} };
    }),
    ...overrides,
  } as any;
}

describe('publish tools', () => {
  it('应该注册3个发布工具（video_publish / video_batch_publish / image_publish）', () => {
    const tools: any[] = [];
    registerPublishTools(makeMockServer(tools), {} as BackendClient);
    expect(tools.map(t => t.name)).toEqual(['video_publish', 'video_batch_publish', 'image_publish']);
  });

  it('video_publish 走 /api/v2/videos/batch-publish（与网页同链路），构造完整 draft_data 快照', async () => {
    const mockClient = makeMockClient();
    const tools: any[] = [];
    registerPublishTools(makeMockServer(tools), mockClient);
    const videoPublish = tools.find(t => t.name === 'video_publish')!;

    const result = await videoPublish.handler({
      account_ids: [7],
      material_id: 'mat-1',
      title: '测试标题',
      description: '测试描述',
      tags: ['测试'],
      platform_settings: { douyin: { aiContent: '内容由AI生成' } },
      schedule_time: '2026-09-20 18:00:00',
    });

    expect(result.isError).toBeFalsy();
    expect(mockClient.post).toHaveBeenCalledWith('/api/v2/videos/batch-publish', expect.objectContaining({
      videos: [expect.objectContaining({
        publishAccountIds: [7],
        platformConfigs: {
          douyin: expect.objectContaining({
            title: '测试标题',
            description: '测试描述',
            tags: ['测试'],
            aiContent: '内容由AI生成',
            scheduleTime: '2026-09-20 18:00:00',
          }),
        },
      })],
      interval_minutes: 0,
    }), expect.any(Number));

    // 载荷结构与网页一致：媒体放 commonConfig（orientation 决定横/竖字段）
    const call = mockClient.post.mock.calls.find(c => c[0] === '/api/v2/videos/batch-publish');
    const video = call![1].videos[0];
    expect(video.commonConfig.videoLandscape).toEqual(expect.objectContaining({
      id: 'mat-1', stored_path: 'materials/v.mp4',
    }));
    expect(video.commonConfig.videoPortrait).toBeNull();
    expect(video.platformOverrides).toEqual({});
    expect(video.accountOverrides).toEqual({});
  });

  it('video_publish 默认等待终态，返回 all_success', async () => {
    const mockClient = makeMockClient();
    const tools: any[] = [];
    registerPublishTools(makeMockServer(tools), mockClient);
    const videoPublish = tools.find(t => t.name === 'video_publish')!;

    const result = await videoPublish.handler({
      account_ids: [7], material_id: 'mat-1', title: 't',
    });

    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.all_success).toBe(true);
    expect(parsed.tasks).toEqual([expect.objectContaining({ task_id: 'task-1', status: 'success' })]);
  });

  it('video_publish wait=false 立即返回 task_ids 不轮询', async () => {
    const mockClient = makeMockClient();
    const tools: any[] = [];
    registerPublishTools(makeMockServer(tools), mockClient);
    const videoPublish = tools.find(t => t.name === 'video_publish')!;

    const result = await videoPublish.handler({
      account_ids: [7], material_id: 'mat-1', title: 't', wait: false,
    });

    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.task_ids).toEqual(['task-1']);
    // 不应有任务轮询调用
    expect(mockClient.get).not.toHaveBeenCalledWith('/api/v2/tasks/task-1', undefined);
  });

  it('video_publish 不存在的素材返回 MATERIAL_NOT_FOUND', async () => {
    const mockClient = makeMockClient();
    mockClient.get = vi.fn(async (path: string) => {
      if (path === '/getAccounts') return { data: [[7, 3, '/cookies/dy.json', '抖音号', 1, '']] };
      if (path === '/api/v2/platforms') return { data: { platforms: [{ id: 3, key: 'douyin', default_config: {} }] } };
      if (path.startsWith('/api/materials/')) {
        const err: any = new Error('not found');
        err.response = { status: 404 };
        throw err;
      }
      return { data: null };
    });
    const tools: any[] = [];
    registerPublishTools(makeMockServer(tools), mockClient);
    const videoPublish = tools.find(t => t.name === 'video_publish')!;

    const result = await videoPublish.handler({ account_ids: [7], material_id: 'nope', title: 't' });
    expect(result.isError).toBe(true);
    expect(JSON.parse(result.content[0].text).error).toBe('MATERIAL_NOT_FOUND');
    expect(mockClient.post).not.toHaveBeenCalled();
  });

  it('video_publish 不存在的账号返回 ACCOUNT_NOT_FOUND', async () => {
    const mockClient = makeMockClient();
    const tools: any[] = [];
    registerPublishTools(makeMockServer(tools), mockClient);
    const videoPublish = tools.find(t => t.name === 'video_publish')!;

    const result = await videoPublish.handler({ account_ids: [999], material_id: 'mat-1', title: 't' });
    expect(result.isError).toBe(true);
    expect(JSON.parse(result.content[0].text).error).toBe('ACCOUNT_NOT_FOUND');
    expect(mockClient.post).not.toHaveBeenCalled();
  });

  it('video_batch_publish 多视频一次提交', async () => {
    const mockClient = makeMockClient();
    mockClient.post = vi.fn(async (path: string) => {
      if (path === '/api/v2/videos/batch-publish') {
        return { code: 200, data: { task_ids: ['task-1'], batch_ids: ['batch-1'], failed: [] } };
      }
      return { code: 200, data: {} };
    });
    const tools: any[] = [];
    registerPublishTools(makeMockServer(tools), mockClient);
    const batchPublish = tools.find(t => t.name === 'video_batch_publish')!;

    const result = await batchPublish.handler({
      videos: [
        { account_ids: [7], material_id: 'mat-1', title: '视频1' },
        { account_ids: [7], material_id: 'mat-1', title: '视频2' },
      ],
      interval_minutes: 10,
      wait: false,
    });

    expect(result.isError).toBeFalsy();
    const call = mockClient.post.mock.calls.find(c => c[0] === '/api/v2/videos/batch-publish');
    expect(call![1].videos).toHaveLength(2);
    expect(call![1].interval_minutes).toBe(10);
  });

  it('image_publish 自动解析账号 cookie 路径并注入平台声明字段', async () => {
    const mockClient = makeMockClient();
    const tools: any[] = [];
    registerPublishTools(makeMockServer(tools), mockClient);
    const imagePublish = tools.find(t => t.name === 'image_publish')!;

    const result = await imagePublish.handler({
      image_ids: ['img-1'],
      account_configs: [{
        account_id: 7,
        title: '图文标题',
        platform_settings: { aiContent: '内容由AI生成', isOriginal: true },
      }],
    });

    expect(result.isError).toBeFalsy();
    expect(mockClient.post).toHaveBeenCalledWith('/api/image-publish/publish', expect.objectContaining({
      image_ids: ['img-1'],
      account_configs: [expect.objectContaining({
        account_id: 7,
        platform: 'douyin',
        filePath: '/cookies/dy.json',
        cover_path: '',
        dry_run: false,
        aiContent: '内容由AI生成',
        isOriginal: true,
      })],
    }), expect.any(Number));
  });
});
