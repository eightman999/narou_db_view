"""
更新された小説一覧を表示するUIコンポーネント（ページネーション機能付き）
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

    """
    UpdatePanelクラスの修正パッチ
    """

    # UpdatePanelクラスの__init__メソッドを修正
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

        # update_managerからdb_managerを取得
        self.db_manager = update_manager.db_manager

        # 状態管理
        self.shinchaku_novels = UpdatePanel._shinchaku_novels
        self.novels_with_missing_episodes = []  # 欠落エピソードがある小説のリスト
        self.selected_novels = {}  # 選択された小説を追跡するための辞書 {n_code: bool}
        self.last_check_time = UpdatePanel._last_check_time
        self.currently_updating_novels = []  # 現在更新中の小説のリスト

        # ページネーション管理
        self.current_page = 0
        self.items_per_page = 20  # 1ページあたりの表示件数を20に設定
        self.total_pages = 0

        # 初回起動管理用の設定ファイルパス
        self.config_file = os.path.join('app', 'config', 'app_state.json')
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

        # ページネーション用のコントロール
        self.prev_button = None  # 前ページボタン
        self.next_button = None  # 次ページボタン
        self.page_label = None  # ページ表示ラベル

    # load_shinchaku_novelsメソッドを修正
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
            self.after(0, lambda: self.progress_frame.pack(fill="x", pady=5, padx=10,
                                                           after=self.scrollable_frame.winfo_children()[0]))
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
                        logger.debug(f"欠落エピソードがある小説を新たに追加: {ncode}")
                        # 小説の詳細情報を取得
                        query = """
                        SELECT n_code, title, total_ep, general_all_no, rating 
                        FROM novels_descs 
                        WHERE n_code = ?
                        """
                        full_novel = self.db_manager.execute_read_query(query, (ncode,), fetch_all=False)
                        logger.debug(f"取得した小説詳細: {full_novel}")

                        if full_novel:
                            title = full_novel[1]
                            # 安全にcurrent_epとtotal_epを取得
                            current_ep = 0
                            total_ep = 0

                            try:
                                if len(full_novel) > 5 and full_novel[5] is not None:
                                    current_ep_raw = full_novel[5]
                                    logger.debug(f"Current EP raw: {current_ep_raw}, type: {type(current_ep_raw)}")
                                    current_ep = int(current_ep_raw)
                            except (ValueError, TypeError) as e:
                                logger.warning(f"小説 {ncode} の現在エピソード数の変換エラー: {e}")

                            try:
                                if len(full_novel) > 6 and full_novel[6] is not None:
                                    total_ep_raw = full_novel[6]
                                    logger.debug(f"Total EP raw: {total_ep_raw}, type: {type(total_ep_raw)}")
                                    total_ep = int(total_ep_raw)
                            except (ValueError, TypeError) as e:
                                logger.warning(f"小説 {ncode} の総エピソード数の変換エラー: {e}")

                            logger.debug(f"変換後のエピソード数: current_ep={current_ep}, total_ep={total_ep}")
                            rating = full_novel[4] if len(full_novel) > 4 else None

                            # 必要な情報を含むタプルを作成
                            novel_tuple = (
                                ncode,
                                title,
                                current_ep,
                                total_ep,
                                rating
                            )
                            logger.debug(f"作成した小説タプル: {novel_tuple}")
                            # この小説には欠落エピソードがあることを記録
                            self.novels_with_missing_episodes.append(novel_tuple)

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

            # 総ページ数を計算
            self.total_pages = (len(self.shinchaku_novels) + self.items_per_page - 1) // self.items_per_page

            # UIの更新はメインスレッドで行う（0ページ目を表示）
            self.after(0, lambda: self.load_page(0))

        except Exception as e:
            error_message = f"新着小説の読み込みに失敗しました: {str(e)}"
            logger.error(f"新着小説データの読み込みエラー: {e}")
            # エラー表示 - ラムダ関数内でローカル変数eを使わない
            self.after(0, lambda msg=error_message: self.show_error(msg))
            # 更新確認ボタンを有効化
            self.after(0, lambda: self.update_check_button.config(state="normal"))

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

    """
    UpdatePanelクラスのcheck_progress_queueメソッドの修正パッチ
    """

    # check_progress_queueメソッドを修正
    def check_progress_queue(self):
        """進捗キューの確認とUI更新"""
        try:
            # キューからメッセージを取得（非ブロッキング）
            while not self.progress_queue.empty():
                progress_data = self.progress_queue.get_nowait()

                # ウィジェットが存在するか確認
                if not hasattr(self, 'progress_bar') or not self.progress_bar.winfo_exists():
                    logger.debug("プログレスバーが存在しないため、進捗更新をスキップします")
                    continue

                # 進捗データの形式をチェック
                if isinstance(progress_data, dict):
                    # 進捗率の更新
                    if 'percent' in progress_data:
                        try:
                            self.progress_bar['value'] = progress_data['percent']
                        except Exception as e:
                            logger.error(f"プログレスバーの更新中にエラーが発生しました: {e}")

                    # メッセージの更新
                    if 'message' in progress_data and hasattr(self,
                                                              'progress_label') and self.progress_label.winfo_exists():
                        try:
                            self.progress_label.config(text=progress_data['message'])
                        except Exception as e:
                            logger.error(f"プログレスラベルの更新中にエラーが発生しました: {e}")

                    # 進捗表示の表示/非表示
                    if 'show' in progress_data and hasattr(self,
                                                           'progress_frame') and self.progress_frame.winfo_exists():
                        try:
                            if progress_data['show']:
                                # progress_frameが表示されていないことを確認してから表示
                                if not self.progress_frame.winfo_ismapped():
                                    if len(self.scrollable_frame.winfo_children()) > 0:
                                        self.progress_frame.pack(fill="x", pady=5, padx=10,
                                                                 after=self.scrollable_frame.winfo_children()[0])
                                    else:
                                        self.progress_frame.pack(fill="x", pady=5, padx=10)
                            else:
                                self.progress_frame.pack_forget()
                        except Exception as e:
                            logger.error(f"進捗フレームの表示/非表示中にエラーが発生しました: {e}")
                else:
                    # 文字列の場合はメッセージとして表示
                    if hasattr(self, 'progress_label') and self.progress_label.winfo_exists():
                        try:
                            self.progress_label.config(text=str(progress_data))
                        except Exception as e:
                            logger.error(f"プログレスラベルの更新中にエラーが発生しました: {e}")

                self.progress_queue.task_done()

        except queue.Empty:
            pass
        except Exception as e:
            logger.error(f"進捗キュー処理中に予期しないエラーが発生しました: {e}")

        # 定期的にキューをチェック（100ミリ秒ごと）
        if self.winfo_exists():  # ウィジェットが存在する場合のみスケジュール
            self.after(100, self.check_progress_queue)

    # init_uiメソッドの修正（プログレスフレームの初期化部分）

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

        # 進捗表示フレーム - 先に初期化しておく
        self.progress_frame = tk.Frame(self.scrollable_frame, bg="#F0F0F0")

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

        # 一括欠落確認＆更新ボタン（新規追加）
        check_missing_all_button = ttk.Button(
            button_frame,
            text="一括欠落確認＆更新",
            command=self.check_and_update_all_missing
        )
        check_missing_all_button.pack(side="left", padx=5)

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

        # ページングコントロールフレーム
        paging_frame = tk.Frame(self.scrollable_frame, bg="#F0F0F0")
        paging_frame.pack(fill="x", pady=5, padx=10)

        # 前のページボタン
        self.prev_button = ttk.Button(
            paging_frame,
            text="←",
            width=5,
            command=lambda: self.load_page(self.current_page - 1)
        )
        self.prev_button.pack(side="left", padx=5)

        # ページ表示ラベル
        self.page_label = tk.Label(
            paging_frame,
            text="ページ 0/0",
            bg="#F0F0F0"
        )
        self.page_label.pack(side="left", padx=5)

        # 次のページボタン
        self.next_button = ttk.Button(
            paging_frame,
            text="→",
            width=5,
            command=lambda: self.load_page(self.current_page + 1)
        )
        self.next_button.pack(side="left", padx=5)

        # リスト表示フレーム
        self.list_display_frame = tk.Frame(self.scrollable_frame, bg="#F0F0F0")
        self.list_display_frame.pack(fill="x", expand=True, padx=10)

        # 初期状態では進捗表示を隠す
        self.progress_frame.pack_forget()

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

        # 現在表示中のチェックボックスの状態を更新
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

    def update_paging_controls(self, current_page, total_pages):
        """
        ページングコントロールの状態を更新

        Args:
            current_page (int): 現在のページ番号
            total_pages (int): 総ページ数
        """
        # ページ表示ラベルを更新
        self.page_label.config(text=f"ページ {current_page + 1}/{total_pages if total_pages > 0 else 1}")

        # 前/次ボタンの有効/無効状態を更新
        self.prev_button.config(state=tk.NORMAL if current_page > 0 else tk.DISABLED)
        self.next_button.config(state=tk.NORMAL if current_page < total_pages - 1 else tk.DISABLED)

    def start_progress_update_timer(self):
        """進捗更新タイマーを開始"""
        self.check_progress_queue()

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
            # 総ページ数を計算
            self.total_pages = (len(self.shinchaku_novels) + self.items_per_page - 1) // self.items_per_page
            # 最初のページを表示
            self.load_page(0)
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

        # ページングコントロールを更新
        self.update_paging_controls(0, 0)

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

        # ページングコントロールを更新
        self.update_paging_controls(0, 0)

        # ローディングメッセージ
        loading_label = tk.Label(
            self.list_display_frame,
            text="新着小説を確認しています...",
            bg="#F0F0F0",
            font=("", 12)
        )
        loading_label.pack(pady=20)


    def load_page(self, page_num):
        """
        指定ページの小説を表示

        Args:
            page_num (int): 表示するページ番号
        """
        # ページ境界チェック
        if page_num < 0 or (page_num >= self.total_pages and self.total_pages > 0):
            return

        self.current_page = page_num

        # 前のリストをクリア
        for widget in self.list_display_frame.winfo_children():
            widget.destroy()

        # 選択状態を初期化（表示中のページのみ）
        self.checkbox_vars = {}

        # 全選択チェックボックスの状態をリセット
        self.select_all_var.set(False)

        # ページングコントロールを更新
        self.update_paging_controls(page_num, self.total_pages)

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

        # 現在のページに表示する項目の範囲を計算
        start_idx = page_num * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, len(self.shinchaku_novels))
        current_page_items = self.shinchaku_novels[start_idx:end_idx]

        # 更新情報を表示
        info_label = tk.Label(
            self.list_display_frame,
            text=f"全{len(self.shinchaku_novels)}件中 {start_idx + 1}～{end_idx}件表示中",
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

        # 現在のページの小説一覧を表示
        for i, novel_data in enumerate(current_page_items):
            n_code, title, current_ep, total_ep, rating = novel_data

            # 項目用フレーム
            item_frame = tk.Frame(self.list_display_frame, bg="#F0F0F0")
            item_frame.pack(fill="x", pady=2)

            # 欠落エピソードがある小説かどうか確認
            is_missing = any(n_code == n[0] for n in self.novels_with_missing_episodes)

            # 欠落エピソードリストを取得
            missing_episodes = []
            if is_missing:
                missing_episodes = self.update_manager.db_manager.find_missing_episodes(n_code)

            # 更新が必要なエピソード数
            required_updates = 0

            if is_missing and missing_episodes:
                # 欠落エピソードがある場合
                required_updates = len(missing_episodes)
            else:
                # 通常の新着更新
                required_updates = total_ep - current_ep

            # チェックボックス用の変数を作成
            # 選択状態を保持するために、全体の選択ディクショナリから値を取得
            is_selected = self.selected_novels.get(n_code, False)
            self.checkbox_vars[n_code] = tk.BooleanVar(value=is_selected)

            # チェックボックス
            checkbox = ttk.Checkbutton(
                item_frame,
                variable=self.checkbox_vars[n_code],
                command=lambda n=n_code: self.toggle_selection(n)
            )
            checkbox.pack(side="left", padx=5)

            # 現在の状態表示
            status_text = f"{current_ep}/{total_ep}話"

            if is_missing and missing_episodes:
                # 欠落エピソードがある場合は、欠落数を表示
                status_text = f"{current_ep}/{total_ep}話 (欠落{len(missing_episodes)}話)"
            elif current_ep < total_ep:
                # 通常の更新がある場合
                status_text = f"{current_ep}/{total_ep}話 (未取得{total_ep - current_ep}話)"

            status_label = tk.Label(
                item_frame,
                text=status_text,
                bg="#F0F0F0",
                width=20
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

            # 更新ボタンのコマンドを状況に応じて変更
            if is_missing and missing_episodes:
                update_command = lambda ncode=n_code, t=title, r=rating, m=missing_episodes: self.show_episode_selection_dialog(ncode, t, r, m)
                button_text = "欠落更新"
            else:
                update_command = lambda novel=novel_data: self.show_update_confirmation(novel)
                button_text = "更新"

            # 更新ボタン
            update_button = ttk.Button(
                item_frame,
                text=button_text,
                width=8,
                command=update_command
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

            # 欠落エピソードがある小説は背景色を変える
            if is_missing and missing_episodes:
                item_frame.config(bg="#FFECEC")
                status_label.config(bg="#FFECEC")
                title_label.config(bg="#FFECEC")
    # app/ui/components/update_panel.py の update_ui メソッド内の問題箇所を修正

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

            # 文字列型を整数型に変換（エラー対策）
            if isinstance(current_ep, str):
                current_ep = int(current_ep) if current_ep.isdigit() else 0
            else:
                current_ep = int(current_ep) if current_ep is not None else 0

            if isinstance(total_ep, str):
                total_ep = int(total_ep) if total_ep.isdigit() else 0
            else:
                total_ep = int(total_ep) if total_ep is not None else 0

            # 項目用フレーム
            item_frame = tk.Frame(self.list_display_frame, bg="#F0F0F0")
            item_frame.pack(fill="x", pady=2)

            # 欠落エピソードがある小説かどうか確認
            is_missing = any(n_code == n[0] for n in self.novels_with_missing_episodes)

            # 欠落エピソードリストを取得
            missing_episodes = []
            if is_missing:
                missing_episodes = self.update_manager.db_manager.find_missing_episodes(n_code)

            # 更新が必要なエピソード数
            required_updates = 0

            if is_missing and missing_episodes:
                # 欠落エピソードがある場合
                required_updates = len(missing_episodes)
            else:
                # 通常の新着更新
                required_updates = total_ep - current_ep

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

            if is_missing and missing_episodes:
                # 欠落エピソードがある場合は、欠落数を表示
                status_text = f"{current_ep}/{total_ep}話 (欠落{len(missing_episodes)}話)"
            elif current_ep < total_ep:
                # 通常の更新がある場合
                status_text = f"{current_ep}/{total_ep}話 (未取得{total_ep - current_ep}話)"

            status_label = tk.Label(
                item_frame,
                text=status_text,
                bg="#F0F0F0",
                width=20
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

            # 更新ボタンのコマンドを状況に応じて変更
            if is_missing and missing_episodes:
                update_command = lambda ncode=n_code, t=title, r=rating, m=missing_episodes: self.show_episode_selection_dialog(ncode, t, r, m)
                button_text = "欠落更新"
            else:
                update_command = lambda \
                    novel=(n_code, title, current_ep, total_ep, rating): self.show_update_confirmation(novel)
                button_text = "更新"

            # 更新ボタン
            update_button = ttk.Button(
                item_frame,
                text=button_text,
                width=8,
                command=update_command
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

            # 欠落エピソードがある小説は背景色を変える
            if is_missing and missing_episodes:
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
                text="※ 赤背景の小説には、欠落しているエピソードがあります。",
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

    def update_all_novels(self, progress_queue=None, on_complete=None):
        """
        全ての更新可能な小説を更新（欠落エピソードも含む）

        Args:
            progress_queue: 進捗状況を通知するキュー
            on_complete: 完了時に呼び出すコールバック関数
        """
        try:
            # 更新が必要な小説を取得
            needs_update = self.db_manager.get_novels_needing_update()

            # 更新対象の小説がない場合
            if not needs_update:
                if progress_queue:
                    progress_queue.put({
                        'show': True,
                        'percent': 100,
                        'message': "更新が必要な小説がありません。"
                    })

                if on_complete:
                    on_complete()
                return

            # 全小説の欠落エピソードをチェックして、対応するncodeのリストを作成
            novels_with_missing = []
            novel_count = len(needs_update)

            if progress_queue:
                progress_queue.put({
                    'show': True,
                    'percent': 0,
                    'message': f"{novel_count}件の小説の欠落エピソードをチェック中..."
                })

            # 全小説の欠落エピソードを確認
            for i, (ncode, title, _, _, _) in enumerate(needs_update):
                # 進捗表示を更新
                if progress_queue:
                    check_progress = int((i / novel_count) * 20)  # 全体の20%をチェック処理に使用
                    progress_queue.put({
                        'percent': check_progress,
                        'message': f"小説の欠落エピソードをチェック中... ({i + 1}/{novel_count})"
                    })

                # 欠落エピソードを確認
                missing_episodes = self.db_manager.find_missing_episodes(ncode)
                if missing_episodes and len(missing_episodes) > 0:
                    novels_with_missing.append((ncode, title, missing_episodes))
                    logger.info(f"小説 {ncode} ({title}) に {len(missing_episodes)} 個の欠落エピソードがあります")

            # 欠落エピソードがある小説の情報を表示
            if novels_with_missing:
                if progress_queue:
                    missing_message = f"{len(novels_with_missing)}冊の小説に欠落エピソードがあります。これらも合わせて更新します。"
                    progress_queue.put({
                        'percent': 20,
                        'message': missing_message
                    })
                    logger.info(missing_message)

            # 通常の更新処理を実行（進捗レンジを20%～60%に設定）
            def on_normal_update_complete():
                # 新着更新完了後に欠落エピソードの処理を開始
                logger.info("通常更新が完了しました。欠落エピソードの更新を開始します。")
                self._update_missing_episodes(novels_with_missing, progress_queue, on_complete)

            # 新着更新の進捗計算用のカスタムキューを作成
            normal_progress_queue = None
            if progress_queue:
                normal_progress_queue = self._create_progress_wrapper(progress_queue, 20, 60)

            # 更新処理を実行（コールバックを変更して欠落更新に繋げる）
            self.update_novels(needs_update, normal_progress_queue, on_normal_update_complete)

        except Exception as e:
            logger.error(f"全小説の更新エラー: {e}")
            if progress_queue:
                progress_queue.put({
                    'percent': 0,
                    'message': f"エラー: {e}"
                })

            # 完了コールバックの呼び出し
            if on_complete:
                on_complete()

    def _update_missing_episodes(self, novels_with_missing, progress_queue=None, on_complete=None):
        """
        欠落エピソードのある小説を更新する内部メソッド

        Args:
            novels_with_missing: [(ncode, title, missing_episodes), ...] 形式のリスト
            progress_queue: 進捗状況を通知するキュー
            on_complete: 完了時に呼び出すコールバック関数
        """
        if not novels_with_missing:
            logger.info("欠落エピソードのある小説はありません")
            if progress_queue:
                progress_queue.put({
                    'percent': 100,
                    'message': "全ての更新処理が完了しました。"
                })

            if on_complete:
                on_complete()
            return

        total_novels = len(novels_with_missing)
        total_episodes = sum(len(episodes) for _, _, episodes in novels_with_missing)

        if progress_queue:
            progress_queue.put({
                'percent': 60,
                'message': f"{total_novels}冊の小説から合計{total_episodes}話の欠落エピソードを更新します..."
            })

        # 処理カウンタ
        processed_novels = 0
        processed_episodes = 0

        try:
            # 各小説の欠落エピソードを処理
            for ncode, title, missing_episodes in novels_with_missing:
                # 小説情報を取得
                novel = self.novel_manager.get_novel(ncode)
                if not novel:
                    logger.warning(f"小説 {ncode} ({title}) の情報が見つかりません")
                    processed_novels += 1
                    continue

                rating = novel[4] if len(novel) > 4 else None

                # 小説ごとの進捗メッセージ
                if progress_queue:
                    novel_progress = 60 + (processed_novels / total_novels) * 40
                    progress_queue.put({
                        'percent': int(novel_progress),
                        'message': f"[{processed_novels + 1}/{total_novels}] {title} - {len(missing_episodes)}話の欠落エピソードを更新中..."
                    })

                # 現在の日時を取得（更新時のタイムスタンプとして使用）
                current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                # 各欠落エピソードを処理
                for i, ep_no in enumerate(missing_episodes):
                    episode_progress = i / len(missing_episodes)
                    overall_progress = 60 + ((processed_novels + episode_progress) / total_novels) * 40

                    if progress_queue:
                        progress_queue.put({
                            'percent': int(overall_progress),
                            'message': f"[{processed_novels + 1}/{total_novels}] {title} - エピソード {ep_no} を取得中... ({i + 1}/{len(missing_episodes)})"
                        })

                    # エピソードを取得
                    episode_content, episode_title = catch_up_episode(ncode, ep_no, rating)

                    # データベースに保存
                    if episode_content and episode_title:
                        self.db_manager.insert_episode(ncode, ep_no, episode_content, episode_title, current_time)
                        processed_episodes += 1
                    else:
                        logger.warning(f"エピソード {ncode}-{ep_no} の取得に失敗しました")

                # 総エピソード数を更新
                self.db_manager.update_total_episodes(ncode)

                # 小説テーブルのupdate_atを更新
                self.db_manager.execute_query(
                    "UPDATE novels_descs SET updated_at = ? WHERE n_code = ?",
                    (current_time, ncode)
                )

                # 小説キャッシュをクリア
                self.novel_manager.clear_cache(ncode)

                # 処理済みカウンタを増加
                processed_novels += 1

            # 処理完了メッセージ
            if progress_queue:
                progress_queue.put({
                    'percent': 100,
                    'message': f"全ての更新処理が完了しました。欠落エピソード {processed_episodes}話を更新しました。"
                })

            logger.info(
                f"欠落エピソードの更新が完了しました。{processed_novels}冊の小説から{processed_episodes}話を更新しました。")

        except Exception as e:
            logger.error(f"欠落エピソード更新エラー: {e}")
            if progress_queue:
                progress_queue.put({
                    'percent': 60,
                    'message': f"欠落エピソード更新中にエラーが発生しました: {e}"
                })

        finally:
            # 更新情報を再チェック
            self.check_shinchaku()

            # 完了コールバックの呼び出し
            if on_complete:
                on_complete()

    def _create_progress_wrapper(self, original_queue, start_percent, end_percent):
        """
        進捗表示を指定した範囲に調整するためのラッパーキューを作成

        Args:
            original_queue: 元の進捗表示キュー
            start_percent: 開始進捗率（全体に対する割合）
            end_percent: 終了進捗率（全体に対する割合）

        Returns:
            Queue: ラッパーキュー
        """
        wrapper_queue = queue.Queue()

        def process_queue():
            while True:
                try:
                    # タイムアウト付きでキューからデータを取得
                    progress_data = wrapper_queue.get(timeout=0.1)

                    # 進捗率を調整
                    if isinstance(progress_data, dict) and 'percent' in progress_data:
                        original_percent = progress_data['percent']
                        # 進捗率を指定範囲に変換
                        adjusted_percent = start_percent + (original_percent / 100) * (end_percent - start_percent)
                        progress_data['percent'] = int(adjusted_percent)

                    # 元のキューに送信
                    original_queue.put(progress_data)

                    wrapper_queue.task_done()

                except queue.Empty:
                    # キューが空の場合は一定時間待機
                    time.sleep(0.1)
                    continue
                except Exception as e:
                    logger.error(f"進捗ラッパーエラー: {e}")
                    continue

        # キュー処理スレッドを開始
        thread = threading.Thread(target=process_queue, daemon=True)
        thread.start()

        return wrapper_queue

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


    # app/ui/components/update_panel.py の _check_missing_episodes_thread メソッドの修正版



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

            # 文字列型を整数型に変換（エラー対策）
            current_ep = novel[5] if novel[5] is not None else 0
            total_ep = novel[6] if novel[6] is not None else 0

            if isinstance(current_ep, str):
                current_ep = int(current_ep) if current_ep.isdigit() else 0
            else:
                current_ep = int(current_ep) if current_ep is not None else 0

            if isinstance(total_ep, str):
                total_ep = int(total_ep) if total_ep.isdigit() else 0
            else:
                total_ep = int(total_ep) if total_ep is not None else 0

            # 欠落エピソードを検索
            missing_episodes = self.update_manager.db_manager.find_missing_episodes(ncode)

            # ログにデバッグ情報を出力
            logger.debug(
                f"再確認: {ncode} - {title} - current_ep: {current_ep}, total_ep: {total_ep}, missing: {len(missing_episodes) if missing_episodes else 0}")

            # 更新リストから該当小説を探す
            novel_index = None
            for i, novel_data in enumerate(self.shinchaku_novels):
                if novel_data[0] == ncode:
                    novel_index = i
                    break

            if novel_index is not None:
                # 更新が完了かつ欠落なしの場合（または欠落エピソードが空リストの場合）
                if current_ep >= total_ep and (not missing_episodes or len(missing_episodes) == 0):
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

                    if missing_episodes and len(missing_episodes) > 0:
                        self.progress_queue.put({
                            'message': f"小説 [{title}] にはまだ{len(missing_episodes)}個の欠落エピソードがあります。"
                        })
                    elif current_ep < total_ep:
                        self.progress_queue.put({
                            'message': f"小説 [{title}] にはまだ{total_ep - current_ep}話の未取得エピソードがあります。"
                        })
                    else:
                        self.progress_queue.put({
                            'message': f"小説 [{title}] の再確認が完了しました。"
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

        # 現在更新中リストをクリア
        self.currently_updating_novels = []

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

            # 更新完了コールバックを呼び出し
            if self.on_complete_callback:
                self.after(1500, self.on_complete_callback)

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


    # app/core/update_manager.py に追加する新しいメソッド

    def update_specific_episodes(self, ncode, episode_list, progress_queue=None, on_complete=None):
        """
        指定された小説の特定エピソードのみを更新

        Args:
            ncode (str): 小説コード
            episode_list (list): 更新するエピソード番号のリスト
            progress_queue (Queue, optional): 進捗状況を通知するキュー
            on_complete (callable, optional): 完了時に呼び出すコールバック関数
        """
        try:
            # この小説のデータを取得
            novel = self.novel_manager.get_novel(ncode)
            if not novel:
                if progress_queue:
                    progress_queue.put({
                        'show': True,
                        'percent': 0,
                        'message': f"エラー: 小説 {ncode} が見つかりません"
                    })

                if on_complete:
                    on_complete()
                return

            title = novel[1]
            rating = novel[4] if len(novel) > 4 else None

            # 指定されたエピソードが空の場合
            if not episode_list:
                if progress_queue:
                    progress_queue.put({
                        'show': True,
                        'percent': 100,
                        'message': f"小説 [{title}] に更新するエピソードはありません"
                    })

                if on_complete:
                    on_complete()
                return

            total_episodes = len(episode_list)

            if progress_queue:
                progress_queue.put({
                    'show': True,
                    'percent': 0,
                    'message': f"小説 [{title}] の {total_episodes} 話を更新します"
                })

            # 現在の日時を取得（エピソード更新時に使用）
            current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # エピソードを取得して保存
            for i, ep_no in enumerate(episode_list):
                # 進捗率計算
                progress_percent = int((i / total_episodes) * 100)

                if progress_queue:
                    progress_queue.put({
                        'percent': progress_percent,
                        'message': f"エピソード {i + 1}/{total_episodes} (No.{ep_no}) を取得中... ({progress_percent}%)"
                    })

                # エピソードを取得
                episode_content, episode_title = catch_up_episode(ncode, ep_no, rating)

                # データベースに保存
                if episode_content and episode_title:
                    self.db_manager.insert_episode(ncode, ep_no, episode_content, episode_title, current_time)
                else:
                    logger.warning(f"エピソード {ncode}-{ep_no} の取得に失敗しました")

            # 総エピソード数を更新
            self.db_manager.update_total_episodes(ncode)

            # 小説テーブルのupdate_atを更新
            self.db_manager.execute_query(
                "UPDATE novels_descs SET updated_at = ? WHERE n_code = ?",
                (current_time, ncode)
            )

            # 小説キャッシュをクリア
            self.novel_manager.clear_cache(ncode)

            if progress_queue:
                progress_queue.put({
                    'percent': 100,
                    'message': f"小説 [{title}] の指定エピソード {total_episodes}話の更新が完了しました"
                })

            logger.info(f"小説 {ncode} の指定エピソード {total_episodes}話の更新が完了しました")

        except Exception as e:
            logger.error(f"指定エピソード更新エラー: {e}")
            if progress_queue:
                progress_queue.put({
                    'percent': 0,
                    'message': f"エラー: {e}"
                })

        finally:
            # 更新情報を再チェック
            self.check_shinchaku()

            # 完了コールバックの呼び出し
            if on_complete:
                on_complete()


    # app/ui/components/update_panel.py に追加する新しいメソッド

    def show_episode_selection_dialog(self, ncode, title, rating, missing_episodes):
        """
        エピソード選択ダイアログを表示

        Args:
            ncode (str): 小説コード
            title (str): 小説タイトル
            rating (int): レーティング
            missing_episodes (list): 欠落エピソードのリスト
        """
        if not missing_episodes:
            messagebox.showinfo("情報", f"小説「{title}」に欠落エピソードはありません。")
            return

        # ダイアログウィンドウの作成
        dialog = tk.Toplevel(self)
        dialog.title(f"「{title}」欠落エピソード選択")
        dialog.geometry("500x400")
        dialog.transient(self)  # 親ウィンドウの上に表示
        dialog.grab_set()  # モーダルダイアログにする

        # ウィンドウの中央配置
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = (dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (dialog.winfo_screenheight() // 2) - (height // 2)
        dialog.geometry(f"+{x}+{y}")

        # 説明ラベル
        info_frame = tk.Frame(dialog, bg="#F0F0F0")
        info_frame.pack(fill="x", pady=10, padx=20)

        info_label = tk.Label(
            info_frame,
            text=f"小説「{title}」には以下の{len(missing_episodes)}話の欠落エピソードがあります。\n"
                 "更新するエピソードを選択してください。",
            justify="left",
            bg="#F0F0F0",
            wraplength=460
        )
        info_label.pack(fill="x")

        # 全選択チェックボックス
        select_all_frame = tk.Frame(dialog, bg="#F0F0F0")
        select_all_frame.pack(fill="x", pady=5, padx=20)

        select_all_var = tk.BooleanVar(value=True)  # デフォルトで全選択

        def toggle_all_selections():
            is_selected = select_all_var.get()
            for var in episode_vars:
                var.set(is_selected)

        select_all_checkbox = ttk.Checkbutton(
            select_all_frame,
            text="すべて選択/解除",
            variable=select_all_var,
            command=toggle_all_selections
        )
        select_all_checkbox.pack(side="left", padx=5)

        # チェックボックスフレーム（スクロール可能）
        canvas = tk.Canvas(dialog, bg="#F0F0F0")
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=(20, 0), pady=10)
        scrollbar.pack(side="right", fill="y", padx=(0, 20), pady=10)

        # マウスホイールイベントの設定
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # エピソードごとのチェックボックスを作成
        episode_vars = []
        episode_checkboxes = []

        # エピソード番号でソート
        sorted_episodes = sorted(missing_episodes)

        # 複数行に配置するための計算
        columns = 5  # 1行あたりの列数

        for i, ep_no in enumerate(sorted_episodes):
            row = i // columns
            col = i % columns

            # 変数を作成
            var = tk.BooleanVar(value=True)  # デフォルトで選択状態
            episode_vars.append(var)

            # チェックボックス
            checkbox = ttk.Checkbutton(
                scrollable_frame,
                text=f"{ep_no}話",
                variable=var,
                width=10
            )
            checkbox.grid(row=row, column=col, sticky="w", padx=5, pady=2)
            episode_checkboxes.append(checkbox)

        # 更新・キャンセルボタン
        button_frame = tk.Frame(dialog, bg="#F0F0F0")
        button_frame.pack(fill="x", pady=10, padx=20)

        def on_update():
            # 選択されたエピソードを取得
            selected_episodes = []
            for i, var in enumerate(episode_vars):
                if var.get():
                    selected_episodes.append(sorted_episodes[i])

            if not selected_episodes:
                messagebox.showinfo("情報", "エピソードが選択されていません。")
                return

            # ダイアログを閉じる
            dialog.destroy()

            # 更新処理を開始
            self.update_selected_episodes(ncode, title, rating, selected_episodes)

        update_button = ttk.Button(
            button_frame,
            text=f"選択したエピソードを更新",
            command=on_update
        )
        update_button.pack(side="left", padx=10)

        cancel_button = ttk.Button(
            button_frame,
            text="キャンセル",
            command=dialog.destroy
        )
        cancel_button.pack(side="right", padx=10)


    def update_selected_episodes(self, ncode, title, rating, episode_list):
        """
        選択されたエピソードを更新

        Args:
            ncode (str): 小説コード
            title (str): 小説タイトル
            rating (int): レーティング
            episode_list (list): 更新するエピソード番号のリスト
        """
        if not episode_list:
            return

        if self.update_in_progress:
            messagebox.showinfo("情報", "既に更新処理が実行中です")
            return

        # 確認ダイアログ
        confirm = messagebox.askyesno(
            "確認",
            f"小説「{title}」の選択された{len(episode_list)}話を更新します。\n続行しますか？"
        )

        if not confirm:
            return

        # 更新中フラグをセット
        self.update_in_progress = True

        # 進捗表示の初期化
        self.progress_queue.put({
            'show': True,
            'percent': 0,
            'message': f"選択されたエピソードの更新を開始します..."
        })

        # 更新処理を非同期で実行
        threading.Thread(
            target=self.update_manager.update_specific_episodes,
            args=(ncode, episode_list, self.progress_queue, self.on_update_complete)
        ).start()

    # 2. 一括欠落確認＆更新機能の実装

    # 2. 一括欠落確認＆更新機能の実装
    def check_and_update_all_missing(self):
        """すべての小説の欠落エピソードを確認して更新する"""
        if self.update_in_progress:
            messagebox.showinfo("情報", "現在更新処理中です。完了後にお試しください。")
            return

        # 確認ダイアログを表示
        confirm = messagebox.askyesno(
            "確認",
            "すべての小説の欠落エピソードを確認し、見つかった場合は更新します。\n"
            "この処理には時間がかかる場合があります。\n続行しますか？"
        )

        if not confirm:
            return

        # 処理中フラグを設定
        self.update_in_progress = True

        # 進捗表示の初期化
        self.progress_queue.put({
            'show': True,
            'percent': 0,
            'message': "すべての小説の欠落エピソードを確認中..."
        })

        # 進捗表示を確実に表示（タイマーを開始）
        self.check_progress_queue()

        # バックグラウンドで処理
        logger.info("一括欠落確認＆更新スレッドを開始します")
        thread = threading.Thread(target=self._check_and_update_all_missing_thread)
        thread.daemon = True
        thread.start()

    def _check_and_update_all_missing_thread(self):
        """一括欠落確認＆更新の実行（バックグラウンドスレッド用）"""
        try:
            logger.info("一括欠落確認＆更新処理を開始します")
            # データベースから全小説を取得（excluded カラムは存在しないのでシンプルに全小説を取得）
            query = """
            SELECT n_code, title, rating
            FROM novels_descs
            """
            all_novels = self.db_manager.execute_read_query(query)

            total_novels = len(all_novels)
            novels_with_missing = []

            logger.info(f"合計{total_novels}冊の小説をチェックします")
            self.progress_queue.put({
                'percent': 0,
                'message': f"{total_novels}冊の小説の欠落エピソードを確認中..."
            })

            # すべての小説の欠落エピソードを確認
            for i, (ncode, title, rating) in enumerate(all_novels):
                # 進捗表示を更新
                progress_percent = int((i / total_novels) * 50)  # 全体の50%を確認処理に使用
                self.progress_queue.put({
                    'percent': progress_percent,
                    'message': f"小説を確認中... ({i + 1}/{total_novels}): {title}"
                })

                # 欠落エピソードを確認
                try:
                    missing_episodes = self.db_manager.find_missing_episodes(ncode)
                    if missing_episodes and len(missing_episodes) > 0:
                        logger.info(f"小説 {ncode} ({title}) に {len(missing_episodes)} 個の欠落エピソードがあります")
                        novels_with_missing.append((ncode, title, rating, missing_episodes))
                except Exception as e:
                    logger.error(f"小説 {ncode} の欠落エピソード確認中にエラー: {e}")
                    continue

            # 欠落エピソードが見つかった小説数を表示
            if not novels_with_missing:
                logger.info("欠落エピソードのある小説は見つかりませんでした")
                self.progress_queue.put({
                    'percent': 100,
                    'message': "欠落エピソードのある小説は見つかりませんでした。"
                })

                # メインスレッドで実行するため、afterを使用
                def cleanup():
                    # 3秒後に進捗表示を非表示
                    self.progress_queue.put({'show': False})
                    # 更新中フラグをクリア
                    self.update_in_progress = False

                self.after(3000, cleanup)
                return

            # 欠落エピソードがある小説を更新
            total_missing_novels = len(novels_with_missing)
            total_missing_episodes = sum(len(episodes) for _, _, _, episodes in novels_with_missing)

            logger.info(
                f"{total_missing_novels}冊の小説から合計{total_missing_episodes}話の欠落エピソードが見つかりました")
            self.progress_queue.put({
                'percent': 50,
                'message': f"{total_missing_novels}冊の小説から合計{total_missing_episodes}話の欠落エピソードが見つかりました"
            })

            # 自動的に更新処理を続行する（確認ダイアログなしでシンプルに）
            logger.info("欠落エピソードの更新を開始します")

            # 処理カウンタ
            processed_novels = 0
            processed_episodes = 0

            # 現在の日時（更新時のタイムスタンプ用）
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            for ncode, title, rating, missing_episodes in novels_with_missing:
                # 小説ごとの進捗メッセージ
                novel_progress = 50 + (processed_novels / total_missing_novels) * 50
                self.progress_queue.put({
                    'percent': int(novel_progress),
                    'message': f"[{processed_novels + 1}/{total_missing_novels}] {title} - {len(missing_episodes)}話の欠落エピソードを更新中..."
                })

                # 各欠落エピソードを処理
                for i, ep_no in enumerate(missing_episodes):
                    episode_progress = i / len(missing_episodes)
                    overall_progress = 50 + ((processed_novels + episode_progress) / total_missing_novels) * 50

                    self.progress_queue.put({
                        'percent': int(overall_progress),
                        'message': f"[{processed_novels + 1}/{total_missing_novels}] {title} - エピソード {ep_no} を取得中... ({i + 1}/{len(missing_episodes)})"
                    })

                    # エピソードを取得
                    try:
                        from app.core.checker import catch_up_episode
                        episode_content, episode_title = catch_up_episode(ncode, ep_no, rating)

                        # データベースに保存
                        if episode_content and episode_title:
                            self.db_manager.insert_episode(ncode, ep_no, episode_content, episode_title, current_time)
                            processed_episodes += 1
                            logger.info(f"エピソード {ncode}-{ep_no} を取得して保存しました")
                        else:
                            logger.warning(f"エピソード {ncode}-{ep_no} の取得に失敗しました")
                    except Exception as e:
                        logger.error(f"エピソード {ncode}-{ep_no} の処理中にエラー: {e}")
                        continue

                # 総エピソード数を更新
                self.db_manager.update_total_episodes(ncode)

                # 小説テーブルのupdate_atを更新
                self.db_manager.execute_query(
                    "UPDATE novels_descs SET updated_at = ? WHERE n_code = ?",
                    (current_time, ncode)
                )

                # 小説キャッシュをクリア
                # 修正後
                try:
                    # update_managerを通じてnovel_managerにアクセス
                    self.update_manager.novel_manager.clear_cache(ncode)
                except AttributeError:
                    logger.warning(f"novel_managerにアクセスできませんでした：ncode={ncode}")
                except Exception as e:
                    logger.error(f"キャッシュクリア中にエラー: {e}")

                # 処理済みカウンタを増加
                processed_novels += 1

            # 完了メッセージ
            self.progress_queue.put({
                'percent': 100,
                'message': f"欠落エピソードの更新が完了しました。{processed_novels}冊の小説から{processed_episodes}話を更新しました。"
            })

            # 更新情報を再チェック
            self.check_shinchaku()

            # UIを更新（メインスレッドで）
            self.after(0, self.update_ui)

            # 欠落エピソードを順番に更新
            processed_novels = 0
            processed_episodes = 0

            # 現在の日時（更新時のタイムスタンプ用）
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            for ncode, title, rating, missing_episodes in novels_with_missing:
                # 小説ごとの進捗メッセージ
                novel_progress = 50 + (processed_novels / total_missing_novels) * 50
                self.progress_queue.put({
                    'percent': int(novel_progress),
                    'message': f"[{processed_novels + 1}/{total_missing_novels}] {title} - {len(missing_episodes)}話の欠落エピソードを更新中..."
                })

                # 各欠落エピソードを処理
                for i, ep_no in enumerate(missing_episodes):
                    episode_progress = i / len(missing_episodes)
                    overall_progress = 50 + ((processed_novels + episode_progress) / total_missing_novels) * 50

                    self.progress_queue.put({
                        'percent': int(overall_progress),
                        'message': f"[{processed_novels + 1}/{total_missing_novels}] {title} - エピソード {ep_no} を取得中... ({i + 1}/{len(missing_episodes)})"
                    })

                    # エピソードを取得
                    episode_content, episode_title = catch_up_episode(ncode, ep_no, rating)

                    # データベースに保存
                    if episode_content and episode_title:
                        self.db_manager.insert_episode(ncode, ep_no, episode_content, episode_title, current_time)
                        processed_episodes += 1
                    else:
                        logger.warning(f"エピソード {ncode}-{ep_no} の取得に失敗しました")

                # 総エピソード数を更新
                self.db_manager.update_total_episodes(ncode)

                # 小説テーブルのupdate_atを更新
                self.db_manager.execute_query(
                    "UPDATE novels_descs SET updated_at = ? WHERE n_code = ?",
                    (current_time, ncode)
                )

                # 小説キャッシュをクリア
                self.novel_manager.clear_cache(ncode)

                # 処理済みカウンタを増加
                processed_novels += 1

            # 完了メッセージ
            self.progress_queue.put({
                'percent': 100,
                'message': f"欠落エピソードの更新が完了しました。{processed_novels}冊の小説から{processed_episodes}話を更新しました。"
            })

            # 更新情報を再チェック
            self.check_shinchaku()

            # UIを更新（メインスレッドで）
            self.after(0, self.update_ui)

            # 3秒後に進捗表示を非表示
            self.after(3000, lambda: self.progress_queue.put({'show': False}))

        except Exception as e:
            logger.error(f"一括欠落確認＆更新エラー: {e}")
            import traceback
            logger.error(f"詳細エラー情報: {traceback.format_exc()}")

            # エラー表示
            self.progress_queue.put({
                'percent': 0,
                'message': f"エラーが発生しました: {e}"
            })

        finally:
            # 更新中フラグをクリア
            self.update_in_progress = False

            # 更新完了コールバックを呼び出し
            if self.on_complete_callback:
                self.after(0, self.on_complete_callback)

    def _set_result(self, result_container, value):
        """スレッド間通信用のヘルパーメソッド"""
        result_container[0] = value