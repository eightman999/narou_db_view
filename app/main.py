import configparser
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from bs4 import BeautifulSoup
from PIL import ImageFont, Image, ImageDraw, ImageTk
import tkinter.font as tkFont
import threading
import logging
import queue

from app.bookshelf import shelf_maker, get_last_read, episode_getter, input_last_read
from core.checker import load_conf, db_update, shinchaku_checker, dell_dl, del_yml
from database.db_handler import DatabaseHandler
from tools.episode_fetcher import EpisodeFetcher

# ロガーの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='app_main.log'
)
logger = logging.getLogger('AppMain')

# グローバル変数の定義
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

# データベースハンドラとエピソードフェッチャーを初期化
db = DatabaseHandler()
episode_fetcher = EpisodeFetcher(max_workers=10)

# 更新状況追跡用の変数
update_in_progress = False
update_progress_queue = queue.Queue()


def main(main_shelf=None, last_read_novel=None, last_read_epno=0,
         set_font="YuKyokasho Yoko", novel_fontsize=14, bg_color="#FFFFFF",
         shinchaku_ep=0, main_shinchaku=None, shinchaku_novel=0):
    """
    アプリケーションのメイン関数

    Args:
        main_shelf (list): 小説の一覧
        last_read_novel (list): 最後に読んだ小説情報
        last_read_epno (int): 最後に読んだエピソード番号
        set_font (str): 設定フォント
        novel_fontsize (int): フォントサイズ
        bg_color (str): 背景色
        shinchaku_ep (int): 新着エピソード数
        main_shinchaku (list): 新着小説リスト
        shinchaku_novel (int): 新着小説数
    """
    # グローバル変数の設定
    global scrollable_frame, scroll_canvas, update_in_progress

    # 引数がNoneの場合のデフォルト値設定
    if main_shelf is None:
        main_shelf = []
    if last_read_novel is None:
        last_read_novel = []
    if main_shinchaku is None:
        main_shinchaku = []

    # メインウィンドウの設定
    root = tk.Tk()
    root.title("小説アプリ")
    root.attributes("-fullscreen", True)  # フルスクリーンモード
    root.configure(bg="#0080A0")  # 背景色を変更

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

    # 進捗状況表示用ラベル
    progress_label = tk.Label(
        header_frame,
        text="",
        bg="#0080A0",
        fg="white",
        font=("Helvetica", 12),
        anchor="center",
    )
    progress_label.pack(side="top", pady=5)

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

    # 進捗状況を更新する関数
    def update_progress():
        """進捗状況の表示を更新する"""
        if not update_progress_queue.empty():
            message = update_progress_queue.get()
            progress_label.config(text=message)

        # 更新中は定期的に再実行
        if update_in_progress:
            root.after(100, update_progress)
        else:
            progress_label.config(text="")

    # 小説リストを表示する関数
    def show_novel_list():
        """小説一覧を表示する"""
        global scrollable_frame, scroll_canvas

        # 既存のウィジェットをクリア
        for widget in list_frame.winfo_children():
            widget.destroy()

        # スクロールキャンバスとフレームを初期化
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

        # データ構造を準備
        buttons_data = [
            {"title": f"読む", "text": f"{row[1]} - 作者: {row[2]}", "n_code": row[0]}
            for row in main_shelf
        ]

        # すべてのボタンを描画
        for data in buttons_data:
            frame = tk.Frame(scrollable_frame, bg="#F0F0F0")
            frame.pack(fill="x", pady=2)

            # タイトルラベル
            title_label = tk.Label(frame, text=data["text"], bg="#F0F0F0", anchor="w")
            title_label.pack(side="left", padx=5, fill="x", expand=True)

            # クリックイベントをラベルにバインド
            title_label.bind("<Button-1>", lambda e, n_code=data["n_code"]: on_title_click(e, n_code))

    def on_title_click(event, n_code):
        """小説タイトルがクリックされたときの処理"""
        global episodes
        episodes = episode_getter(n_code)
        show_episode_list(episodes, n_code)

    def show_episode_list(episodes, ncode):
        """エピソード一覧を表示する"""
        global scrollable_frame, scroll_canvas

        # エピソード番号でソート
        episodes.sort(key=lambda episode: int(episode[0]))

        # スクロール位置をリセット
        scroll_canvas.yview_moveto(0)

        # 既存のウィジェットをクリア
        for widget in scrollable_frame.winfo_children():
            widget.destroy()

        # エピソード表示用のフレームとラベルを作成
        for episode in episodes:
            frame = tk.Frame(scrollable_frame, bg="#F0F0F0")
            frame.pack(fill="x", pady=2)

            # エピソードラベル
            episode_label = tk.Label(frame, text=f"Episode {episode[0]}: {episode[1]}", bg="#F0F0F0", anchor="w")
            episode_label.pack(side="left", padx=5, fill="x", expand=True)

            # クリックイベントをラベルにバインド
            episode_label.bind("<Button-1>", lambda e, ep=episode: on_episode_click(e, ep, ncode))

        # エピソードリスト用のスクロールバーを作成
        scrollbar = ttk.Scrollbar(scrollable_frame, orient="vertical", command=scroll_canvas.yview)
        scrollbar.pack(side="right", fill="y")

        # スクロールバーを設定
        scroll_canvas.config(yscrollcommand=scrollbar.set)

    def on_episode_click(event, episode, n_code):
        """エピソードがクリックされたときの処理"""

        def show_episode(episode):
            # 既存のコンテンツをクリア
            scrolled_text.config(state=tk.NORMAL)
            scrolled_text.delete(1.0, tk.END)

            # HTMLコンテンツを解析
            soup = BeautifulSoup(episode[2], "html.parser")

            # 空の段落を削除
            for p in soup.find_all('p'):
                if not p.get_text(strip=True) and not p.attrs:
                    p.decompose()

            # クリーンなテキストコンテンツを抽出
            text_content = soup.get_text()

            # テキストをスクロールテキストウィジェットに挿入
            scrolled_text.insert(tk.END, text_content)
            scrolled_text.config(state=tk.DISABLED, bg=bg_color)

        def next_episode(event):
            nonlocal episode
            current_index = episodes.index(episode)
            if current_index < len(episodes) - 1:
                episode = episodes[current_index + 1]
                show_episode(episode)
                input_last_read(n_code, episode[0])
            episode_window.title(f"Episode {episode[0]}: {episode[1]}")

        def previous_episode(event):
            nonlocal episode
            current_index = episodes.index(episode)
            if current_index > 0:
                episode = episodes[current_index - 1]
                show_episode(episode)
                input_last_read(n_code, episode[0])
            episode_window.title(f"Episode {episode[0]}: {episode[1]}")

        # エピソードコンテンツを表示する新しいウィンドウを作成
        episode_window = tk.Toplevel()
        episode_window.title(f"Episode {episode[0]}: {episode[1]}")
        episode_window.geometry("800x600")
        input_last_read(n_code, episode[0])

        # エピソードコンテンツを表示するスクロールテキストウィジェットを作成
        scrolled_text = scrolledtext.ScrolledText(episode_window, wrap=tk.WORD, font=(set_font, novel_fontsize))
        scrolled_text.pack(fill=tk.BOTH, expand=True)

        # 初期エピソードコンテンツを表示
        show_episode(episode)

        # 左右の矢印キーでエピソードを移動するバインド
        episode_window.bind("<Right>", next_episode)
        episode_window.bind("<Left>", previous_episode)

    def show_settings():
        """設定画面を表示する"""
        # 既存のスクロールキャンバス以外のウィジェットをクリア
        for widget in list_frame.winfo_children():
            if widget != scroll_canvas:
                widget.destroy()

        # 設定用のフレームを作成
        setting_frame = tk.Frame(list_frame, bg="#F0F0F0")
        setting_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # フォント選択
        font_label = tk.Label(setting_frame, text="フォント:", bg="#F0F0F0", anchor="w")
        font_label.grid(row=0, column=0, sticky="w", pady=5)
        font_var = tk.StringVar(value=set_font)
        font_dropdown = ttk.Combobox(setting_frame, textvariable=font_var, values=tkFont.families())
        font_dropdown.grid(row=0, column=1, sticky="ew", pady=5)

        # フォントサイズ
        size_label = tk.Label(setting_frame, text="文字サイズ:", bg="#F0F0F0", anchor="w")
        size_label.grid(row=1, column=0, sticky="w", pady=5)
        size_var = tk.IntVar(value=novel_fontsize)
        size_entry = tk.Entry(setting_frame, textvariable=size_var)
        size_entry.grid(row=1, column=1, sticky="ew", pady=5)

        # 背景色
        bg_label = tk.Label(setting_frame, text="バックグラウンド色 (RGB):", bg="#F0F0F0", anchor="w")
        bg_label.grid(row=2, column=0, sticky="w", pady=5)
        bg_var = tk.StringVar(value=bg_color)
        bg_entry = tk.Entry(setting_frame, textvariable=bg_var)
        bg_entry.grid(row=2, column=1, sticky="ew", pady=5)

        # 適用ボタン
        def apply_settings():
            nonlocal novel_fontsize
            novel_fontsize = size_var.get()

            # ConfigParserオブジェクトを作成
            config = configparser.ConfigParser()

            # 設定をconfigオブジェクトに追加
            config['Settings'] = {
                'Font': font_var.get(),
                'FontSize': novel_fontsize,
                'BackgroundColor': bg_var.get()
            }

            # 設定をファイルに書き込み
            with open('settings.ini', 'w') as configfile:
                config.write(configfile)

            messagebox.showinfo("設定", "設定が適用されました")

        apply_button = ttk.Button(setting_frame, text="適用", command=apply_settings)
        apply_button.grid(row=3, column=0, columnspan=2, pady=10)

    def show_input_screen():
        """入力画面を表示する"""
        input_window = tk.Toplevel()
        input_window.title("入力画面")
        input_window.geometry("500x300")

        input_label = tk.Label(input_window, text="")
        input_label.pack(pady=10)

        input_text = tk.Text(input_window, height=10, width=50)
        input_text.pack(pady=5)

        def send_input(event=None):
            """入力テキストを処理する"""
            user_input = input_text.get("1.0", tk.END).strip()
            logger.info(f"User input: {user_input}")

            if user_input == "exit":
                root.quit()

            elif "update" in user_input:
                parts = user_input.split("update")

                if "--all" in parts[1]:
                    # 全ての対象小説を更新
                    threading.Thread(target=update_all_novels_threaded, args=(main_shinchaku,)).start()

                elif "--single" in parts[1]:
                    remaining = parts[1].split("--single")[1]

                    if "--re_all" in remaining:
                        # 指定された小説の全エピソードを再取得
                        if "--n" in remaining:
                            ncode_part = remaining.split("--n")[1].strip()
                            # 空白やその他の文字を除去
                            ncode = ncode_part.split()[0] if ' ' in ncode_part else ncode_part

                            threading.Thread(target=refetch_all_episodes, args=(ncode,)).start()
                            input_label.config(text=f"小説 {ncode} の全エピソードを再取得中...")

                        else:
                            input_label.config(text="エラー: ncodeを指定してください (--n)")

                    elif "--get_lost" in remaining:
                        # 欠落しているエピソードを取得
                        if "--n" in remaining:
                            ncode_part = remaining.split("--n")[1].strip()
                            ncode = ncode_part.split()[0] if ' ' in ncode_part else ncode_part

                            threading.Thread(target=fetch_missing_episodes, args=(ncode,)).start()
                            input_label.config(text=f"小説 {ncode} の欠落エピソードを取得中...")

                        else:
                            input_label.config(text="エラー: ncodeを指定してください (--n)")
                    else:
                        input_label.config(text="無効なコマンド")
                else:
                    input_label.config(text="無効なコマンド")

            elif "n" in user_input:
                try:
                    index = int(user_input.replace("n", ""))
                    if 0 <= index < len(main_shelf):
                        ncode = main_shelf[index][0]
                        title = main_shelf[index][1]
                        input_label.config(text=f"ncode: {ncode}, title: {title}")
                    else:
                        input_label.config(text="インデックスが範囲外です")
                except ValueError:
                    input_label.config(text="無効な入力です")
            else:
                input_label.config(text=f"入力: {user_input}")

            input_text.delete("1.0", tk.END)

        def exit_input():
            """入力画面を閉じる"""
            input_window.destroy()

        exit_button = tk.Button(input_window, text="終了", command=exit_input)
        exit_button.pack(pady=10)
        input_text.bind("<Return>", send_input)

    def show_updated_novels():
        """更新された小説一覧を表示する"""
        global scrollable_frame, scroll_canvas

        # 既存のウィジェットをクリア
        for widget in list_frame.winfo_children():
            widget.destroy()

        # キャンバスとスクロールバーを作成
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

        # 上部に「一括更新」ボタンを追加
        update_all_button = ttk.Button(
            scrollable_frame,
            text="一括更新",
            command=lambda: threading.Thread(target=update_all_novels_threaded, args=(main_shinchaku,)).start()
        )
        update_all_button.pack(fill="x", pady=2)

        # 更新された小説のタイトルを表示
        for data in buttons_data:
            frame = tk.Frame(scrollable_frame, bg="#F0F0F0")
            frame.pack(fill="x", pady=2)

            # タイトルラベル
            title_label = tk.Label(frame, text=data["text"], bg="#F0F0F0", anchor="w")
            title_label.pack(side="left", padx=5, fill="x", expand=True)

            # クリックイベントをラベルにバインド
            title_label.bind(
                "<Button-1>",
                lambda e, n_code=data["n_code"], ep_no=data["ep_no"], gen_all_no=data["gen_all_no"],
                       rating=data["rating"]:
                threading.Thread(target=update_novel_threaded, args=(n_code, ep_no, gen_all_no, rating)).start()
            )

    def update_all_novels_threaded(shinchaku_novels):
        """
        すべての新着小説を更新する（スレッド実行用）

        Args:
            shinchaku_novels (list): 更新対象の小説リスト
        """
        global update_in_progress, shinchaku_ep, main_shinchaku, shinchaku_novel

        if update_in_progress:
            messagebox.showinfo("更新中", "既に更新処理が実行中です。完了までお待ちください。")
            return

        update_in_progress = True
        update_progress_queue.put("更新処理を開始しています...")
        root.after(100, update_progress)

        try:
            total = len(shinchaku_novels)
            for i, row in enumerate(shinchaku_novels):
                update_progress_queue.put(f"更新中: {i + 1}/{total} - {row[1]}")

                try:
                    # エピソードフェッチャーを使用して更新
                    episode_fetcher.update_novel_episodes(row[0], row[2], row[3], row[4])
                    logger.info(f"小説 {row[0]} ({row[1]}) を更新しました")
                except Exception as e:
                    logger.error(f"小説 {row[0]} の更新中にエラーが発生しました: {e}")

            # 更新後に新着状態を再確認
            shinchaku_ep, main_shinchaku, shinchaku_novel = shinchaku_checker()

            # UIの更新は必ずメインスレッドで実行
            root.after(0, lambda: header_label.config(text=f"新着情報\n新着{shinchaku_novel}件,{shinchaku_ep}話"))
            root.after(0, show_updated_novels)

            logger.info("すべての小説の更新が完了しました")
            update_progress_queue.put("更新が完了しました")

        except Exception as e:
            logger.error(f"更新処理中にエラーが発生しました: {e}")
            update_progress_queue.put(f"エラー: {str(e)}")

        finally:
            update_in_progress = False
            # 3秒後にメッセージをクリア
            root.after(3000, lambda: progress_label.config(text=""))

    def fetch_missing_episodes(ncode):
        """
        指定された小説の欠落しているエピソードを取得する

        Args:
            ncode (str): 小説コード
        """
        global update_in_progress

        if update_in_progress:
            messagebox.showinfo("更新中", "既に更新処理が実行中です。完了までお待ちください。")
            return

        update_in_progress = True
        update_progress_queue.put(f"小説 {ncode} の欠落エピソードを検索中...")
        root.after(100, update_progress)

        try:
            # この小説のデータを取得
            novel = db.get_novel_by_ncode(ncode)
            if not novel:
                update_progress_queue.put(f"エラー: 小説 {ncode} が見つかりません")
                update_in_progress = False
                return

            rating = novel[4] if len(novel) > 4 else None

            # 欠落エピソードを検索
            missing_episodes = db.find_missing_episodes(ncode)

            if not missing_episodes:
                update_progress_queue.put(f"小説 {ncode} に欠落エピソードはありません")
                update_in_progress = False
                return

            update_progress_queue.put(f"{len(missing_episodes)}個の欠落エピソードを取得中...")

            # エピソードフェッチャーを使用して欠落エピソードを取得
            episode_fetcher.update_missing_episodes(ncode, rating)

            logger.info(f"小説 {ncode} の欠落エピソード {len(missing_episodes)}個を取得しました")
            update_progress_queue.put(f"小説 {ncode} の欠落エピソード {len(missing_episodes)}個を取得しました")

            # 総エピソード数を更新
            db.update_total_episodes(ncode)

        except Exception as e:
            logger.error(f"小説 {ncode} の欠落エピソード取得中にエラーが発生しました: {e}")
            update_progress_queue.put(f"エラー: {str(e)}")

        finally:
            update_in_progress = False
            # 3秒後にメッセージをクリア
            root.after(3000, lambda: progress_label.config(text=""))

    current_row = 0

    # 「小説をさがす」セクション
    create_section_title(content_frame, "小説をさがす", current_row)
    current_row += 1
    search_buttons = ["ランキング", "キーワード検索", "詳細検索", "ノクターノベルズ", "ムーンライトノベルズ", "PickUp!"]
    for btn_text in search_buttons:
        create_button(content_frame, btn_text, current_row)
        current_row += 1

    # 「小説を読む」セクション
    create_section_title(content_frame, "小説を読む", current_row)
    current_row += 1
    read_buttons = [
        ("小説一覧", show_novel_list),
        ("最近更新された小説", show_updated_novels),
        ("最近読んだ小説", None),
        ("作者別・シリーズ別", None),
        ("タグ検索", None),
    ]
    for btn_text, command in read_buttons:
        create_button(content_frame, btn_text, current_row, command=command)
        current_row += 1

    # 「オプション」セクション
    create_section_title(content_frame, "オプション", current_row)
    current_row += 1
    option_buttons = [("ダウンロード状況", None), ("設定", show_settings)]
    for btn_text in option_buttons:
        create_button(content_frame, btn_text, current_row)
        current_row += 1

    # データベース接続の終了処理
    def on_closing():
        """アプリケーション終了時の処理"""
        try:
            db.close_all_connections()
            logger.info("データベース接続を閉じました")
        except Exception as e:
            logger.error(f"データベース接続の終了中にエラーが発生しました: {e}")
        finally:
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)

    # アプリの起動
    root.bind('<Command-@>', lambda event: show_input_screen())
    root.mainloop()


