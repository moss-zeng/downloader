# -*- coding: utf-8 -*-
"""
媒体下载器 - 可视化选择界面
支持平台: 抖音 / Instagram
启动后浏览器访问 http://localhost:5001
"""

import os
import sys
import json
import time
import copy
import threading
import requests
import traceback
from pathlib import Path
from flask import Flask, render_template, request, jsonify

from apiproxy.douyin.douyin import Douyin
from apiproxy.douyin import douyin_headers
from apiproxy.tiktok.tiktok_browser import TikTokBrowser
from apiproxy.tiktok.tiktok import TikTok
from apiproxy.tiktok import tiktok_headers
from apiproxy.instagram.instagram import Instagram
from apiproxy.instagram import instagram_headers
from apiproxy.common import utils

app = Flask(__name__, template_folder="templates")

# ============ 全局配置 ============
SAVE_PATH = os.path.join(os.path.expanduser("~"), "Desktop")

# 全局状态
fetched_data = {}
fetch_status = {
    "running": False,
    "total_fetched": 0,
    "filtered_count": 0,
    "finished": False,
    "error": "",
    "items": [],
    "nickname": "",
    "sec_uid": "",
    "platform": "",
}
download_status = {
    "running": False,
    "total": 0,
    "done": 0,
    "failed": 0,
    "current": "",
    "finished": False,
}


def reset_download_status():
    download_status.update({
        "running": False, "total": 0, "done": 0,
        "failed": 0, "current": "", "finished": False,
    })


def detect_platform(url):
    """根据 URL 自动识别平台"""
    url_lower = url.lower()
    if any(d in url_lower for d in ['douyin.com', 'iesdouyin.com']):
        return 'douyin'
    elif any(d in url_lower for d in ['instagram.com', 'instagr.am']):
        return 'instagram'
    elif any(d in url_lower for d in ['tiktok.com']):
        return 'tiktok'
    return 'unknown'


def parse_cookie_input(raw: str) -> str:
    """
    自动识别 cookie 格式并转为 header 字符串
    支持:
      1. JSON数组 (Cookies Editor导出): [{"name":"xx","value":"yy"}, ...]
      2. Header字符串: name1=value1; name2=value2
    """
    raw = raw.strip()
    if not raw:
        return ""

    # 尝试 JSON 格式
    if raw.startswith("["):
        try:
            cookies = json.loads(raw)
            parts = []
            for c in cookies:
                name = c.get("name", "")
                value = c.get("value", "")
                if name:
                    parts.append(f"{name}={value}")
            return "; ".join(parts)
        except (json.JSONDecodeError, TypeError):
            pass

    # 已经是 header 字符串格式，直接返回
    return raw


# ============ 路由 ============

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/fetch", methods=["POST"])
def api_fetch():
    """根据链接获取作品列表（异步）"""
    global fetched_data, fetch_status

    if fetch_status["running"]:
        return jsonify({"ok": False, "msg": "已有获取任务在进行中"})

    data = request.json
    link = data.get("link", "").strip()
    cookie_raw = data.get("cookie", "").strip()

    if not link:
        return jsonify({"ok": False, "msg": "链接不能为空"})

    # 识别平台
    platform = detect_platform(link)
    if platform == "unknown":
        return jsonify({"ok": False, "msg": "无法识别链接，目前支持抖音、TikTok和Instagram"})

    # 解析 Cookie
    cookie_str = parse_cookie_input(cookie_raw)
    if platform != "tiktok" and not cookie_str:
        return jsonify({"ok": False, "msg": "未设置Cookie，请粘贴对应平台的Cookie"})
   
    # 设置 Cookie 到对应平台的 headers
    if platform == "douyin":
        douyin_headers["Cookie"] = cookie_str
    elif platform == "tiktok":
        tiktok_headers["Cookie"] = cookie_str
    elif platform == "instagram":
        instagram_headers["Cookie"] = cookie_str

    # 重置状态
    fetched_data = {}
    fetch_status.update({
        "running": True, "total_fetched": 0, "filtered_count": 0,
        "finished": False, "error": "", "items": [],
        "nickname": "", "sec_uid": "", "platform": platform,
    })

    t = threading.Thread(
        target=_fetch_worker,
        args=(link, data, platform),
        daemon=True,
    )
    t.start()

    return jsonify({"ok": True, "msg": f"开始获取作品列表（{platform}）"})


