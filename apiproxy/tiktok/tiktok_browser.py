#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TikTok 主页作品收集器（基于真实 Chrome 浏览器）

原理：连接到你用调试模式启动的 Chrome（里面已登录 TikTok），
打开目标用户主页并自动向下滚动；浏览器自己会发出 item_list 请求、
自己带合法签名和 msToken，我们只在旁边监听这些请求的响应、把作品数据捡下来。
这样彻底绕开纯 Python 算不出的 msToken / 签名问题。

依赖：
    pip install playwright
    （用现成 Chrome，无需 playwright install chromium）

使用前提：
    Chrome 需用调试模式启动（见 web_app 接入说明），且已登录 TikTok。
"""

import time
import json
import re

from playwright.sync_api import sync_playwright


class TikTokBrowser:
    def __init__(self, cdp_url="http://localhost:9222", timeout=30):
        """
        cdp_url: 调试模式 Chrome 的地址，默认 9222 端口
        """
        self.cdp_url = cdp_url
        self.timeout = timeout

    def get_user_posts(self, home_url, start_time="1970-01-01",
                       end_time="2099-12-31", max_idle_rounds=5,
                       progress_callback=None):
        """
        打开用户主页，自动滚动，收集全部作品。

        home_url: 用户主页，如 https://www.tiktok.com/@username
                  （会自动去掉 /video/... 尾巴）
        返回：作品原始数据列表（每个是 item_list 里的一个 item，
              结构与原 tiktok.py 期望的一致：含 id / createTime / video / imagePost / desc 等）
        """
        # 规整主页 URL：只保留到 @username
        m = re.search(r'(https?://[^/]*tiktok\.com/@[^/?#]+)', home_url)
        if m:
            home_url = m.group(1)

        collected = {}        # id -> item，自动去重
        order = []            # 保持收集顺序

        with sync_playwright() as p:
            # 连接到你已经用调试模式打开的 Chrome
            try:
                browser = p.chromium.connect_over_cdp(self.cdp_url)
            except Exception as e:
                raise RuntimeError(
                    f"连不上调试模式的 Chrome（{self.cdp_url}）。"
                    f"请先用调试参数启动 Chrome 再运行。原始错误：{e}"
                )

            # 用 Chrome 现有的上下文（带着你的登录态）
            contexts = browser.contexts
            context = contexts[0] if contexts else browser.new_context()
            page = context.new_page()

            # —— 监听 item_list 响应，把作品捡下来 ——
            seen = {"count": 0, "reached_old": False}

            def handle_response(response):
                url = response.url
                if "/api/post/item_list" not in url:
                    return
                seen["count"] += 1
                try:
                    data = response.json()
                except Exception:
                    return
                items = data.get("itemList") or []
                for item in items:
                    pid = str(item.get("id", ""))
                    if pid and pid not in collected:
                        collected[pid] = item
                        order.append(pid)
                        ts = int(item.get("createTime", 0))
                        d = time.strftime("%Y-%m-%d", time.localtime(ts))
                        if d < start_time:
                            seen["reached_old"] = True

            page.on("response", handle_response)

            # 打开主页
            # wait_until="domcontentloaded"：页面骨架出来就继续，不死等所有后台请求
            # （TikTok 这类页面常常永远不触发 "load"，用 load 会超时）
            try:
                page.goto(home_url, timeout=60000, wait_until="domcontentloaded")
            except Exception as e:
                print(f"[警告] goto 提示: {e}（继续尝试滚动收集）")
            page.wait_for_timeout(5000)  # 多等几秒，让首屏作品和首个 item_list 回来

            # —— 自动滚动，直到连续多轮没有新作品 ——
            idle = 0
            last_count = 0
            while idle < max_idle_rounds and not seen["reached_old"]:
                page.keyboard.press("End")
                page.wait_for_timeout(600)
                page.evaluate("window.scrollBy(0, 2500)")
                page.wait_for_timeout(600)
                page.evaluate("document.scrollingElement.scrollTop = document.scrollingElement.scrollHeight")
                page.wait_for_timeout(2500)

                cur = len(collected)
                if cur == last_count:
                    idle += 1
                else:
                    idle = 0
                    last_count = cur

                if progress_callback:
                    progress_callback(cur, cur)

            page.close()
            print(f"[诊断] 共监听到 {seen['count']} 次 item_list 响应，"
                  f"收集到 {len(collected)} 个去重作品")
            # 注意：不要 browser.close()，那会关掉用户的 Chrome；
            # connect_over_cdp 下我们只是借用，断开即可（with 退出自动处理）

        # —— 按收集顺序整理，并做时间过滤 ——
        result = []
        for pid in order:
            item = collected[pid]
            create_ts = int(item.get("createTime", 0))
            create_date = time.strftime("%Y-%m-%d", time.localtime(create_ts))
            if create_date < start_time or create_date > end_time:
                continue
            result.append(item)

        return result

    def download_urls(self, tasks, progress_callback=None):
            """
            用调试 Chrome 下载。tasks: [{"url":..., "path": 本地保存绝对路径}, ...]
            返回 (成功数, 失败数)
            """
            import base64, os
            done = fail = 0
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(self.cdp_url)
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                page = context.new_page()
                page.goto("https://www.tiktok.com/", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2000)
                for t in tasks:
                    try:
                        b64 = page.evaluate("""async (url) => {
                            const r = await fetch(url, {credentials:'include'});
                            if (!r.ok) throw new Error('status ' + r.status);
                            const buf = await r.arrayBuffer();
                            let bin = ''; const bytes = new Uint8Array(buf);
                            for (let i=0;i<bytes.length;i++) bin += String.fromCharCode(bytes[i]);
                            return btoa(bin);
                        }""", t["url"])
                        os.makedirs(os.path.dirname(t["path"]), exist_ok=True)
                        with open(t["path"], "wb") as f:
                            f.write(base64.b64decode(b64))
                        done += 1
                    except Exception as e:
                        print(f"[TikTok浏览器下载失败] {e}")
                        fail += 1
                    if progress_callback:
                        progress_callback(done, fail)
                page.close()
            return done, fail

if __name__ == "__main__":
    # 简单本地自测（需先用调试模式启动 Chrome 并登录 TikTok）
    tb = TikTokBrowser()
    posts = tb.get_user_posts(
        "https://www.tiktok.com/@nakajimasaneatsu1997",
        progress_callback=lambda c, t: print(f"已收集: {c}"),
    )
    print(f"共收集 {len(posts)} 个作品")
    if posts:
        print("第一个示例:", json.dumps(posts[0], ensure_ascii=False)[:200])