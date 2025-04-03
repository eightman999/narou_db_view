import asyncio
import configparser
import threading
import tkinter as tk
import sqlite3  # 修正: dbm import sqlite3 からこの行に変更
from tkinter import ttk, scrolledtext, messagebox  # messagebox を追加
from bs4 import BeautifulSoup
from PIL import ImageFont, Image, ImageDraw, ImageTk
import tkinter.font as tkFont
import logging
import sys

# 自作モジュールのインポート（非同期版に置き換える）
from async_bookshelf import shelf_maker, get_last_read, episode_getter, input_last_read
from async_checker import NovelUpdater
from async_episode_count import update_total_episodes_single, update_total_episodes
from async_ackground_executor import BackgroundExecutor
from checker import load_conf, dell_dl, del_yml, USER_AGENTS

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

# グローバル変数
global scrollable_frame, scroll_canvas
main_shelf = []
last_read_novel = []
episodes = []
last_read_epno = 0
novel_fontsize = 14
set_font = "YuKyokasho Yoko"
bg_color = "#FFFFFF"
shinchaku_ep = 0
shinchaku_novel = 0
main_shinchaku = []


# メインクラス
class AsyncApp:
    def __init__(self, root):
        self.root = root
        self.running = True
        self.loop = asyncio.get_event_loop()

        # BackgroundExecutorを初期化
        self.executor = BackgroundExecutor(root)

        # NovelUpdaterの初期化（後で非同期で行う）
        self.novel_updater = None

    async def initialize(self):
        """アプリケーションの初期化を非同期で行う"""
        global main_shelf, last_read_novel, last_read_epno, set_font, novel_fontsize, bg_color, shinchaku_ep, main_shinchaku, shinchaku_novel

        # 初期化処理
        dell_dl()
        del_yml()

        # 小説データの読み込み
        main_shelf = await shelf_maker()
        last_read_novel, last_read_epno = await get_last_read(main_shelf)
        set_font, novel_fontsize, bg_color = load_conf()

        # NovelUpdaterの初期化
        try:
            self.novel_updater = await NovelUpdater().initialize()
            logger.info("小説更新機能の初期化に成功しました")
        except Exception as e:
            logger.error(f"Failed to initialize novel updater: {e}")
            tk.messagebox.showerror("初期化エラー",
                                    f"小説更新機能の初期化に失敗しました：{e}\n\nアプリを再起動してください。")
            self.novel_updater = None

        # 新着情報の取得
        if self.novel_updater:
            try:
                shinchaku_ep, main_shinchaku, shinchaku_novel = await self.novel_updater.shinchaku_checker()
            except Exception as e:
                logger.error(f"新着チェック中にエラー: {e}")

        return self

    def run_async(self, coro):
        """非同期コルーチンをGUIスレッドから実行する"""
        if asyncio.iscoroutine(coro):
            return asyncio.run_coroutine_threadsafe(coro, self.loop)
        else:
            return coro