@app.route("/api/fetch_status")
def api_fetch_status():
    return jsonify({
        "running": fetch_status["running"],
        "total_fetched": fetch_status["total_fetched"],
        "filtered_count": fetch_status["filtered_count"],
        "finished": fetch_status["finished"],
        "error": fetch_status["error"],
        "nickname": fetch_status["nickname"],
        "sec_uid": fetch_status["sec_uid"],
        "platform": fetch_status["platform"],
    })


@app.route("/api/fetch_result")
def api_fetch_result():
    return jsonify({
        "items": fetch_status["items"],
        "nickname": fetch_status["nickname"],
        "sec_uid": fetch_status["sec_uid"],
        "platform": fetch_status["platform"],
    })


# ============ Fetch Workers ============

def _fetch_worker(link, data, platform):
    """根据平台分发到对应的获取逻辑"""
    if platform == "douyin":
        _fetch_douyin_worker(link, data)
    elif platform == "tiktok":
        _fetch_tiktok_worker(link, data)
    elif platform == "instagram":
        _fetch_instagram_worker(link, data)
    else:
        fetch_status["error"] = "不支持的平台"
        fetch_status["running"] = False
        fetch_status["finished"] = True


def _fetch_douyin_worker(link, data):
    """抖音作品获取"""
    global fetched_data, fetch_status
    try:
        dy = Douyin(database=False)
        url = dy.getShareLink(link)
        key_type, key = dy.getKey(url)

        if key_type != "user":
            fetch_status["error"] = f"目前只支持用户主页链接，检测到类型: {key_type}"
            fetch_status["running"] = False
            fetch_status["finished"] = True
            return

        user_data = dy.getUserDetailInfo(sec_uid=key)
        nickname = ""
        if user_data and user_data.get("user"):
            nickname = user_data["user"]["nickname"]

        fetch_status["nickname"] = nickname
        fetch_status["sec_uid"] = key

        start_date = data.get("start_date", "").strip() or "1970-01-01"
        end_date = data.get("end_date", "").strip() or "2099-12-31"

        def on_progress(filtered, total):
            fetch_status["filtered_count"] = filtered
            fetch_status["total_fetched"] = total

        aweme_list = dy.getUserInfo(
            sec_uid=key, mode="post", count=35,
            number=0, increase=False,
            start_time=start_date, end_time=end_date,
            progress_callback=on_progress,
        )

        if not aweme_list:
            fetch_status["error"] = "未获取到作品数据，可能是Cookie失效或链接无效"
            fetch_status["running"] = False
            fetch_status["finished"] = True
            return

        items = []
        for aweme in aweme_list:
            aweme_id = aweme.get("aweme_id", "")
            aweme_type = aweme.get("awemeType", 0)

            cover_url = ""
            if aweme_type == 0:
                cover_urls = aweme.get("video", {}).get("cover", {}).get("url_list", [])
                if cover_urls:
                    cover_url = cover_urls[0]
            else:
                images = aweme.get("images", [])
                if images:
                    first = images[0]
                    if isinstance(first, dict):
                        img_urls = first.get("url_list", [])
                        cover_url = img_urls[0] if img_urls else ""
                    elif isinstance(first, str):
                        cover_url = first

            items.append({
                "aweme_id": aweme_id,
                "type": "video" if aweme_type == 0 else "image",
                "desc": aweme.get("desc", ""),
                "create_time": aweme.get("create_time", ""),
                "cover_url": cover_url,
            })
            fetched_data[aweme_id] = aweme

        fetch_status["items"] = items
        fetch_status["filtered_count"] = len(items)

    except Exception as e:
        traceback.print_exc()          
        fetch_status["error"] = f"请求出错: {str(e)}"

    fetch_status["running"] = False
    fetch_status["finished"] = True

