> [English](README.md) | [简体中文](README.zh-CN.md) | **日本語**

# メディアダウンローダー

ローカルの Web インターフェースを備えたマルチプラットフォーム対応のプロフィールダウンローダーです。**TikTok・Instagram・Douyin（抖音）** に対応しています。

クリエイターの投稿一覧をプレビューし、日付で絞り込み、欲しいものだけを手動で選んでダウンロードできます。動画と画像（カルーセル）は自動的に別々のフォルダに整理されます。

Douyin のコア部分は [jiji262/douyin-downloader](https://github.com/jiji262/douyin-downloader)（MIT）をベースにしており、その上に Web UI・日付フィルタ・TikTok / Instagram 対応を追加したものです。

![UI プレビュー](preview_tiktok.png)
![UI プレビュー](preview_instagram.png)
![UI プレビュー](preview_douyin.png)

## 機能

- プロフィール URL を貼り付けるだけで、そのアカウントの全投稿リストを取得
- Web UI 上でサムネイル・キャプション・投稿日時・種別タグ（動画 / 画像）を表示
- 投稿日で範囲フィルタが可能
- 欲しい投稿だけにチェックを入れて選択
- ダウンロード結果は `video/` と `image/` のサブフォルダに自動振り分け
- バックグラウンドで静かにダウンロードし、進捗をブラウザ上にリアルタイム表示
- URL からプラットフォーム（TikTok / Instagram / Douyin）を自動判別

## 対応プラットフォーム一覧

| プラットフォーム | リスト取得方式       | Cookie の要否                        | 追加要件                                          |
| ---------------- | -------------------- | ------------------------------------ | ------------------------------------------------- |
| TikTok           | 実ブラウザセッション | 不要（ブラウザのログイン状態を利用） | Chrome をデバッグモードで起動し TikTok にログイン |
| Instagram        | Web API              | 必要（UI に貼り付け）                | なし                                              |
| Douyin           | Web API              | 必要（UI に貼り付け）                | なし                                              |

> TikTok のボット対策は Douyin より大幅に厳しく、純粋な HTTP リクエストはブロックされます。本プロジェクトでも TikTok の Web 署名（X-Bogus / X-Gnarly）を Python だけで再実装しようと試みましたが、`item_list` エンドポイントは実ブラウザセッション由来の `msToken` まで要求するため、スクリプト単体では安定して取得できず、最終的にこの方式は断念しました。

> そのため TikTok については、**ローカルの実 Chrome を駆動する**方式に切り替えています。正規のログイン済みセッションをブラウザ自身が提供するため、署名や対策の問題を回避できます。これが TikTok のセットアップ手順だけ他の 2 つと異なる理由です。

## インストール

Python 3.8 以上が必要です。

```bash
pip install -r requirements.txt
```

TikTok を使う場合はさらに Playwright（ブラウザ操作用）が必要です。

```bash
pip install playwright
```

> 本プロジェクトは**既にインストールされている Chrome** を使用するため、`playwright install chromium` を実行する**必要はありません**。

## 使い方

### TikTok

TikTok はまず Chrome をデバッグモードで起動し、ログイン済みのブラウザセッションをツールにアタッチさせる必要があります。

1. **Chrome のウィンドウをすべて閉じてから**、以下のコマンドでデバッグフラグ付きの Chrome を起動します。

   **Windows:**

   ```bash
   "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\chrome-debug"
   ```

   **macOS:**

   ```bash
   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="$HOME/chrome-debug"
   ```

   **Linux:**

   ```bash
   google-chrome --remote-debugging-port=9222 --user-data-dir="$HOME/chrome-debug"
   ```

2. 起動した Chrome で **TikTok にログイン**し、対象ユーザーのプロフィールが普通に閲覧できることを確認します。
   このウィンドウはダウンロード中ずっと**開いたまま**にしてください。ダウンロード中に他のサイトを開くのは避けてください。

3. 別のターミナルを開いてサーバーを起動します。

   ```bash
   python web_app.py
   ```

4. ブラウザで `http://localhost:5001` を開き、TikTok のプロフィール URL
   （`https://www.tiktok.com/@username`）を貼り付け、必要なら日付範囲を設定して **「リスト取得」** をクリックします。
   ツールがデバッグモードの Chrome を操作してプロフィールを開き、自動でスクロールしながら投稿を収集します。

5. 欲しい投稿にチェックを入れて **「ダウンロード開始」** をクリックします。

> 回線が遅いと、最後までスクロールして「これ以上投稿がない」と判定するまで 10 秒以上かかることがあります。これは正常な動作です。

### Instagram

1. ブラウザで Instagram にログインし、[Cookies Editor](https://chromewebstore.google.com/detail/cookies-editor/iphcomljdfghbkdcfndaijbokpgddeno) などの拡張機能で Cookie をエクスポートします。
2. サーバーを起動します。

   ```bash
   python web_app.py
   ```

   ブラウザで `http://localhost:5001` を開きます。

3. エクスポートした Cookie を画面の Cookie 欄に貼り付けます。
4. プロフィール URL を貼り付けます：`https://www.instagram.com/ユーザー名/`
5. （任意）開始日・終了日を設定します。
6. **「リスト取得」** をクリックし、欲しい投稿にチェックを入れて **「ダウンロード開始」** をクリックします。

### Douyin（抖音）

Instagram と同じ流れです。

1. Douyin の Web 版にログインし、[Cookies Editor](https://chromewebstore.google.com/detail/cookies-editor/iphcomljdfghbkdcfndaijbokpgddeno) などで Cookie をエクスポートします。
2. サーバーを起動します。

   ```bash
   python web_app.py
   ```

3. `http://localhost:5001` を開き、Cookie を貼り付けたうえでプロフィール URL を入力します：
   - `https://v.douyin.com/xxx/` または
   - `https://www.douyin.com/user/xxx`
4. （任意）日付範囲を設定します。
5. **「リスト取得」** → チェック → **「ダウンロード開始」** の順にクリックします。

## ファイル構成

```
保存先パス/
  ユーザー名/
    video/
      2026-01-01_キャプション.mp4
    image/
      2026-01-02_カルーセルのキャプション/
        1.jpg
        2.jpg
```

## 注意事項・免責

- 本プロジェクトは**個人の学習およびバックアップ用途**のみを想定しています。商用利用・大量スクレイピング・他者の権利を侵害する行為には使用しないでください。
- コンテンツ制作者の権利を尊重し、各プラットフォームの利用規約を遵守してください。
- 本ツールの使用によって生じたいかなる結果についても、利用者自身が責任を負うものとします。
- Cookie やセッショントークンには有効期限があります。失効した場合は再度エクスポートまたは再ログインしてください。
- プラットフォームに負荷をかけないよう、リクエスト頻度は節度を持って利用してください。

## ライセンス

[MIT](https://opensource.org/licenses/MIT) ライセンスのもとで公開しています。

Douyin のダウンロードコアは [jiji262/douyin-downloader](https://github.com/jiji262/douyin-downloader)（MIT）をベースにしており、元のライセンス表示と著作権表示はそのまま保持しています。原作者の方々に感謝いたします。
