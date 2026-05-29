#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
TikTok 数据获取模块
通过 Cookie 认证，使用 TikTok 网页内部 API 获取用户主页的所有作品
"""

import re
import requests
import json
import time
from urllib.parse import urlparse

from apiproxy.tiktok import tiktok_headers


class TikTok:

    def __init__(self):
        self.timeout = 20
        self.headers = dict(tiktok_headers)
        self.session = requests.Session()

    def set_cookie(self, cookie_str):
        """设置 Cookie"""
        self.headers["Cookie"] = cookie_str
        self.session.headers.update(self.headers)

    def validate_cookie(self, cookie_str):
        """
        校验 Cookie 是否包含必要字段
        返回 (is_valid, error_message)
        """
        if not cookie_str:
            return False, "Cookie 为空"

        # TikTok 的关键 cookie 字段
        if 'sessionid' not in cookie_str and 'sid_tt' not in cookie_str:
            return False, "Cookie 中缺少 sessionid 或 sid_tt，请确保已登录 TikTok 后再导出 Cookie"

        return True, ""

    def get_username_from_url(self, url):
        """
        从 TikTok URL 中提取用户名
        支持:
          https://www.tiktok.com/@username
          https://www.tiktok.com/@username?lang=en
          https://vt.tiktok.com/xxxxx/  (短链，需跟踪重定向)
        """
        url = url.strip()

        # 短链接跟踪重定向
        if "tiktok.com/@" not in url.lower():
            try:
                resp = requests.get(url, allow_redirects=True, timeout=10,
                                    headers={"User-Agent": self.headers["User-Agent"]})
                url = resp.url
            except Exception:
                return None

        parsed = urlparse(url)
        path = parsed.path.strip('/')
        parts = path.split('/')

        # 提取 @username
        if parts and parts[0].startswith('@'):
            return parts[0][1:]  # 去掉 @
        return None

    def _request_with_retry(self, url, params=None, max_retries=3, delay=3):
        """带重试的 GET 请求"""
        for attempt in range(max_retries):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)

                if 200 <= resp.status_code < 300:
                    return resp

                if resp.status_code == 429:
                    wait = delay * (attempt + 1)
                    print(f"[TikTok] 被限流(429)，等待 {wait}s 后重试... ({attempt+1}/{max_retries})")
                    time.sleep(wait)
                    continue

                if resp.status_code in (401, 403):
                    print(f"[TikTok] 认证失败({resp.status_code})，请检查 Cookie 是否有效")
                    return None

                print(f"[TikTok] 请求失败，状态码: {resp.status_code}")
                if attempt < max_retries - 1:
                    time.sleep(delay)

            except requests.exceptions.Timeout:
                print(f"[TikTok] 请求超时，重试中... ({attempt+1}/{max_retries})")
                time.sleep(delay)
            except Exception as e:
                print(f"[TikTok] 请求异常: {e}")
                if attempt < max_retries - 1:
                    time.sleep(delay)

        return None

    def get_user_info(self, username):
        """
        获取用户信息（secUid、nickname 等）
        优先从主页 HTML 提取，失败后使用 API
        """
        # 方式1: 从主页 HTML 中提取 __UNIVERSAL_DATA_FOR_REHYDRATION__
        print("[TikTok] 尝试从主页提取用户信息...")
        url = f"https://www.tiktok.com/@{username}"
        resp = self._request_with_retry(url)
        if resp:
            try:
                html = resp.text
                # TikTok 把用户数据嵌入在页面 JSON 中
                match = re.search(
                    r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
                    html, re.DOTALL
                )
                if match:
                    json_data = json.loads(match.group(1))
                    print(f"[TikTok DEBUG posts] text_start={resp.text[:200]}")
                    # 路径: __DEFAULT_SCOPE__["webapp.user-detail"]["userInfo"]
                    user_detail = (
                        json_data.get("__DEFAULT_SCOPE__", {})
                        .get("webapp.user-detail", {})
                        .get("userInfo", {})
                    )
                    user = user_detail.get("user", {})
                    if user.get("secUid"):
                        print(f"[TikTok] 从主页提取成功: {user.get('nickname', username)}")
                        return {
                            "id": user.get("id", ""),
                            "uniqueId": user.get("uniqueId", username),
                            "nickname": user.get("nickname", username),
                            "secUid": user.get("secUid", ""),
                        }
                        
            except Exception as e:
                print(f"[TikTok] 主页解析失败: {e}")

        # 方式2: API 接口
        print("[TikTok] 主页提取失败，尝试 API...")
        api_url = "https://www.tiktok.com/api/user/detail/"
        params = {"uniqueId": username, "aid": "1988", "device_platform": "web_pc"}
        resp = self._request_with_retry(api_url, params=params)
        if resp:
            try:
                data = resp.json()
                user = data.get("userInfo", {}).get("user", {})
                if user.get("secUid"):
                    print(f"[TikTok] API 获取成功: {user.get('nickname', username)}")
                    return {
                        "id": user.get("id", ""),
                        "uniqueId": user.get("uniqueId", username),
                        "nickname": user.get("nickname", username),
                        "secUid": user.get("secUid", ""),
                    }
            except (json.JSONDecodeError, KeyError):
                pass

        print("[TikTok] 所有方式均失败，请检查 Cookie 和用户名")
        return None

    def get_user_posts(self, sec_uid, count=35, start_time="1970-01-01",
                    end_time="2099-12-31", progress_callback=None):
        from apiproxy.common import tiktok_utils

        all_posts = []
        cursor = "0"
        total_fetched = 0
        consecutive_errors = 0

        ua = self.headers.get("User-Agent", "")
        ms_token = ""
        m = re.search(r'msToken=([^;\s]+)', self.headers.get("Cookie", ""))
        if m:
            ms_token = m.group(1)

        while True:
            # 1) 固定顺序拼查询串（签名是对这串精确字符算的，之后顺序/编码都不能再变）
            query = (
                "aid=1988&app_name=tiktok_web&channel=tiktok_web"
                "&device_platform=web_pc&cookie_enabled=true"
                "&focus_state=true&is_fullscreen=false&is_page_visible=true"
                "&history_len=2&from_page=user"
                f"&count={count}&cursor={cursor}&secUid={sec_uid}&msToken={ms_token}"
            )

            # 2) 签名：得到带 &X-Bogus= 的查询串 + X-Gnarly 头
            signed_query, x_gnarly = tiktok_utils.sign(query, ua)
            url = "https://www.tiktok.com/api/post/item_list/?" + signed_query

            # 3) 发请求：注意——必须传完整 URL 字符串，不要用 params=，否则会打乱已签名的串
            headers = dict(self.headers)
            headers["X-Gnarly"] = x_gnarly
            try:
                resp = self.session.get(url, headers=headers, timeout=self.timeout)
            except Exception as e:
                print(f"[TikTok] 请求异常: {e}")
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    break
                time.sleep(3); continue

            # —— 排错用：把 TikTok 真实回应打印出来 ——
            if resp.status_code != 200 or not resp.text.strip():
                print(f"[TikTok] 状态码={resp.status_code} 响应长度={len(resp.text)} "
                    f"开头={resp.text[:200]!r}")
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    break
                time.sleep(3); continue

            try:
                data = resp.json()
            except json.JSONDecodeError:
                print(f"[TikTok] 响应不是 JSON，开头={resp.text[:200]!r}")
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    break
                time.sleep(3); continue

            consecutive_errors = 0
            items = data.get("itemList") or []
            if not items:
                print(f"[TikTok] 无 itemList，statusCode={data.get('statusCode')} "
                    f"keys={list(data.keys())[:8]}")
                break

            total_fetched += len(items)
            for item in items:
                create_ts = item.get("createTime", 0)
                create_date = time.strftime("%Y-%m-%d", time.localtime(int(create_ts)))
                if create_date < start_time:
                    return all_posts
                if create_date > end_time:
                    continue
                all_posts.append(item)
                if progress_callback:
                    progress_callback(len(all_posts), total_fetched)

            if not data.get("hasMore", False):
                break
            cursor = str(data.get("cursor", "0"))
            if cursor == "0":
                break
            time.sleep(2)

        return all_posts

    @staticmethod
    def get_media_type(item):
        """
        判断作品类型
        有 imagePost 字段 → 图集，否则 → 视频
        """
        if item.get("imagePost"):
            return "image"
        return "video"

    @staticmethod
    def get_cover_url(item):
        """获取作品封面图 URL"""
        # 图集取第一张图
        image_post = item.get("imagePost")
        if image_post:
            images = image_post.get("images", [])
            if images:
                url_list = images[0].get("imageURL", {}).get("urlList", [])
                if url_list:
                    return url_list[0]

        # 视频封面
        cover = item.get("video", {}).get("cover", "")
        if cover:
            return cover
        origin_cover = item.get("video", {}).get("originCover", "")
        return origin_cover

    @staticmethod
    def get_caption(item):
        """获取作品文案"""
        return item.get("desc", "")

    @staticmethod
    def get_media_urls(item):
        """
        提取作品中所有媒体的下载 URL

        Returns:
            list of dict: [{"url": "...", "type": "image"|"video", "index": 1}, ...]
        """
        media_list = []

        image_post = item.get("imagePost")
        if image_post:
            # 图集
            for i, img in enumerate(image_post.get("images", []), 1):
                url_list = img.get("imageURL", {}).get("urlList", [])
                if url_list:
                    media_list.append({
                        "url": url_list[0],
                        "type": "image",
                        "index": i,
                    })
        else:
            # 视频 — 优先 downloadAddr，其次 playAddr
            video = item.get("video", {})
            download_addr = video.get("downloadAddr", "")
            play_addr = video.get("playAddr", "")
            url = download_addr or play_addr
            if url:
                media_list.append({
                    "url": url,
                    "type": "video",
                    "index": 1,
                })

        return media_list


if __name__ == "__main__":
    pass