import asyncio
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from bs4 import BeautifulSoup
import sqlite3
import os
import configparser
import threading
import time
import logging
from PIL import ImageFont, Image, ImageDraw, ImageTk
import tkinter.font as tkFont

# 自作モジュールのインポート
from bookshelf import shelf_maker, get_last_read, episode_getter, input_last_read
from checker import load_conf, dell_dl, del_yml, USER_AGENTS
from episode_count import update_total_episodes_single, update_total_episodes
from async_ackground_executor import BackgroundExecutor
from async_checker import NovelUpdater

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("novel_app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("main_view")


class NovelApp:
    def __init__(self, root):
        # メインウィンドウの設定
        self.root = root
        self.root.title("小説アプリ")
        self.root.attributes("-fullscreen", True)
        self.root.configure(bg="#0080A0")

        # インスタンス変数の初期化
        self.main_shelf = []
        self.last_read_novel = []
        self.episodes = []
        self.last_read_epno = 0
        self.novel_fontsize = 14
        self.set_font = "YuKyokasho Yoko"
        self.bg_color = "#FFFFFF"
        self.shinchaku_ep = 0
        self.shinchaku_novel = 0
        self.main_shinchaku = []

        # スクロール可能なフレームの設定
        self.scroll_canvas = None
        self.scrollable_frame = None

        # バックグラウンドエグゼキューター
        self.executor = BackgroundExecutor(self.root)

        # 非同期小説更新クラス
        self.novel_updater = None

        # UIの初期化
        self._initialize_ui()

        # ショートカットキーの設定
        self.root.bind('<Command-@>', lambda event: self.show_input_screen())

        # アプリ終了時の処理
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    async def initialize_async(self):
        """非同期初期化処理を行う"""
        # 非同期小説更新クラスを初期化
        try:
            self.novel_updater = await NovelUpdater().initialize()
        except Exception as e:
            logger.error(f"Failed to initialize novel updater: {e}")
            messagebox.showerror("初期化エラー",
                                 f"小説更新機能の初期化に失敗しました：{e}\n\nアプリを再起動してください。")
        return self

    def _initialize_ui(self):
        """UIコンポーネントの初期化"""
        # ボタンのスタイル設定
        self.BUTTON_WIDTH = 25
        self.BUTTON_FONT = ("Helvetica", 18)

        # ヘッダーフレーム
        self.header_frame = tk.Frame(self.root, bg="#0080A0")
        self.header_frame.grid(row=0, column=0, columnspan=2, sticky="ew")

        # 新着情報ラベル
        self.header_label = tk.Label(
            self.header_frame,
            text=f"新着情報\n新着{self.shinchaku_novel}件,{self.shinchaku_ep}話",
            bg="#0080A0",
            fg="white",
            font=("Helvetica", 24),
            anchor="w",
            justify="left",
        )
        self.header_label.pack(side="left", padx=30, pady=10)

        # 最後に読んだ小説のラベル
        last_read_title = f"{self.last_read_novel[1]} {self.last_read_epno}話" if self.last_read_novel else "なし"
        self.last_read_label = tk.Label(
            self.header_frame,
            text=f"最後に開いていた小説\n{last_read_title}",
            bg="#0080A0",
            fg="white",
            font=("Helvetica", 24),
            anchor="e",
            justify="right",
        )
        self.last_read_label.pack(side="right", padx=30, pady=10)

        # コンテンツフレーム（左側）
        self.content_frame = tk.Frame(self.root, bg="#F0F0F0")
        self.content_frame.grid(row=1, column=0, sticky="nsew")

        # リストフレーム（右側）
        self.list_frame = tk.Frame(self.root, bg="#F0F0F0")
        self.list_frame.grid(row=1, column=1, sticky="nsew")

        # スクロールキャンバスを初期化
        self._initialize_scroll_frame()

        # グリッドの行列調整
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=2)  # 小説一覧部分を広くする

        # メニューボタンの作成
        self._create_menu_buttons()

    def _initialize_scroll_frame(self):
        """スクロール可能なフレームを初期化"""
        self.scroll_canvas = tk.Canvas(self.list_frame, bg="#F0F0F0")
        self.scrollbar = ttk.Scrollbar(self.list_frame, orient="vertical", command=self.scroll_canvas.yview)
        self.scrollable_frame = ttk.Frame(self.scroll_canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all"))
        )

        self.scroll_canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.scroll_canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scroll_canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

    def _create_section_title(self, parent, text, row):
        """セクションタイトルを作成"""
        title = tk.Label(parent, text=text, font=self.BUTTON_FONT, bg="#0080A0", fg="white", anchor="w")
        title.grid(row=row, column=0, sticky="w", pady=(10, 0), padx=20)

    def _create_button(self, parent, text, row, command=None):
        """ボタンを作成"""
        if isinstance(text, tuple):
            text, command = text
        btn = ttk.Button(parent, text=text, width=self.BUTTON_WIDTH, command=command)
        btn.grid(row=row, column=0, padx=20, pady=5, sticky="w")

    def _create_menu_buttons(self):
        """メニューボタンを作成"""
        current_row = 0

        # 「小説をさがす」セクション
        self._create_section_title(self.content_frame, "小説をさがす", current_row)
        current_row += 1
        search_buttons = ["ランキング", "キーワード検索", "詳細検索", "ノクターノベルズ", "ムーンライトノベルズ",
                          "PickUp!"]
        for btn_text in search_buttons:
            self._create_button(self.content_frame, btn_text, current_row)
            current_row += 1

        # 「小説を読む」セクション
        self._create_section_title(self.content_frame, "小説を読む", current_row)
        current_row += 1
        read_buttons = [
            ("小説一覧", self.show_novel_list),
            ("最近更新された小説", self.show_updated_novels),
            ("最近読んだ小説", None),
            ("作者別・シリーズ別", None),
            ("タグ検索", None),
        ]
        for btn_text, command in read_buttons:
            self._create_button(self.content_frame, btn_text, current_row, command=command)
            current_row += 1

        # 「オプション」セクション
        self._create_section_title(self.content_frame, "オプション", current_row)
        current_row += 1
        option_buttons = [
            ("ダウンロード状況", None),
            ("設定", self.show_settings),
            ("更新チェック", self.check_updates)
        ]
        for btn_text in option_buttons:
            self._create_button(self.content_frame, btn_text, current_row)
            current_row += 1

    def _on_closing(self):
        """アプリ終了時の処理"""
        # 非同期処理のクリーンアップ
        self.executor.shutdown()

        # 非同期小説更新クラスのクリーンアップ
        if self.novel_updater:
            asyncio.run(self.novel_updater.close())

        # アプリを終了
        self.root.destroy()

    def _refresh_scroll_frame(self):
        """スクロール可能なフレームを再初期化"""
        # 既存のウィジェットをクリア
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        # スクロールフレームを再初期化
        self._initialize_scroll_frame()

    def show_novel_list(self):
        """小説一覧を表示"""
        self._refresh_scroll_frame()

        # データ準備
        buttons_data = [
            {"title": f"読む", "text": f"{row[1]} - 作者: {row[2]}", "n_code": row[0]}
            for row in self.main_shelf
        ]

        # ボタン作成
        for data in buttons_data:
            frame = tk.Frame(self.scrollable_frame, bg="#F0F0F0")
            frame.pack(fill="x", pady=2)

            # タイトルラベル
            title_label = tk.Label(frame, text=data["text"], bg="#F0F0F0", anchor="w")
            title_label.pack(side="left", padx=5, fill="x", expand=True)

            # クリックイベントをバインド
            title_label.bind("<Button-1>", lambda e, n_code=data["n_code"]: self.on_title_click(e, n_code))

    def on_title_click(self, event, n_code):
        """小説タイトルをクリックしたときの処理"""
        self.episodes = episode_getter(n_code)
        self.show_episode_list(self.episodes, n_code)

    def show_episode_list(self, episodes, ncode):
        """エピソード一覧を表示"""
        # スクロール位置をリセット
        self.scroll_canvas.yview_moveto(0)

        # エピソードを番号順にソート
        episodes.sort(key=lambda episode: int(episode[0]))

        # 既存のウィジェットをクリア
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        # エピソード一覧を表示
        for episode in episodes:
            frame = tk.Frame(self.scrollable_frame, bg="#F0F0F0")
            frame.pack(fill="x", pady=2)

            # エピソードラベル
            episode_label = tk.Label(
                frame,
                text=f"Episode {episode[0]}: {episode[1]}",
                bg="#F0F0F0",
                anchor="w"
            )
            episode_label.pack(side="left", padx=5, fill="x", expand=True)

            # クリックイベントをバインド
            episode_label.bind("<Button-1>", lambda e, ep=episode: self.on_episode_click(e, ep, ncode))

    def on_episode_click(self, event, episode, n_code):
        """エピソードをクリックしたときの処理"""
        # エピソードウィンドウを作成
        episode_window = tk.Toplevel(self.root)
        episode_window.title(f"Episode {episode[0]}: {episode[1]}")
        episode_window.geometry("800x600")

        # 最後に読んだ小説を記録
        input_last_read(n_code, episode[0])

        # スクロールテキストウィジェットを作成
        scrolled_text = scrolledtext.ScrolledText(
            episode_window,
            wrap=tk.WORD,
            font=(self.set_font, self.novel_fontsize)
        )
        scrolled_text.pack(fill=tk.BOTH, expand=True)

        # エピソード内容を表示する関数
        def show_episode(episode):
            scrolled_text.config(state=tk.NORMAL)
            scrolled_text.delete(1.0, tk.END)

            # HTMLコンテンツを解析
            soup = BeautifulSoup(episode[2], "html.parser")

            # 空の段落を削除
            for p in soup.find_all('p'):
                if not p.get_text(strip=True) and not p.attrs:
                    p.decompose()

            # テキストコンテンツを抽出
            text_content = soup.get_text()

            # テキストを挿入
            scrolled_text.insert(tk.END, text_content)
            scrolled_text.config(state=tk.DISABLED, bg=self.bg_color)

        # 次のエピソードに移動する関数
        def next_episode(event):
            nonlocal episode
            current_index = episodes.index(episode)
            if current_index < len(episodes) - 1:
                episode = episodes[current_index + 1]
                show_episode(episode)
                input_last_read(n_code, episode[0])
                episode_window.title(f"Episode {episode[0]}: {episode[1]}")

        # 前のエピソードに移動する関数
        def previous_episode(event):
            nonlocal episode
            current_index = episodes.index(episode)
            if current_index > 0:
                episode = episodes[current_index - 1]
                show_episode(episode)
                input_last_read(n_code, episode[0])
                episode_window.title(f"Episode {episode[0]}: {episode[1]}")

        # 初期エピソード内容を表示
        show_episode(episode)

        # キーボードショートカットをバインド
        episode_window.bind("<Right>", next_episode)
        episode_window.bind("<Left>", previous_episode)

    def show_settings(self):
        """設定画面を表示"""
        # 既存のウィジェットをクリア（スクロールキャンバスを除く）
        for widget in self.list_frame.winfo_children():
            if widget != self.scroll_canvas:
                widget.destroy()

        # 設定フレームを作成
        setting_frame = tk.Frame(self.list_frame, bg="#F0F0F0")
        setting_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # フォント選択
        font_label = tk.Label(setting_frame, text="フォント:", bg="#F0F0F0", anchor="w")
        font_label.grid(row=0, column=0, sticky="w", pady=5)
        font_var = tk.StringVar(value=self.set_font)
        font_dropdown = ttk.Combobox(setting_frame, textvariable=font_var, values=tkFont.families())
        font_dropdown.grid(row=0, column=1, sticky="ew", pady=5)

        # フォントサイズ
        size_label = tk.Label(setting_frame, text="文字サイズ:", bg="#F0F0F0", anchor="w")
        size_label.grid(row=1, column=0, sticky="w", pady=5)
        size_var = tk.IntVar(value=self.novel_fontsize)
        size_entry = tk.Entry(setting_frame, textvariable=size_var)
        size_entry.grid(row=1, column=1, sticky="ew", pady=5)

        # 背景色
        bg_label = tk.Label(setting_frame, text="バックグラウンド色 (RGB):", bg="#F0F0F0", anchor="w")
        bg_label.grid(row=2, column=0, sticky="w", pady=5)
        bg_var = tk.StringVar(value=self.bg_color)
        bg_entry = tk.Entry(setting_frame, textvariable=bg_var)
        bg_entry.grid(row=2, column=1, sticky="ew", pady=5)

        # 設定を適用する関数
        def apply_settings():
            self.novel_fontsize = size_var.get()
            self.set_font = font_var.get()
            self.bg_color = bg_var.get()

            # ConfigParserオブジェクトを作成
            config = configparser.ConfigParser()

            # 設定を追加
            config['Settings'] = {
                'Font': self.set_font,
                'FontSize': self.novel_fontsize,
                'BackgroundColor': self.bg_color
            }

            # 設定をファイルに書き込む
            with open('settings.ini', 'w') as configfile:
                config.write(configfile)

            messagebox.showinfo("設定", "設定が保存されました")

        # 適用ボタン
        apply_button = ttk.Button(setting_frame, text="適用", command=apply_settings)
        apply_button.grid(row=3, column=0, columnspan=2, pady=10)

    def show_input_screen(self):
        """入力画面を表示"""
        input_window = tk.Toplevel(self.root)
        input_window.title("入力画面")
        input_window.geometry("500x300")

        input_label = tk.Label(input_window, text="")
        input_label.pack(pady=10)

        input_text = tk.Text(input_window, height=10, width=50)
        input_text.pack(pady=5)

        def send_input(event=None):
            user_input = input_text.get("1.0", tk.END).strip()
            logger.info(f"User input: {user_input}")

            if user_input == "exit":
                self.root.quit()
            elif "update" in user_input:
                parts = user_input.split("update")
                if "--all" in parts[1]:
                    self.update_all_novels_async(self.main_shinchaku)
                elif "--single" in parts[1]:
                    single_parts = parts[1].split("--single")
                    if "--re_all" in single_parts[1] and "--n" in single_parts[1]:
                        ncode = single_parts[1].split("--")[1].strip()
                        self.re_fetch_all_episodes_async(ncode)
                    elif "--get_lost" in single_parts[1] and "--n" in single_parts[1]:
                        ncode = single_parts[1].split("--")[1].strip()
                        self.get_missing_episodes_async(ncode)
                    else:
                        input_label.config(text="コマンドが正しくありません")
                else:
                    input_label.config(text="コマンドが正しくありません")
            else:
                input_label.config(text=f"入力: {user_input}")

            input_text.delete("1.0", tk.END)

        def exit_input():
            input_window.destroy()

        exit_button = tk.Button(input_window, text="終了", command=exit_input)
        exit_button.pack(pady=10)
        input_text.bind("<Return>", send_input)

    def show_updated_novels(self):
        """更新された小説一覧を表示"""
        self._refresh_scroll_frame()

        # データを準備
        buttons_data = [
            {"text": f"{row[1]}", "n_code": row[0], "ep_no": row[2], "gen_all_no": row[3], "rating": row[4]}
            for row in self.main_shinchaku
        ]

        # 「一括更新」ボタンを上部に追加
        update_all_button = ttk.Button(
            self.scrollable_frame,
            text="一括更新",
            command=lambda: self.update_all_novels_async(self.main_shinchaku)
        )
        update_all_button.pack(fill="x", pady=2)

        # 更新された小説ごとにラベルを作成
        for data in buttons_data:
            frame = tk.Frame(self.scrollable_frame, bg="#F0F0F0")
            frame.pack(fill="x", pady=2)

            # タイトルラベル
            title_label = tk.Label(frame, text=data["text"], bg="#F0F0F0", anchor="w")
            title_label.pack(side="left", padx=5, fill="x", expand=True)

            # クリックイベントをバインド
            title_label.bind(
                "<Button-1>",
                lambda e, n_code=data["n_code"], ep_no=data["ep_no"],
                       gen_all_no=data["gen_all_no"], rating=data["rating"]:
                self.update_novel_async(n_code, ep_no, gen_all_no, rating)
            )

    async def _check_updates_async(self, progress_callback):
        """更新をチェックする非同期関数"""
        try:
            # データベース更新
            progress_callback(0, "データベースを更新中...")
            await self.novel_updater.db_update()

            # 新着チェック
            progress_callback(50, "新着小説をチェック中...")
            shinchaku_ep, main_shinchaku, shinchaku_novel = await self.novel_updater.shinchaku_checker()

            return shinchaku_ep, main_shinchaku, shinchaku_novel

        except Exception as e:
            logger.error(f"Error checking updates: {e}")
            raise

    def check_updates(self):
        """更新チェックを実行"""
        if not self.novel_updater:
            messagebox.showerror("エラー", "小説更新機能が初期化されていません")
            return

        # 更新チェックを開始
        self.executor.run_in_background(
            self._check_updates_async,
            on_complete=self._on_check_updates_complete
        )

    def _on_check_updates_complete(self, result):
        """更新チェック完了時の処理"""
        if result:
            shinchaku_ep, main_shinchaku, shinchaku_novel = result

            # UIを更新
            self.shinchaku_ep = shinchaku_ep
            self.main_shinchaku = main_shinchaku
            self.shinchaku_novel = shinchaku_novel

            self.header_label.config(text=f"新着情報\n新着{shinchaku_novel}件,{shinchaku_ep}話")

            # 更新情報を表示
            messagebox.showinfo(
                "更新チェック完了",
                f"新着小説: {shinchaku_novel}件\n新着エピソード: {shinchaku_ep}話"
            )

            # 新着リストがあれば表示
            if main_shinchaku:
                self.show_updated_novels()

    async def _update_novel_async(self, n_code, episode_no, general_all_no, rating, progress_callback):
        """小説を更新する非同期関数"""
        try:
            # エピソードを取得
            await self.novel_updater.new_episode(n_code, episode_no, general_all_no, rating)

            # データベースの更新
            progress_callback(90, "データベースを更新中...")
            await self.novel_updater._update_total_episodes_single(n_code)

            # 新着情報を更新
            progress_callback(95, "新着情報を更新中...")
            shinchaku_ep, main_shinchaku, shinchaku_novel = await self.novel_updater.shinchaku_checker()

            return {
                "n_code": n_code,
                "shinchaku_ep": shinchaku_ep,
                "main_shinchaku": main_shinchaku,
                "shinchaku_novel": shinchaku_novel
            }

        except Exception as e:
            logger.error(f"Error updating novel {n_code}: {e}")
            raise

    def update_novel_async(self, n_code, episode_no, general_all_no, rating):
        """非同期小説更新を開始"""
        if not self.novel_updater:
            messagebox.showerror("エラー", "小説更新機能が初期化されていません")
            return

        # 小説更新を開始
        self.executor.run_in_background(
            lambda progress_callback: self._update_novel_async(
                n_code, episode_no, general_all_no, rating, progress_callback
            ),
            on_complete=self._on_update_novel_complete
        )

    def _on_update_novel_complete(self, result):
        """小説更新完了時の処理"""
        if result:
            # UIを更新
            self.shinchaku_ep = result["shinchaku_ep"]
            self.main_shinchaku = result["main_shinchaku"]
            self.shinchaku_novel = result["shinchaku_novel"]

            self.header_label.config(text=f"新着情報\n新着{self.shinchaku_novel}件,{self.shinchaku_ep}話")

            # 小説一覧と更新された小説一覧を更新
            self.show_novel_list()
            self.show_updated_novels()

            # 成功メッセージを表示
            messagebox.showinfo("更新完了", f"小説 {result['n_code']} の更新が完了しました")

    async def _update_all_novels_async(self, shinchaku_novels, progress_callback):
        """すべての新着小説を更新する非同期関数"""
        try:
            if not shinchaku_novels:
                return {
                    "shinchaku_ep": 0,
                    "main_shinchaku": [],
                    "shinchaku_novel": 0,
                    "updated_count": 0
                }

            progress_callback(0, "小説を更新中...")

            # すべての小説を更新
            results = await self.novel_updater.update_all_novels(shinchaku_novels)

            # 戻り値をデバッグログに出力
            logger.info(f"update_all_novels returned: {type(results)}")
            logger.info(f"results content: {results}")

            # 辞書形式で返す
            return results

        except Exception as e:
            logger.error(f"Error updating all novels: {e}", exc_info=True)
            # エラーが発生してもUIを更新できるよう値を返す
            return {
                "shinchaku_ep": 0,
                "main_shinchaku": [],
                "shinchaku_novel": 0,
                "updated_count": 0,
                "error": str(e)
            }

    def update_all_novels_async(self, shinchaku_novels):
        """すべての新着小説の非同期更新を開始"""
        if not self.novel_updater:
            messagebox.showerror("エラー", "小説更新機能が初期化されていません")
            return

        if not shinchaku_novels:
            messagebox.showinfo("情報", "更新する小説がありません")
            return

        # すべての小説の更新を開始
        self.executor.run_in_background(
            lambda progress_callback: self._update_all_novels_async(
                shinchaku_novels, progress_callback
            ),
            on_complete=self._on_update_all_novels_complete
        )

    def _on_update_all_novels_complete(self, result):
        """すべての小説更新完了時の処理"""
        try:
            # resultがNoneの場合のエラーハンドリング
            if result is None:
                messagebox.showerror("エラー", "更新処理が失敗しました。詳細はログを確認してください。")
                return

            # 型をチェック
            logger.info(f"Received result type: {type(result)}")

            # エラーがあるか確認
            if "error" in result:
                messagebox.showerror("エラー", f"更新中にエラーが発生しました: {result['error']}")

            # UIを更新
            self.shinchaku_ep = result.get("shinchaku_ep", 0)
            self.main_shinchaku = result.get("main_shinchaku", [])
            self.shinchaku_novel = result.get("shinchaku_novel", 0)

            self.header_label.config(text=f"新着情報\n新着{self.shinchaku_novel}件,{self.shinchaku_ep}話")

            # 更新された小説一覧を表示
            self.show_updated_novels()

            # 成功メッセージを表示
            updated_count = result.get("updated_count", 0)
            messagebox.showinfo(
                "一括更新完了",
                f"{updated_count}件の小説が更新されました"
            )
        except Exception as e:
            logger.error(f"Error in _on_update_all_novels_complete: {e}", exc_info=True)
            messagebox.showerror("エラー", f"結果の処理中にエラーが発生しました: {str(e)}")
            # バックアップメッセージを表示
            self.show_updated_novels()

    async def _re_fetch_all_episodes_async(self, ncode, progress_callback):
        """小説のすべてのエピソードを再取得する非同期関数"""
        try:
            progress_callback(0, f"{ncode}のエピソード情報を取得中...")

            # データベースから現在のエピソード情報を取得
            conn = sqlite3.connect('database/novel_status.db')
            cursor = conn.cursor()

            cursor.execute('SELECT n_code, rating, general_all_no FROM novels_descs WHERE n_code = ?', (ncode,))
            novel_info = cursor.fetchone()

            if not novel_info:
                return {"success": False, "message": f"小説 {ncode} が見つかりません"}

            _, rating, general_all_no = novel_info

            if not general_all_no:
                return {"success": False, "message": f"小説 {ncode} のエピソード数情報がありません"}

            # エピソードを再取得
            progress_callback(10, f"{ncode}のエピソードを再取得中...")
            for i in range(general_all_no):
                if i % 5 == 0:  # 進捗更新
                    progress = int(10 + (i / general_all_no) * 80)
                    progress_callback(progress, f"エピソード {i + 1}/{general_all_no} を取得中...")

                episode_no = i + 1
                episode, title = await self.novel_updater.catch_up_episode(ncode, episode_no, rating)

                if episode and title:
                    # データベースを更新
                    cursor.execute("""
                        INSERT OR REPLACE INTO episodes (ncode, episode_no, body, e_title)
                        VALUES (?, ?, ?, ?)
                    """, (ncode, episode_no, episode, title))

                    if episode_no % 10 == 0:  # 10エピソードごとにコミット
                        conn.commit()

                # レート制限を回避するために待機
                await asyncio.sleep(0.5)

            # 最終コミット
            conn.commit()

            # 総エピソード数を更新
            progress_callback(95, "データベースを更新中...")
            await self.novel_updater._update_total_episodes_single(ncode)

            conn.close()

            return {"success": True, "message": f"{ncode}の全{general_all_no}エピソードを再取得しました"}

        except Exception as e:
            logger.error(f"Error re-fetching episodes for {ncode}: {e}")
            if 'conn' in locals():
                conn.close()
            raise

    def re_fetch_all_episodes_async(self, ncode):
        """小説のすべてのエピソードの非同期再取得を開始"""
        if not self.novel_updater:
            messagebox.showerror("エラー", "小説更新機能が初期化されていません")
            return

        # 再取得を開始
        self.executor.run_in_background(
            lambda progress_callback: self._re_fetch_all_episodes_async(
                ncode, progress_callback
            ),
            on_complete=self._on_re_fetch_all_episodes_complete
        )

    def _on_re_fetch_all_episodes_complete(self, result):
        """エピソード再取得完了時の処理"""
        if result:
            if result["success"]:
                messagebox.showinfo("完了", result["message"])
            else:
                messagebox.showerror("エラー", result["message"])

    async def _get_missing_episodes_async(self, ncode, progress_callback):
        """欠落しているエピソードを取得する非同期関数"""
        try:
            progress_callback(0, f"{ncode}のエピソード情報を取得中...")

            # データベースから現在のエピソード情報を取得
            conn = sqlite3.connect('database/novel_status.db')
            cursor = conn.cursor()

            cursor.execute('SELECT n_code, rating, general_all_no FROM novels_descs WHERE n_code = ?', (ncode,))
            novel_info = cursor.fetchone()

            if not novel_info:
                return {"success": False, "message": f"小説 {ncode} が見つかりません"}

            _, rating, general_all_no = novel_info

            if not general_all_no:
                return {"success": False, "message": f"小説 {ncode} のエピソード数情報がありません"}

            # 既存のエピソードを取得
            cursor.execute('SELECT episode_no FROM episodes WHERE ncode = ?', (ncode,))
            existing_episodes = [int(row[0]) for row in cursor.fetchall()]

            # 欠落しているエピソードを特定
            all_episodes = set(range(1, general_all_no + 1))
            missing_episodes = sorted(list(all_episodes - set(existing_episodes)))

            if not missing_episodes:
                return {"success": True, "message": f"小説 {ncode} に欠落しているエピソードはありません"}

            # 欠落エピソードを取得
            progress_callback(10, f"{ncode}の欠落エピソードを取得中...")
            total_missing = len(missing_episodes)

            for i, episode_no in enumerate(missing_episodes):
                progress = int(10 + (i / total_missing) * 80)
                progress_callback(progress, f"欠落エピソード {i + 1}/{total_missing} ({episode_no}) を取得中...")

                episode, title = await self.novel_updater.catch_up_episode(ncode, episode_no, rating)

                if episode and title:
                    # データベースを更新
                    cursor.execute("""
                        INSERT OR REPLACE INTO episodes (ncode, episode_no, body, e_title)
                        VALUES (?, ?, ?, ?)
                    """, (ncode, episode_no, episode, title))

                    if i % 10 == 0:  # 10エピソードごとにコミット
                        conn.commit()

                # レート制限を回避するために待機
                await asyncio.sleep(0.5)

            # 最終コミット
            conn.commit()

            # 総エピソード数を更新
            progress_callback(95, "データベースを更新中...")
            await self.novel_updater._update_total_episodes_single(ncode)

            conn.close()

            return {
                "success": True,
                "message": f"{ncode}の欠落{total_missing}エピソードを取得しました"
            }

        except Exception as e:
            logger.error(f"Error getting missing episodes for {ncode}: {e}")
            if 'conn' in locals():
                conn.close()
            raise

    def get_missing_episodes_async(self, ncode):
        """欠落エピソードの非同期取得を開始"""
        if not self.novel_updater:
            messagebox.showerror("エラー", "小説更新機能が初期化されていません")
            return

        # 欠落エピソードの取得を開始
        self.executor.run_in_background(
            lambda progress_callback: self._get_missing_episodes_async(
                ncode, progress_callback
            ),
            on_complete=self._on_get_missing_episodes_complete
        )

    def _on_get_missing_episodes_complete(self, result):
        """欠落エピソード取得完了時の処理"""
        if result:
            if result["success"]:
                messagebox.showinfo("完了", result["message"])
            else:
                messagebox.showerror("エラー", result["message"])


