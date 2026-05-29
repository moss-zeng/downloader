#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Instagram 数据获取模块
通过 Cookie 认证，使用 Instagram 私有 API 获取用户主页的所有帖子
"""

import re
import requests
import json
import time
from urllib.parse import urlparse

from apiproxy.instagram import instagram_headers


class Instagram:

    def __init__(self):
        self.timeout = 20
        self.headers = dict(instagram_headers)
        self.session = requests.Session()

    def set_cookie(self, cookie_str):
        """设置 Cookie 并自动提取 csrftoken 和 ds_user_id"""
        self.headers["Cookie"] = cookie_str

        # 提取 csrftoken
        match = re.search(r'csrftoken=([^;\s]+)', cookie_str)
        if match:
            self.headers["X-CSRFToken"] = match.group(1)

        # 提取 ds_user_id（当前登录用户 ID）
        match = re.search(r'ds_user_id=([^;\s]+)', cookie_str)
        if match:
            self.headers["X-IG-WWW-Claim"] = "hmac.AR3W0DThY2Mu5Fag4sW5u3RhaR3qhFD_5it3UA-K4pR3dQ__"

        # 同步到 session
        self.session.headers.update(self.headers)

    def validate_cookie(self, cookie_str):
        """
        校验 Cookie 是否包含必要字段
        返回 (is_valid, error_message)
        """
        if not cookie_str:
            return False, "Cookie 为空"

        if 'sessionid' not in cookie_str:
            return False, "Cookie 中缺少 sessionid，请确保已登录 Instagram 后再导出 Cookie"

        if 'csrftoken' not in cookie_str:
            return False, "Cookie 中缺少 csrftoken，请重新导出完整的 Cookie"

        return True, ""

    def get_username_from_url(self, url):
        """
        从 Instagram URL 中提取用户名
        支持:
          https://www.instagram.com/username/
          https://www.instagram.com/username/?g=5
          https://instagram.com/username
        """
        url = url.strip()

        # 如果不是 instagram 域名，尝试跟踪重定向
        if "instagram.com" not in url.lower():
            try:
                resp = requests.get(url, allow_redirects=True, timeout=10,
                                    headers={"User-Agent": self.headers["User-Agent"]})
                url = resp.url
            except Exception:
                return None

        parsed = urlparse(url)
        path = parsed.path.strip('/')
        parts = path.split('/')

        # 过滤掉非用户主页路径
        reserved = {
            'p', 'reel', 'reels', 'stories', 'explore',
            'accounts', 'direct', 'tv', 'about', 'legal',
        }

        if parts and parts[0] and parts[0] not in reserved:
            return parts[0]
        return None

    def _request_with_retry(self, url, max_retries=3, delay=3):
        """带重试的 GET 请求"""
        for attempt in range(max_retries):
            try:
                resp = self.session.get(url, timeout=self.timeout)

                if 200 <= resp.status_code < 300:
                    return resp

                if resp.status_code == 429:
                    wait = delay * (attempt + 1)
                    print(f"[Instagram] 被限流(429)，等待 {wait}s 后重试... ({attempt+1}/{max_retries})")
                    time.sleep(wait)
                    continue

                if resp.status_code in (401, 403):
                    print(f"[Instagram] 认证失败({resp.status_code})，请检查 Cookie 是否有效")
                    return None

                print(f"[Instagram] 请求失败，状态码: {resp.status_code}")
                if attempt < max_retries - 1:
                    time.sleep(delay)

            except requests.exceptions.Timeout:
                print(f"[Instagram] 请求超时，重试中... ({attempt+1}/{max_retries})")
                time.sleep(delay)
            except Exception as e:
                print(f"[Instagram] 请求异常: {e}")
                if attempt < max_retries - 1:
                    time.sleep(delay)

        return None
    
    def get_user_info(self, username):
        """
        获取用户详细信息（头像、昵称、user_id 等）
        优先从主页 HTML 提取，失败后使用 web_profile_info 接口
        """
        # 方式1: 从主页 HTML 中提取
        print("[Instagram] 尝试从主页提取用户信息...")
        url3 = f"https://www.instagram.com/{username}/"
        resp = self._request_with_retry(url3)
        if resp:
            try:
                html = resp.text
                uid_match = re.search(r'"user_id"\s*:\s*"(\d+)"', html)
                if uid_match:
                    uid = uid_match.group(1)
                    name_match = re.search(r'<title>([^<]*?)\s*\(@?' + re.escape(username) + r'\)', html)
                    full_name = name_match.group(1).strip() if name_match else username
                    print(f"[Instagram] 从主页 user_id 提取成功: {uid}")
                    # 方式2成功，直接返回，跳过方式1
                    return {
                        "id": uid,
                        "pk": uid,
                        "username": username,
                        "full_name": full_name,
                    }
            except Exception:
                pass

        # 方式2: web_profile_info API
        print("[Instagram] 主页提取失败，尝试调用 API 获取...")
        url1 = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"

        resp = self._request_with_retry(url1)
        if resp:
            try:
                data = resp.json()
                user = data.get("data", {}).get("user")
                if user:
                    print(f"[Instagram] API 获取用户信息成功: {user.get('full_name', username)}")
                    return user
            except (json.JSONDecodeError, KeyError):
                pass

        # 两种方式都失败
        print("[Instagram] 所有接口均失败，请检查 Cookie 和用户名")
        return None

    def get_user_posts(self, user_id, count=33, start_time="1970-01-01",
                       end_time="2099-12-31", progress_callback=None):
        """
        分页获取用户所有帖子

        Args:
            user_id: Instagram 用户 ID (数字)
            count: 每页数量
            start_time: 起始日期 YYYY-MM-DD
            end_time: 结束日期 YYYY-MM-DD
            progress_callback: 回调函数 callback(filtered_count, total_fetched)

        Returns:
            帖子列表（原始 API 数据）
        """
        all_posts = []
        max_id = ""
        total_fetched = 0
        consecutive_errors = 0

        while True:
            # 构建请求 URL
            api_url = f"https://www.instagram.com/api/v1/feed/user/{user_id}/?count={count}"
            if max_id:
                api_url += f"&max_id={max_id}"

            resp = self._request_with_retry(api_url, max_retries=3, delay=3)
            if not resp:
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    print("[Instagram] 连续失败3次，停止获取")
                    break
                continue

            try:
                data = resp.json()
            except json.JSONDecodeError:
                print("[Instagram] 响应不是有效的 JSON")
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    break
                continue

            # 重置连续错误计数
            consecutive_errors = 0

            # 检查 API 状态
            if data.get("status") != "ok":
                msg = data.get("message", "未知错误")
                print(f"[Instagram] API 返回错误: {msg}")
                if "login_required" in str(msg).lower():
                    print("[Instagram] Cookie 已失效，需要重新获取")
                break

            items = data.get("items", [])
            if not items:
                break

            total_fetched += len(items)

            for item in items:
                taken_at = item.get("taken_at", 0)
                create_date = time.strftime("%Y-%m-%d", time.localtime(taken_at))

                # 时间过滤 — 帖子按时间倒序，早于起始时间则后续都更早，直接返回
                if create_date < start_time:
                    return all_posts
                if create_date > end_time:
                    continue

                all_posts.append(item)

                if progress_callback:
                    progress_callback(len(all_posts), total_fetched)

            # 检查是否还有更多
            if not data.get("more_available", False):
                break

            max_id = data.get("next_max_id", "")
            if not max_id:
                break

            # 控制请求频率，避免被限流
            time.sleep(2)

        return all_posts

    @staticmethod
    def get_media_type(item):
        """
        判断帖子类型
        media_type: 1=图片, 2=视频, 8=轮播(carousel)

        按用户约定:
          - 仅 media_type==2 (单个视频) → "video"
          - 其他所有情况 → "image"
        """
        return "video" if item.get("media_type") == 2 else "image"

    @staticmethod
    def get_cover_url(item):
        """获取帖子封面图 URL"""
        # 轮播取第一张
        if item.get("media_type") == 8 and item.get("carousel_media"):
            first = item["carousel_media"][0]
            candidates = first.get("image_versions2", {}).get("candidates", [])
        else:
            candidates = item.get("image_versions2", {}).get("candidates", [])

        if candidates:
            # 取分辨率适中的封面
            for c in candidates:
                if c.get("width", 0) <= 640:
                    return c["url"]
            return candidates[0]["url"]
        return ""

    @staticmethod
    def get_caption(item):
        """获取帖子文案"""
        caption = item.get("caption")
        if caption and isinstance(caption, dict):
            return caption.get("text", "")
        return ""

    @staticmethod
    def get_media_urls(item):
        """
        提取帖子中所有媒体的下载 URL

        Returns:
            list of dict: [{"url": "...", "type": "image"|"video", "index": 1}, ...]
        """
        media_list = []
        media_type = item.get("media_type")

        if media_type == 8:
            # 轮播 — 遍历每个 slide
            for i, media in enumerate(item.get("carousel_media", []), 1):
                if media.get("media_type") == 2 and media.get("video_versions"):
                    media_list.append({
                        "url": media["video_versions"][0]["url"],
                        "type": "video",
                        "index": i,
                    })
                else:
                    candidates = media.get("image_versions2", {}).get("candidates", [])
                    if candidates:
                        best = max(candidates, key=lambda c: c.get("width", 0))
                        media_list.append({
                            "url": best["url"],
                            "type": "image",
                            "index": i,
                        })

        elif media_type == 2:
            # 单个视频
            if item.get("video_versions"):
                media_list.append({
                    "url": item["video_versions"][0]["url"],
                    "type": "video",
                    "index": 1,
                })

        else:
            # 单张图片
            candidates = item.get("image_versions2", {}).get("candidates", [])
            if candidates:
                best = max(candidates, key=lambda c: c.get("width", 0))
                media_list.append({
                    "url": best["url"],
                    "type": "image",
                    "index": 1,
                })

        return media_list


if __name__ == "__main__":
    pass