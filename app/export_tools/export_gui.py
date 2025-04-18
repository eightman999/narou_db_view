#!/usr/bin/env python3
"""
小説データをHTML形式にエクスポートするGUIアプリケーション
"""
import os
import sys
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import time

# ルートディレクトリをパスに追加
current_dir = Path(__file__).parent
root_dir = current_dir.parent
sys.path.insert(0, str(root_dir))

from app.utils.exporters.html_exporter import HTMLExporter
from app.utils.logger_manager import get_logger
from app.database.db_handler import DatabaseHandler

# ロガーの設定
logger = get_logger('ExportGUI')


class ExportProgressDialog(tk.Toplevel):
    """エクスポート進捗表示ダイアログ"""

    def __init__(self, parent, title="エクスポート進捗"):
        """
        初期化

        Args:
            parent: 親ウィンドウ
            title: ダイアログタイトル
        """
        super().__init__(parent)
        self.title(title)
        self.geometry("500x300")
        self.resizable(False, False)
        self.transient(parent)  # 親ウィンドウの上に表示
        self.grab_set()  # モーダルダイアログにする

        # ウィンドウの中央配置
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"+{x}+{y}")

        # メッセージラベル
        self.message_label = tk.Label(
            self,
            text="エクスポート処理中...",
            font=("", 12)
        )
        self.message_label.pack(pady=20)

        # 現在処理中の小説
        self.novel_label = tk.Label(
            self,
            text="",
            font=("", 10)
        )
        self.novel_label.pack(pady=10)

        # 進捗バー
        self.progress_bar = ttk.Progressbar(
            self,
            orient="horizontal",
            length=400,
            mode="determinate"
        )
        self.progress_bar.pack(pady=20)

        # 進捗テキスト
        self.progress_text = tk.Label(
            self,
            text="0%",
            font=("", 10)
        )
        self.progress_text.pack(pady=5)

        # キャンセルボタン
        self.cancel_button = ttk.Button(
            self,
            text="キャンセル",
            command=self.on_cancel
        )
        self.cancel_button.pack(pady=20)

        # キャンセルフラグ
        self.cancelled = False

        # 閉じるボタンを無効化
        self.protocol("WM_DELETE_WINDOW", lambda: None)

    def update_progress(self, percentage, message="", novel=""):
        """
        進捗を更新

        Args:
            percentage (int): 進捗率（0-100）
            message (str): 表示メッセージ
            novel (str): 処理中の小説
        """
        if message:
            self.message_label.config(text=message)

        if novel:
            self.novel_label.config(text=f"処理中: {novel}")

        self.progress_bar["value"] = percentage
        self.progress_text.config(text=f"{percentage}%")
        self.update()

    def on_cancel(self):
        """キャンセルボタンクリック時の処理"""
        if messagebox.askyesno("確認", "エクスポートをキャンセルしますか？"):
            self.cancelled = True
            self.message_label.config(text="キャンセル中...")
            self.cancel_button.config(state="disabled")

    def finished(self, success=True, message=""):
        """
        処理完了時の表示

        Args:
            success (bool): 成功したかどうか
            message (str): 完了メッセージ
        """
        if success:
            self.message_label.config(text=message if message else "エクスポートが完了しました")
            self.progress_bar["value"] = 100
            self.progress_text.config(text="100%")
        else:
            self.message_label.config(text=message if message else "エクスポートに失敗しました")

        # キャンセルボタンを閉じるボタンに変更
        self.cancel_button.config(text="閉じる", command=self.destroy)

        # 閉じるボタンを有効化
        self.protocol("WM_DELETE_WINDOW", self.destroy)