def _fetch_tiktok_worker(link, data):
    """TikTok 作品获取"""
    global fetched_data, fetch_status
    try:
        start_date = data.get("start_date", "").strip() or "1970-01-01"
        end_date = data.get("end_date", "").strip() or "2099-12-31"

        def on_progress(filtered, total):
            fetch_status["filtered_count"] = filtered
            fetch_status["total_fetched"] = total

        tb = TikTokBrowser()
        try:
            posts = tb.get_user_posts(
                home_url=link,
                start_time=start_date, end_time=end_date,
                progress_callback=on_progress,
            )
        except RuntimeError as e:
            fetch_status["error"] = str(e)
            fetch_status["running"] = False
            fetch_status["finished"] = True
            return

        # 昵称从第一个作品的 author 里取
        nickname = "tiktok_user"
        username = ""
        if posts:
            author = posts[0].get("author", {})
            username = author.get("uniqueId", "")
            nickname = author.get("nickname") or username or nickname
        if not username:
            m = re.search(r'tiktok\.com/@([^/?#]+)', link)
            if m:
                username = m.group(1)
        fetch_status["nickname"] = nickname
        fetch_status["sec_uid"] = username
        fetch_status["sec_uid"] = ""
        if not posts:
            fetch_status["error"] = "未获取到作品数据，可能是Cookie失效、账号私密或链接无效"
            fetch_status["running"] = False
            fetch_status["finished"] = True
            return

        items = []
        for post in posts:
            post_id = str(post.get("id", ""))
            create_ts = post.get("createTime", 0)
            create_time = time.strftime("%Y-%m-%d %H.%M.%S", time.localtime(int(create_ts)))

            items.append({
                "aweme_id": post_id,
                "type": TikTok.get_media_type(post),
                "desc": TikTok.get_caption(post),
                "create_time": create_time,
                "cover_url": TikTok.get_cover_url(post),
            })
            fetched_data[post_id] = post

        fetch_status["items"] = items
        fetch_status["filtered_count"] = len(items)

    except Exception as e:
        fetch_status["error"] = f"请求出错: {str(e)}"

    fetch_status["running"] = False
    fetch_status["finished"] = True

def _fetch_instagram_worker(link, data):
    """Instagram 帖子获取"""
    global fetched_data, fetch_status
    try:
        ig = Instagram()
        cookie_str = instagram_headers.get("Cookie", "")

        # 校验 Cookie
        is_valid, err_msg = ig.validate_cookie(cookie_str)
        if not is_valid:
            fetch_status["error"] = err_msg
            fetch_status["running"] = False
            fetch_status["finished"] = True
            return

        ig.set_cookie(cookie_str)

        # 从 URL 提取用户名
        username = ig.get_username_from_url(link)
        if not username:
            fetch_status["error"] = "无法从链接中提取用户名，请粘贴用户主页链接"
            fetch_status["running"] = False
            fetch_status["finished"] = True
            return

        # 获取用户信息
        user_info = ig.get_user_info(username)
        if not user_info:
            fetch_status["error"] = "获取用户信息失败，请检查Cookie是否有效"
            fetch_status["running"] = False
            fetch_status["finished"] = True
            return

        user_id = user_info.get("id") or user_info.get("pk")
        nickname = user_info.get("full_name") or user_info.get("username", username)

        fetch_status["nickname"] = nickname
        fetch_status["sec_uid"] = str(user_id)

        start_date = data.get("start_date", "").strip() or "1970-01-01"
        end_date = data.get("end_date", "").strip() or "2099-12-31"

        def on_progress(filtered, total):
            fetch_status["filtered_count"] = filtered
            fetch_status["total_fetched"] = total

        # 获取所有帖子
        posts = ig.get_user_posts(
            user_id=user_id, count=33,
            start_time=start_date, end_time=end_date,
            progress_callback=on_progress,
        )

        if not posts:
            fetch_status["error"] = "未获取到作品数据，可能是Cookie失效、账号私密或链接无效"
            fetch_status["running"] = False
            fetch_status["finished"] = True
            return

        items = []
        for post in posts:
            post_id = str(post.get("pk", post.get("id", "")))
            taken_at = post.get("taken_at", 0)
            create_time = time.strftime("%Y-%m-%d %H.%M.%S", time.localtime(taken_at))

            items.append({
                "aweme_id": post_id,
                "type": ig.get_media_type(post),
                "desc": ig.get_caption(post),
                "create_time": create_time,
                "cover_url": ig.get_cover_url(post),
            })
            fetched_data[post_id] = post

        fetch_status["items"] = items
        fetch_status["filtered_count"] = len(items)

    except Exception as e:
        fetch_status["error"] = f"请求出错: {str(e)}"

    fetch_status["running"] = False
    fetch_status["finished"] = True


