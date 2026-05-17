import asyncio
from datetime import datetime
from pathlib import Path

from conf import BASE_DIR
from uploader.douyin_uploader.main import DouYinVideo, DOUYIN_PUBLISH_STRATEGY_SCHEDULED, DOUYIN_PUBLISH_STRATEGY_IMMEDIATE
from uploader.ks_uploader.main import KSVideo
from uploader.tencent_uploader.main import TencentVideo
from uploader.xiaohongshu_uploader.main import XiaoHongShuVideo, XIAOHONGSHU_PUBLISH_STRATEGY_SCHEDULED, XIAOHONGSHU_PUBLISH_STRATEGY_IMMEDIATE
from utils.constant import TencentZoneTypes
from utils.files_times import generate_schedule_time_next_day


def _parse_schedule_time(schedule_time_str, total_files, enableTimer, videos_per_day, daily_times, start_days):
    """解析用户指定的定时发布时间，如果没有则自动生成"""
    if enableTimer and schedule_time_str:
        try:
            raw = str(schedule_time_str)
            # 兼容 UTC ISO 格式（前端旧版可能传 2026-05-16T13:00:00.000Z）
            is_utc = raw.endswith("Z") or "+00:00" in raw
            raw_clean = raw.replace("+08:00", "").replace("+00:00", "")

            for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    dt = datetime.strptime(raw_clean, fmt)
                    if is_utc:
                        from datetime import timedelta
                        dt = dt + timedelta(hours=8)
                    print(f"[定时发布] 使用用户指定时间: {dt}")
                    return [dt] * total_files
                except ValueError:
                    continue
            print(f"[定时发布] 无法解析时间 '{schedule_time_str}'，回退到自动生成")
        except Exception as e:
            print(f"[定时发布] 解析时间出错: {e}，回退到自动生成")

    # 没有用户指定时间，用自动生成逻辑
    if enableTimer:
        return generate_schedule_time_next_day(total_files, videos_per_day, daily_times, start_days)
    else:
        return [0 for _ in range(total_files)]


def post_video_tencent(title,files,tags,account_file,category=TencentZoneTypes.LIFESTYLE.value,enableTimer=False,videos_per_day = 1, daily_times=None,start_days = 0, is_draft=False, thumbnail_path=None, desc='', schedule_time_str=''):
    # 生成文件的完整路径
    account_file = [Path(BASE_DIR / "cookiesFile" / file) for file in account_file]
    files = [Path(BASE_DIR / "videoFile" / file) for file in files]
    if thumbnail_path:
        thumbnail_path = str(Path(BASE_DIR / "videoFile" / thumbnail_path))
    publish_datetimes = _parse_schedule_time(schedule_time_str, len(files), enableTimer, videos_per_day, daily_times, start_days)
    for index, file in enumerate(files):
        for cookie in account_file:
            print(f"文件路径{str(file)}")
            print(f"视频文件名：{file}")
            print(f"标题：{title}")
            print(f"描述：{desc}")
            print(f"Hashtag：{tags}")
            app = TencentVideo(title, str(file), tags, publish_datetimes[index], cookie, category, is_draft, desc=desc or None, thumbnail_path=thumbnail_path, headless=False)
            asyncio.run(app.main(), debug=False)


def post_video_DouYin(title,files,tags,account_file,category=TencentZoneTypes.LIFESTYLE.value,enableTimer=False,videos_per_day = 1, daily_times=None,start_days = 0,
                      thumbnail_landscape_path = '', thumbnail_portrait_path = '',
                      productLink = '', productTitle = '', desc='', schedule_time_str='', ai_content=''):
    # 生成文件的完整路径
    account_file = [Path(BASE_DIR / "cookiesFile" / file) for file in account_file]
    files = [Path(BASE_DIR / "videoFile" / file) for file in files]
    if thumbnail_landscape_path:
        thumbnail_landscape_path = str(Path(BASE_DIR / "videoFile" / thumbnail_landscape_path))
    if thumbnail_portrait_path:
        thumbnail_portrait_path = str(Path(BASE_DIR / "videoFile" / thumbnail_portrait_path))
    publish_datetimes = _parse_schedule_time(schedule_time_str, len(files), enableTimer, videos_per_day, daily_times, start_days)
    douyin_strategy = DOUYIN_PUBLISH_STRATEGY_SCHEDULED if enableTimer and schedule_time_str else DOUYIN_PUBLISH_STRATEGY_IMMEDIATE
    for index, file in enumerate(files):
        for cookie in account_file:
            print(f"文件路径{str(file)}")
            print(f"视频文件名：{file}")
            print(f"标题：{title}")
            print(f"描述：{desc}")
            print(f"Hashtag：{tags}")
            app = DouYinVideo(title, str(file), tags, publish_datetimes[index], cookie,
                              thumbnail_landscape_path=thumbnail_landscape_path or None,
                              thumbnail_portrait_path=thumbnail_portrait_path or None,
                              productLink=productLink, productTitle=productTitle,
                              desc=desc or None, ai_content=ai_content,
                              publish_strategy=douyin_strategy,
                              headless=False)
            asyncio.run(app.douyin_upload_video(), debug=False)


