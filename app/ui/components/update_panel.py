"""
更新された小説一覧を表示するUIコンポーネント
"""
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import queue
import os
import json
from datetime import datetime

from app.core.checker import catch_up_episode
from app.utils.logger_manager import get_logger

# ロガーの設定
logger = get_logger('UpdatePanel')


class UpdatePanel(ttk.Frame):
    """更新された小説一覧を表示するビュークラス"""

    # クラス変数として更新リストと更新時刻を保持
    _shinchaku_novels = []
    _last_check_time = None

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
        self.shinchaku_novels = UpdatePanel._shinchaku_novels
        self.novels_with_missing_episodes = []  # 欠落エピソードがある小説のリスト
        self.selected_novels = {}  # 選択された小説を追跡するための辞書 {n_code: bool}
        self.last_check_time = UpdatePanel._last_check_time
        self.currently_updating_novels = []  # 現在更新中の小説のリスト

        # 初回起動管理用の設定ファイルパス
        self.config_file = os.path.join('config', 'app_state.json')
        self.is_first_run = self.check_first_run()

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
        self.update_check_button = None  # 更新確認ボタン
        self.select_all_var = None  # 全選択用の変数
        self.select_all_checkbox = None  # 全選択チェックボックス
        self.update_selected_button = None  # 選択した小説を更新するボタン
        self.checkbox_vars = {}  # チェックボックスの変数を保持する辞書 {n_code: BooleanVar}
        self.last_check_label = None  # 最終更新確認時刻を表示するラベル

    def check_first_run(self):
        """
        アプリが初回起動かどうかを確認する

        Returns:
            bool: 初回起動ならTrue、それ以外はFalse
        """
        # configディレクトリがなければ作成
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)

        # 設定ファイルが存在しなければ初回起動とみなす
        if not os.path.exists(self.config_file):
            # 初回起動の記録を保存
            self.save_app_state()
            logger.info("初回起動を確認しました")
            return True

        # ファイルが存在する場合はその内容を確認
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
                return state.get('is_first_run', True)
        except Exception as e:
            logger.error(f"設定ファイル読み込みエラー: {e}")
            return True  # エラー時は安全のため初回起動とみなす

    def save_app_state(self, is_first_run=False):
        """
        アプリケーションの状態を保存

        Args:
            is_first_run (bool): 初回起動フラグ
        """
        try:
            state = {'is_first_run': is_first_run}
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(state, f)
            logger.info("アプリケーション状態を保存しました")
        except Exception as e:
            logger.error(f"設定ファイル保存エラー: {e}")

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

        # 最終確認時刻を表示するラベル
        self.last_check_label = tk.Label(
            self,
            text="",
            font=("", 10),
            bg="#F0F0F0"
        )
        self.last_check_label.pack(pady=(0, 10))

        # 最終確認時刻がある場合は表示を更新
        if self.last_check_time:
            self.update_last_check_label()

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

        # ボタンフレーム
        button_frame = tk.Frame(self.scrollable_frame, bg="#F0F0F0")
        button_frame.pack(fill="x", pady=10, padx=10)

        # 更新確認ボタン
        self.update_check_button = ttk.Button(
            button_frame,
            text="新着小説を確認する",
            command=self.check_updates
        )
        self.update_check_button.pack(side="left", padx=5)

        # 選択した小説を更新するボタン
        self.update_selected_button = ttk.Button(
            button_frame,
            text="選択した小説を更新",
            command=self.update_selected_novels,
            state="disabled"  # 初期状態では無効
        )
        self.update_selected_button.pack(side="left", padx=5)

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

        # 全選択フレーム
        select_all_frame = tk.Frame(self.scrollable_frame, bg="#F0F0F0")
        select_all_frame.pack(fill="x", pady=5, padx=10)

        # 全選択チェックボックス
        self.select_all_var = tk.BooleanVar(value=False)
        self.select_all_checkbox = ttk.Checkbutton(
            select_all_frame,
            text="すべて選択/解除",
            variable=self.select_all_var,
            command=self.toggle_all_selections
        )
        self.select_all_checkbox.pack(side="left", padx=5)

        # リスト表示フレーム
        self.list_display_frame = tk.Frame(self.scrollable_frame, bg="#F0F0F0")
        self.list_display_frame.pack(fill="x", expand=True, padx=10)

        # 進捗更新タイマーを開始
        self.start_progress_update_timer()

    def update_last_check_label(self):
        """最終確認時刻ラベルの表示を更新"""
        if self.last_check_time:
            formatted_time = self.last_check_time.strftime("%Y年%m月%d日 %H:%M:%S")
            self.last_check_label.config(text=f"最終更新確認: {formatted_time}")
        else:
            self.last_check_label.config(text="")

    def toggle_all_selections(self):
        """すべての小説の選択状態を切り替える"""
        is_selected = self.select_all_var.get()

        # すべてのチェックボックスの状態を更新
        for n_code, var in self.checkbox_vars.items():
            var.set(is_selected)
            self.selected_novels[n_code] = is_selected

        # 選択状態に基づいてボタンの有効/無効を更新
        self.update_button_state()

    def update_button_state(self):
        """選択状態に基づいて更新ボタンの有効/無効を切り替え"""
        if any(self.selected_novels.values()):
            self.update_selected_button.config(state="normal")
        else:
            self.update_selected_button.config(state="disabled")

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

    def check_updates(self):
        """
        更新確認ボタンがクリックされたときの処理
        新着小説を確認して表示を更新
        """
        if self.update_in_progress:
            messagebox.showinfo("情報", "すでに更新処理が実行中です")
            return

        # ローディング表示
        self.show_loading()

        # 新着小説データを取得（バックグラウンドスレッドで）
        threading.Thread(target=self.load_shinchaku_novels).start()

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
        # UIが初期化されていない場合は初期化
        if not hasattr(self, 'scroll_canvas') or self.scroll_canvas is None:
            self.init_ui()

        # スクロール位置をリセット
        self.scroll_canvas.yview_moveto(0)

        # 初回起動時のみ自動的に新着チェックを実行
        if self.is_first_run:
            logger.info("初回起動のため自動的に新着を確認します")
            self.show_loading()
            threading.Thread(target=self.load_shinchaku_novels).start()
            # 次回からは自動チェックしないように設定
            self.is_first_run = False
            self.save_app_state(is_first_run=False)
        elif self.shinchaku_novels:
            # 既に取得済みの更新情報がある場合は表示
            self.update_ui()
        else:
            # 初回起動でなく、更新情報もない場合は空のリストを表示
            self.show_empty_list()

        # 最終確認時刻を表示
        if hasattr(self, 'last_check_label') and self.last_check_label:
            self.update_last_check_label()

    def show_empty_list(self):
        """
        更新確認前の空のリスト表示
        """
        # 前のリストをクリア
        for widget in self.list_display_frame.winfo_children():
            widget.destroy()

        # 情報メッセージ
        info_label = tk.Label(
            self.list_display_frame,
            text="更新確認をするには「新着小説を確認する」ボタンをクリックしてください",
            bg="#F0F0F0",
            font=("", 12)
        )
        info_label.pack(pady=20)

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
        """新着小説データの読み込み（バックグラウンドスレッドで実行）"""
        try:
            # 更新確認ボタンを無効化
            self.after(0, lambda: self.update_check_button.config(state="disabled"))

            # 新着情報を取得
            _, shinchaku_novels, _ = self.update_manager.check_shinchaku()
            self.shinchaku_novels = shinchaku_novels

            # クラス変数にも保存して永続化
            UpdatePanel._shinchaku_novels = shinchaku_novels

            # 更新確認時刻を記録
            self.last_check_time = datetime.now()
            UpdatePanel._last_check_time = self.last_check_time

            # 最終確認時刻ラベルを更新
            self.after(0, self.update_last_check_label)

            # 欠落エピソードがある小説を検索
            self.novels_with_missing_episodes = []

            # 更新除外されていない全小説を取得
            all_novels = self.update_manager.novel_manager.get_all_novels()

            # 進捗状況を初期化
            total_novels = len(all_novels)
            progress_step = 0

            # 進捗表示
            self.after(0, lambda: self.progress_frame.pack(fill="x", pady=5, padx=10, after=self.scrollable_frame.winfo_children()[0]))
            self.after(0, lambda: self.progress_label.config(text="小説の欠落エピソードをチェック中..."))
            self.after(0, lambda: self.progress_bar.config(value=0))

            for novel in all_novels:
                # 進捗表示を更新（100冊ごと）
                progress_step += 1
                if progress_step % 100 == 0:
                    progress_percent = int((progress_step / total_novels) * 100)
                    # メインスレッドへのキューイング
                    self.after(0, lambda p=progress_percent: self.progress_bar.config(value=p))
                    self.after(0, lambda msg=f"小説の欠落エピソードをチェック中... ({progress_step}/{total_novels})":
                    self.progress_label.config(text=msg))

                ncode = novel[0]

                # 更新除外フラグがある場合はスキップ
                excluded = novel[8] if len(novel) > 8 else 0
                if excluded == 1:
                    continue

                # 欠落エピソードを検索
                missing_episodes = self.update_manager.db_manager.find_missing_episodes(ncode)

                if missing_episodes:
                    # 欠落エピソードがある場合は、既存の更新リストにない場合のみ追加
                    if not any(ncode == n[0] for n in self.shinchaku_novels):
                        # 小説情報を取得
                        title = novel[1]
                        current_ep = novel[5] if novel[5] is not None else 0
                        total_ep = novel[6] if novel[6] is not None else 0
                        rating = novel[4] if len(novel) > 4 else None

                        # この小説には欠落エピソードがあることを記録
                        self.novels_with_missing_episodes.append((ncode, title, current_ep, total_ep, rating))

            # 欠落エピソードがある小説を通常の更新リストに追加
            for novel in self.novels_with_missing_episodes:
                if not any(novel[0] == n[0] for n in self.shinchaku_novels):
                    self.shinchaku_novels.append(novel)

            # クラス変数にも更新内容を保存
            UpdatePanel._shinchaku_novels = self.shinchaku_novels

            # 進捗表示を非表示
            self.after(0, lambda: self.progress_frame.pack_forget())

            # 更新確認ボタンを有効化
            self.after(0, lambda: self.update_check_button.config(state="normal"))

            # UIの更新はメインスレッドで行う
            self.after(0, self.update_ui)

        except Exception as e:
            logger.error(f"新着小説データの読み込みエラー: {e}")
            # エラー表示
            self.after(0, lambda: self.show_error(f"新着小説の読み込みに失敗しました: {e}"))
            # 更新確認ボタンを有効化
            self.after(0, lambda: self.update_check_button.config(state="normal"))

    def update_ui(self):
        """UIの更新"""
        # 前のリストをクリア
        for widget in self.list_display_frame.winfo_children():
            widget.destroy()

        # 選択状態を初期化
        self.selected_novels = {}
        self.checkbox_vars = {}

        # 全選択チェックボックスの状態をリセット
        self.select_all_var.set(False)

        # 新着小説がない場合
        if not self.shinchaku_novels:
            no_novels_label = tk.Label(
                self.list_display_frame,
                text="更新が必要な小説はありません",
                bg="#F0F0F0",
                font=("", 12)
            )
            no_novels_label.pack(pady=20)

            # 更新ボタンを無効化
            self.update_selected_button.config(state="disabled")
            return

        # 更新情報を表示
        info_label = tk.Label(
            self.list_display_frame,
            text=f"{len(self.shinchaku_novels)}件の小説に更新または欠落エピソードがあります",
            bg="#F0F0F0",
            font=("", 12)
        )
        info_label.pack(pady=10)

        # ヘッダー行
        header_frame = tk.Frame(self.list_display_frame, bg="#E0E0E0")
        header_frame.pack(fill="x", pady=2)

        # チェックボックス用の空ラベル
        check_header = tk.Label(
            header_frame,
            text="",
            bg="#E0E0E0",
            width=2
        )
        check_header.pack(side="left", padx=5)

        # 状態ヘッダー
        status_header = tk.Label(
            header_frame,
            text="進捗",
            bg="#E0E0E0",
            width=10,
            anchor="w"
        )
        status_header.pack(side="left", padx=5)

        # タイトルヘッダー
        title_header = tk.Label(
            header_frame,
            text="タイトル",
            bg="#E0E0E0",
            anchor="w",
            font=("", 10, "bold")
        )
        title_header.pack(side="left", padx=5, fill="x", expand=True)

        # ボタンスペース用空ラベル
        buttons_header = tk.Label(
            header_frame,
            text="",
            bg="#E0E0E0",
            width=20
        )
        buttons_header.pack(side="right", padx=5)

        # 新着小説一覧を表示
        for i, novel_data in enumerate(self.shinchaku_novels):
            n_code, title, current_ep, total_ep, rating = novel_data

            # 項目用フレーム
            item_frame = tk.Frame(self.list_display_frame, bg="#F0F0F0")
            item_frame.pack(fill="x", pady=2)

            # 欠落エピソードがある小説かどうか確認
            is_missing = any(n_code == n[0] for n in self.novels_with_missing_episodes)

            # チェックボックス用の変数を作成
            self.checkbox_vars[n_code] = tk.BooleanVar(value=False)
            self.selected_novels[n_code] = False

            # チェックボックス
            checkbox = ttk.Checkbutton(
                item_frame,
                variable=self.checkbox_vars[n_code],
                command=lambda n=n_code: self.toggle_selection(n)
            )
            checkbox.pack(side="left", padx=5)

            # 現在の状態表示
            status_text = f"{current_ep}/{total_ep}話"
            if is_missing:
                status_text += " ※"

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
                checkbox.config(style="Alt.TCheckbutton")  # カスタムスタイルを適用（あれば）

            # 欠落エピソードがある小説は背景色を変える
            if is_missing:
                item_frame.config(bg="#FFECEC")
                status_label.config(bg="#FFECEC")
                title_label.config(bg="#FFECEC")

        # 欠落エピソードの説明を追加
        if any(n_code == n[0] for n in self.shinchaku_novels for n_code in
               [n2[0] for n2 in self.novels_with_missing_episodes]):
            note_frame = tk.Frame(self.list_display_frame, bg="#F0F0F0")
            note_frame.pack(fill="x", pady=10)

            note_label = tk.Label(
                note_frame,
                text="※ 印がついている小説には、欠落しているエピソードがあります。",
                bg="#F0F0F0",
                font=("", 10),
                anchor="w"
            )
            note_label.pack(side="left", padx=10)

        # 選択ボタンの状態を初期化
        self.update_button_state()

    def toggle_selection(self, n_code):
        """
        小説の選択状態を切り替える

        Args:
            n_code: 小説コード
        """
        # 選択状態を更新
        self.selected_novels[n_code] = self.checkbox_vars[n_code].get()

        # すべてのチェックボックスがチェックされているか確認
        all_checked = all(var.get() for var in self.checkbox_vars.values())
        all_unchecked = not any(var.get() for var in self.checkbox_vars.values())

        # 全選択チェックボックスの状態を更新
        if all_checked:
            self.select_all_var.set(True)
        elif all_unchecked:
            self.select_all_var.set(False)

        # 選択状態に基づいてボタンの有効/無効を更新
        self.update_button_state()

    def update_selected_novels(self):
        """選択された小説だけを更新"""
        # 選択された小説を取得
        selected_list = []
        for novel in self.shinchaku_novels:
            n_code = novel[0]
            if n_code in self.selected_novels and self.selected_novels[n_code]:
                selected_list.append(novel)

        if not selected_list:
            messagebox.showinfo("情報", "更新する小説が選択されていません")
            return

        if self.update_in_progress:
            messagebox.showinfo("情報", "既に更新処理が実行中です")
            return

        # 更新確認ダイアログ
        confirm = messagebox.askyesno(
            "確認",
            f"{len(selected_list)}件の選択された小説を更新します。\nこの処理には時間がかかる場合があります。\n続行しますか？"
        )

        if not confirm:
            return

        # 更新処理を開始
        self.update_in_progress = True
        self.currently_updating_novels = selected_list.copy()  # 更新中の小説リストを保持
        self.progress_queue.put({
            'show': True,
            'percent': 0,
            'message': f"選択された{len(selected_list)}件の小説の更新を開始します..."
        })

        # 更新を実行（コールバック経由）
        if self.update_callback:
            self.update_callback(selected_list)

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
        if self.update_in_progress:
            messagebox.showinfo("情報", "現在更新処理中です。完了後にお試しください。")
            return

        # 欠落エピソード確認中の表示
        self.progress_queue.put({
            'show': True,
            'percent': 0,
            'message': f"小説の欠落エピソードを確認中..."
        })

        # バックグラウンドでチェック
        threading.Thread(target=self._check_missing_episodes_thread, args=(ncode,)).start()

    def _check_missing_episodes_thread(self, ncode):
        """欠落エピソード確認のスレッド処理"""
        try:
            # 小説情報を取得
            novel = self.update_manager.novel_manager.get_novel(ncode)
            if not novel:
                self.progress_queue.put({
                    'message': f"エラー: 小説が見つかりません"
                })
                return

            title = novel[1]

            # 欠落エピソードを検索
            missing_episodes = self.update_manager.db_manager.find_missing_episodes(ncode)

            # 検索完了
            self.progress_queue.put({
                'percent': 100,
                'message': f"欠落エピソード確認完了"
            })

            # 検索結果を表示
            def show_result():
                if not missing_episodes:
                    messagebox.showinfo("欠落エピソード確認", f"小説「{title}」に欠落エピソードはありません。")
                else:
                    # 欠落エピソードがある場合は詳細を表示
                    result = f"小説「{title}」には以下の{len(missing_episodes)}個の欠落エピソードがあります:\n\n"

                    # 欠落エピソードが多すぎる場合は一部だけ表示
                    if len(missing_episodes) > 20:
                        shown_episodes = missing_episodes[:20]
                        result += ", ".join(map(str, shown_episodes))
                        result += f"\n\n...他 {len(missing_episodes) - 20} 話"
                    else:
                        result += ", ".join(map(str, missing_episodes))

                    result += "\n\n欠落エピソードを取得しますか？"

                    # 確認ダイアログを表示
                    confirm = messagebox.askyesno("欠落エピソード確認", result)
                    if confirm:
                        # 欠落エピソード取得処理を開始
                        self.fetch_missing_episodes(ncode, novel)

            # UIスレッドで結果表示
            self.after(0, show_result)

            # 進捗表示を非表示
            self.after(3000, lambda: self.progress_queue.put({'show': False}))

        except Exception as e:
            logger.error(f"欠落エピソード確認エラー: {e}")
            self.progress_queue.put({
                'message': f"エラー: {e}"
            })
            self.after(3000, lambda: self.progress_queue.put({'show': False}))

    def fetch_missing_episodes(self, ncode, novel):
        """
        欠落エピソードを取得する

        Args:
            ncode: 小説コード
            novel: 小説情報
        """
        # 更新中フラグをセット
        self.update_in_progress = True

        # 欠落エピソード取得処理を開始
        self.progress_queue.put({
            'show': True,
            'percent': 0,
            'message': f"欠落エピソードの取得を開始します..."
        })

        # バックグラウンドで取得処理
        threading.Thread(
            target=self.update_manager.fetch_missing_episodes,
            args=(ncode, self.progress_queue, self.on_missing_complete)
        ).start()

    def on_missing_complete(self):
        """欠落エピソード取得完了時の処理"""
        # 更新中フラグをクリア
        self.update_in_progress = False

        # 更新情報を再取得して表示を更新
        self.show_novels()

        # 更新完了コールバックを呼び出し
        if self.on_complete_callback:
            self.on_complete_callback()

    def show_error(self, message):
        """
        エラーメッセージを表示

        Args:
            message: エラーメッセージ
        """
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

            # 更新後に再チェックして状態を確認
            self.after(1000, lambda: self.recheck_novel_status(n_code, title, rating))

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

    def recheck_novel_status(self, ncode, title, rating):
        """
        更新後に小説の状態を再確認

        Args:
            ncode: 小説コード
            title: 小説タイトル
            rating: レーティング
        """
        try:
            self.progress_queue.put({
                'message': f"小説 [{title}] の状態を再確認中..."
            })

            # 小説の最新情報を取得
            novel = self.update_manager.novel_manager.get_novel(ncode)
            if not novel:
                logger.warning(f"小説 {ncode} の情報が見つかりません")
                return

            current_ep = novel[5] if novel[5] is not None else 0
            total_ep = novel[6] if novel[6] is not None else 0

            # 欠落エピソードを検索
            missing_episodes = self.update_manager.db_manager.find_missing_episodes(ncode)

            # 更新リストから該当小説を探す
            novel_index = None
            for i, novel_data in enumerate(self.shinchaku_novels):
                if novel_data[0] == ncode:
                    novel_index = i
                    break

            if novel_index is not None:
                if current_ep >= total_ep and not missing_episodes:
                    # 更新完了かつ欠落なしの場合はリストから削除
                    self.progress_queue.put({
                        'message': f"小説 [{title}] は完全に更新されました。リストから削除します。"
                    })

                    # リストから削除
                    del self.shinchaku_novels[novel_index]
                    # クラス変数も更新
                    UpdatePanel._shinchaku_novels = self.shinchaku_novels

                    # UIを更新
                    self.after(2000, self.update_ui)
                else:
                    # まだ更新が必要な場合は最新の情報に更新
                    new_novel_data = (ncode, title, current_ep, total_ep, rating)
                    self.shinchaku_novels[novel_index] = new_novel_data
                    UpdatePanel._shinchaku_novels = self.shinchaku_novels

                    if missing_episodes:
                        self.progress_queue.put({
                            'message': f"小説 [{title}] にはまだ{len(missing_episodes)}個の欠落エピソードがあります。"
                        })
                    elif current_ep < total_ep:
                        self.progress_queue.put({
                            'message': f"小説 [{title}] にはまだ{total_ep - current_ep}話の未取得エピソードがあります。"
                        })

                    # UIを更新
                    self.after(2000, self.update_ui)

            # 3秒後に進捗表示を非表示にする
            self.after(3000, lambda: self.progress_queue.put({'show': False}))

            # 更新完了コールバックを呼び出し
            if self.on_complete_callback:
                self.after(3500, self.on_complete_callback)

        except Exception as e:
            logger.error(f"小説 {ncode} の再確認中にエラーが発生しました: {e}")
            self.progress_queue.put({
                'message': f"再確認エラー: {e}"
            })

            # 3秒後に進捗表示を非表示にする
            self.after(3000, lambda: self.progress_queue.put({'show': False}))

    # 一括更新完了後の処理を改良
    def on_update_complete(self):
        """更新完了時の処理"""
        self.update_in_progress = False

        # 現在の小説リストをコピー（反復処理中に削除するため）
        current_novels = self.currently_updating_novels.copy() if hasattr(self, 'currently_updating_novels') else []

        if current_novels:
            # 更新された小説を順番に再チェック
            self.progress_queue.put({
                'show': True,
                'percent': 100,
                'message': "更新された小説の状態を再確認しています..."
            })

            # 少し待ってから再チェック開始（DBの更新を確実にするため）
            self.after(1000, lambda: self.start_batch_rechecking(current_novels))
        else:
            # 更新情報を再取得して表示を更新
            shinchaku_info = self.update_manager.check_shinchaku()
            self.shinchaku_novels = shinchaku_info[1]
            UpdatePanel._shinchaku_novels = self.shinchaku_novels

            # UIを更新
            self.update_ui()

            # 進捗表示を非表示
            self.after(1000, lambda: self.progress_queue.put({'show': False}))

    def start_batch_rechecking(self, novels_to_check):
        """
        一括で小説の状態を再確認

        Args:
            novels_to_check: 再チェックする小説のリスト
        """
        if not novels_to_check:
            # すべての再チェックが完了したらUIを更新
            self.update_ui()

            # 進捗表示を非表示
            self.after(1000, lambda: self.progress_queue.put({'show': False}))
            return

        # 先頭の小説を取り出して再チェック
        novel = novels_to_check.pop(0)
        ncode, title = novel[0], novel[1]
        rating = novel[4] if len(novel) > 4 else None

        # 再チェック実行
        self.recheck_novel_status(ncode, title, rating)

        # 少し待ってから次の小説を再チェック
        self.after(1500, lambda: self.start_batch_rechecking(novels_to_check))