# ============ Download ============

@app.route("/api/download", methods=["POST"])
def api_download():
    """下载选中的作品"""
    global download_status

    if download_status["running"]:
        return jsonify({"ok": False, "msg": "已有下载任务在进行中"})

    data = request.json
    ids = data.get("ids", [])
    nickname = data.get("sec_uid", "").strip() or data.get("nickname", "unknown")
    save_path = data.get("save_path", "").strip() or SAVE_PATH

    if not ids:
        return jsonify({"ok": False, "msg": "未选择任何作品"})

    to_download = [fetched_data[aid] for aid in ids if aid in fetched_data]
    if not to_download:
        return jsonify({"ok": False, "msg": "选中的作品数据无效"})

    platform = fetch_status.get("platform", "douyin")

    reset_download_status()
    download_status["running"] = True
    download_status["total"] = len(to_download)

    t = threading.Thread(
        target=_download_worker,
        args=(to_download, nickname, save_path, platform),
        daemon=True,
    )
    t.start()

    return jsonify({"ok": True, "msg": f"开始下载 {len(to_download)} 个作品"})


@app.route("/api/download_status")
def api_download_status():
    return jsonify(download_status)


def _download_worker(aweme_list, nickname, save_path, platform):
    """后台下载线程 — 根据平台分发"""
    if platform == "instagram":
        _download_instagram_worker(aweme_list, nickname, save_path)
    elif platform == "tiktok":
        _download_tiktok_worker(aweme_list, nickname, save_path)
    else:
        _download_douyin_worker(aweme_list, nickname, save_path)


def _download_douyin_worker(aweme_list, nickname, save_path):
    """抖音下载逻辑（原有逻辑不变）"""
    global download_status

    nickname_clean = utils.replaceStr(nickname)
    base_path = Path(save_path) / nickname_clean
    video_path = base_path / "video"
    image_path = base_path / "image"
    video_path.mkdir(parents=True, exist_ok=True)
    image_path.mkdir(parents=True, exist_ok=True)

    for aweme in aweme_list:
        try:
            aweme_type = aweme.get("awemeType", 0)
            desc = utils.replaceStr(aweme.get("desc", "无描述"))
            create_time = aweme.get("create_time", "")
            file_prefix = f"{create_time}_{desc}"[:80]

            download_status["current"] = desc[:30]

            if aweme_type == 0:
                video_urls = aweme.get("video", {}).get("play_addr", {}).get("url_list", [])
                if video_urls:
                    video_file = video_path / f"{file_prefix}.mp4"
                    if not video_file.exists():
                        _download_file(video_urls[0], video_file, headers=douyin_headers)
            else:
                images = aweme.get("images", [])
                if images:
                    img_folder = image_path / file_prefix
                    img_folder.mkdir(parents=True, exist_ok=True)
                    for i, img in enumerate(images, 1):
                        if isinstance(img, dict):
                            img_urls = img.get("url_list", [])
                            img_url = img_urls[0] if img_urls else ""
                        else:
                            img_url = img
                        if img_url:
                            img_file = img_folder / f"{i}.jpg"
                            if not img_file.exists():
                                _download_file(img_url, img_file, headers=douyin_headers)

            download_status["done"] += 1

        except Exception as e:
            download_status["failed"] += 1

    download_status["running"] = False
    download_status["finished"] = True
    download_status["current"] = ""