def post_video_ks(title,files,tags,account_file,category=TencentZoneTypes.LIFESTYLE.value,enableTimer=False,videos_per_day = 1, daily_times=None,start_days = 0, thumbnail_path=None, desc='', schedule_time_str='', author_declaration=''):
    # 生成文件的完整路径
    account_file = [Path(BASE_DIR / "cookiesFile" / file) for file in account_file]
    files = [Path(BASE_DIR / "videoFile" / file) for file in files]
    if thumbnail_path:
        thumbnail_path = str(Path(BASE_DIR / "videoFile" / thumbnail_path))
    publish_datetimes = _parse_schedule_time(schedule_time_str, len(files), enableTimer, videos_per_day, daily_times, start_days)
    for index, file in enumerate(files):
        for cookie in account_file:
            print(f"文件路径{str(file)}")
            print(f"视频文件名：{file}")
            print(f"标题：{title}")
            print(f"描述：{desc}")
            print(f"Hashtag：{tags}")
            app = KSVideo(title, str(file), tags, publish_datetimes[index], cookie, thumbnail_path=thumbnail_path, desc=desc or None, headless=False, author_declaration=author_declaration)
            asyncio.run(app.main(), debug=False)

def post_video_xhs(title,files,tags,account_file,category=TencentZoneTypes.LIFESTYLE.value,enableTimer=False,videos_per_day = 1, daily_times=None,start_days = 0, thumbnail_path=None, desc='', schedule_time_str='', ai_content=''):
    # 生成文件的完整路径
    account_file = [Path(BASE_DIR / "cookiesFile" / file) for file in account_file]
    files = [Path(BASE_DIR / "videoFile" / file) for file in files]
    if thumbnail_path:
        thumbnail_path = str(Path(BASE_DIR / "videoFile" / thumbnail_path))
    publish_datetimes = _parse_schedule_time(schedule_time_str, len(files), enableTimer, videos_per_day, daily_times, start_days)
    # 小红书兼容：如果只有一个文件，直接传 datetime 对象而非列表
    if not enableTimer or not schedule_time_str:
        publish_datetimes = 0 if not enableTimer else publish_datetimes
    xhs_strategy = XIAOHONGSHU_PUBLISH_STRATEGY_SCHEDULED if enableTimer and schedule_time_str else XIAOHONGSHU_PUBLISH_STRATEGY_IMMEDIATE
    for index, file in enumerate(files):
        for cookie in account_file:
            print(f"视频文件名：{file}")
            print(f"标题：{title}")
            print(f"描述：{desc}")
            print(f"Hashtag：{tags}")
            app = XiaoHongShuVideo(title, file, tags, publish_datetimes if not isinstance(publish_datetimes, list) else publish_datetimes[index], cookie, thumbnail_path=thumbnail_path, desc=desc or None, ai_content=ai_content, publish_strategy=xhs_strategy, headless=False)
            asyncio.run(app.main(), debug=False)


def post_video_bilibili(title, files, tags, account_file, category=None,
                        enableTimer=False, videos_per_day=1, daily_times=None,
                        start_days=0, desc='', thumbnailLandscape=None, thumbnailPortrait=None, schedule_time_str='',
                        ai_content='', creation_declaration=''):
    """B站视频上传 — 浏览器自动化方式"""
    from uploader.bilibili_uploader.main import BilibiliVideo

    # 生成文件的完整路径
    account_file = [Path(BASE_DIR / "cookiesFile" / file) for file in account_file]
    files = [Path(BASE_DIR / "videoFile" / file) for file in files]

    # B站使用横版封面
    thumbnail_path = None
    if thumbnailLandscape:
        thumbnail_path = str(Path(BASE_DIR / "videoFile" / thumbnailLandscape))

    publish_datetimes = _parse_schedule_time(schedule_time_str, len(files), enableTimer, videos_per_day, daily_times, start_days)

    for index, file in enumerate(files):
        for cookie in account_file:
            print(f"视频文件名：{file}")
            print(f"标题：{title}")
            print(f"描述：{desc}")
            print(f"Hashtag：{tags}")
            app = BilibiliVideo(
                title=title,
                file_path=str(file),
                tags=tags or [],
                publish_date=publish_datetimes[index] if isinstance(publish_datetimes, list) else publish_datetimes,
                account_file=str(cookie),
                category=category,
                desc=desc,
                thumbnail_path=thumbnail_path,
                ai_content=ai_content,
                creation_declaration=creation_declaration,
                headless=False,
            )
            asyncio.run(app.main(), debug=False)


