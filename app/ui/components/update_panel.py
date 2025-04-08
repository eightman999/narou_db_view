"""
更新された小説一覧を表示するUIコンポーネント
"""
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import queue

from app.core.checker import catch_up_episode
from app.utils.logger_manager import get_logger

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

        # 進捗状況管理
        self.progress_queue = queue.Queue()
        self.update_in_progress = False

        # UIコンポーネント
        self.scroll_canvas = None
        self.scrollable_frame = None
        self.list_display_frame = None
        self.progress_frame = None
        self.progress_bar = None
        self.progress_label = None

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

        # 進捗表示フレーム
        self.progress_frame = tk.Frame(self.scrollable_frame, bg="#F0F0F0")
        self.progress_frame.pack(fill="x", pady=5, padx=10)

        # 進捗ラベル
        self.progress_label = tk.Label(
            self.progress_frame,
            text="",
            bg="#F0F0F0",
            anchor="w"
        )
        self.progress_label.pack(fill="x", pady=(0, 5))

        # 進捗バー
        self.progress_bar = ttk.Progressbar(
            self.progress_frame,
            orient="horizontal",
            mode="determinate",
            length=100
        )
        self.progress_bar.pack(fill="x")

        # 初期状態では進捗表示を隠す
        self.progress_frame.pack_forget()

        # リスト表示フレーム
        self.list_display_frame = tk.Frame(self.scrollable_frame, bg="#F0F0F0")
        self.list_display_frame.pack(fill="x", expand=True, padx=10)

        # 進捗更新タイマーを開始
        self.start_progress_update_timer()

    def start_progress_update_timer(self):
        """進捗更新タイマーを開始"""
        self.check_progress_queue()

    def check_progress_queue(self):
        """進捗キューの確認とUI更新"""
        try:
            # キューからメッセージを取得（非ブロッキング）
            while not self.progress_queue.empty():
                progress_data = self.progress_queue.get_nowait()

                # 進捗データの形式をチェック
                if isinstance(progress_data, dict):
                    # 進捗率の更新
                    if 'percent' in progress_data:
                        self.progress_bar['value'] = progress_data['percent']

                    # メッセージの更新
                    if 'message' in progress_data:
                        self.progress_label.config(text=progress_data['message'])

                    # 進捗表示の表示/非表示
                    if 'show' in progress_data:
                        if progress_data['show']:
                            self.progress_frame.pack(fill="x", pady=5, padx=10, after=self.scrollable_frame.winfo_children()[0])
                        else:
                            self.progress_frame.pack_forget()
                else:
                    # 文字列の場合はメッセージとして表示
                    self.progress_label.config(text=str(progress_data))

                self.progress_queue.task_done()

        except queue.Empty:
            pass

        # 定期的にキューをチェック（100ミリ秒ごと）
        self.after(100, self.check_progress_queue)

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
        for i, novel_data in enumerate(self.shinchaku_novels):
            n_code, title, current_ep, total_ep, rating = novel_data

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

            # タイトルラベル（クリック可能）
            title_label = tk.Label(
                item_frame,
                text=title,
                bg="#F0F0F0",
                anchor="w",
                cursor="hand2"  # クリック可能なことを示すカーソル
            )
            title_label.pack(side="left", padx=5, fill="x", expand=True)

            # タイトルのクリックイベント
            title_label.bind(
                "<Button-1>",
                lambda e, novel=novel_data: self.show_update_confirmation(novel)
            )

            # 更新ボタン
            update_button = ttk.Button(
                item_frame,
                text="更新",
                width=8,
                command=lambda novel=novel_data: self.show_update_confirmation(novel)
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

    def show_update_confirmation(self, novel_data):
        """
        更新確認ダイアログを表示

        Args:
            novel_data: 小説データ (n_code, title, current_ep, total_ep, rating)
        """
        n_code, title, current_ep, total_ep, rating = novel_data
        missing_episodes = total_ep - current_ep

        # 確認ダイアログ
        dialog = tk.Toplevel(self)
        dialog.title("小説更新の確認")
        dialog.geometry("400x250")
        dialog.transient(self)  # 親ウィンドウの上に表示
        dialog.grab_set()  # モーダルダイアログにする

        # ウィンドウの中央配置
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = (dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (dialog.winfo_screenheight() // 2) - (height // 2)
        dialog.geometry(f"+{x}+{y}")

        # タイトルとNコード表示
        title_frame = tk.Frame(dialog, bg="#F0F0F0")
        title_frame.pack(fill="x", pady=10, padx=20)

        title_label = tk.Label(
            title_frame,
            text=title,
            font=("", 12, "bold"),
            wraplength=360,
            justify="center",
            bg="#F0F0F0"
        )
        title_label.pack(fill="x")

        ncode_label = tk.Label(
            title_frame,
            text=f"Nコード: {n_code}",
            font=("", 10),
            bg="#F0F0F0"
        )
        ncode_label.pack(fill="x")

        # 更新情報
        info_frame = tk.Frame(dialog, bg="#F0F0F0")
        info_frame.pack(fill="x", pady=10, padx=20)

        if missing_episodes > 0:
            info_text = f"この小説には {missing_episodes} 話の未取得エピソードがあります。\n"
            info_text += f"現在のエピソード数: {current_ep} 話\n"
            info_text += f"合計エピソード数: {total_ep} 話\n\n"
            info_text += "更新を実行しますか？"
        else:
            info_text = "この小説は既に最新です。"

        info_label = tk.Label(
            info_frame,
            text=info_text,
            justify="left",
            wraplength=360,
            bg="#F0F0F0"
        )
        info_label.pack(fill="x")

        # ボタンフレーム
        button_frame = tk.Frame(dialog, bg="#F0F0F0")
        button_frame.pack(fill="x", pady=10, padx=20)

        if missing_episodes > 0:
            # 更新ボタン
            update_button = ttk.Button(
                button_frame,
                text="更新",
                command=lambda: self.execute_update(novel_data, dialog)
            )
            update_button.pack(side="left", padx=10)

            # キャンセルボタン
            cancel_button = ttk.Button(
                button_frame,
                text="キャンセル",
                command=dialog.destroy
            )
            cancel_button.pack(side="right", padx=10)
        else:
            # 閉じるボタン
            close_button = ttk.Button(
                button_frame,
                text="閉じる",
                command=dialog.destroy
            )
            close_button.pack(side="bottom", pady=10)

    def execute_update(self, novel_data, dialog):
        """
        更新処理を実行

        Args:
            novel_data: 小説データ (n_code, title, current_ep, total_ep, rating)
            dialog: 閉じるべきダイアログ
        """
        # ダイアログを閉じる
        dialog.destroy()

        n_code, title, current_ep, total_ep, rating = novel_data

        # 進捗表示の初期化
        self.update_in_progress = True
        self.progress_queue.put({
            'show': True,
            'percent': 0,
            'message': f"小説 [{title}] の更新を開始します..."
        })

        # 更新処理を非同期で実行
        threading.Thread(
            target=self.update_single_novel,
            args=(novel_data,)
        ).start()

    def update_single_novel(self, novel_data):
        """
        単一の小説を更新（非同期処理用）

        Args:
            novel_data: 小説データ (n_code, title, current_ep, total_ep, rating)
        """
        try:
            n_code, title, current_ep, total_ep, rating = novel_data
            missing_episodes = total_ep - current_ep

            # 更新が必要ないなら終了
            if missing_episodes <= 0:
                self.progress_queue.put({
                    'show': False,
                    'message': ""
                })
                self.update_in_progress = False
                return

            # 欠落エピソードの取得と保存
            for i, ep_no in enumerate(range(current_ep + 1, total_ep + 1)):
                # 進捗率の計算
                progress_percent = int((i / missing_episodes) * 100)

                # 進捗表示の更新
                self.progress_queue.put({
                    'percent': progress_percent,
                    'message': f"小説 [{title}] のエピソード {ep_no}/{total_ep} を取得中... ({progress_percent}%)"
                })

                try:
                    # エピソードを取得
                    episode_content, episode_title = catch_up_episode(n_code, ep_no, rating)

                    # データベースに保存
                    if episode_content and episode_title:
                        self.update_manager.db_manager.insert_episode(n_code, ep_no, episode_content, episode_title)
                    else:
                        logger.warning(f"エピソード {ep_no} の取得に失敗しました")

                except Exception as e:
                    logger.error(f"エピソード {ep_no} の処理中にエラーが発生しました: {e}")
                    # エラーが発生しても処理を続行

            # 総エピソード数を更新
            self.update_manager.db_manager.update_total_episodes(n_code)

            # 小説キャッシュをクリア
            self.update_manager.novel_manager.clear_cache(n_code)

            # 完了表示の更新
            self.progress_queue.put({
                'percent': 100,
                'message': f"小説 [{title}] の更新が完了しました"
            })

            # 3秒後に進捗表示を非表示にする
            self.after(3000, lambda: self.progress_queue.put({'show': False}))

            # 更新情報を再取得して表示を更新
            self.after(3500, lambda: self.show_novels())

            # 更新完了コールバックを呼び出し
            if self.on_complete_callback:
                self.after(3500, self.on_complete_callback)

        except Exception as e:
            logger.error(f"小説 {novel_data[0]} の更新中にエラーが発生しました: {e}")

            # エラー表示
            self.progress_queue.put({
                'percent': 0,
                'message': f"エラー: {e}"
            })

            # 3秒後に進捗表示を非表示にする
            self.after(3000, lambda: self.progress_queue.put({'show': False}))

        finally:
            self.update_in_progress = False

    def update_all_novels(self):
        """すべての新着小説を更新"""
        if not self.shinchaku_novels:
            messagebox.showinfo("情報", "更新が必要な小説はありません")
            return

        if self.update_in_progress:
            messagebox.showinfo("情報", "既に更新処理が実行中です")
            return

        # 更新確認ダイアログ
        confirm = messagebox.askyesno(
            "確認",
            f"{len(self.shinchaku_novels)}件の小説を一括更新します。\nこの処理には時間がかかる場合があります。\n続行しますか？"
        )

        if not confirm:
            return

        # 更新処理を開始
        self.update_in_progress = True
        self.progress_queue.put({
            'show': True,
            'percent': 0,
            'message': "すべての新着小説の更新を開始します..."
        })

        # 更新を実行（コールバック経由）
        if self.update_callback:
            self.update_callback(self.shinchaku_novels)

    def check_missing_episodes(self, ncode):
        """
        欠落エピソードを確認

        Args:
            ncode: 小説コード
        """
        # 更新処理中なら実行しない
        if self.update_in_progress:
            messagebox.showinfo("情報", "更新処理の実行中は欠落エピソードの確認はできません")
            return

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
            missing_episodes = self.update_manager.db_manager.find_missing_episodes(ncode)

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
        result_window.transient(self)  # 親ウィンドウの上に表示

        # ウィンドウの中央配置
        result_window.update_idletasks()
        width = result_window.winfo_width()
        height = result_window.winfo_height()
        x = (result_window.winfo_screenwidth() // 2) - (width // 2)
        y = (result_window.winfo_screenheight() // 2) - (height // 2)
        result_window.geometry(f"+{x}+{y}")

        # 小説情報の取得
        novel_info = self.update_manager.novel_manager.get_novel(ncode)
        title = novel_info[1] if novel_info else "不明なタイトル"

        # 情報表示
        info_frame = tk.Frame(result_window, bg="#F0F0F0")
        info_frame.pack(fill="x", pady=10, padx=10)

        title_label = tk.Label(
            info_frame,
            text=title,
            font=("", 12, "bold"),
            bg="#F0F0F0"
        )
        title_label.pack(fill="x")

        info_label = tk.Label(
            info_frame,
            text=f"{len(missing_episodes)}個の欠落エピソードが見つかりました",
            font=("", 10),
            bg="#F0F0F0"
        )
        info_label.pack(fill="x", pady=5)

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
        # 更新処理中なら実行しない
        if self.update_in_progress:
            messagebox.showinfo("情報", "既に更新処理が実行中です")
            return

        # ウィンドウを閉じる
        window.destroy()

        # 小説情報の取得
        novel_info = self.update_manager.novel_manager.get_novel(ncode)
        title = novel_info[1] if novel_info else "不明なタイトル"

        # 進捗表示の初期化
        self.update_in_progress = True
        self.progress_queue.put({
            'show': True,
            'percent': 0,
            'message': f"小説 [{title}] の欠落エピソード取得を開始します..."
        })

        # 欠落エピソード取得を実行（バックグラウンドスレッドで）
        threading.Thread(
            target=self.execute_fetch_missing,
            args=(ncode,)
        ).start()

    def execute_fetch_missing(self, ncode):
        """
        欠落エピソード取得の実行（バックグラウンドスレッド用）

        Args:
            ncode: 小説コード
        """
        try:
            # 小説情報の取得
            novel_info = self.update_manager.novel_manager.get_novel(ncode)
            title = novel_info[1] if novel_info else "不明なタイトル"
            rating = novel_info[4] if len(novel_info) > 4 else None

            # 欠落エピソードの検索
            missing_episodes = self.update_manager.db_manager.find_missing_episodes(ncode)

            if not missing_episodes:
                self.progress_queue.put({
                    'show': False,
                    'message': ""
                })
                self.after(0, lambda: messagebox.showinfo("情報", "欠落エピソードがありません"))
                self.update_in_progress = False
                return

            total_missing = len(missing_episodes)

            # 欠落エピソードの取得と保存
            for i, ep_no in enumerate(missing_episodes):
                # 進捗率の計算
                progress_percent = int((i / total_missing) * 100)

                # 進捗表示の更新
                self.progress_queue.put({
                    'percent': progress_percent,
                    'message': f"小説 [{title}] の欠落エピソード {ep_no} を取得中... ({progress_percent}%)"
                })

                try:
                    # エピソードを取得
                    episode_content, episode_title = catch_up_episode(ncode, ep_no, rating)

                    # データベースに保存
                    if episode_content and episode_title:
                        self.update_manager.db_manager.insert_episode(ncode, ep_no, episode_content, episode_title)
                    else:
                        logger.warning(f"エピソード {ep_no} の取得に失敗しました")

                except Exception as e:
                    logger.error(f"エピソード {ep_no} の処理中にエラーが発生しました: {e}")
                    # エラーが発生しても処理を続行

            # 総エピソード数を更新
            self.update_manager.db_manager.update_total_episodes(ncode)

            # 小説キャッシュをクリア
            self.update_manager.novel_manager.clear_cache(ncode)

            # 完了表示の更新
            self.progress_queue.put({
                'percent': 100,
                'message': f"小説 [{title}] の欠落エピソード取得が完了しました"
            })

            # 3秒後に進捗表示を非表示にする
            self.after(3000, lambda: self.progress_queue.put({'show': False}))

            # 更新情報を再取得して表示を更新
            self.after(3500, lambda: self.show_novels())

            # 更新完了コールバックを呼び出し
            if self.on_complete_callback:
                self.after(3500, self.on_complete_callback)

        except Exception as e:
            logger.error(f"欠落エピソード取得中にエラーが発生しました: {e}")

            # エラー表示
            self.progress_queue.put({
                'percent': 0,
                'message': f"エラー: {e}"
            })

            # 3秒後に進捗表示を非表示にする
            self.after(3000, lambda: self.progress_queue.put({'show': False}))

        finally:
            self.update_in_progress = False

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