> [English](README.md) | **简体中文** | [日本語](README.ja.md)

# 媒体下载器（可视化版）

一个带本地网页界面的多平台主页作品下载工具，支持 **抖音 / TikTok / Instagram**。
可以预览作品列表、按日期筛选、手动勾选下载，视频与图集自动分目录存储。

抖音核心基于 [jiji262/douyin-downloader](https://github.com/jiji262/douyin-downloader)（MIT）修改，
在其之上新增了可视化界面、日期筛选、TikTok 与 Instagram 支持。

![界面预览](preview_douyin.png)
![界面预览](preview_tiktok.png)
![界面预览](preview_instagram.png)

## 功能

- 输入用户主页链接，获取该主页的全部作品列表
- 网页端展示封面缩略图、作品描述、发布时间、类型标签（视频 / 图集）
- 按发布日期范围筛选
- 手动勾选想要下载的内容
- 下载后自动分为 `video/` 和 `image/` 两个子目录
- 后台静默下载，前端实时显示进度
- 自动识别链接所属平台（抖音 / TikTok / Instagram）

## 平台支持一览

| 平台      | 列表获取方式   | 是否需要 Cookie        | 额外要求                              |
| --------- | -------------- | ---------------------- | ------------------------------------- |
| 抖音      | 网页接口       | 是（网页粘贴）         | 无                                    |
| Instagram | 网页接口       | 是（网页粘贴）         | 无                                    |
| TikTok    | 真实浏览器收集 | 否（借用浏览器登录态） | 需以调试模式启动 Chrome 并登录 TikTok |

> TikTok 的风控强度远高于抖音，纯接口请求会被拦截，本项目曾尝试用纯 Python 复刻 TikTok 的 Web 签名（X-Bogus / X-Gnarly），但 TikTok 的 `item_list` 接口还要求由真实浏览器会话产生的 `msToken`，纯脚本无法稳定提供，最终该方案被放弃，改用上述浏览器方案。

> 本项目对 TikTok采用「驱动你本地真实 Chrome 浏览器」的方式收集作品列表，由浏览器自身携带合法登录态，规避签名与风控问题。这也是 TikTok 步骤与其他平台不同的原因。

## 安装

需要 Python 3.8+

```bash
pip install -r requirements.txt
```

TikTok 功能额外需要 Playwright（用于驱动浏览器）：

```bash
pip install playwright
```

> 本项目使用**已安装的 Chrome**，因此**无需**执行 `playwright install chromium`。

## 使用

### 抖音 / Instagram

两个平台用法相同。

1. 用浏览器登录对应平台网页版，通过 [Cookies Editor](https://chromewebstore.google.com/detail/cookies-editor/iphcomljdfghbkdcfndaijbokpgddeno) 等扩展导出 Cookie。
2. 启动服务：

   ```bash
   python web_app.py
   ```

   浏览器打开 `http://localhost:5001`

3. 将导出的 Cookie 粘贴到页面的 Cookie 输入框。
4. 粘贴用户主页链接：
   - 抖音：`https://v.douyin.com/xxx/` 或 `https://www.douyin.com/user/xxx`
   - Instagram：`https://www.instagram.com/用户名/`
5. （可选）设置起始 / 结束日期。
6. 点击「获取列表」，勾选想要的作品，点击「开始下载」。

### TikTok

TikTok 需要先以调试模式启动 Chrome，让程序借用浏览器的登录态。

1. **关闭所有 Chrome 窗口**，然后用调试参数启动 Chrome：

   ```bash
   "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\chrome-debug"
   ```

   （macOS / Linux 的 Chrome 路径不同，请相应替换。）

2. 在这个新打开的 Chrome 中**登录 TikTok**，确认能正常浏览目标用户主页。
   此窗口在整个下载过程中**保持打开**，下载期间请勿用它浏览其他网页。
3. 另开一个终端启动服务：

   ```bash
   python web_app.py
   ```

4. 浏览器打开 `http://localhost:5001`，粘贴 TikTok 用户主页链接
   （`https://www.tiktok.com/@用户名`），设置日期范围，点击「获取列表」。
   此时程序会驱动那个调试模式的 Chrome 自动打开主页并向下滚动收集作品。
5. 收集完成后勾选作品，点击「开始下载」。

> 网络较慢时，主页滚动到底、判定「无更多作品」可能需要等待十几秒，属正常现象。

### 文件结构

```
保存路径/
  用户名/
    video/
      2026-01-01_作品描述.mp4
    image/
      2026-01-02_图集描述/
        1.jpg
        2.jpg
```

## 注意事项与免责声明

- 本项目仅供**个人学习与备份**用途，请勿用于商业用途、批量抓取或任何侵犯他人权益的行为。
- 请尊重内容创作者的权利，遵守各平台的服务条款。
- 下载和使用所产生的一切责任由使用者自行承担。
- Cookie / 登录态有有效期，失效后需重新获取或重新登录。
- 请控制使用频率，避免对平台造成压力。

## 许可证

本项目以 [MIT](https://opensource.org/licenses/MIT) 许可证发布。

抖音下载核心基于 [jiji262/douyin-downloader](https://github.com/jiji262/douyin-downloader)（MIT），
已保留其原始许可与版权声明，特此致谢。