def post_video_baijiahao(title, files, tags, account_file,
                         enableTimer=False, videos_per_day=1, daily_times=None,
                         start_days=0, thumbnail_landscape_path=None, thumbnail_portrait_path=None,
                         desc='', schedule_time_str='',
                         creation_declaration='', supplementary_declaration='',
                         ai_content=False):
    """百家号视频上传"""
    from uploader.baijiahao_uploader.main import BaiJiaHaoVideo

    account_file = [Path(BASE_DIR / "cookiesFile" / file) for file in account_file]
    files = [Path(BASE_DIR / "videoFile" / file) for file in files]
    if thumbnail_landscape_path:
        thumbnail_landscape_path = str(Path(BASE_DIR / "videoFile" / thumbnail_landscape_path))
    if thumbnail_portrait_path:
        thumbnail_portrait_path = str(Path(BASE_DIR / "videoFile" / thumbnail_portrait_path))
    publish_datetimes = _parse_schedule_time(schedule_time_str, len(files), enableTimer, videos_per_day, daily_times, start_days)

    for index, file in enumerate(files):
        for cookie in account_file:
            print(f"视频文件名：{file}")
            print(f"标题：{title}")
            print(f"描述：{desc}")
            print(f"Hashtag：{tags}")
            app = BaiJiaHaoVideo(
                title=title,
                file_path=str(file),
                tags=tags or [],
                publish_date=publish_datetimes[index] if isinstance(publish_datetimes, list) else publish_datetimes,
                account_file=str(cookie),
                desc=desc or None,
                thumbnail_landscape_path=thumbnail_landscape_path,
                thumbnail_portrait_path=thumbnail_portrait_path,
                creation_declaration=creation_declaration,
                supplementary_declaration=supplementary_declaration,
                ai_content=ai_content,
                headless=False,
            )
            asyncio.run(app.main(), debug=False)


def post_video_tiktok(title, files, tags, account_file,
                      enableTimer=False, videos_per_day=1, daily_times=None,
                      start_days=0, desc='', schedule_time_str=''):
    """TikTok海外版视频上传"""
    from uploader.tk_uploader.main import TiktokVideo

    account_file = [Path(BASE_DIR / "cookiesFile" / file) for file in account_file]
    files = [Path(BASE_DIR / "videoFile" / file) for file in files]
    publish_datetimes = _parse_schedule_time(schedule_time_str, len(files), enableTimer, videos_per_day, daily_times, start_days)

    for index, file in enumerate(files):
        for cookie in account_file:
            print(f"视频文件名：{file}")
            print(f"标题：{title}")
            print(f"描述：{desc}")
            print(f"Hashtag：{tags}")
            app = TiktokVideo(
                title=title,
                file_path=str(file),
                tags=tags or [],
                publish_date=publish_datetimes[index] if isinstance(publish_datetimes, list) else publish_datetimes,
                account_file=str(cookie),
                desc=desc or None,
                headless=False,
            )
            asyncio.run(app.main(), debug=False)


def post_video_youtube(title, files, tags, account_file,
                       enableTimer=False, videos_per_day=1, daily_times=None,
                       start_days=0, thumbnail_path=None, desc='', schedule_time_str='',
                       audience='not_kids', altered_content=False):
    """YouTube视频上传"""
    from uploader.youtube_uploader.main import YouTubeVideo

    account_file = [Path(BASE_DIR / "cookiesFile" / file) for file in account_file]
    files = [Path(BASE_DIR / "videoFile" / file) for file in files]
    if thumbnail_path:
        thumbnail_path = str(Path(BASE_DIR / "videoFile" / thumbnail_path))
    publish_datetimes = _parse_schedule_time(schedule_time_str, len(files), enableTimer, videos_per_day, daily_times, start_days)

    for index, file in enumerate(files):
        for cookie in account_file:
            print(f"视频文件名：{file}")
            print(f"标题：{title}")
            print(f"描述：{desc}")
            print(f"Hashtag：{tags}")
            app = YouTubeVideo(
                title=title,
                file_path=str(file),
                tags=tags or [],
                publish_date=publish_datetimes[index] if isinstance(publish_datetimes, list) else publish_datetimes,
                account_file=str(cookie),
                desc=desc or None,
                thumbnail_path=thumbnail_path,
                headless=False,
                audience=audience,
                altered_content=altered_content,
            )
            asyncio.run(app.main(), debug=False)