# スクリプトが直接実行された場合にmain()を呼び出す
if __name__ == "__main__":
    dell_dl()
    del_yml()
    main_shelf = shelf_maker()
    last_read_novel, last_read_epno = get_last_read(main_shelf)
    set_font, novel_fontsize, bg_color = load_conf()
    db_update()
    shinchaku_ep, main_shinchaku, shinchaku_novel = shinchaku_checker()

    main(
        main_shelf=main_shelf,
        last_read_novel=last_read_novel,
        last_read_epno=last_read_epno,
        set_font=set_font,
        novel_fontsize=novel_fontsize,
        bg_color=bg_color,
        shinchaku_ep=shinchaku_ep,
        main_shinchaku=main_shinchaku,
        shinchaku_novel=shinchaku_novel
    )


    def update_novel_threaded(n_code, episode_no, general_all_no, rating):
        """
        指定された小説を更新する（スレッド実行用）

        Args:
            n_code (str): 小説コード
            episode_no (int): 現在のエピソード数
            general_all_no (int): 全体のエピソード数
            rating (int): レーティング
        """
        global update_in_progress, shinchaku_ep, main_shinchaku, shinchaku_novel

        if update_in_progress:
            messagebox.showinfo("更新中", "既に更新処理が実行中です。完了までお待ちください。")
            return

        update_in_progress = True
        update_progress_queue.put(f"小説 {n_code} を更新中...")
        root.after(100, update_progress)

        try:
            # エピソードフェッチャーを使用して更新
            episode_fetcher.update_novel_episodes(n_code, episode_no, general_all_no, rating)

            # 更新後に新着状態を再確認
            shinchaku_ep, main_shinchaku, shinchaku_novel = shinchaku_checker()

            # UIの更新は必ずメインスレッドで実行
            root.after(0, lambda: header_label.config(text=f"新着情報\n新着{shinchaku_novel}件,{shinchaku_ep}話"))
            root.after(0, show_novel_list)
            root.after(0, show_updated_novels)

            logger.info(f"小説 {n_code} の更新が完了しました")
            update_progress_queue.put("更新が完了しました")

        except Exception as e:
            logger.error(f"小説 {n_code} の更新中にエラーが発生しました: {e}")
            update_progress_queue.put(f"エラー: {str(e)}")

        finally:
            update_in_progress = False
            # 3秒後にメッセージをクリア
            root.after(3000, lambda: progress_label.config(text=""))


    def refetch_all_episodes(ncode):
        """
        指定された小説の全エピソードを再取得する

        Args:
            ncode (str): 小説コード
        """
        global update_in_progress

        if update_in_progress:
            messagebox.showinfo("更新中", "既に更新処理が実行中です。完了までお待ちください。")
            return

        update_in_progress = True
        update_progress_queue.put(f"小説 {ncode} の全エピソードを再取得中...")
        root.after(100, update_progress)

        try:
            # この小説のデータを取得
            novel = db.get_novel_by_ncode(ncode)
            if not novel:
                update_progress_queue.put(f"エラー: 小説 {ncode} が見つかりません")
                update_in_progress = False
                return

            rating = novel[4] if len(novel) > 4 else None

            # 既存のエピソードを削除
            db.execute_query("DELETE FROM episodes WHERE ncode = ?", (ncode,))
            logger.info(f"小説 {ncode} の既存エピソードを削除しました")

            # 総エピソード数を取得
            general_all_no = novel[6] if len(novel) > 6 else 0

            if general_all_no and general_all_no > 0:
                # エピソードフェッチャーを使用して全エピソードを取得（0から開始して全て取得）
                episode_fetcher.update_novel_episodes(ncode, 0, general_all_no, rating)
                logger.info(f"小説 {ncode} の全 {general_all_no} エピソードを再取得しました")
                update_progress_queue.put(f"小説 {ncode} の全 {general_all_no} エピソードを再取得しました")
            else:
                update_progress_queue.put(f"警告: 小説 {ncode} のエピソード総数が不明です")

            # 総エピソード数を更新
            db.update_total_episodes(ncode)

        except Exception as e:
            logger.error(f"小説 {ncode} の再取得中にエラーが発生しました: {e}")
            update_progress_queue.put(f"エラー: {str(e)}")

        finally:
            update_in_progress = False
            # 3秒後にメッセージをクリア
            root.after(3000, lambda: progress_label.config(text=""))