# アプリの起動関数
async def start_app():
    # 初期化処理
    dell_dl()
    del_yml()

    # メインウィンドウを作成
    root = tk.Tk()

    # アプリを初期化
    app = NovelApp(root)
    await app.initialize_async()

    # データを読み込み
    app.main_shelf = shelf_maker()
    app.last_read_novel, app.last_read_epno = get_last_read(app.main_shelf)
    app.set_font, app.novel_fontsize, app.bg_color = load_conf()

    # 新着情報を取得
    shinchaku_ep, main_shinchaku, shinchaku_novel = 0, [], 0
    try:
        shinchaku_ep, main_shinchaku, shinchaku_novel = await app.novel_updater.shinchaku_checker()
    except Exception as e:
        logger.error(f"Error checking updates: {e}")

    app.shinchaku_ep = shinchaku_ep
    app.main_shinchaku = main_shinchaku
    app.shinchaku_novel = shinchaku_novel

    # ヘッダーを更新
    app.header_label.config(text=f"新着情報\n新着{shinchaku_novel}件,{shinchaku_ep}話")

    # 最後に読んだ小説情報を更新
    if app.last_read_novel:
        app.last_read_label.config(text=f"最後に開いていた小説\n{app.last_read_novel[1]} {app.last_read_epno}話")

    return app, root


# メイン関数
def main():
    # 非同期処理でアプリを起動
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # アプリの初期化と起動
    app, root = loop.run_until_complete(start_app())

    # GUIループを開始
    root.mainloop()


if __name__ == "__main__":
    main()