class ExportApp(tk.Tk):
    """エクスポートアプリケーションメインウィンドウ"""

    def __init__(self):
        """初期化"""
        super().__init__()
        self.title("小説HTML書き出しツール")
        self.geometry("600x500")
        self.resizable(True, True)

        # データベースハンドラ
        self.db_handler = DatabaseHandler()

        # 小説リスト
        self.novels = []

        # UIの初期化
        self.init_ui()

        # 小説データの読み込み
        self.load_novels()

    def init_ui(self):
        """UIの初期化"""
        # メインフレーム
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill="both", expand=True)

        # タイトル
        title_label = ttk.Label(
            main_frame,
            text="小説HTML書き出しツール",
            font=("", 14, "bold")
        )
        title_label.pack(pady=10)

        # 説明
        desc_label = ttk.Label(
            main_frame,
            text="データベースの小説をHTML形式でエクスポートします。\nAndroid端末にコピーして読むことができます。",
            justify="center"
        )
        desc_label.pack(pady=5)

        # エクスポート先フレーム
        export_frame = ttk.LabelFrame(main_frame, text="エクスポート設定", padding=10)
        export_frame.pack(fill="x", pady=10)

        # エクスポート先パス
        path_frame = ttk.Frame(export_frame)
        path_frame.pack(fill="x", pady=5)

        ttk.Label(path_frame, text="エクスポート先:").pack(side="left")

        self.export_path_var = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "html_export"))
        export_path_entry = ttk.Entry(path_frame, textvariable=self.export_path_var, width=40)
        export_path_entry.pack(side="left", fill="x", expand=True, padx=5)

        browse_button = ttk.Button(path_frame, text="参照...", command=self.browse_export_path)
        browse_button.pack(side="left")

        # オプションフレーム
        options_frame = ttk.Frame(export_frame)
        options_frame.pack(fill="x", pady=5)

        self.create_zip_var = tk.BooleanVar(value=True)
        zip_check = ttk.Checkbutton(
            options_frame,
            text="ZIPファイルにまとめる",
            variable=self.create_zip_var
        )
        zip_check.pack(side="left", padx=5)

        # 小説選択フレーム
        novels_frame = ttk.LabelFrame(main_frame, text="小説選択", padding=10)
        novels_frame.pack(fill="both", expand=True, pady=10)

        # 選択モードラジオボタン
        selection_frame = ttk.Frame(novels_frame)
        selection_frame.pack(fill="x", pady=5)

        self.selection_mode = tk.StringVar(value="all")

        all_radio = ttk.Radiobutton(
            selection_frame,
            text="すべての小説",
            variable=self.selection_mode,
            value="all",
            command=self.toggle_selection_mode
        )
        all_radio.pack(side="left", padx=5)

        selected_radio = ttk.Radiobutton(
            selection_frame,
            text="選択した小説のみ",
            variable=self.selection_mode,
            value="selected",
            command=self.toggle_selection_mode
        )
        selected_radio.pack(side="left", padx=5)

        # 全選択ボタン
        select_all_button = ttk.Button(
            selection_frame,
            text="全選択",
            command=self.select_all_novels
        )
        select_all_button.pack(side="right", padx=5)

        # 選択解除ボタン
        clear_selection_button = ttk.Button(
            selection_frame,
            text="選択解除",
            command=self.clear_all_selection
        )
        clear_selection_button.pack(side="right", padx=5)

        # 検索ボックス
        search_frame = ttk.Frame(novels_frame)
        search_frame.pack(fill="x", pady=5)

        ttk.Label(search_frame, text="検索:").pack(side="left")

        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side="left", fill="x", expand=True, padx=5)
        search_entry.bind("<Return>", self.search_novels)

        search_button = ttk.Button(search_frame, text="検索", command=self.search_novels)
        search_button.pack(side="left")

        clear_button = ttk.Button(search_frame, text="クリア", command=self.clear_search)
        clear_button.pack(side="left", padx=5)

        # 小説リストボックス
        list_frame = ttk.Frame(novels_frame)
        list_frame.pack(fill="both", expand=True, pady=5)

        self.novels_listbox = tk.Listbox(
            list_frame,
            selectmode="multiple",
            exportselection=0,
            font=("", 10)
        )
        self.novels_listbox.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.novels_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.novels_listbox.config(yscrollcommand=scrollbar.set)

        # ボタンフレーム
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=10)

        # 情報ラベル
        self.info_label = ttk.Label(button_frame, text="")
        self.info_label.pack(side="left", padx=5)

        # エクスポートボタン
        export_button = ttk.Button(button_frame, text="エクスポート開始", command=self.start_export)
        export_button.pack(side="right", padx=5)

    def browse_export_path(self):
        """エクスポート先パスの選択ダイアログを表示"""
        current_path = self.export_path_var.get()
        directory = filedialog.askdirectory(
            initialdir=current_path if os.path.exists(current_path) else os.path.expanduser("~"),
            title="エクスポート先フォルダを選択"
        )

        if directory:  # ユーザーがキャンセルしなかった場合
            self.export_path_var.set(directory)

    def toggle_selection_mode(self):
        """選択モードの切り替え"""
        mode = self.selection_mode.get()
        if mode == "all":
            # すべての小説を選択
            self.novels_listbox.config(selectmode="browse")
            self.novels_listbox.selection_clear(0, tk.END)
        else:
            # 個別選択モード
            self.novels_listbox.config(selectmode="multiple")

    def load_novels(self):
        """小説データの読み込み"""
        try:
            # すべての小説を取得
            self.novels = self.db_handler.get_all_novels()

            # リストボックスに表示
            self.novels_listbox.delete(0, tk.END)

            for novel in self.novels:
                ncode = novel[0]
                title = novel[1] if novel[1] else "無題の小説"
                author = novel[2] if novel[2] else "著者不明"
                episodes = novel[5] if len(novel) > 5 and novel[5] is not None else 0

                self.novels_listbox.insert(tk.END, f"{title} - {author} ({episodes}話)")

            # 情報ラベルを更新
            self.info_label.config(text=f"合計: {len(self.novels)}作品")

        except Exception as e:
            logger.error(f"小説データの読み込みエラー: {e}")
            messagebox.showerror("エラー", f"小説データの読み込みに失敗しました: {e}")

    def search_novels(self, event=None):
        """検索キーワードに一致する小説を表示"""
        search_term = self.search_var.get().lower()

        if not search_term:
            # 検索条件なしならすべて表示
            self.load_novels()
            return

        # リストボックスをクリア
        self.novels_listbox.delete(0, tk.END)

        # 検索条件に一致する小説を表示
        matched_count = 0
        for novel in self.novels:
            ncode = novel[0]
            title = novel[1] if novel[1] else "無題の小説"
            author = novel[2] if novel[2] else "著者不明"
            episodes = novel[5] if len(novel) > 5 and novel[5] is not None else 0
            synopsis = novel[7] if len(novel) > 7 and novel[7] else ""

            # タイトル、作者、あらすじのいずれかに検索語が含まれるかチェック
            if (search_term in title.lower() or
                    search_term in author.lower() or
                    search_term in synopsis.lower() or
                    search_term in ncode.lower()):
                self.novels_listbox.insert(tk.END, f"{title} - {author} ({episodes}話)")
                matched_count += 1

        # 情報ラベルを更新
        self.info_label.config(text=f"検索結果: {matched_count}作品")

    def clear_search(self):
        """検索をクリア"""
        self.search_var.set("")
        self.load_novels()

    def get_selected_novels(self):
        """選択された小説のリストを取得"""
        selected_indices = self.novels_listbox.curselection()

        if not selected_indices:
            if self.selection_mode.get() == "all":
                # すべての小説モードの場合は全小説を返す
                return self.novels
            else:
                # 選択モードで何も選択されていない場合は空リストを返す
                return []

        # 選択された小説のみ返す
        selected_novels = []
        for i in selected_indices:
            if i < len(self.novels):
                selected_novels.append(self.novels[i])

        return selected_novels

    def select_all_novels(self):
        """すべての小説を選択する"""
        # 選択モードに変更
        self.selection_mode.set("selected")
        self.toggle_selection_mode()

        # すべてのアイテムを選択
        self.novels_listbox.selection_set(0, tk.END)

    def clear_all_selection(self):
        """すべての選択を解除する"""
        self.novels_listbox.selection_clear(0, tk.END)

    def start_export(self):
        """エクスポート処理を開始"""
        # エクスポート先パスの取得と検証
        export_path = self.export_path_var.get()
        if not export_path:
            messagebox.showerror("エラー", "エクスポート先パスを指定してください")
            return

        # ディレクトリが存在しなければ作成するか確認
        if not os.path.exists(export_path):
            if messagebox.askyesno("確認", f"ディレクトリ '{export_path}' が存在しません。作成しますか？"):
                try:
                    os.makedirs(export_path)
                except Exception as e:
                    messagebox.showerror("エラー", f"ディレクトリの作成に失敗しました: {e}")
                    return
            else:
                return

        # 選択された小説を取得
        selected_novels = self.get_selected_novels()
        if not selected_novels:
            # 全小説モードであればすべての小説を使用
            if self.selection_mode.get() == "all":
                selected_novels = self.novels
            else:
                messagebox.showerror("エラー", "エクスポートする小説が選択されていません")
                return

        # ZIPオプションの取得
        create_zip = self.create_zip_var.get()

        # プログレスダイアログを表示
        progress_dialog = ExportProgressDialog(self)

        # エクスポート処理を別スレッドで実行
        export_thread = threading.Thread(
            target=self.run_export,
            args=(export_path, selected_novels, create_zip, progress_dialog)
        )
        export_thread.daemon = True
        export_thread.start()

    def run_export(self, export_path, novels, create_zip, progress_dialog):
        """
        エクスポート処理を実行（バックグラウンドスレッド）

        Args:
            export_path (str): エクスポート先パス
            novels (list): エクスポートする小説のリスト
            create_zip (bool): ZIPファイルを作成するかどうか
            progress_dialog: 進捗ダイアログ
        """
        try:
            # エクスポーターの初期化
            exporter = HTMLExporter(export_path)

            # 小説の総数
            total_novels = len(novels)

            # 選択したモード
            all_novels = self.selection_mode.get() == "all"

            # 全小説モードかどうかによって処理を分ける
            if all_novels:
                # すべての小説をエクスポート
                progress_dialog.update_progress(0, "すべての小説をエクスポートしています...")
                result = exporter.export_all_novels()

                if progress_dialog.cancelled:
                    progress_dialog.finished(False, "エクスポートがキャンセルされました")
                    return

                if not result:
                    progress_dialog.finished(False, "エクスポートに失敗しました")
                    return
            else:
                # 選択された小説のみエクスポート
                for i, novel in enumerate(novels):
                    if progress_dialog.cancelled:
                        progress_dialog.finished(False, "エクスポートがキャンセルされました")
                        return

                    ncode = novel[0]
                    title = novel[1] if novel[1] else "無題の小説"

                    # 進捗更新
                    progress = int((i / total_novels) * 100)
                    progress_dialog.update_progress(
                        progress,
                        f"小説をエクスポート中... ({i + 1}/{total_novels})",
                        title
                    )

                    # 小説をエクスポート
                    exporter.export_novel(ncode)

                    # 少し待機（UI更新のため）
                    time.sleep(0.1)

            # ZIPファイルの作成
            if create_zip and not progress_dialog.cancelled:
                progress_dialog.update_progress(95, "ZIPファイルを作成しています...")
                zip_path = exporter.export_as_zip()

                if progress_dialog.cancelled:
                    progress_dialog.finished(False, "エクスポートがキャンセルされました")
                    return

                # 成功メッセージ
                if os.path.exists(zip_path):
                    message = f"エクスポートが完了しました\nZIPファイル: {zip_path}"
                else:
                    message = f"エクスポートは完了しましたが、ZIPファイルの作成に失敗しました"

                progress_dialog.finished(True, message)
            else:
                # ZIP無しで完了
                message = f"エクスポートが完了しました\nフォルダ: {export_path}"
                progress_dialog.finished(True, message)

        except Exception as e:
            logger.error(f"エクスポート処理中にエラーが発生しました: {e}")
            import traceback
            logger.error(traceback.format_exc())
            progress_dialog.finished(False, f"エラー: {e}")


if __name__ == "__main__":
    app = ExportApp()
    app.mainloop()