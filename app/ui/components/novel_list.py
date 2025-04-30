"""
小説一覧を表示するUIコンポーネント（ソート機能付き）
"""
import threading
import tkinter as tk
from tkinter import ttk
import time
from app.utils.logger_manager import get_logger

# ロガーの設定
logger = get_logger('NovelListView')


class NovelListView(ttk.Frame):
    """小説一覧を表示するビュークラス"""

    def __init__(self, parent, font_name, novel_manager, on_select_callback):
        """
        初期化

        Args:
            parent: 親ウィジェット
            font_name: フォント名
            novel_manager: 小説マネージャ
            on_select_callback: 小説選択時のコールバック関数
        """
        super().__init__(parent)
        self.parent = parent
        self.font_name = font_name
        self.novel_manager = novel_manager
        self.on_select_callback = on_select_callback

        # 状態管理
        self.current_page = 0
        self.items_per_page = 100
        self.total_pages = 0
        self.novels = []
        self.search_text = ""
        self.sort_key = "updated_at"  # デフォルトのソート基準
        self.sort_order = True  # True: 降順, False: 昇順

        # UIコンポーネント
        self.scroll_canvas = None
        self.scrollable_frame = None
        self.page_label = None
        self.prev_button = None
        self.next_button = None
        self.list_display_frame = None
        self.search_entry = None
        self.sort_combobox = None  # 追加：ソートプルダウン

        # UIの初期化
        self.init_ui()

    def init_ui(self):
        """UIコンポーネントの初期化"""
        # 検索バー
        search_frame = ttk.Frame(self)
        search_frame.pack(fill="x", pady=5, padx=5)

        ttk.Label(search_frame, text="検索:").pack(side="left", padx=5)

        self.search_entry = ttk.Entry(search_frame)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.search_entry.bind("<Return>", self.search_novels)

        search_button = ttk.Button(search_frame, text="検索", command=self.search_novels)
        search_button.pack(side="left", padx=5)

        clear_button = ttk.Button(search_frame, text="クリア", command=self.clear_search)
        clear_button.pack(side="left", padx=5)

        # ソートドロップダウン（新規追加）
        sort_frame = ttk.Frame(self)
        sort_frame.pack(fill="x", pady=(0, 5), padx=5)

        ttk.Label(sort_frame, text="並び替え:").pack(side="left", padx=5)

        # ソートオプション
        self.sort_options = [
            "更新日時 降順",
            "更新日時 昇順",
            "Nコード 昇順",
            "Nコード 降順",
            "タイトル 昇順",
            "タイトル 降順",
            "総話数 降順",
            "総話数 昇順"
        ]

        self.sort_var = tk.StringVar()
        self.sort_var.set(self.sort_options[0])  # デフォルト値

        self.sort_combobox = ttk.Combobox(sort_frame, textvariable=self.sort_var,
                                          values=self.sort_options, state="readonly", width=15)
        self.sort_combobox.pack(side="left", padx=5)
        self.sort_combobox.bind("<<ComboboxSelected>>", self.sort_novels)

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

        # ページングコントロールフレーム
        paging_frame = tk.Frame(self.scrollable_frame, bg="#F0F0F0")
        paging_frame.pack(fill="x", pady=5)

        # 前のページボタン
        self.prev_button = ttk.Button(
            paging_frame,
            text="前へ",
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
            text="次へ",
            command=lambda: self.load_page(self.current_page + 1)
        )
        self.next_button.pack(side="left", padx=5)

        # リスト表示フレーム
        self.list_display_frame = tk.Frame(self.scrollable_frame, bg="#F0F0F0")
        self.list_display_frame.pack(fill="x", expand=True)

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
        """小説一覧を表示"""
        # スクロール位置をリセット
        self.scroll_canvas.yview_moveto(0)

        # ローディング表示
        self.show_loading()

        # 小説データを取得（バックグラウンドスレッドで）
        threading.Thread(target=self.load_novels).start()

    def show_loading(self):
        """ローディング表示"""
        # 前のリストをクリア
        for widget in self.list_display_frame.winfo_children():
            widget.destroy()

        # ローディングメッセージ
        loading_label = tk.Label(
            self.list_display_frame,
            text="小説データを読み込んでいます...",
            bg="#F0F0F0",
            font=(self.font_name, 12)
        )
        loading_label.pack(pady=20)

    def load_novels(self):
        """小説データの読み込み（バックグラウンドスレッド用）"""
        try:
            # 小説データを取得
            self.novels = self.novel_manager.get_all_novels()

            # 検索フィルタが有効ならフィルタリング
            if self.search_text:
                self.novels = [n for n in self.novels if self.filter_novel(n, self.search_text)]

            # 選択されたソート条件に従ってソート
            self.sort_novels_data()

            # 総ページ数を計算
            self.total_pages = (len(self.novels) + self.items_per_page - 1) // self.items_per_page

            # UIの更新はメインスレッドで行う
            self.after(0, lambda: self.load_page(0))

        except Exception as e:
            logger.error(f"小説データの読み込みエラー: {e}")
            # エラー表示
            self.after(0, lambda: self.show_error(f"小説データの読み込みに失敗しました: {e}"))

    def sort_novels(self, event=None):
        """ソート変更時の処理"""
        # 現在選択されているソートオプションを取得
        selected_option = self.sort_var.get()

        # ソートオプションに基づいて、ソートキーと順序を設定
        if "更新日時" in selected_option:
            self.sort_key = "updated_at"
        elif "Nコード" in selected_option:
            self.sort_key = "n_code"
        elif "タイトル" in selected_option:
            self.sort_key = "title"
        elif "総話数" in selected_option:
            self.sort_key = "total_ep"

        # 昇順・降順の設定
        self.sort_order = "降順" in selected_option

        # データを再読み込み
        self.show_novels()

    def sort_novels_data(self):
        """選択されたソート条件に従って小説リストをソート"""
        try:
            # ソートキーに基づいて、インデックスを決定
            if self.sort_key == "updated_at":
                key_index = 3  # updated_at のインデックス
            elif self.sort_key == "n_code":
                key_index = 0  # n_code のインデックス
            elif self.sort_key == "title":
                key_index = 1  # title のインデックス
            elif self.sort_key == "total_ep":
                key_index = 5  # total_ep のインデックス（もしくは使用しているものに合わせる）
            else:
                key_index = 3  # デフォルトは更新日時

            # ソート実行
            def sort_key(novel):
                value = novel[key_index] if key_index < len(novel) else None

                # 数値型の場合は数値に変換してソート
                if self.sort_key == "total_ep" and value is not None:
                    try:
                        return int(value) if value else 0
                    except (ValueError, TypeError):
                        return 0

                # 文字列の場合
                if value is None:
                    return "" if self.sort_key == "n_code" or self.sort_key == "title" else "0000-00-00"

                return value

            # ソート実行（昇順・降順に合わせる）
            self.novels.sort(key=sort_key, reverse=self.sort_order)

        except Exception as e:
            logger.error(f"小説のソート中にエラーが発生しました: {e}")

    def load_page(self, page_num):
        """指定ページの小説を表示"""
        # ページ境界チェック
        if page_num < 0 or (page_num >= self.total_pages and self.total_pages > 0):
            return

        self.current_page = page_num

        # 前のリストをクリア
        for widget in self.list_display_frame.winfo_children():
            widget.destroy()

        # 現在のページに表示する項目の範囲を計算
        start_idx = self.current_page * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, len(self.novels))

        # ページングラベルを更新
        self.page_label.config(text=f"ページ {self.current_page + 1}/{self.total_pages if self.total_pages > 0 else 1}")

        # 前/次ボタンの有効/無効状態を更新
        self.prev_button.config(state=tk.NORMAL if self.current_page > 0 else tk.DISABLED)
        self.next_button.config(state=tk.NORMAL if self.current_page < self.total_pages - 1 else tk.DISABLED)

        # 小説が一つもない場合のメッセージ
        if not self.novels:
            no_novels_label = tk.Label(
                self.list_display_frame,
                text="小説が見つかりません",
                bg="#F0F0F0",
                font=(self.font_name, 12)
            )
            no_novels_label.pack(pady=20)
            return

        # 現在のページの項目を表示
        for i in range(start_idx, end_idx):
            row = self.novels[i]

            # 項目用フレーム
            item_frame = tk.Frame(self.list_display_frame, bg="#F0F0F0")
            item_frame.pack(fill="x", pady=2)

            # タイトルラベル
            title_text = f"{row[1]}"
            if row[2]:  # 作者名がある場合
                title_text += f" - 作者: {row[2]}"

            title_label = tk.Label(
                item_frame,
                text=title_text,
                bg="#F0F0F0",
                anchor="w",
                font=(self.font_name, 10)
            )
            title_label.pack(side="left", padx=5, fill="x", expand=True)

            # クリックイベント
            title_label.bind("<Button-1>", lambda e, n_code=row[0]: self.on_novel_click(n_code))

            # ホバーエフェクト
            title_label.bind("<Enter>", lambda e, label=title_label: label.config(bg="#E0E0E0"))
            title_label.bind("<Leave>", lambda e, label=title_label: label.config(bg="#F0F0F0"))

    def on_novel_click(self, n_code):
        """小説がクリックされたときの処理"""
        if self.on_select_callback:
            self.on_select_callback(n_code)

    def search_novels(self, event=None):
        """小説の検索"""
        self.search_text = self.search_entry.get().strip().lower()
        self.show_novels()

    def clear_search(self):
        """検索をクリア"""
        self.search_entry.delete(0, tk.END)
        self.search_text = ""
        self.show_novels()

    def filter_novel(self, novel, search_text):
        """
        検索テキストに基づいて小説をフィルタリング

        Args:
            novel: 小説データ
            search_text: 検索テキスト

        Returns:
            bool: 検索条件に一致するかどうか
        """
        if not search_text:
            return True

        # 小説コード、タイトル、作者名、あらすじを検索
        n_code = novel[0].lower() if novel[0] else ""
        title = novel[1].lower() if novel[1] else ""
        author = novel[2].lower() if novel[2] else ""
        synopsis = novel[7].lower() if len(novel) > 7 and novel[7] else ""

        # いずれかのフィールドに検索テキストが含まれるかチェック
        return (search_text in n_code or
                search_text in title or
                search_text in author or
                search_text in synopsis)

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