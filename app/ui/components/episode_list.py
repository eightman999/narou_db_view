"""
エピソード一覧を表示するUIコンポーネント
"""
import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import time
from bs4 import BeautifulSoup
from app.utils.logger_manager import get_logger

# ロガーの設定
logger = get_logger('EpisodeListView')


class EpisodeListView(ttk.Frame):
    """エピソード一覧を表示するビュークラス"""

    def __init__(self, parent, font_name, font_size, bg_color, novel_manager):
        """
        初期化

        Args:
            parent: 親ウィジェット
            font_name: フォント名
            font_size: フォントサイズ
            bg_color: 背景色
            novel_manager: 小説マネージャ
        """
        super().__init__(parent)
        self.parent = parent
        self.font_name = font_name
        self.font_size = font_size
        self.bg_color = bg_color
        self.novel_manager = novel_manager

        # 状態管理
        self.current_ncode = None
        self.episodes = []

        # UIコンポーネント
        self.scroll_canvas = None
        self.scrollable_frame = None
        self.novel_title_label = None
        self.list_display_frame = None

        # UIの初期化
        self.init_ui()

    def init_ui(self):
        """UIコンポーネントの初期化"""
        # 小説タイトル表示
        self.novel_title_label = tk.Label(
            self,
            text="エピソード一覧",
            font=(self.font_name, 14, "bold"),
            bg="#F0F0F0"
        )
        self.novel_title_label.pack(fill="x", pady=10, padx=10)

        # 戻るボタン
        back_button = ttk.Button(
            self,
            text="小説一覧に戻る",
            command=self.on_back_click
        )
        back_button.pack(anchor="w", padx=10, pady=5)

        # キャンバスとスクロールバー
        self.scroll_canvas = tk.Canvas(self, bg="#F0F0F0")
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.scroll_canvas.yview)
        self.scrollable_frame = ttk.Frame(self.scroll_canvas)

        self.scroll_canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.scroll_canvas.configure(yscrollcommand=scrollbar.set)

        self.scroll_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # スクロールイベントを設定
        self.configure_scroll_event()

        # エピソード表示フレーム
        self.list_display_frame = tk.Frame(self.scrollable_frame, bg="#F0F0F0")
        self.list_display_frame.pack(fill="x", expand=True, padx=10)

    def configure_scroll_event(self):
        """スクロールイベントの設定"""
        # スクロールイベントがトリガーされた回数を制限するための変数
        self.last_scroll_time = 0
        self.scroll_delay = 100  # ミリ秒単位

        def throttled_scroll_event(event):
            current_time = int(time.time() * 1000)

            # 前回のスクロールから一定時間経過していない場合はイベントを無視
            if current_time - self.last_scroll_time < self.scroll_delay:
                return "break"

            self.last_scroll_time = current_time

            # 通常のスクロール処理
            if event.delta > 0:
                self.scroll_canvas.yview_scroll(-1, "units")
            else:
                self.scroll_canvas.yview_scroll(1, "units")

            return "break"

        # マウスホイールイベントをバインド
        self.scroll_canvas.bind_all("<MouseWheel>", throttled_scroll_event)

    def show_episodes(self, ncode):
        """
        エピソード一覧を表示

        Args:
            ncode: 小説コード
        """
        self.current_ncode = ncode

        # スクロール位置をリセット
        self.scroll_canvas.yview_moveto(0)

        # ローディング表示
        self.show_loading()

        # エピソードデータを取得（バックグラウンドスレッドで）
        threading.Thread(target=self.load_episodes, args=(ncode,)).start()

    def show_loading(self):
        """ローディング表示"""
        # 前のリストをクリア
        for widget in self.list_display_frame.winfo_children():
            widget.destroy()

        # ローディングメッセージ
        loading_label = tk.Label(
            self.list_display_frame,
            text="エピソードを読み込んでいます...",
            bg="#F0F0F0",
            font=(self.font_name, 12)
        )
        loading_label.pack(pady=20)

    def load_episodes(self, ncode):
        """
        エピソードデータの読み込み（バックグラウンドスレッド用）

        Args:
            ncode: 小説コード
        """
        try:
            # 小説情報を取得
            novel = self.novel_manager.get_novel(ncode)
            if not novel:
                raise ValueError(f"小説 {ncode} が見つかりません")

            # エピソード一覧を取得
            self.episodes = self.novel_manager.get_episodes(ncode)

            # エピソード番号でソート
            self.episodes.sort(key=lambda ep: int(ep[0]))

            # UIの更新はメインスレッドで行う
            self.after(0, lambda: self.update_ui(novel))

        except Exception as e:
            logger.error(f"エピソードデータの読み込みエラー: {e}")
            # エラー表示
            self.after(0, lambda: self.show_error(f"エピソードの読み込みに失敗しました: {e}"))

    def update_ui(self, novel):
        """
        UIの更新

        Args:
            novel: 小説情報
        """
        # 小説タイトルを更新
        title_text = f"{novel[1]}"
        if novel[2]:  # 作者名がある場合
            title_text += f" (作者: {novel[2]})"
        self.novel_title_label.config(text=title_text)

        # 前のリストをクリア
        for widget in self.list_display_frame.winfo_children():
            widget.destroy()

        # エピソードがない場合
        if not self.episodes:
            no_episodes_label = tk.Label(
                self.list_display_frame,
                text="エピソードがありません",
                bg="#F0F0F0",
                font=(self.font_name, 12)
            )
            no_episodes_label.pack(pady=20)
            return

        # エピソード一覧を表示
        for episode in self.episodes:
            episode_no, episode_title, _ = episode

            # エピソードフレーム
            episode_frame = tk.Frame(self.list_display_frame, bg="#F0F0F0")
            episode_frame.pack(fill="x", pady=2)

            # エピソードラベル
            label_text = f"第{episode_no}話: {episode_title}"
            episode_label = tk.Label(
                episode_frame,
                text=label_text,
                bg="#F0F0F0",
                anchor="w",
                font=(self.font_name, 10)
            )
            episode_label.pack(side="left", padx=5, fill="x", expand=True)

            # クリックイベント
            episode_label.bind("<Button-1>", lambda e, ep=episode: self.on_episode_click(ep))

            # ホバーエフェクト
            episode_label.bind("<Enter>", lambda e, label=episode_label: label.config(bg="#E0E0E0"))
            episode_label.bind("<Leave>", lambda e, label=episode_label: label.config(bg="#F0F0F0"))

    def on_episode_click(self, episode):
        """
        エピソードがクリックされたときの処理

        Args:
            episode: エピソードデータ
        """
        # 既読情報を更新
        self.novel_manager.update_last_read(self.current_ncode, episode[0])

        # エピソードビューワーを表示
        self.show_episode_viewer(episode)

    def show_episode_viewer(self, episode):
        """
        エピソードビューワーを表示

        Args:
            episode: エピソードデータ
        """
        episode_no, episode_title, episode_body = episode

        def show_episode(episode_body):
            """エピソードコンテンツを表示"""
            # 既存のコンテンツをクリア
            scrolled_text.config(state=tk.NORMAL)
            scrolled_text.delete(1.0, tk.END)

            # HTMLコンテンツを解析
            soup = BeautifulSoup(episode_body, "html.parser")

            # 空の段落を削除
            for p in soup.find_all('p'):
                if not p.get_text(strip=True) and not p.attrs:
                    p.decompose()

            # クリーンなテキストコンテンツを抽出
            text_content = soup.get_text()

            # テキストをスクロールテキストウィジェットに挿入
            scrolled_text.insert(tk.END, text_content)
            scrolled_text.config(state=tk.DISABLED, bg=self.bg_color)

        def next_episode(event=None):
            """次のエピソードを表示"""
            current_index = self.episodes.index(episode)
            if current_index < len(self.episodes) - 1:
                new_episode = self.episodes[current_index + 1]
                # 既読情報を更新
                self.novel_manager.update_last_read(self.current_ncode, new_episode[0])
                # エピソードコンテンツを更新
                show_episode(new_episode[2])
                # ウィンドウタイトルを更新
                episode_window.title(f"第{new_episode[0]}話: {new_episode[1]}")

        def previous_episode(event=None):
            """前のエピソードを表示"""
            current_index = self.episodes.index(episode)
            if current_index > 0:
                new_episode = self.episodes[current_index - 1]
                # 既読情報を更新
                self.novel_manager.update_last_read(self.current_ncode, new_episode[0])
                # エピソードコンテンツを更新
                show_episode(new_episode[2])
                # ウィンドウタイトルを更新
                episode_window.title(f"第{new_episode[0]}話: {new_episode[1]}")

        # エピソードコンテンツを表示する新しいウィンドウを作成
        episode_window = tk.Toplevel(self)
        episode_window.title(f"第{episode_no}話: {episode_title}")
        episode_window.geometry("800x600")

        # エピソードコンテンツを表示するスクロールテキストウィジェットを作成
        scrolled_text = scrolledtext.ScrolledText(
            episode_window,
            wrap=tk.WORD,
            font=(self.font_name, self.font_size)
        )
        scrolled_text.pack(fill=tk.BOTH, expand=True)

        # ナビゲーションボタンフレーム
        nav_frame = tk.Frame(episode_window)
        nav_frame.pack(fill=tk.X, pady=5)

        # 前のエピソードボタン
        prev_button = ttk.Button(
            nav_frame,
            text="前のエピソード",
            command=previous_episode
        )
        prev_button.pack(side=tk.LEFT, padx=10)

        # 次のエピソードボタン
        next_button = ttk.Button(
            nav_frame,
            text="次のエピソード",
            command=next_episode
        )
        next_button.pack(side=tk.RIGHT, padx=10)

        # 初期エピソードコンテンツを表示
        show_episode(episode_body)

        # 左右の矢印キーでエピソードを移動するバインド
        episode_window.bind("<Right>", next_episode)
        episode_window.bind("<Left>", previous_episode)

    def on_back_click(self):
        """戻るボタンがクリックされたときの処理"""
        # カスタムイベントを発生させる
        self.event_generate("<<ShowNovelList>>")

    def show_error(self, message):
        """エラーメッセージを表示"""
        # 前のリストをクリア
        for widget in self.list_display_frame.winfo_children():
            widget.destroy()

        # エラーメッセージを表示
        error_label = tk.Label(
            self.list_display_frame,
            text=message,
            bg="#F0F0F0",
            fg="red",
            font=(self.font_name, 12)
        )
        error_label.pack(pady=20)

    def update_settings(self, font_name, font_size, bg_color):
        """
        設定の更新

        Args:
            font_name: フォント名
            font_size: フォントサイズ
            bg_color: 背景色
        """
        self.font_name = font_name
        self.font_size = font_size
        self.bg_color = bg_color