def _download_tiktok_worker(post_list, nickname, save_path):
    global download_status
    from apiproxy.tiktok.tiktok_browser import TikTokBrowser

    nickname_clean = utils.replaceStr(nickname) or nickname or "tiktok_user"
    base_path = Path(save_path) / nickname_clean
    video_path = base_path / "video"
    image_path = base_path / "image"
    video_path.mkdir(parents=True, exist_ok=True)
    image_path.mkdir(parents=True, exist_ok=True)

    tasks = []
    for post in post_list:
        create_ts = post.get("createTime", 0)
        create_time = time.strftime("%Y-%m-%d %H.%M.%S", time.localtime(int(create_ts)))
        desc = utils.replaceStr(TikTok.get_caption(post)) or "无描述"
        file_prefix = f"{create_time}_{desc}"[:80]
        media_type = TikTok.get_media_type(post)
        media_urls = TikTok.get_media_urls(post)
        if not media_urls:
            continue
        if media_type == "video":
            tasks.append({"url": media_urls[0]["url"], "path": str(video_path / f"{file_prefix}.mp4")})
        else:
            if len(media_urls) == 1:
                tasks.append({"url": media_urls[0]["url"], "path": str(image_path / f"{file_prefix}.jpg")})
            else:
                for media in media_urls:
                    tasks.append({"url": media["url"],
                                  "path": str(image_path / file_prefix / f"{media['index']}.jpg")})

    download_status["total"] = len(tasks)

    def on_prog(done, fail):
        download_status["done"] = done
        download_status["failed"] = fail

    tb = TikTokBrowser()
    try:
        tb.download_urls(tasks, progress_callback=on_prog)
    except Exception as e:
        print(f"[TikTok下载整体出错] {e}")

    download_status["running"] = False
    download_status["finished"] = True
    download_status["current"] = ""


def _download_instagram_worker(post_list, nickname, save_path):
    """Instagram 下载逻辑"""
    global download_status

    nickname_clean = utils.replaceStr(nickname)
    base_path = Path(save_path) / nickname_clean
    video_path = base_path / "video"
    image_path = base_path / "image"
    video_path.mkdir(parents=True, exist_ok=True)
    image_path.mkdir(parents=True, exist_ok=True)

    for post in post_list:
        try:
            taken_at = post.get("taken_at", 0)
            create_time = time.strftime("%Y-%m-%d %H.%M.%S", time.localtime(taken_at))
            caption = Instagram.get_caption(post)
            desc = utils.replaceStr(caption) if caption else "无描述"
            file_prefix = f"{create_time}_{desc}"[:80]
            media_type = post.get("media_type")

            download_status["current"] = desc[:30]

            media_urls = Instagram.get_media_urls(post)

            if media_type == 2:
                # 单视频 → 直接存 video/
                if media_urls:
                    video_file = video_path / f"{file_prefix}.mp4"
                    if not video_file.exists():
                        _download_file(media_urls[0]["url"], video_file)
            else:
                # 单图 / 轮播 → 存 image/ 下的子文件夹
                if media_urls:
                    if len(media_urls) == 1 and media_urls[0]["type"] == "image":
                        # 单张图片，直接存到 image/ 下
                        img_file = image_path / f"{file_prefix}.jpg"
                        if not img_file.exists():
                            _download_file(media_urls[0]["url"], img_file)
                    else:
                        # 多张（轮播），创建子文件夹
                        item_folder = image_path / file_prefix
                        item_folder.mkdir(parents=True, exist_ok=True)
                        for media in media_urls:
                            ext = ".mp4" if media["type"] == "video" else ".jpg"
                            media_file = item_folder / f"{media['index']}{ext}"
                            if not media_file.exists():
                                _download_file(media["url"], media_file)

            download_status["done"] += 1

        except Exception as e:
            download_status["failed"] += 1

    download_status["running"] = False
    download_status["finished"] = True
    download_status["current"] = ""


def _download_file(url, save_path, headers=None):
    """下载单个文件"""
    if headers is None:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/125.0.0.0 Safari/537.36"
        }
    else:
        headers = dict(headers)

    resp = requests.get(url, headers=headers, stream=True, timeout=30)
    resp.raise_for_status()
    with open(save_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("  媒体下载器 - 可视化界面")
    print("  支持: 抖音 / TikTok / Instagram")
    print("  打开浏览器访问: http://localhost:5001")
    print("=" * 50 + "\n")
    app.run(host="127.0.0.1", port=5001, debug=False)