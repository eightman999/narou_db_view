"""
更新された小説一覧を表示するUIコンポーネント
"""
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
from utils.logger_manager import get_logger

# ロガーの設定
logger = get_logger('UpdatePanel')


class UpdatePanel(ttk.Frame):
    """更新された小説一覧を表示するビュークラス"""

    def __init__(self, parent, update_manager, update_callback, on_complete_callback):
        """
        初期化

        Args:
            parent: 親ウィジェット
            update_manager: 更新マネージャ
            update_callback: 更新実行時のコールバック関数
            on_complete_callback: 更新完了時のコールバック関数
        """
        super().__init__(parent)
        self.parent = parent
        self.update_manager = update_manager
        self.update_callback = update_callback
        self.on_complete_callback = on_complete_callback

        # 状態管理
        self.shinchaku_novels = []

        # UIコンポーネント
        self.scroll_canvas = None
        self.scrollable_frame = None
        self.list_display_frame = None

        # UIの初期化
        self.init_ui()

    def init_ui(self):
        """UIコンポーネントの初期化"""
        # 見出し
        header_label = tk.Label(
            self,
            text="更新が必要な小説",
            font=("", 14, "bold"),
            bg="#F0F0F0"
        )
        header_label.pack(pady=10)

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

        # 一括更新ボタンフレーム
        button_frame = tk.Frame(self.scrollable_frame, bg="#F0F0F0")
        button_frame.pack(fill="x", pady=10, padx=10)

        # 一括更新ボタン
        update_all_button = ttk.Button(
            button_frame,
            text="すべての新着小説を更新",
            command=self.update_all_novels
        )
        update_all_button.pack(side="left", padx=5)

        # リスト表示フレーム
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

    def show_novels(self):
        """更新が必要な小説一覧を表示"""
        # スクロール位置をリセット
        self.scroll_canvas.yview_moveto(0)

        # ローディング表示
        self.show_loading()

        # 新着小説データを取得（バックグラウンドスレッドで）
        threading.Thread(target=self.load_shinchaku_novels).start()

    def show_loading(self):
        """ローディング表示"""
        # 前のリストをクリア
        for widget in self.list_display_frame.winfo_children():
            widget.destroy()

        # ローディングメッセージ
        loading_label = tk.Label(
            self.list_display_frame,
            text="新着小説を確認しています...",
            bg="#F0F0F0",
            font=("", 12)
        )
        loading_label.pack(pady=20)

    def load_shinchaku_novels(self):
        """新着小説データの読み込み（バックグラウンドスレッド用）"""
        try:
            # 新着情報を取得
            _, self.shinchaku_novels, _ = self.update_manager.check_shinchaku()

            # UIの更新はメインスレッドで行う
            self.after(0, self.update_ui)

        except Exception as e:
            logger.error(f"新着小説データの読み込みエラー: {e}")
            # エラー表示
            self.after(0, lambda: self.show_error(f"新着小説の読み込みに失敗しました: {e}"))

    def update_ui(self):
        """UIの更新"""
        # 前のリストをクリア
        for widget in self.list_display_frame.winfo_children():
            widget.destroy()

        # 新着小説がない場合
        if not self.shinchaku_novels:
            no_novels_label = tk.Label(
                self.list_display_frame,
                text="更新が必要な小説はありません",
                bg="#F0F0F0",
                font=("", 12)
            )
            no_novels_label.pack(pady=20)
            return

        # 更新情報を表示
        info_label = tk.Label(
            self.list_display_frame,
            text=f"{len(self.shinchaku_novels)}件の小説に更新があります",
            bg="#F0F0F0",
            font=("", 12)
        )
        info_label.pack(pady=10)

        # 新着小説一覧を表示
        for i, row in enumerate(self.shinchaku_novels):
            n_code, title, current_ep, total_ep, rating = row

            # 項目用フレーム
            item_frame = tk.Frame(self.list_display_frame, bg="#F0F0F0")
            item_frame.pack(fill="x", pady=2)

            # 現在の状態表示
            status_text = f"{current_ep}/{total_ep}話"
            status_label = tk.Label(
                item_frame,
                text=status_text,
                bg="#F0F0F0",
                width=10
            )
            status_label.pack(side="left", padx=5)

            # タイトルラベル
            title_label = tk.Label(
                item_frame,
                text=title,
                bg="#F0F0F0",
                anchor="w"
            )
            title_label.pack(side="left", padx=5, fill="x", expand=True)

            # 更新ボタン
            update_button = ttk.Button(
                item_frame,
                text="更新",
                width=8,
                command=lambda n=n_code, t=title, c=current_ep, to=total_ep, r=rating:
                self.update_novel(n, t, c, to, r)
            )
            update_button.pack(side="right", padx=5)

            # 欠落エピソード検索ボタン
            missing_button = ttk.Button(
                item_frame,
                text="欠落確認",
                width=8,
                command=lambda n=n_code: self.check_missing_episodes(n)
            )
            missing_button.pack(side="right", padx=5)

            # 奇数行と偶数行で背景色を変える
            if i % 2 == 1:
                item_frame.config(bg="#E8E8E8")
                status_label.config(bg="#E8E8E8")
                title_label.config(bg="#E8E8E8")

    def update_all_novels(self):
        """すべての新着小説を更新"""
        if not self.shinchaku_novels:
            messagebox.showinfo("情報", "更新が必要な小説はありません")
            return

        # 更新を実行（コールバック経由）
        if self.update_callback:
            self.update_callback(self.shinchaku_novels)

    def update_novel(self, n_code, title, current_ep, total_ep, rating):
        """
        単一の小説を更新

        Args:
            n_code: 小説コード
            title: タイトル
            current_ep: 現在のエピソード数
            total_ep: 総エピソード数
            rating: レーティング
        """
        # 更新を実行（コールバック経由）
        if self.update_callback:
            self.update_callback([(n_code, title, current_ep, total_ep, rating)])

    def check_missing_episodes(self, ncode):
        """
        欠落エピソードを確認

        Args:
            ncode: 小説コード
        """
        # ローディング表示
        messagebox.showinfo("情報", "欠落エピソードを確認しています。処理が完了するまでお待ちください。")

        # バックグラウンドスレッドで実行
        threading.Thread(target=self.execute_missing_check, args=(ncode,)).start()

    def execute_missing_check(self, ncode):
        """
        欠落エピソード確認の実行（バックグラウンドスレッド用）

        Args:
            ncode: 小説コード
        """
        try:
            # 欠落エピソードを検索
            missing_episodes = self.update_manager.update_manager.db_manager.find_missing_episodes(ncode)

            # UIの更新はメインスレッドで行う
            if missing_episodes:
                self.after(0, lambda: self.show_missing_episodes(ncode, missing_episodes))
            else:
                self.after(0, lambda: messagebox.showinfo("情報", "欠落エピソードは見つかりませんでした"))

        except Exception as e:
            logger.error(f"欠落エピソード確認エラー: {e}")
            self.after(0, lambda: messagebox.showerror("エラー", f"欠落エピソード確認中にエラーが発生しました: {e}"))

    def show_missing_episodes(self, ncode, missing_episodes):
        """
        欠落エピソード一覧を表示

        Args:
            ncode: 小説コード
            missing_episodes: 欠落エピソード番号のリスト
        """
        # 結果ウィンドウの作成
        result_window = tk.Toplevel(self)
        result_window.title("欠落エピソード")
        result_window.geometry("400x300")

        # 情報表示
        info_label = tk.Label(
            result_window,
            text=f"{len(missing_episodes)}個の欠落エピソードが見つかりました",
            font=("", 12)
        )
        info_label.pack(pady=10)

        # エピソードリストフレーム
        list_frame = tk.Frame(result_window)
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # スクロールバー付きリストボックス
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        episode_list = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            font=("", 10),
            height=10
        )
        episode_list.pack(side="left", fill="both", expand=True)

        scrollbar.config(command=episode_list.yview)

        # エピソードリストに追加
        for ep_no in missing_episodes:
            episode_list.insert(tk.END, f"エピソード {ep_no}")

        # ボタンフレーム
        button_frame = tk.Frame(result_window)
        button_frame.pack(fill="x", pady=10)

        # 取得ボタン
        fetch_button = ttk.Button(
            button_frame,
            text="欠落エピソードを取得",
            command=lambda: self.fetch_missing_episodes(ncode, result_window)
        )
        fetch_button.pack(side="left", padx=10)

        # キャンセルボタン
        cancel_button = ttk.Button(
            button_frame,
            text="キャンセル",
            command=result_window.destroy
        )
        cancel_button.pack(side="right", padx=10)

    def fetch_missing_episodes(self, ncode, window):
        """
        欠落エピソードを取得

        Args:
            ncode: 小説コード
            window: 閉じるウィンドウ
        """
        # ウィンドウを閉じる
        window.destroy()

        # 欠落エピソード取得を実行（コールバック経由）
        if self.update_callback:
            # バックグラウンドで実行するFetchMissingEpisodesタスクを作成
            threading.Thread(
                target=self.update_manager.fetch_missing_episodes,
                args=(ncode, None, self.on_complete_callback)
            ).start()

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
            font=("", 12)
        )
        error_label.pack(pady=20)