# メインウィンドウのセットアップ
async def main():
    # メインウィンドウの設定
    root = tk.Tk()
    root.title("小説アプリ")
    root.attributes("-fullscreen", True)  # フルスクリーンモード
    root.configure(bg="#0080A0")  # 背景色を変更

    # アプリケーションの初期化
    app = AsyncApp(root)
    await app.initialize()

    # ボタンの幅と高さ
    BUTTON_WIDTH = 25
    BUTTON_FONT = ("Helvetica", 18)

    # ヘッダー部分
    header_frame = tk.Frame(root, bg="#0080A0")
    header_frame.grid(row=0, column=0, columnspan=2, sticky="ew")  # ヘッダーを上部に配置

    header_label = tk.Label(
        header_frame,
        text=f"新着情報\n新着{shinchaku_novel}件,{shinchaku_ep}話",
        bg="#0080A0",
        fg="white",
        font=("Helvetica", 24),
        anchor="w",
        justify="left",
    )
    header_label.pack(side="left", padx=30, pady=10)  # 左端から十分な余白

    last_read_title = f"{last_read_novel[1]} {last_read_epno}話" if last_read_novel else "なし"
    last_read_label = tk.Label(
        header_frame,
        text=f"最後に開いていた小説\n{last_read_title}",
        bg="#0080A0",
        fg="white",
        font=("Helvetica", 24),
        anchor="e",
        justify="right",
    )
    last_read_label.pack(side="right", padx=30, pady=10)  # 右端から十分な余白

    # セクションタイトルを作成する関数
    def create_section_title(parent, text, row):
        title = tk.Label(parent, text=text, font=BUTTON_FONT, bg="#0080A0", fg="white", anchor="w")
        title.grid(row=row, column=0, sticky="w", pady=(10, 0), padx=20)

    # ボタンを作成する関数
    def create_button(parent, text, row, command=None):
        if isinstance(text, tuple):
            text, command = text
        btn = ttk.Button(parent, text=text, width=BUTTON_WIDTH, command=command)
        btn.grid(row=row, column=0, padx=20, pady=5, sticky="w")

    # コンテンツ部分
    content_frame = tk.Frame(root, bg="#F0F0F0")
    content_frame.grid(row=1, column=0, sticky="nsew")

    # 小説一覧の表示部分
    list_frame = tk.Frame(root, bg="#F0F0F0")
    list_frame.grid(row=1, column=1, sticky="nsew")

    scroll_canvas = tk.Canvas(list_frame, bg="#F0F0F0")
    scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=scroll_canvas.yview)
    scrollable_frame = ttk.Frame(scroll_canvas)

    scrollable_frame.bind(
        "<Configure>",
        lambda e: scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))
    )

    scroll_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    scroll_canvas.configure(yscrollcommand=scrollbar.set)

    scroll_canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # グリッドの行列調整
    root.grid_rowconfigure(1, weight=1)
    root.grid_columnconfigure(0, weight=1)
    root.grid_columnconfigure(1, weight=2)  # 小説一覧部分を広くする

    # 小説リストを表示する関数
    async def show_novel_list():
        global scrollable_frame, scroll_canvas

        # Clear the existing widgets in the list_frame
        for widget in list_frame.winfo_children():
            widget.destroy()

        # Initialize the canvas and scrollable frame
        scroll_canvas = tk.Canvas(list_frame, bg="#F0F0F0")
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=scroll_canvas.yview)
        scrollable_frame = ttk.Frame(scroll_canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))
        )

        scroll_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        scroll_canvas.configure(yscrollcommand=scrollbar.set)

        scroll_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Prepare the data structure
        buttons_data = [
            {"title": f"読む", "text": f"{row[1]} - 作者: {row[2]}", "n_code": row[0]}
            for row in main_shelf
        ]

        # Draw all buttons
        for data in buttons_data:
            frame = tk.Frame(scrollable_frame, bg="#F0F0F0")
            frame.pack(fill="x", pady=2)

            # Title label
            title_label = tk.Label(frame, text=data["text"], bg="#F0F0F0", anchor="w")
            title_label.pack(side="left", padx=5, fill="x", expand=True)

            # Bind click event to the label
            title_label.bind("<Button-1>", lambda e, n_code=data["n_code"]: on_title_click(e, n_code))

    # タイトルクリック時の処理 - 非同期化のために関数を定義
    def on_title_click(event, n_code):
        # 非同期関数をバックグラウンドで実行
        app.executor.run_in_background(
            lambda progress_callback: handle_title_click(n_code, progress_callback),
            on_complete=lambda result: show_episode_list(result, n_code)
        )

    # タイトルクリックの非同期処理
    async def handle_title_click(n_code, progress_callback):
        progress_callback(0, f"エピソード情報を取得中...")
        episodes = await episode_getter(n_code)
        progress_callback(100, "完了")
        return episodes

    # エピソード一覧を表示
    def show_episode_list(episodes_data, ncode):
        global scrollable_frame, scroll_canvas, episodes

        # エピソードをグローバル変数に格納
        episodes = episodes_data

        # Sort the episodes by episode_no (episode[0])
        scroll_canvas.yview_moveto(0)
        episodes.sort(key=lambda episode: int(episode[0]))

        # Clear the existing widgets in the scrollable_frame
        for widget in scrollable_frame.winfo_children():
            widget.destroy()

        # Create frames and labels to display the episodes
        for episode in episodes:
            frame = tk.Frame(scrollable_frame, bg="#F0F0F0")
            frame.pack(fill="x", pady=2)

            # Episode label
            episode_label = tk.Label(frame, text=f"Episode {episode[0]}: {episode[1]}", bg="#F0F0F0", anchor="w")
            episode_label.pack(side="left", padx=5, fill="x", expand=True)

            # Bind click event to the label
            episode_label.bind("<Button-1>", lambda e, ep=episode: on_episode_click(e, ep, ncode))

        # Create a scrollbar for the episode list
        scrollbar = ttk.Scrollbar(scrollable_frame, orient="vertical", command=scroll_canvas.yview)
        scrollbar.pack(side="right", fill="y")

        # Configure the scrollbar
        scroll_canvas.config(yscrollcommand=scrollbar.set)

    # エピソードクリック時の処理
    def on_episode_click(event, episode, n_code):
        # 非同期で最後に読んだ小説を記録
        asyncio.run_coroutine_threadsafe(input_last_read(n_code, episode[0]), app.loop)

        def show_episode(episode):
            # Clear the existing content
            scrolled_text.config(state=tk.NORMAL)
            scrolled_text.delete(1.0, tk.END)

            # Parse the HTML content
            soup = BeautifulSoup(episode[2], "html.parser")

            # Remove empty paragraphs
            for p in soup.find_all('p'):
                if not p.get_text(strip=True) and not p.attrs:
                    p.decompose()

            # Extract the cleaned text content
            text_content = soup.get_text()

            # Insert the text content into the scrolled text widget
            scrolled_text.insert(tk.END, text_content)
            scrolled_text.config(state=tk.DISABLED, bg=bg_color)

        def next_episode(event):
            nonlocal episode
            current_index = episodes.index(episode)
            if current_index < len(episodes) - 1:
                episode = episodes[current_index + 1]
                show_episode(episode)
                # 非同期で最後に読んだ小説を記録
                asyncio.run_coroutine_threadsafe(input_last_read(n_code, episode[0]), app.loop)
            episode_window.title(f"Episode {episode[0]}: {episode[1]}")

        def previous_episode(event):
            nonlocal episode
            current_index = episodes.index(episode)
            if current_index > 0:
                episode = episodes[current_index - 1]
                show_episode(episode)
                # 非同期で最後に読んだ小説を記録
                asyncio.run_coroutine_threadsafe(input_last_read(n_code, episode[0]), app.loop)
            episode_window.title(f"Episode {episode[0]}: {episode[1]}")

        # Create a new window to display the episode content
        episode_window = tk.Toplevel()
        episode_window.title(f"Episode {episode[0]}: {episode[1]}")
        episode_window.geometry("800x600")

        # Create a scrolled text widget to display the episode content
        scrolled_text = scrolledtext.ScrolledText(episode_window, wrap=tk.WORD, font=(set_font, novel_fontsize))
        scrolled_text.pack(fill=tk.BOTH, expand=True)

        # Show the initial episode content
        show_episode(episode)

        # Bind the left and right arrow keys to navigate episodes
        episode_window.bind("<Right>", next_episode)
        episode_window.bind("<Left>", previous_episode)

    # 設定画面を表示
    def show_settings():
        # Clear the existing widgets in the list_frame except scroll_canvas
        for widget in list_frame.winfo_children():
            if widget != scroll_canvas:
                widget.destroy()

        # Create a frame for settings
        setting_frame = tk.Frame(list_frame, bg="#F0F0F0")
        setting_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Font selection
        font_label = tk.Label(setting_frame, text="フォント:", bg="#F0F0F0", anchor="w")
        font_label.grid(row=0, column=0, sticky="w", pady=5)
        font_var = tk.StringVar(value=set_font)
        font_dropdown = ttk.Combobox(setting_frame, textvariable=font_var, values=tkFont.families())
        font_dropdown.grid(row=0, column=1, sticky="ew", pady=5)

        # Font size
        size_label = tk.Label(setting_frame, text="文字サイズ:", bg="#F0F0F0", anchor="w")
        size_label.grid(row=1, column=0, sticky="w", pady=5)
        size_var = tk.IntVar(value=novel_fontsize)
        size_entry = tk.Entry(setting_frame, textvariable=size_var)
        size_entry.grid(row=1, column=1, sticky="ew", pady=5)

        # Background color
        bg_label = tk.Label(setting_frame, text="バックグラウンド色 (RGB):", bg="#F0F0F0", anchor="w")
        bg_label.grid(row=2, column=0, sticky="w", pady=5)
        bg_var = tk.StringVar(value=bg_color)
        bg_entry = tk.Entry(setting_frame, textvariable=bg_var)
        bg_entry.grid(row=2, column=1, sticky="ew", pady=5)

        # Apply button
        def apply_settings():
            global novel_fontsize, set_font, bg_color
            novel_fontsize = size_var.get()
            set_font = font_var.get()
            bg_color = bg_var.get()

            # Create a ConfigParser object
            config = configparser.ConfigParser()

            # Add settings to the config object
            config['Settings'] = {
                'Font': font_var.get(),
                'FontSize': novel_fontsize,
                'BackgroundColor': bg_var.get()
            }

            # Write the settings to a config file
            with open('settings.ini', 'w') as configfile:
                config.write(configfile)

            tk.messagebox.showinfo("設定", "設定が保存されました")

        apply_button = ttk.Button(setting_frame, text="適用", command=apply_settings)
        apply_button.grid(row=3, column=0, columnspan=2, pady=10)

    # 入力画面を表示
    def show_input_screen():
        input_window = tk.Toplevel()
        input_window.title("入力画面")
        input_window.geometry("500x300")

        input_label = tk.Label(input_window, text="")
        input_label.pack(pady=10)

        input_text = tk.Text(input_window, height=10, width=50)
        input_text.pack(pady=5)

        def send_input(event=None):
            user_input = input_text.get("1.0", tk.END).strip()
            print(f"User input: {user_input}")

            if user_input == "exit":
                root.quit()
            elif "update" in user_input:
                user_input = user_input.split("update")
                if "--all" in user_input[1]:
                    # 非同期で更新処理を実行
                    messagebox.showinfo("機能未実装", "一括更新機能はまだ実装されていません")
                    # app.executor.run_in_background(
                    #    lambda progress_callback: update_all_novels_async(main_shinchaku, progress_callback),
                    #    on_complete=on_update_complete
                    # )
                elif "--single" in user_input[1]:
                    user_input = user_input[1].split("--single")
                    if "--re_all" in user_input[1]:
                        if "--n" in user_input[1]:
                            ncode = user_input[1].split("--")[1].strip()
                            # 非同期で再取得処理を実行
                            # ここで参照エラーが発生するため、簡易的なメッセージだけ表示する
                            messagebox.showinfo("機能未実装", f"再取得機能はまだ実装されていません: {ncode}")
                            # app.executor.run_in_background(
                            #    lambda progress_callback: re_fetch_all_episodes_async(ncode, progress_callback),
                            #    on_complete=on_update_complete
                            # )
                        else:
                            print("Please provide an ncode to update.")
                            input_label.config(text="ncodeを指定してください")
                    elif "--get_lost" in user_input[1]:
                        if "--n" in user_input[1]:
                            ncode = user_input[1].split("--")[1].strip()
                            # 非同期で欠落エピソード取得処理を実行
                            # 未実装関数の対応
                            messagebox.showinfo("機能未実装", f"欠落エピソード取得機能はまだ実装されていません: {ncode}")
                            # app.executor.run_in_background(
                            #    lambda progress_callback: get_missing_episodes_async(ncode, progress_callback),
                            #    on_complete=on_update_complete
                            # )
                        else:
                            print("Please provide an ncode to update.")
                            input_label.config(text="ncodeを指定してください")
                    else:
                        print("Invalid command.")
                        input_label.config(text="コマンドが無効です")
                else:
                    print("Invalid command.")
                    input_label.config(text="コマンドが無効です")
            elif "n" in user_input:
                ncode = user_input
                try:
                    novel_index = int(ncode)
                    if 0 <= novel_index < len(main_shelf):
                        input_label.config(
                            text="ncode:" + main_shelf[novel_index][0] + "title:" + main_shelf[novel_index][1])
                    else:
                        input_label.config(text="無効なインデックスです")
                except ValueError:
                    input_label.config(text=f"User input: {user_input}")
            else:
                input_label.config(text=f"User input: {user_input}")

            input_text.delete("1.0", tk.END)

        def exit_input():
            input_window.destroy()

        exit_button = tk.Button(input_window, text="終了", command=exit_input)
        exit_button.pack(pady=10)
        input_text.bind("<Return>", send_input)

    # 更新された小説の一覧を表示
    async def show_updated_novels():
        global scrollable_frame, scroll_canvas

        # Clear the existing widgets in the list_frame
        for widget in list_frame.winfo_children():
            widget.destroy()

        # Create a canvas and a scrollbar
        scroll_canvas = tk.Canvas(list_frame, bg="#F0F0F0")
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=scroll_canvas.yview)
        scrollable_frame = ttk.Frame(scroll_canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))
        )

        buttons_data = [
            {"title": f"更新", "text": f"{row[1]}", "n_code": row[0], "ep_no": row[2], "gen_all_no": row[3],
             "rating": row[4]}
            for row in main_shinchaku
        ]

        scroll_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        scroll_canvas.configure(yscrollcommand=scrollbar.set)

        scroll_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Add the "一括更新" button at the top
        update_all_button = ttk.Button(
            scrollable_frame,
            text="一括更新",
            command=lambda: messagebox.showinfo("機能未実装", "一括更新機能はまだ実装されていません")
            # command=lambda: app.executor.run_in_background(
            #    lambda progress_callback: update_all_novels_async(main_shinchaku, progress_callback),
            #    on_complete=on_update_complete
            # )
        )
        update_all_button.pack(fill="x", pady=2)

        # Display each updated novel's title
        for data in buttons_data:
            frame = tk.Frame(scrollable_frame, bg="#F0F0F0")
            frame.pack(fill="x", pady=2)

            # Title label
            title_label = tk.Label(frame, text=data["text"], bg="#F0F0F0", anchor="w")
            title_label.pack(side="left", padx=5, fill="x", expand=True)

            # Bind click event to the label
            title_label.bind(
                "<Button-1>",
                lambda e, n_code=data["n_code"], ep_no=data["ep_no"], gen_all_no=data["gen_all_no"],
                       rating=data["rating"]:
                messagebox.showinfo("機能未実装", f"小説更新機能はまだ実装されていません: {n_code}")
                # app.executor.run_in_background(
                #    lambda progress_callback: update_novel_async(n_code, ep_no, gen_all_no, rating, progress_callback),
                #    on_complete=on_update_complete
                # )
            )

    # 非同期処理：すべての小説を更新
    async def update_all_novels_async(shinchaku_novels, progress_callback):
        """すべての新着小説を更新する非同期関数"""
        if not app.novel_updater:
            progress_callback(100, "小説更新機能が初期化されていません")
            return {"error": "小説更新機能が初期化されていません"}

        if not shinchaku_novels:
            progress_callback(100, "更新する小説がありません")
            return {"error": "更新する小説がありません"}

        progress_callback(0, "小説を一括更新中...")

        # 小説更新クラスを使用して更新
        results = await app.novel_updater.update_all_novels(shinchaku_novels)

        progress_callback(100, "小説の更新が完了しました")
        return results

    # 非同期処理：特定の小説を更新
    async def update_novel_async(n_code, episode_no, general_all_no, rating, progress_callback):
        """指定した小説を更新する非同期関数"""
        if not app.novel_updater:
            progress_callback(100, "小説更新機能が初期化されていません")
            return {"error": "小説更新機能が初期化されていません"}

        progress_callback(0, f"{n_code}を更新中...")

        # エピソードを取得
        await app.novel_updater.new_episode(n_code, episode_no, general_all_no, rating)

        # データベースの更新
        progress_callback(90, "データベースを更新中...")
        await app.novel_updater._update_total_episodes_single(n_code)

        # 新着情報を更新
        progress_callback(95, "新着情報を更新中...")
        shinchaku_ep, main_shinchaku, shinchaku_novel = await app.novel_updater.shinchaku_checker()

        return {
            "n_code": n_code,
            "shinchaku_ep": shinchaku_ep,
            "main_shinchaku": main_shinchaku,
            "shinchaku_novel": shinchaku_novel
        }

    # 非同期処理：すべてのエピソードを再取得
    async def re_fetch_all_episodes_async(ncode, progress_callback):
        """小説のすべてのエピソードを再取得する非同期関数"""
        if not app.novel_updater:
            progress_callback(100, "小説更新機能が初期化されていません")
            return {"success": False, "message": "小説更新機能が初期化されていません"}

        progress_callback(0, f"{ncode}のエピソード情報を取得中...")

        # AsyncConnectionクラスのインポートが漏れているので、ローカルで定義
        class AsyncConnection:
            def __init__(self, db_path):
                self.db_path = db_path
                self.conn = None

            async def __aenter__(self):
                def connect():
                    conn = sqlite3.connect(self.db_path)
                    return conn

                self.conn = await asyncio.to_thread(connect)
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                if self.conn:
                    await asyncio.to_thread(self.conn.close)

            async def execute(self, sql, params=None):
                if params is None:
                    params = []
                cursor = self.conn.cursor()
                await asyncio.to_thread(lambda: cursor.execute(sql, params))
                return cursor

            async def fetchall(self, cursor):
                return await asyncio.to_thread(cursor.fetchall)

            async def commit(self):
                await asyncio.to_thread(self.conn.commit)

        async with AsyncConnection('database/novel_status.db') as db:
            # その小説の情報を取得
            cursor = await db.execute('SELECT n_code, rating, general_all_no FROM novels_descs WHERE n_code = ?',
                                      (ncode,))
            result = await db.fetchall(cursor)
            novel_info = result[0] if result else None

            if not novel_info:
                return {"success": False, "message": f"小説 {ncode} が見つかりません"}

            _, rating, general_all_no = novel_info

            if not general_all_no:
                return {"success": False, "message": f"小説 {ncode} のエピソード数情報がありません"}

            # エピソードを再取得
            progress_callback(10, f"{ncode}のエピソードを再取得中...")
            for i in range(general_all_no):
                episode_no = i + 1
                progress = int(10 + (i / general_all_no) * 80)
                progress_callback(progress, f"エピソード {episode_no}/{general_all_no} を取得中...")

                episode, title = await app.novel_updater.catch_up_episode(ncode, episode_no, rating)

                if episode and title:
                    # データベースを更新
                    await db.execute("""
                        INSERT OR REPLACE INTO episodes (ncode, episode_no, body, e_title)
                        VALUES (?, ?, ?, ?)
                    """, (ncode, episode_no, episode, title))

                    if episode_no % 10 == 0:  # 10エピソードごとにコミット
                        await db.commit()

                # レート制限を回避するために待機
                await asyncio.sleep(0.5)

            # 最終コミット
            await db.commit()

            # 総エピソード数を更新
            progress_callback(95, "データベースを更新中...")
            await app.novel_updater._update_total_episodes_single(ncode)

            # 新着情報を更新
            shinchaku_ep, main_shinchaku, shinchaku_novel = await app.novel_updater.shinchaku_checker()

            return {
                "success": True,
                "message": f"{ncode}の全{general_all_no}エピソードを再取得しました",
                "shinchaku_ep": shinchaku_ep,
                "main_shinchaku": main_shinchaku,
                "shinchaku_novel": shinchaku_novel
            }

if __name__ == "__main__":
    asyncio.run(main())