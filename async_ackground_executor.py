import asyncio
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("background_tasks.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("background_executor")


class BackgroundExecutor:
    """
    バックグラウンドでの処理を管理するクラス。
    asyncio関数をTkinterアプリで実行するための橋渡しを行う。
    """

    def __init__(self, root):
        """
        初期化関数

        Args:
            root: Tkinterのrootウィンドウ
        """
        self.root = root
        self.tasks = {}  # タスクを追跡する辞書
        self.loop = None  # 非同期ループ
        self.thread = None  # バックグラウンドスレッド
        self.executor = ThreadPoolExecutor(max_workers=4)
        self._initialize_async_loop()

    def _initialize_async_loop(self):
        """新しい非同期ループを別スレッドで初期化"""

        def run_async_loop():
            """非同期ループを実行するスレッド"""
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()

        self.thread = threading.Thread(target=run_async_loop, daemon=True)
        self.thread.start()
        logger.info("Async loop initialized in background thread")

    def run_in_background(self, async_func, on_complete=None, on_error=None, show_progress=True):
        """
        非同期関数をバックグラウンドで実行

        Args:
            async_func: 実行する非同期関数
            on_complete: 完了時に呼び出すコールバック関数
            on_error: エラー時に呼び出すコールバック関数
            show_progress: 進捗ダイアログを表示するかどうか

        Returns:
            task_id: タスクを追跡するためのID
        """
        task_id = f"task_{id(async_func)}_{time.time()}"
        progress_dialog = None
        progress_var = tk.DoubleVar(value=0)
        status_var = tk.StringVar(value="処理を開始します...")

        # 進捗ダイアログを作成
        if show_progress:
            progress_dialog = self._create_progress_dialog(task_id, progress_var, status_var)

        # 進捗コールバック関数
        def progress_callback(progress, message):
            """進捗状況が更新されたときに呼び出される"""
            if progress_dialog and progress_dialog.winfo_exists():
                progress_var.set(progress)
                status_var.set(message)

        # 完了コールバック関数（修正）
        def task_done_callback(future):
            """タスクが完了したときに呼び出される"""
            try:
                # future.result()はCoroutine Futureではなく、
                # run_async_taskの戻り値（async_funcの実行結果を取得するための別のfuture）
                inner_future = future.result()
                if inner_future:
                    # 実際の結果を取得
                    try:
                        real_result = inner_future.result()
                        # デバッグログを追加
                        logger.info(f"Task {task_id} completed with result type: {type(real_result)}")

                        # GUIスレッドで完了時の処理を実行
                        self.root.after(0, lambda: self._handle_task_completion(
                            task_id, real_result, on_complete, progress_dialog
                        ))
                    except Exception as e:
                        logger.error(f"Error getting result from inner future: {e}")
                        # GUIスレッドでエラー処理を実行
                        self.root.after(0, lambda: self._handle_task_error(
                            task_id, e, on_error, progress_dialog
                        ))
                else:
                    logger.error(f"Inner future is None for task {task_id}")
                    # GUIスレッドでエラー処理を実行
                    self.root.after(0, lambda: self._handle_task_error(
                        task_id, Exception("Inner future is None"), on_error, progress_dialog
                    ))
            except Exception as e:
                logger.error(f"Error in background task {task_id}: {e}")

                # GUIスレッドでエラー処理を実行
                self.root.after(0, lambda: self._handle_task_error(
                    task_id, e, on_error, progress_dialog
                ))

        # バックグラウンドタスクを実行する関数（修正）
        def run_async_task():
            """非同期関数を実行し、結果を返す"""
            try:
                # 渡された非同期関数を実行して結果を返す
                logger.info(f"Starting async task {task_id}")
                future = asyncio.run_coroutine_threadsafe(
                    async_func(progress_callback), self.loop
                )
                return future  # asyncio.Futureを返す
            except Exception as e:
                logger.error(f"Failed to start background task: {e}")
                if progress_dialog and progress_dialog.winfo_exists():
                    progress_dialog.destroy()
                return None

        # ThreadPoolExecutorでタスクを実行
        future = self.executor.submit(run_async_task)
        future.add_done_callback(task_done_callback)

        # タスクを記録
        self.tasks[task_id] = {
            'future': future,
            'progress_dialog': progress_dialog,
            'start_time': time.time()
        }

        return task_id

    def _create_progress_dialog(self, task_id, progress_var, status_var):
        """
        進捗ダイアログを作成

        Args:
            task_id: タスクID
            progress_var: 進捗バーの値
            status_var: ステータスメッセージ

        Returns:
            progress_dialog: 進捗ダイアログウィンドウ
        """
        progress_dialog = tk.Toplevel(self.root)
        progress_dialog.title("処理中...")
        progress_dialog.geometry("400x150")
        progress_dialog.resizable(False, False)

        # モーダルダイアログとして設定
        progress_dialog.transient(self.root)
        progress_dialog.grab_set()

        # ウィンドウを中央に配置
        window_width = 400
        window_height = 150
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        position_top = int(screen_height / 2 - window_height / 2)
        position_right = int(screen_width / 2 - window_width / 2)
        progress_dialog.geometry(f"{window_width}x{window_height}+{position_right}+{position_top}")

        # レイアウト
        main_frame = ttk.Frame(progress_dialog, padding="20 20 20 20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ステータスラベル
        status_label = ttk.Label(main_frame, textvariable=status_var, wraplength=360)
        status_label.pack(fill=tk.X, pady=(0, 10))

        # 進捗バー
        progress_bar = ttk.Progressbar(
            main_frame,
            orient="horizontal",
            length=360,
            mode="determinate",
            variable=progress_var
        )
        progress_bar.pack(fill=tk.X, pady=(0, 10))

        # キャンセルボタン
        cancel_button = ttk.Button(
            main_frame,
            text="キャンセル",
            command=lambda: self.cancel_task(task_id)
        )
        cancel_button.pack()

        return progress_dialog

    def _handle_task_completion(self, task_id, result, on_complete, progress_dialog):
        """
        タスク完了時の処理を行う

        Args:
            task_id: タスクID
            result: 処理結果
            on_complete: 完了時コールバック
            progress_dialog: 進捗ダイアログ
        """
        if task_id in self.tasks:
            # 進捗ダイアログを閉じる
            if progress_dialog and progress_dialog.winfo_exists():
                progress_dialog.destroy()

            # 完了コールバックを呼び出す
            if on_complete:
                logger.info(f"Calling on_complete callback for task {task_id}")
                on_complete(result)

            # タスク情報を削除
            del self.tasks[task_id]

    def _handle_task_error(self, task_id, error, on_error, progress_dialog):
        """
        タスクエラー時の処理を行う

        Args:
            task_id: タスクID
            error: 発生したエラー
            on_error: エラー時コールバック
            progress_dialog: 進捗ダイアログ
        """
        if task_id in self.tasks:
            # 進捗ダイアログを閉じる
            if progress_dialog and progress_dialog.winfo_exists():
                progress_dialog.destroy()

            # エラーメッセージを表示
            error_msg = f"エラーが発生しました: {str(error)}"
            messagebox.showerror("エラー", error_msg)

            # エラーコールバックを呼び出す
            if on_error:
                on_error(error)

            # タスク情報を削除
            del self.tasks[task_id]

    def cancel_task(self, task_id):
        """
        実行中のタスクをキャンセル

        Args:
            task_id: キャンセルするタスクのID

        Returns:
            bool: キャンセルに成功したかどうか
        """
        if task_id not in self.tasks:
            return False

        task_info = self.tasks[task_id]
        future = task_info['future']

        if future and not future.done():
            # タスクをキャンセル
            success = future.cancel()

            if success:
                logger.info(f"Task {task_id} was cancelled")

                # 進捗ダイアログを閉じる
                progress_dialog = task_info.get('progress_dialog')
                if progress_dialog and progress_dialog.winfo_exists():
                    progress_dialog.destroy()

                # タスク情報を削除
                del self.tasks[task_id]

                # キャンセルメッセージを表示
                messagebox.showinfo("キャンセル", "処理をキャンセルしました。")

                return True

        return False

    def is_task_running(self, task_id):
        """
        タスクが実行中かどうかを確認

        Args:
            task_id: チェックするタスクのID

        Returns:
            bool: タスクが実行中かどうか
        """
        if task_id in self.tasks:
            task_info = self.tasks[task_id]
            future = task_info['future']
            return future and not future.done()
        return False

    def get_running_tasks(self):
        """
        実行中のタスク一覧を取得

        Returns:
            list: 実行中のタスクIDのリスト
        """
        return [task_id for task_id in self.tasks.keys() if self.is_task_running(task_id)]

    def shutdown(self):
        """バックグラウンド処理を終了"""
        if self.loop:
            # すべてのタスクをキャンセル
            for task_id in list(self.tasks.keys()):
                self.cancel_task(task_id)

            # ループを停止
            self.loop.call_soon_threadsafe(self.loop.stop)

            # エグゼキューターを終了
            self.executor.shutdown(wait=False)

            logger.info("Background executor shutdown")


# 使用例
if __name__ == "__main__":
    # サンプルの非同期関数（テスト用）
    async def sample_async_task(progress_callback):
        for i in range(100):
            await asyncio.sleep(0.1)  # シミュレーション
            progress_callback(i + 1, f"処理中... {i + 1}%")
        return "処理が完了しました"


    # GUIサンプル
    root = tk.Tk()
    root.title("バックグラウンド処理テスト")
    root.geometry("500x300")

    executor = BackgroundExecutor(root)


    def on_complete(result):
        messagebox.showinfo("完了", result)


    def start_task():
        executor.run_in_background(
            sample_async_task,
            on_complete=on_complete
        )


    start_button = ttk.Button(root, text="タスク開始", command=start_task)
    start_button.pack(pady=20)

    root.protocol("WM_DELETE_WINDOW", lambda: (executor.shutdown(), root.destroy()))
    root.mainloop()