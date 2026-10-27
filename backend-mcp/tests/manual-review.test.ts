import { describe, it, expect, vi } from 'vitest';
import { BackendClient } from '../src/client';

describe('manual review request lifetime', () => {
  it('preserves timeout=0 so waiting for human review does not time out', async () => {
    const client = new BackendClient('http://localhost:5409');
    const post = vi.spyOn((client as any).http, 'post')
      .mockResolvedValue({ data: { code: 200 } });
    await client.post('/api/image-publish/publish', { image_ids: ['test'] }, 0);
    expect(post).toHaveBeenCalledWith('/api/image-publish/publish', { image_ids: ['test'] }, { timeout: 0 });
    post.mockRestore();
  });

  it('keeps the default timeout when no override is provided', async () => {
    const client = new BackendClient('http://localhost:5409');
    const post = vi.spyOn((client as any).http, 'post')
      .mockResolvedValue({ data: { code: 200 } });
    await client.post('/api/v2/tasks', {});
    expect(post).toHaveBeenCalledWith('/api/v2/tasks', {}, undefined);
    post.mockRestore();
  });
});
