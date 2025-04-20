"""
小説データをHTML形式に書き出すモジュール
Androidで読みやすいフォーマットでエクスポートします
"""
import os
import sqlite3
import datetime
import shutil
from pathlib import Path
import json
from app.utils.logger_manager import get_logger
from app.database.db_handler import DatabaseHandler
from config import DATABASE_PATH, PACKAGE_ASSETS_DIR

# ロガーの設定
logger = get_logger('HTMLExporter')


class HTMLExporter:
    """
    小説データをHTML形式でエクスポートするクラス
    assets_dirに配置されたスタイルやスクリプトを使用します
    """

    def __init__(self, export_dir='html_export'):
        """
        初期化

        Args:
            export_dir (str): エクスポート先ディレクトリ
        """
        self.db_path = DATABASE_PATH
        self.export_dir = export_dir
        self.db_handler = DatabaseHandler()

        # パッケージのassets_dirパス（CSSやJSが格納されている場所）
        self.package_assets_dir = PACKAGE_ASSETS_DIR

        # エクスポート先ディレクトリの作成
        self.base_dir = Path(self.export_dir)
        self.base_dir.mkdir(exist_ok=True)

        # 必要なサブディレクトリの作成
        self.novels_dir = self.base_dir / 'novels'
        self.novels_dir.mkdir(exist_ok=True)

        self.assets_dir = self.base_dir / 'assets'
        self.assets_dir.mkdir(exist_ok=True)

        # 外部アセットファイルをコピー
        self._copy_asset_files()

        # Service WorkerとManifestを作成
        self._create_service_worker()
        self._create_manifest_json()

    def _copy_asset_files(self):
        """
        外部アセットファイル（CSS、JS）をエクスポート先にコピー
        """
        # パッケージのassetsディレクトリが存在するか確認
        if not self.package_assets_dir.exists():
            logger.warning(f"アセットディレクトリが見つかりません: {self.package_assets_dir}")
            logger.info("アセットディレクトリを作成します")
            self.package_assets_dir.mkdir(exist_ok=True)

        # CSS、JSの各ファイルをチェック
        css_file = self.package_assets_dir / 'style.css'
        js_file = self.package_assets_dir / 'script.js'

        # CSSファイルをコピー
        if css_file.exists():
            shutil.copy(css_file, self.assets_dir / 'style.css')
            logger.info(f"CSSファイルをコピーしました: {css_file} -> {self.assets_dir / 'style.css'}")
        else:
            logger.warning(f"CSSファイルが見つかりません: {css_file}")
            logger.info("CSSファイルは別途用意する必要があります")

        # JSファイルをコピー
        if js_file.exists():
            shutil.copy(js_file, self.assets_dir / 'script.js')
            logger.info(f"JavaScriptファイルをコピーしました: {js_file} -> {self.assets_dir / 'script.js'}")
        else:
            logger.warning(f"JavaScriptファイルが見つかりません: {js_file}")
            logger.info("JavaScriptファイルは別途用意する必要があります")

    def _create_service_worker(self):
        """
        Service Workerファイルを作成
        パッケージ内のテンプレートを使用するか、シンプルなバージョンを作成
        """
        # Service Workerファイルのパス
        sw_path = self.base_dir / 'service-worker.js'

        # パッケージ内のテンプレートをチェック
        sw_template = self.package_assets_dir / 'service-worker.js'

        if sw_template.exists():
            # テンプレートがある場合はコピー
            shutil.copy(sw_template, sw_path)
            logger.info(f"Service Workerテンプレートをコピーしました: {sw_template} -> {sw_path}")
        else:
            # テンプレートがない場合は基本的な内容を生成
            logger.info(f"Service Workerテンプレートが見つからないため、基本バージョンを作成します: {sw_path}")

            # キャッシュするリソースのリスト
            cached_urls = [
                './',
                './index.html',
                './assets/style.css',
                './assets/script.js',
                './manifest.json'
            ]

            # 各キャッシュURLをJSON文字列化
            cache_list = ',\n    '.join([f"'{url}'" for url in cached_urls])

            # Service Workerの基本構造
            simple_sw = f"""// 小説ライブラリ用 Service Worker
const CACHE_NAME = 'novel-library-cache-v1';

// キャッシュするリソースのリスト
const urlsToCache = [
    {cache_list}
];

// Service Workerインストール時
self.addEventListener('install', event => {{
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {{
                console.log('キャッシュを開きました');
                return cache.addAll(urlsToCache);
            }})
    );
}});

// フェッチ時の処理（キャッシュファースト）
self.addEventListener('fetch', event => {{
    event.respondWith(
        caches.match(event.request)
            .then(response => {{
                if (response) {{
                    return response;
                }}
                return fetch(event.request);
            }})
    );
}});

// 古いキャッシュの削除
self.addEventListener('activate', event => {{
    const cacheWhitelist = [CACHE_NAME];
    event.waitUntil(
        caches.keys().then(cacheNames => {{
            return Promise.all(
                cacheNames.map(cacheName => {{
                    if (cacheWhitelist.indexOf(cacheName) === -1) {{
                        return caches.delete(cacheName);
                    }}
                }})
            );
        }})
    );
}});
"""
            # ファイルに書き込み
            with open(sw_path, 'w', encoding='utf-8') as f:
                f.write(simple_sw)

            logger.info(f"基本的なService Workerファイルを作成しました: {sw_path}")

    def _create_manifest_json(self):
        """
        PWA用のmanifest.jsonファイルを作成
        パッケージ内のテンプレートを使用するか、シンプルなバージョンを作成
        """
        # マニフェストファイルのパス
        manifest_path = self.base_dir / 'manifest.json'

        # パッケージ内のテンプレートをチェック
        manifest_template = self.package_assets_dir / 'manifest.json'

        if manifest_template.exists():
            # テンプレートがある場合はコピー
            shutil.copy(manifest_template, manifest_path)
            logger.info(f"マニフェストテンプレートをコピーしました: {manifest_template} -> {manifest_path}")
        else:
            # テンプレートがない場合は基本的な内容を生成
            logger.info(f"マニフェストテンプレートが見つからないため、基本バージョンを作成します: {manifest_path}")

            # 基本的なマニフェスト情報
            manifest_data = {
                "name": "小説ライブラリ",
                "short_name": "小説App",
                "description": "オフラインで読める小説ライブラリ",
                "start_url": "./index.html",
                "display": "standalone",
                "background_color": "#ffffff",
                "theme_color": "#4a4a4a",
                "icons": [
                    {
                        "src": "assets/icon-192.png",
                        "sizes": "192x192",
                        "type": "image/png"
                    },
                    {
                        "src": "assets/icon-512.png",
                        "sizes": "512x512",
                        "type": "image/png"
                    }
                ]
            }

            # JSONファイルとして書き込み
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest_data, f, ensure_ascii=False, indent=2)

            logger.info(f"基本的なマニフェストファイルを作成しました: {manifest_path}")

    def _create_simple_icons(self):
        """
        シンプルなアイコンを生成（PWA用）
        """
        try:
            # PILが利用可能か確認
            try:
                from PIL import Image, ImageDraw, ImageFont
                pil_available = True
            except ImportError:
                logger.warning("PILモジュールが見つからないため、サンプルアイコンの作成をスキップします")
                logger.info("アイコンファイルは別途用意する必要があります")
                return

            # アイコン用のディレクトリを作成
            icons_dir = self.assets_dir
            icons_dir.mkdir(exist_ok=True)

            # アイコンテンプレートをチェック
            icon_template_192 = self.package_assets_dir / 'icon-192.png'
            icon_template_512 = self.package_assets_dir / 'icon-512.png'

            # テンプレートが存在する場合はコピー
            if icon_template_192.exists() and icon_template_512.exists():
                shutil.copy(icon_template_192, self.assets_dir / 'icon-192.png')
                shutil.copy(icon_template_512, self.assets_dir / 'icon-512.png')
                logger.info("アイコンテンプレートをコピーしました")
                return

            # テンプレートがない場合は新規作成
            logger.info("アイコンテンプレートが見つからないため、シンプルなアイコンを作成します")

            # 背景色とテキスト色
            bg_color = (74, 74, 74)  # ヘッダーと同じグレー
            text_color = (255, 255, 255)  # 白

            # 192x192サイズのアイコン
            img_192 = Image.new('RGB', (192, 192), bg_color)
            draw_192 = ImageDraw.Draw(img_192)

            # 512x512サイズのアイコン
            img_512 = Image.new('RGB', (512, 512), bg_color)
            draw_512 = ImageDraw.Draw(img_512)

            # フォントが利用可能か確認
            try:
                # 適切なフォントを探す
                font_paths = [
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
                    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",  # macOS
                    "C:\\Windows\\Fonts\\meiryo.ttc",  # Windows
                    "Arial"  # フォールバック
                ]

                font_path = None
                for path in font_paths:
                    if os.path.exists(path):
                        font_path = path
                        break

                # フォントでテキスト描画
                if font_path:
                    font_192 = ImageFont.truetype(font_path, 80)
                    draw_192.text((96, 96), "小", fill=text_color, font=font_192, anchor="mm")

                    font_512 = ImageFont.truetype(font_path, 200)
                    draw_512.text((256, 256), "小", fill=text_color, font=font_512, anchor="mm")
                else:
                    # フォントが見つからない場合は円を描画
                    raise FileNotFoundError("適切なフォントが見つかりません")
            except Exception as e:
                logger.warning(f"テキスト描画に失敗しました: {e}")
                # 円を描画（フォールバック）
                draw_192.ellipse((48, 48, 144, 144), fill=text_color)
                draw_512.ellipse((128, 128, 384, 384), fill=text_color)

            # アイコンを保存
            img_192.save(self.assets_dir / 'icon-192.png')
            img_512.save(self.assets_dir / 'icon-512.png')

            logger.info("シンプルなアイコンファイルを作成しました")

        except Exception as e:
            logger.warning(f"アイコン生成に失敗しました: {e}")
            logger.info("アイコンファイルは別途用意する必要があります")

    def export_all_novels(self):
        """
        全ての小説をエクスポート

        Returns:
            bool: 成功したかどうか
        """
        try:
            # 小説リストの取得
            novels = self.db_handler.get_all_novels()

            if not novels:
                logger.warning("エクスポートする小説がありません")
                return False

            # インデックスページの作成
            logger.info("インデックスページを作成します...")
            self._create_index_page(novels)

            # 各小説のページを作成
            logger.info(f"合計 {len(novels)} 作品をエクスポートします")
            for i, novel in enumerate(novels):
                try:
                    ncode = novel[0]
                    logger.info(f"小説のエクスポート中 ({i+1}/{len(novels)}): {ncode}")
                    self.export_novel(ncode)
                except Exception as e:
                    logger.error(f"小説 {ncode} のエクスポート中にエラーが発生しました: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

            # PWA用のアイコンを作成
            self._create_simple_icons()

            logger.info(f"全ての小説のエクスポートが完了しました。合計: {len(novels)}作品")
            return True

        except Exception as e:
            logger.error(f"小説のエクスポートに失敗しました: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def export_novel(self, ncode):
        """
        指定された小説をエクスポート

        Args:
            ncode (str): 小説コード

        Returns:
            bool: 成功したかどうか
        """
        try:
            # 小説情報の取得
            novel = self.db_handler.get_novel_by_ncode(ncode)
            if not novel:
                logger.warning(f"小説 {ncode} が見つかりません")
                return False

            # 小説タイトルの取得
            title = novel[1] if novel[1] else "無題の小説"
            author = novel[2] if novel[2] else "著者不明"
            synopsis = novel[7] if len(novel) > 7 and novel[7] else "あらすじはありません"

            # エピソードの取得
            episodes = self.db_handler.get_episodes_by_ncode(ncode)
            if not episodes:
                logger.warning(f"小説 {ncode} にはエピソードがありません")
                episodes = []

            # 小説用ディレクトリの作成
            novel_dir = self.novels_dir / ncode
            novel_dir.mkdir(exist_ok=True)

            # 小説情報ページの作成
            self._create_novel_page(novel_dir, novel, episodes)

            # 各エピソードのページを作成
            logger.info(f"小説 {ncode} のエピソード {len(episodes)}話を処理中...")
            for episode in episodes:
                episode_no, title, body = episode
                self._create_episode_page(novel_dir, novel, episode, episodes)

            logger.info(f"小説 {ncode} のエクスポートが完了しました。エピソード数: {len(episodes)}")
            return True

        except Exception as e:
            logger.error(f"小説 {ncode} のエクスポート中にエラーが発生しました: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _create_index_page(self, novels):
        """
        インデックスページを作成

        Args:
            novels (list): 小説のリスト
        """
        # 現在日時を取得
        now = datetime.datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')

        html_content = f"""
        <!DOCTYPE html>
        <html lang="ja">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>小説ライブラリ</title>
            <link rel="stylesheet" href="assets/style.css">
            <script src="assets/script.js" defer></script>
            <link rel="manifest" href="manifest.json">
        </head>
        <body>
            <header>
                <div class="container">
                    <h1>小説ライブラリ</h1>
                </div>
            </header>
            
            <main class="container">
                <div class="search-container">
                    <input type="text" class="search-box" placeholder="小説を検索...">
                </div>
                
                <div class="novel-list">
        """

        # 小説カードを追加
        for novel in novels:
            ncode = novel[0]
            title = novel[1] if novel[1] else "無題の小説"
            author = novel[2] if novel[2] else "著者不明"
            updated_at = novel[3] if novel[3] else "更新日不明"
            episodes = novel[5] if len(novel) > 5 and novel[5] is not None else 0
            synopsis = novel[7] if len(novel) > 7 and novel[7] else "あらすじはありません"

            # あらすじの短縮
            if len(synopsis) > 150:
                synopsis = synopsis[:150] + "..."

            html_content += f"""
            <div class="novel-card">
                <h3><a href="novels/{ncode}/index.html">{title}</a></h3>
                <div class="novel-info">作者: {author} | エピソード数: {episodes}</div>
                <div class="novel-info">更新: {updated_at}</div>
                <div class="novel-synopsis">{synopsis}</div>
            </div>
            """

        html_content += f"""
                </div>
            </main>
            
            <button class="back-to-top">↑</button>
            
            <footer class="container">
                <p>エクスポート日時: {now}</p>
            </footer>

            <script>
                // Service Workerの登録
                if ('serviceWorker' in navigator) {{
                    window.addEventListener('load', function() {{
                        navigator.serviceWorker.register('./service-worker.js')
                            .then(function(registration) {{
                                console.log('Service Worker登録成功:', registration.scope);
                            }})
                            .catch(function(error) {{
                                console.log('Service Worker登録失敗:', error);
                            }});
                    }});
                }}
            </script>
        </body>
        </html>
        """

        # ファイルに書き込み
        index_path = self.base_dir / 'index.html'
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        logger.info(f"インデックスページを作成しました: {index_path}")

    def _create_novel_page(self, novel_dir, novel, episodes):
        """
        小説情報ページを作成

        Args:
            novel_dir (Path): 小説ディレクトリのパス
            novel (tuple): 小説情報
            episodes (list): エピソードのリスト
        """
        ncode = novel[0]
        title = novel[1] if novel[1] else "無題の小説"
        author = novel[2] if novel[2] else "著者不明"
        updated_at = novel[3] if novel[3] else "更新日不明"
        synopsis = novel[7] if len(novel) > 7 and novel[7] else "あらすじはありません"

        # 目次を作成
        episodes_html = ""
        for episode in sorted(episodes, key=lambda x: int(x[0]) if x[0].isdigit() else 0):
            episode_no, episode_title, _ = episode
            episodes_html += f"""
            <li class="episode-item">
                <a href="episode_{episode_no}.html" class="episode-link">第{episode_no}話: {episode_title}</a>
            </li>
            """

        html_content = f"""
        <!DOCTYPE html>
        <html lang="ja">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{title} - 小説ライブラリ</title>
            <link rel="stylesheet" href="../../assets/style.css">
            <script src="../../assets/script.js" defer></script>
        </head>
        <body>
            <header>
                <div class="container">
                    <h1>{title}</h1>
                </div>
            </header>
            
            <main class="container">
                <a href="../../index.html" class="back-link">← 小説一覧に戻る</a>
                
                <div class="novel-meta">
                    <h2>{title}</h2>
                    <p>作者: {author}</p>
                    <p>最終更新: {updated_at}</p>
                    <p>エピソード数: {len(episodes)}</p>
                    <h3>あらすじ</h3>
                    <p>{synopsis}</p>
                </div>
                
                <div class="search-container">
                    <input type="text" class="search-box" placeholder="エピソードを検索...">
                </div>
                
                <h3>目次</h3>
                <ul class="episode-list">
                    {episodes_html}
                </ul>
            </main>
            
            <button class="back-to-top">↑</button>
        </body>
        </html>
        """

        # ファイルに書き込み
        index_path = novel_dir / 'index.html'
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        logger.info(f"小説情報ページを作成しました: {index_path}")

    def _create_episode_page(self, novel_dir, novel, episode, all_episodes):
        """
        エピソードページを作成

        Args:
            novel_dir (Path): 小説ディレクトリのパス
            novel (tuple): 小説情報
            episode (tuple): エピソード情報
            all_episodes (list): すべてのエピソードのリスト
        """
        ncode = novel[0]
        novel_title = novel[1] if novel[1] else "無題の小説"
        author = novel[2] if novel[2] else "著者不明"

        episode_no, episode_title, episode_body = episode

        # 本文の整形
        processed_body = ""
        if episode_body:
            # HTML除去
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(episode_body, 'html.parser')
            clean_text = soup.get_text()

            # 段落ごとに分割して整形
            paragraphs = clean_text.split('\n\n')
            processed_paragraphs = []

            for paragraph in paragraphs:
                paragraph = paragraph.strip()
                if paragraph:
                    processed_paragraphs.append(f'<p>{paragraph}</p>')

            processed_body = '\n'.join(processed_paragraphs)
        else:
            processed_body = "<p>本文がありません</p>"

        # 前後のエピソードへのリンクを準備
        sorted_episodes = sorted(all_episodes, key=lambda x: int(x[0]) if x[0].isdigit() else 0)
        episode_index = next((i for i, ep in enumerate(sorted_episodes) if ep[0] == episode_no), -1)

        prev_link = ""
        next_link = ""

        if episode_index > 0:
            prev_episode = sorted_episodes[episode_index - 1]
            prev_no = prev_episode[0]
            prev_link = f'<a href="episode_{prev_no}.html" class="nav-button">← 前話: 第{prev_no}話</a>'
        else:
            prev_link = '<span></span>'

        if episode_index < len(sorted_episodes) - 1:
            next_episode = sorted_episodes[episode_index + 1]
            next_no = next_episode[0]
            next_link = f'<a href="episode_{next_no}.html" class="nav-button">次話: 第{next_no}話 →</a>'
        else:
            next_link = '<span></span>'

        # 読書設定パネル
        settings_panel = """
        <div class="reading-settings">
            <button class="settings-toggle">⚙</button>
            <div class="settings-group">
                <h3>テーマ</h3>
                <select id="theme-selector" class="theme-selector">
                    <option value="default">デフォルト</option>
                    <option value="light-theme">ライト</option>
                    <option value="dark-theme">ダーク</option>
                    <option value="sepia-theme">セピア</option>
                </select>
            </div>
            
            <div class="settings-group">
                <h3>フォント</h3>
                <select id="font-selector" class="font-selector">
                    <option value="default">デフォルト</option>
                    <option value="'Hiragino Mincho ProN', serif">明朝体</option>
                    <option value="'Hiragino Sans', sans-serif">ゴシック体</option>
                    <option value="'Meiryo', sans-serif">メイリオ</option>
                    <option value="'Yu Gothic', sans-serif">游ゴシック</option>
                </select>
            </div>
            
            <div class="settings-group">
                <h3>行間</h3>
                <input type="range" id="line-height-slider" class="line-height-slider" min="1.2" max="2.4" step="0.1" value="1.8">
            </div>
        </div>"""

        html_content = f"""
        <!DOCTYPE html>
        <html lang="ja">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>第{episode_no}話: {episode_title} - {novel_title}</title>
            <link rel="stylesheet" href="../../assets/style.css">
            <script src="../../assets/script.js" defer></script>
        </head>
        <body data-novel-id="{ncode}" data-episode-id="{episode_no}">
            <header>
                <div class="container">
                    <h1>{novel_title}</h1>
                    <h2>第{episode_no}話: {episode_title}</h2>
                </div>
            </header>
            
            <main class="container">
                <a href="index.html" class="back-link">← 目次に戻る</a>
                
                <div class="episode-content">
                    {processed_body}
                </div>
                
                <div class="episode-nav">
                    {prev_link}
                    {next_link}
                </div>
            </main>
            
            {settings_panel}
            
            <div class="font-size-controls">
                <button id="decrease-font" class="font-button">A-</button>
                <button id="increase-font" class="font-button">A+</button>
            </div>
            
            <button class="back-to-top">↑</button>
        </body>
        </html>
        """

        # ファイルに書き込み
        episode_path = novel_dir / f'episode_{episode_no}.html'
        with open(episode_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        logger.info(f"エピソードページを作成しました: {episode_path}")

    def create_readme(self):
        """
        使い方などを説明したREADMEファイルを作成
        """
        # 現在日時を取得
        now = datetime.datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')

        readme_content = f"""# 小説ライブラリ - 使い方

## 概要
このHTMLエクスポートは、データベースに保存された小説データをオフラインで読めるようにHTMLに変換したものです。
Android端末のブラウザで開くことで、小説を快適に読むことができます。

## 使い方

### インストール方法
1. このフォルダ全体をAndroid端末に転送します
2. ブラウザで「index.html」を開きます
3. PWA対応ブラウザ（ChromeやEdgeなど）であれば、「ホーム画面に追加」からアプリのように使用できます

### 機能
- 小説一覧：トップページから全小説が閲覧できます
- 検索機能：タイトルや作者名で検索できます
- 読書設定：フォント、テーマ、行間などを調整できます
- 自動スクロール位置保存：前回読んでいた位置を自動的に記憶します
- ダークモード対応：システムの設定に応じて自動的に切り替わります

### 注意事項
- このエクスポートデータは定期的に更新する必要があります
- 画像などのリッチコンテンツには対応していません

## 更新履歴
- 初回エクスポート日時: {now}
"""

        # ファイルに書き込み
        readme_path = self.base_dir / 'README.txt'
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(readme_content)

        logger.info(f"READMEファイルを作成しました: {readme_path}")

    def export_as_zip(self, zip_filename='novel_library.zip'):
        """
        エクスポートディレクトリをZIPにまとめる

        Args:
            zip_filename (str): 出力するZIPファイル名

        Returns:
            str: 作成したZIPファイルのパス
        """
        import zipfile

        # READMEファイルを作成
        self.create_readme()

        # PWA用アイコンを作成（必要であれば）
        self._create_simple_icons()

        # ZIPファイルを作成
        zip_path = Path(zip_filename)
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(self.base_dir):
                for file in files:
                    file_path = Path(root) / file
                    rel_path = file_path.relative_to(self.base_dir)
                    zipf.write(file_path, str(rel_path))

        logger.info(f"エクスポートデータをZIPにまとめました: {zip_path}")
        return str(zip_path)


def run_export(export_dir='html_export', create_zip=True):
    """
    エクスポート処理を実行する単独関数

    Args:
        export_dir (str): エクスポート先ディレクトリ
        create_zip (bool): ZIPファイルを作成するかどうか

    Returns:
        bool: 成功したかどうか
    """
    try:
        # エクスポーターの初期化
        exporter = HTMLExporter(export_dir)

        # 全小説をエクスポート
        result = exporter.export_all_novels()

        if result and create_zip:
            # ZIPファイルにまとめる
            zip_path = exporter.export_as_zip()
            print(f"エクスポートが完了しました。ZIPファイル: {zip_path}")
        elif result:
            print(f"エクスポートが完了しました。ディレクトリ: {export_dir}")
        else:
            print("エクスポートに失敗しました。ログを確認してください。")

        return result

    except Exception as e:
        logger.error(f"エクスポート処理中にエラーが発生しました: {e}")
        import traceback
        logger.error(traceback.format_exc())
        print(f"エラー: {e}")
        return False


# コマンドラインから直接実行された場合
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='小説データをHTML形式にエクスポートします')
    parser.add_argument('--dir', default='html_export', help='エクスポート先ディレクトリ')
    parser.add_argument('--no-zip', action='store_true', help='ZIPファイルを作成しない')
    parser.add_argument('--ncode', help='特定の小説だけをエクスポート')

    args = parser.parse_args()

    if args.ncode:
        # 特定の小説のみエクスポート
        exporter = HTMLExporter(args.dir)
        result = exporter.export_novel(args.ncode)

        if result:
            print(f"小説 {args.ncode} のエクスポートが完了しました")

            if not args.no_zip:
                zip_path = exporter.export_as_zip(f"{args.ncode}_export.zip")
                print(f"ZIPファイルを作成しました: {zip_path}")
        else:
            print(f"小説 {args.ncode} のエクスポートに失敗しました")
    else:
        # 全小説をエクスポート
        run_export(args.dir, not args.no_zip)