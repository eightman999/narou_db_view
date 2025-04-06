"""
改良された小説ビューアアプリケーション
- モジュール化されたアプリケーション構造
- 非同期データロード
- オンデマンドファイル操作
- パフォーマンス最適化
"""
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import queue

# モジュールのインポート
from app.ui.components.novel_list import NovelListView
from app.ui.components.episode_list import EpisodeListView
from app.ui.components.settings_panel import SettingsPanel
from app.ui.components.command_prompt import CommandPrompt
from app.ui.components.update_panel import UpdatePanel

from app.core.novel_manager import NovelManager
from app.core.database_manager import DatabaseManager
from app.core.settings_manager import SettingsManager
from app.core.update_manager import UpdateManager

from app.utils.logger_manager import get_logger

# ロガーの設定
logger = get_logger('AppMain')


class NovelViewerApp:
    """メインアプリケーションクラス"""

    def __init__(self):
        """アプリケーションの初期化"""
        self.root = None
        self.main_frame = None
        self.side_panel = None
        self.content_frame = None

        # コンポーネント
        self.header_label = None
        self.progress_label = None

        # マネージャーの初期化
        self.settings_manager = SettingsManager()
        self.db_manager = DatabaseManager()
        self.novel_manager = NovelManager(self.db_manager)
        self.update_manager = UpdateManager(self.db_manager, self.novel_manager)

        # 非同期処理用キュー
        self.task_queue = queue.Queue()
        self.update_progress_queue = queue.Queue()

        # ビュー
        self.novel_list_view = None
        self.episode_list_view = None
        self.settings_panel = None
        self.update_panel = None

        # 状態管理
        self.update_in_progress = False
        self.current_view = None  # 現在表示しているビューを追跡するための変数

        # 設定の読み込み
        self.load_settings()

    def load_settings(self):
        """設定を読み込む"""
        self.font_name, self.font_size, self.bg_color = self.settings_manager.load_settings()
        logger.info(f"設定を読み込みました: フォント={self.font_name}, サイズ={self.font_size}, 背景色={self.bg_color}")

    def initialize_ui(self):
        """UIの初期化"""
        # ルートウィンドウの設定
        self.root = tk.Tk()
        self.root.title("小説ビューア")
        self.root.geometry("1000x600")

        # スタイル設定
        ttk.Style().configure("TButton", font=(self.font_name, 10))

        # メインフレーム
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(fill="both", expand=True)

        # サイドパネル
        self.side_panel = tk.Frame(self.main_frame, width=200, bg="#E0E0E0")
        self.side_panel.pack(side="left", fill="y")
        self.side_panel.pack_propagate(False)  # サイズを固定

        # コンテンツフレーム
        self.content_frame = tk.Frame(self.main_frame, bg="#F0F0F0")
        self.content_frame.pack(side="right", fill="both", expand=True)

        # ヘッダーラベル（新着情報用）
        self.header_label = tk.Label(
            self.side_panel,
            text="新着情報\n読み込み中...",
            bg="#E0E0E0",
            font=(self.font_name, 12)
        )
        self.header_label.pack(pady=10)

        # サイドパネルのボタン
        self.create_side_panel_buttons()

        # 進捗状況ラベル
        self.progress_label = tk.Label(self.side_panel, text="", bg="#E0E0E0", wraplength=180)
        self.progress_label.pack(pady=10, side="bottom")

        # 初期ビューを表示
        self.show_loading_screen()

        # 非同期データロードの開始
        self.start_background_tasks()

        # 進捗状況の更新機能を開始
        self.root.after(100, self.update_progress)

    def create_side_panel_buttons(self):
        """サイドパネルのボタンを作成"""
        # ボタンスタイル
        button_style = {"width": 15, "font": (self.font_name, 10), "pady": 5}

        # 小説一覧ボタン
        novel_list_button = tk.Button(
            self.side_panel,
            text="小説一覧",
            command=lambda: self.show_novel_list(),
            **button_style
        )
        novel_list_button.pack(pady=5)

        # 更新された小説ボタン
        updated_novels_button = tk.Button(
            self.side_panel,
            text="更新された小説",
            command=lambda: self.show_updated_novels(),
            **button_style
        )
        updated_novels_button.pack(pady=5)

        # 設定ボタン
        settings_button = tk.Button(
            self.side_panel,
            text="設定",
            command=lambda: self.show_settings(),
            **button_style
        )
        settings_button.pack(pady=5)

        # コマンド入力ボタン
        command_button = tk.Button(
            self.side_panel,
            text="コマンド入力",
            command=lambda: self.show_command_prompt(),
            **button_style
        )
        command_button.pack(pady=5)

    def show_loading_screen(self):
        """ローディング画面を表示"""
        # 既存コンテンツをクリア
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        # ローディングインジケータ
        loading_frame = tk.Frame(self.content_frame, bg="#F0F0F0")
        loading_frame.pack(fill="both", expand=True)

        loading_label = tk.Label(
            loading_frame,
            text="データを読み込んでいます...",
            font=(self.font_name, 14),
            bg="#F0F0F0"
        )
        loading_label.pack(expand=True)

    def start_background_tasks(self):
        """バックグラウンドタスクを開始"""
        # データベース初期化スレッド
        db_thread = threading.Thread(target=self.initialize_database)
        db_thread.daemon = True
        db_thread.start()

    def initialize_database(self):
        """データベースの初期化（バックグラウンドスレッドで実行）"""
        try:
            # データベース接続
            self.db_manager.connect()

            # 小説データの読み込み
            self.novel_manager.load_novels()

            # 新着情報のチェック
            shinchaku_info = self.update_manager.check_shinchaku()
            shinchaku_ep, shinchaku_novels, shinchaku_count = shinchaku_info

            # UI更新はメインスレッドで実行
            self.root.after(0, lambda: self.header_label.config(
                text=f"新着情報\n新着{shinchaku_count}件,{shinchaku_ep}話"))

            # 初期表示を設定
            self.root.after(0, self.show_novel_list)

            logger.info("データベース初期化が完了しました")

        except Exception as e:
            logger.error(f"データベース初期化エラー: {e}")
            self.root.after(0,
                            lambda: messagebox.showerror("エラー", f"データベース初期化中にエラーが発生しました: {e}"))

    def update_progress(self):
        """進捗状況の表示を更新する"""
        if not self.update_progress_queue.empty():
            message = self.update_progress_queue.get()
            self.progress_label.config(text=message)

        # 更新中は定期的に再実行
        if self.update_in_progress:
            self.root.after(100, self.update_progress)
        else:
            # 3秒後にメッセージをクリア
            self.root.after(3000, lambda: self.progress_label.config(text=""))

    def show_novel_list(self):
        """小説一覧の表示"""
        # 既存コンテンツをクリア
        for widget in self.content_frame.winfo_children():
            widget.destroy()  # 既存ウィジェットを完全に削除

        # 現在のビューを更新
        self.current_view = "novel_list"

        # 小説リストビューを毎回新しく作成
        self.novel_list_view = NovelListView(self.content_frame, self.font_name, self.novel_manager,
                                             self.show_episode_list)
        self.novel_list_view.pack(fill="both", expand=True)
        self.novel_list_view.show_novels()

    def show_episode_list(self, ncode):
        """エピソード一覧の表示"""
        # 既存コンテンツをクリア
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        # 現在のビューを更新
        self.current_view = "episode_list"

        # エピソードリストビューを毎回新しく作成
        self.episode_list_view = EpisodeListView(self.content_frame, self.font_name, self.font_size, self.bg_color,
                                                 self.novel_manager)
        self.episode_list_view.pack(fill="both", expand=True)
        self.episode_list_view.show_episodes(ncode)

    def show_updated_novels(self):
        """更新された小説の表示"""
        # 既存コンテンツをクリア
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        # 現在のビューを更新
        self.current_view = "updated_novels"

        # 更新パネルを毎回新しく作成
        self.update_panel = UpdatePanel(self.content_frame, self.update_manager, self.update_novels,
                                      self.on_update_complete)
        self.update_panel.pack(fill="both", expand=True)
        self.update_panel.show_novels()

    def show_settings(self):
        """設定画面の表示"""
        # 既存コンテンツをクリア
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        # 現在のビューを更新
        self.current_view = "settings"

        # 設定パネルを毎回新しく作成
        self.settings_panel = SettingsPanel(self.content_frame, self.settings_manager, self.on_settings_changed)
        self.settings_panel.pack(fill="both", expand=True)
        self.settings_panel.show_settings(self.font_name, self.font_size, self.bg_color)

    def show_command_prompt(self):
        """コマンドプロンプトの表示"""
        # コマンドプロンプトを作成
        cmd_prompt = CommandPrompt(self.root, self.handle_command)
        return cmd_prompt

    def handle_command(self, command):
        """コマンドの処理"""
        if command.lower().startswith("update"):
            return self.handle_update_command(command)
        else:
            return "エラー: 不明なコマンドです。'help'コマンドでヘルプを表示します。"

    def handle_update_command(self, command):
        """更新コマンドの処理"""
        # 更新処理中なら実行しない
        if self.update_in_progress:
            return "エラー: すでに更新処理が実行中です。完了までお待ちください。"

        # 全作品更新コマンド
        if "--all" in command:
            threading.Thread(
                target=self.update_manager.update_all_novels,
                args=(self.update_progress_queue, self.on_update_complete)
            ).start()
            self.update_in_progress = True
            self.root.after(100, self.update_progress)
            return "全ての更新可能な小説の取得を開始します..."

        # 個別更新コマンド
        elif "--single" in command:
            parts = command.split("--")
            ncode = None

            # ncodeの取得
            for part in parts:
                if part.strip().startswith("n"):
                    ncode = part.strip()
                    break

            if not ncode:
                return "エラー: 小説コード(ncode)が指定されていません。"

            # 全エピソード再取得
            if "--re_all" in command:
                threading.Thread(
                    target=self.update_manager.refetch_all_episodes,
                    args=(ncode, self.update_progress_queue, self.on_update_complete)
                ).start()
                self.update_in_progress = True
                self.root.after(100, self.update_progress)
                return f"小説コード {ncode} の全エピソードの再取得を開始します..."

            # 欠落エピソード取得
            elif "--get_lost" in command:
                threading.Thread(
                    target=self.update_manager.fetch_missing_episodes,
                    args=(ncode, self.update_progress_queue, self.on_update_complete)
                ).start()
                self.update_in_progress = True
                self.root.after(100, self.update_progress)
                return f"小説コード {ncode} の欠落エピソードの取得を開始します..."

            # 通常の更新
            else:
                # 小説情報を取得
                novel = self.novel_manager.get_novel(ncode)
                if not novel:
                    return f"エラー: 小説コード {ncode} は見つかりませんでした。"

                threading.Thread(
                    target=self.update_manager.update_novel,
                    args=(novel, self.update_progress_queue, self.on_update_complete)
                ).start()
                self.update_in_progress = True
                self.root.after(100, self.update_progress)
                return f"小説 {novel[1]} の更新を開始します..."

        else:
            return "エラー: 無効なコマンド形式です。'help'コマンドでヘルプを表示します。"

    def update_novels(self, novels=None):
        """小説を更新する"""
        if self.update_in_progress:
            messagebox.showinfo("更新中", "既に更新処理が実行中です。完了までお待ちください。")
            return

        self.update_in_progress = True
        self.update_progress_queue.put("更新処理を開始しています...")
        self.root.after(100, self.update_progress)

        if novels:
            # 特定の小説を更新
            threading.Thread(
                target=self.update_manager.update_novels,
                args=(novels, self.update_progress_queue, self.on_update_complete)
            ).start()
        else:
            # 全ての新着小説を更新
            threading.Thread(
                target=self.update_manager.update_all_novels,
                args=(self.update_progress_queue, self.on_update_complete)
            ).start()

    def on_update_complete(self):
        """更新完了時の処理"""
        self.update_in_progress = False

        # 新着情報を再取得して表示を更新
        shinchaku_info = self.update_manager.check_shinchaku()
        shinchaku_ep, shinchaku_novels, shinchaku_count = shinchaku_info

        # ヘッダーラベルを更新
        self.header_label.config(text=f"新着情報\n新着{shinchaku_count}件,{shinchaku_ep}話")

        # 現在のビューを更新
        if self.current_view == "novel_list":
            self.show_novel_list()
        elif self.current_view == "updated_novels":
            self.show_updated_novels()
        elif self.current_view == "episode_list":
            # エピソードリストは更新しない
            pass
        elif self.current_view == "settings":
            # 設定画面は更新しない
            pass

    def on_settings_changed(self, font_name, font_size, bg_color):
        """設定変更時の処理"""
        self.font_name = font_name
        self.font_size = font_size
        self.bg_color = bg_color

        # 必要に応じて他のUIコンポーネントも更新
        ttk.Style().configure("TButton", font=(font_name, 10))
        self.header_label.config(font=(font_name, 12))

        logger.info(f"設定を更新しました: フォント={font_name}, サイズ={font_size}, 背景色={bg_color}")

    def run(self):
        """アプリケーションの実行"""
        self.initialize_ui()
        self.root.mainloop()

        # アプリケーション終了時の処理
        self.db_manager.close()
        logger.info("アプリケーションを終了しました")


def main():
    """アプリケーションのエントリーポイント"""
    app = NovelViewerApp()
    app.run()


if __name__ == "__main__":
    main()