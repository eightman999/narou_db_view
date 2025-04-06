import tkinter as tk
from tkinter import scrolledtext, ttk
import threading
import queue
import logging
import time
from datetime import datetime

# ロガーの設定
logger = logging.getLogger('CommandPrompt')


class CommandPrompt:
    def __init__(self, parent, command_callback, title="コマンドプロンプト"):
        """
        コマンドプロンプト風の入力画面を作成

        Args:
            parent: 親ウィジェット
            command_callback: コマンド実行時のコールバック関数
            title: ウィンドウタイトル
        """
        self.parent = parent
        self.command_callback = command_callback
        self.log_queue = queue.Queue()
        self.command_history = []
        self.history_position = 0

        # トップレベルウィンドウの作成
        self.window = tk.Toplevel(parent)
        self.window.title(title)
        self.window.geometry("800x500")
        self.window.configure(bg="#000000")

        # メインフレーム
        main_frame = tk.Frame(self.window, bg="#000000")
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # ログ表示エリア
        self.log_area = scrolledtext.ScrolledText(
            main_frame,
            wrap=tk.WORD,
            bg="#000000",
            fg="#00FF00",
            font=("Consolas", 10),
            insertbackground="#00FF00"  # カーソルの色
        )
        self.log_area.pack(fill="both", expand=True, pady=(0, 10))
        self.log_area.config(state=tk.DISABLED)  # 読み取り専用に設定

        # 入力エリアのフレーム
        input_frame = tk.Frame(main_frame, bg="#000000")
        input_frame.pack(fill="x")

        # プロンプト記号
        prompt_label = tk.Label(
            input_frame,
            text="> ",
            bg="#000000",
            fg="#00FF00",
            font=("Consolas", 10)
        )
        prompt_label.pack(side="left")

        # 入力フィールド
        self.input_field = tk.Entry(
            input_frame,
            bg="#000000",
            fg="#00FF00",
            insertbackground="#00FF00",  # カーソルの色
            font=("Consolas", 10),
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground="#333333",
            highlightcolor="#00FF00"
        )
        self.input_field.pack(side="left", fill="x", expand=True)
        self.input_field.bind("<Return>", self.execute_command)
        self.input_field.bind("<Up>", self.show_previous_command)
        self.input_field.bind("<Down>", self.show_next_command)
        self.input_field.focus_set()

        # ボタンフレーム
        button_frame = tk.Frame(main_frame, bg="#000000")
        button_frame.pack(fill="x", pady=(10, 0))

        # クリアボタン
        clear_button = ttk.Button(
            button_frame,
            text="クリア",
            command=self.clear_log
        )
        clear_button.pack(side="left", padx=5)

        # 閉じるボタン
        close_button = ttk.Button(
            button_frame,
            text="閉じる",
            command=self.window.destroy
        )
        close_button.pack(side="right", padx=5)

        # ログ更新スレッドを開始
        self.running = True
        self.update_thread = threading.Thread(target=self.update_log_area)
        self.update_thread.daemon = True
        self.update_thread.start()

        # 初期メッセージを表示
        self.add_log("小説管理システム コマンドプロンプト")
        self.add_log("コマンド一覧を表示するには 'help' と入力してください\n")

        # ウィンドウが閉じられたときのイベント処理
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        """ウィンドウを閉じる際の処理"""
        self.running = False
        self.window.destroy()

    def add_log(self, message, timestamp=True):
        """
        ログを追加する

        Args:
            message: 表示するメッセージ
            timestamp: タイムスタンプを追加するかどうか
        """
        if timestamp:
            timestamp_str = datetime.now().strftime("[%Y-%m-%d %H:%M:%S] ")
            log_message = f"{timestamp_str}{message}"
        else:
            log_message = message

        self.log_queue.put(log_message)
        logger.info(message)

    def update_log_area(self):
        """ログ表示エリアを更新するスレッド"""
        while self.running:
            try:
                # キューからメッセージを取得（タイムアウト付き）
                while not self.log_queue.empty():
                    message = self.log_queue.get(timeout=0.1)

                    # GUIの更新はメインスレッドで行う
                    if self.running:  # ウィンドウが閉じられていないか確認
                        self.window.after(0, self._update_log_text, message)

                    self.log_queue.task_done()

                # 短いスリープでCPU使用率を抑える
                time.sleep(0.1)

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"ログ更新エラー: {e}")
                continue

    def _update_log_text(self, message):
        """実際にログテキストを更新する（メインスレッドから呼ばれる）"""
        try:
            self.log_area.config(state=tk.NORMAL)
            self.log_area.insert(tk.END, message + "\n")
            self.log_area.see(tk.END)  # 最新のログが見えるようにスクロール
            self.log_area.config(state=tk.DISABLED)
        except Exception as e:
            logger.error(f"ログテキスト更新エラー: {e}")

    def execute_command(self, event=None):
        """コマンドを実行する"""
        command = self.input_field.get().strip()

        if not command:
            return

        # 入力をクリア
        self.input_field.delete(0, tk.END)

        # コマンド履歴に追加
        self.command_history.append(command)
        self.history_position = len(self.command_history)

        # コマンドをログに表示
        self.add_log(f"$ {command}", timestamp=False)

        # コマンドをコールバック関数で処理
        threading.Thread(target=self.process_command, args=(command,)).start()

    def process_command(self, command):
        """コマンドを処理する（別スレッドで実行）"""
        try:
            if command.lower() == "help":
                self.show_help()
            elif command.lower() == "clear":
                self.window.after(0, self.clear_log)
            elif command.lower() == "exit":
                self.window.after(0, self.window.destroy)
            else:
                # コマンドコールバックを呼び出す
                result = self.command_callback(command)
                if result:
                    self.add_log(result)
        except Exception as e:
            self.add_log(f"エラー: {str(e)}")

    def clear_log(self):
        """ログエリアをクリアする"""
        self.log_area.config(state=tk.NORMAL)
        self.log_area.delete(1.0, tk.END)
        self.log_area.config(state=tk.DISABLED)
        self.add_log("ログをクリアしました")

    def show_previous_command(self, event=None):
        """履歴から前のコマンドを表示"""
        if not self.command_history:
            return "break"

        if self.history_position > 0:
            self.history_position -= 1
            self.input_field.delete(0, tk.END)
            self.input_field.insert(0, self.command_history[self.history_position])

        return "break"  # イベントの伝播を停止

    def show_next_command(self, event=None):
        """履歴から次のコマンドを表示"""
        if not self.command_history:
            return "break"

        if self.history_position < len(self.command_history) - 1:
            self.history_position += 1
            self.input_field.delete(0, tk.END)
            self.input_field.insert(0, self.command_history[self.history_position])
        else:
            # 履歴の最後に達したら入力フィールドをクリア
            self.history_position = len(self.command_history)
            self.input_field.delete(0, tk.END)

        return "break"  # イベントの伝播を停止

    def show_help(self):
        """ヘルプを表示"""
        help_text = """
        利用可能なコマンド:
        
        ■ 小説更新コマンド
        update --all                  すべての新着小説を更新
        update --single --n [ncode]   指定されたncodeの小説を更新
        update --single --re_all --n [ncode]   指定されたncodeの小説の全エピソードを再取得
        update --single --get_lost --n [ncode] 指定されたncodeの小説の欠落エピソードを取得

        ■ システムコマンド
        help                      このヘルプを表示
        clear                     ログをクリア
        exit                      コマンドプロンプトを閉じる
        """
        self.add_log(help_text, timestamp=False)