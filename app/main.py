import configparser
import sqlite3
import time
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
from utils.logger_manager import get_logger
from app.ui.components.command_prompt import CommandPrompt

# ロガーの設定
logger = get_logger('AppMain')

# グローバル変数の定義
global scrollable_frame, scroll_canvas, root, header_label, progress_label
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
root = None
header_label = None
progress_label = None
scrollable_frame = None
scroll_canvas = None

# データベースハンドラとエピソードフェッチャーを初期化
db = DatabaseHandler()
episode_fetcher = EpisodeFetcher(max_workers=10)

# 更新状況追跡用の変数
update_in_progress = False
update_progress_queue = queue.Queue()


def show_command_prompt():
    """コマンドプロンプト画面を表示する"""
    global update_in_progress, root, episode_fetcher, db

    def command_handler(command):
        """コマンドを処理する関数"""
        cmd_prompt.add_log(f"コマンド実行: {command}")

        if command.lower() == "help":
            return None  # helpコマンドはCommandPromptクラス内で処理

        elif command.lower() == "clear":
            return None  # clearコマンドはCommandPromptクラス内で処理

        elif command.lower() == "exit":
            return None  # exitコマンドはCommandPromptクラス内で処理

        elif command.lower().startswith("update"):
            # 更新処理中なら実行しない
            if update_in_progress:
                return "エラー: すでに更新処理が実行中です。完了までお待ちください。"

            # 全作品更新コマンド
            if "--all" in command:
                threading.Thread(
                    target=execute_update_all_command,
                    args=(cmd_prompt,)
                ).start()
                return "全ての更新可能な小説の取得を開始します..."

            # 個別更新コマンド
            elif "--single" in command:
                parts = command.split("--")
                ncode = None

                # ncodeの取得
                for part in parts:
                    if part.strip().startswith("n"):
                        ncode = part
                        break

                if not ncode:
                    return "エラー: 小説コード(ncode)が指定されていません。"

                # 全エピソード再取得
                if "--re_all" in command:
                    threading.Thread(
                        target=execute_refetch_command,
                        args=(cmd_prompt, ncode)
                    ).start()
                    return f"小説コード {ncode} の全エピソードの再取得を開始します..."

                # 欠落エピソード取得
                elif "--get_lost" in command:
                    threading.Thread(
                        target=execute_fetch_missing_command,
                        args=(cmd_prompt, ncode)
                    ).start()
                    return f"小説コード {ncode} の欠落エピソードの取得を開始します..."

                # 通常の更新
                else:
                    # 小説情報を取得
                    novel = db.get_novel_by_ncode(ncode)
                    if not novel:
                        return f"エラー: 小説コード {ncode} は見つかりませんでした。"

                    threading.Thread(
                        target=execute_update_single_command,
                        args=(cmd_prompt, novel)
                    ).start()
                    return f"小説 {novel[1]} の更新を開始します..."
            else:
                return "エラー: 無効なコマンド形式です。'help'コマンドでヘルプを表示します。"

        else:
            return "エラー: 不明なコマンドです。'help'コマンドでヘルプを表示します。"

    def execute_update_all_command(prompt):
        """全小説更新コマンドの実行"""
        global update_in_progress, main_shinaku, episode_fetcher

        update_in_progress = True
        try:
            shinchaku_novels = main_shinaku if main_shinaku else []
            total = len(shinchaku_novels)

            if total == 0:
                prompt.add_log("更新が必要な小説がありません。")
                update_in_progress = False
                return

            prompt.add_log(f"合計 {total} 件の小説を更新します。")

            for i, novel in enumerate(shinchaku_novels):
                ncode, title, current_ep, total_ep, rating = novel
                progress_msg = f"[{i + 1}/{total}] {title}(ID:{ncode}) の更新を開始します..."
                prompt.add_log(progress_msg)

                try:
                    # 小説データの更新
                    episode_fetcher.update_novel_episodes(ncode, current_ep, total_ep, rating)
                    prompt.add_log(f"[{i + 1}/{total}] {title} - 更新完了")
                except Exception as e:
                    prompt.add_log(f"[{i + 1}/{total}] {title} の更新中にエラーが発生しました: {str(e)}")

            # 完了後にグローバル変数を更新
            shinchaku_ep, main_shinaku, shinchaku_novel = shinchaku_checker()
            root.after(0, lambda: header_label.config(
                text=f"新着情報\n新着{shinchaku_novel}件,{shinchaku_ep}話"))

            prompt.add_log("すべての更新処理が完了しました。")

        except Exception as e:
            prompt.add_log(f"更新処理中にエラーが発生しました: {str(e)}")
        finally:
            update_in_progress = False

    def execute_update_single_command(prompt, novel):
        """単一小説更新コマンドの実行"""
        global update_in_progress, shinchaku_ep, main_shinaku, shinchaku_novel

        update_in_progress = True
        try:
            n_code, title = novel[0], novel[1]
            current_ep = novel[5] if len(novel) > 5 and novel[5] is not None else 0
            total_ep = novel[6] if len(novel) > 6 and novel[6] is not None else 0
            rating = novel[4] if len(novel) > 4 else None

            prompt.add_log(f"小説 [{title}] (ID:{n_code}) の更新を開始します...")

            # エピソードの更新
            episode_fetcher.update_novel_episodes(n_code, current_ep, total_ep, rating)

            # データベースの更新状態を反映
            shinchaku_ep, main_shinaku, shinchaku_novel = shinchaku_checker()

            # UI更新
            root.after(0, lambda: header_label.config(
                text=f"新着情報\n新着{shinchaku_novel}件,{shinchaku_ep}話"))

            prompt.add_log(f"小説 [{title}] の更新が完了しました")

        except Exception as e:
            prompt.add_log(f"更新処理中にエラーが発生しました: {str(e)}")
        finally:
            update_in_progress = False

    def execute_refetch_command(prompt, ncode):
        """小説の全エピソードを再取得する"""
        global update_in_progress

        update_in_progress = True
        try:
            # 小説情報の取得
            novel = db.get_novel_by_ncode(ncode)
            if not novel:
                prompt.add_log(f"エラー: 小説コード {ncode} は見つかりませんでした。")
                update_in_progress = False
                return

            title = novel[1]
            rating = novel[4] if len(novel) > 4 else None
            total_ep = int(novel[6]) if len(novel) > 6 and novel[6] is not None else 0  # 型変換を追加

            prompt.add_log(f"小説 [{title}] の全エピソード再取得を開始します...")

            # 既存のエピソードを削除
            db.execute_query("DELETE FROM episodes WHERE ncode = ?", (ncode,))
            prompt.add_log(f"既存のエピソードをデータベースから削除しました")

            if total_ep <= 0:
                prompt.add_log(f"警告: 小説 {title} の総エピソード数が不明です。更新をスキップします。")
                update_in_progress = False
                return

            # エピソードの再取得
            episode_fetcher.update_novel_episodes(ncode, 0, total_ep, rating)

            # データベースの更新
            db.update_total_episodes(ncode)

            prompt.add_log(f"小説 [{title}] の全エピソード({total_ep}話)の再取得が完了しました")

        except Exception as e:
            prompt.add_log(f"エラー: {str(e)}")
        finally:
            update_in_progress = False
            
    def execute_fetch_missing_command(prompt, ncode):
        """欠落しているエピソードを取得する"""
        global update_in_progress

        update_in_progress = True
        try:
            # 小説情報の取得
            novel = db.get_novel_by_ncode(ncode)
            if not novel:
                prompt.add_log(f"エラー: 小説コード {ncode} は見つかりませんでした。")
                update_in_progress = False
                return

            title = novel[1]
            rating = novel[4] if len(novel) > 4 else None

            prompt.add_log(f"小説 [{title}] の欠落エピソード取得を開始します...")

            # 欠落エピソードの検索
            missing_episodes = db.find_missing_episodes(ncode)

            if not missing_episodes:
                prompt.add_log(f"小説 [{title}] に欠落エピソードはありません。")
                update_in_progress = False
                return

            prompt.add_log(f"{len(missing_episodes)}件の欠落エピソードが見つかりました。")

            # 欠落エピソードの取得
            episode_fetcher.update_missing_episodes(ncode, rating)

            # データベースの更新
            db.update_total_episodes(ncode)

            prompt.add_log(f"小説 [{title}] の欠落エピソード取得が完了しました")

        except Exception as e:
            prompt.add_log(f"エラー: {str(e)}")
        finally:
            update_in_progress = False

    # コマンドプロンプトウィンドウの作成
    cmd_prompt = CommandPrompt(root, command_handler)
    return cmd_prompt


# 進捗状況を更新する関数
def update_progress():
    """進捗状況の表示を更新する"""
    global progress_label, update_in_progress, root
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
    """小説一覧を表示する（最適化版）"""
    global scrollable_frame, scroll_canvas, main_shelf, list_frame
    global current_page  # グローバル変数として宣言

    # 既存のウィジェットをクリア
    for widget in list_frame.winfo_children():
        widget.destroy()

    # 定数の定義
    ITEMS_PER_PAGE = 100  # 一度に表示する項目数
    current_page = 0
    total_items = len(main_shelf)
    total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE  # 切り上げ除算

    # キャンバスとスクロールバーの設定
    scroll_canvas = tk.Canvas(list_frame, bg="#F0F0F0")
    scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=scroll_canvas.yview)
    scrollable_frame = ttk.Frame(scroll_canvas)

    scroll_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    scroll_canvas.configure(yscrollcommand=scrollbar.set)

    scroll_canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # ページングコントロールフレーム
    paging_frame = tk.Frame(scrollable_frame, bg="#F0F0F0")
    paging_frame.pack(fill="x", pady=5)

    # 前のページボタン
    prev_button = ttk.Button(paging_frame, text="前へ", command=lambda: load_page(current_page - 1))
    prev_button.pack(side="left", padx=5)

    # ページ表示ラベル
    page_label = tk.Label(paging_frame, text=f"ページ {current_page + 1}/{total_pages}", bg="#F0F0F0")
    page_label.pack(side="left", padx=5)

    # 次のページボタン
    next_button = ttk.Button(paging_frame, text="次へ", command=lambda: load_page(current_page + 1))
    next_button.pack(side="left", padx=5)

    # リスト表示フレーム
    list_display_frame = tk.Frame(scrollable_frame, bg="#F0F0F0")
    list_display_frame.pack(fill="x", expand=True)

    # 小説リストを描画する関数（ページング対応）
    def load_page(page_num):
        global current_page

        # ページ境界チェック
        if page_num < 0 or page_num >= total_pages:
            return

        current_page = page_num

        # 前のリストをクリア
        for widget in list_display_frame.winfo_children():
            widget.destroy()

        # 現在のページに表示する項目の範囲を計算
        start_idx = current_page * ITEMS_PER_PAGE
        end_idx = min(start_idx + ITEMS_PER_PAGE, total_items)

        # ページングラベルを更新
        page_label.config(text=f"ページ {current_page + 1}/{total_pages}")

        # 前/次ボタンの有効/無効状態を更新
        prev_button.config(state=tk.NORMAL if current_page > 0 else tk.DISABLED)
        next_button.config(state=tk.NORMAL if current_page < total_pages - 1 else tk.DISABLED)

        # 現在のページの項目を表示
        for i in range(start_idx, end_idx):
            row = main_shelf[i]

            # 項目用フレーム
            item_frame = tk.Frame(list_display_frame, bg="#F0F0F0")
            item_frame.pack(fill="x", pady=2)

            # タイトルラベル
            title_text = f"{row[1]} - 作者: {row[2]}"
            title_label = tk.Label(item_frame, text=title_text, bg="#F0F0F0", anchor="w")
            title_label.pack(side="left", padx=5, fill="x", expand=True)

            # クリックイベント
            title_label.bind("<Button-1>", lambda e, n_code=row[0]: on_title_click(e, n_code))

    # 初期ページを読み込む
    load_page(0)


# スクロールイベント最適化
def configure_scroll_event():
    """スクロールイベントの最適化設定"""
    global scroll_canvas

    # スクロールイベントがトリガーされた回数を制限するための変数
    last_scroll_time = 0
    scroll_delay = 100  # ミリ秒単位

    def throttled_scroll_event(event):
        nonlocal last_scroll_time
        current_time = int(time.time() * 1000)

        # 前回のスクロールから一定時間経過していない場合はイベントを無視
        if current_time - last_scroll_time < scroll_delay:
            return "break"

        last_scroll_time = current_time

        # 通常のスクロール処理
        if event.delta > 0:
            scroll_canvas.yview_scroll(-1, "units")
        else:
            scroll_canvas.yview_scroll(1, "units")

        return "break"

    # マウスホイールイベントをバインド
    scroll_canvas.bind_all("<MouseWheel>", throttled_scroll_event)


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
    global set_font, novel_fontsize, bg_color, episodes

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
    global list_frame, scroll_canvas, set_font, novel_fontsize, bg_color

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
        global novel_fontsize, set_font, bg_color  # nonlocalをglobalに変更

        novel_fontsize = size_var.get()
        set_font = font_var.get()
        bg_color = bg_var.get()

        # ConfigParserオブジェクトを作成
        config = configparser.ConfigParser()

        # 設定をconfigオブジェクトに追加
        config['Settings'] = {
            'Font': set_font,
            'FontSize': novel_fontsize,
            'BackgroundColor': bg_color
        }

        # 設定をファイルに書き込み
        with open('settings.ini', 'w') as configfile:
            config.write(configfile)

        messagebox.showinfo("設定", "設定が適用されました")
        apply_button = ttk.Button(setting_frame, text="適用", command=apply_settings)
        apply_button.grid(row=3, column=0, columnspan=2, pady=10)


def show_updated_novels():
    """更新された小説一覧を表示する"""
    global scrollable_frame, scroll_canvas, list_frame, main_shinchaku

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
    global update_in_progress, shinchaku_ep, main_shinchaku, shinchaku_novel, root, header_label

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
    global update_in_progress, progress_label, root

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


def update_novel_threaded(n_code, episode_no, general_all_no, rating):
    """
    指定された小説を更新する（スレッド実行用）

    Args:
        n_code (str): 小説コード
        episode_no (int): 現在のエピソード数
        general_all_no (int): 全体のエピソード数
        rating (int): レーティング
    """
    global update_in_progress, shinchaku_ep, main_shinchaku, shinchaku_novel, root, header_label, progress_label

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
    global update_in_progress, root, progress_label

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


def main(main_shelf=None, last_read_novel=None, last_read_epno=0,
         set_font="YuKyokasho Yoko", novel_fontsize=14, bg_color="#FFFFFF",
         shinchaku_ep=0, main_shinchaku=None, shinchaku_novel=0):
    """
    アプリケーションのメイン関数（最適化版）

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
    # グローバル変数として宣言
    global scrollable_frame, scroll_canvas, root, header_label, progress_label, list_frame
    global update_in_progress, app_cache

    # アプリケーションキャッシュ初期化
    app_cache = NovelCache(cache_size=1000)

    # 引数がNoneの場合のデフォルト値設定
    if main_shelf is None:
        main_shelf = []
    if last_read_novel is None:
        last_read_novel = []
    if main_shinchaku is None:
        main_shinchaku = []

    # グローバル変数に値を代入
    globals()['main_shelf'] = main_shelf
    globals()['last_read_novel'] = last_read_novel
    globals()['last_read_epno'] = last_read_epno
    globals()['set_font'] = set_font
    globals()['novel_fontsize'] = novel_fontsize
    globals()['bg_color'] = bg_color
    globals()['shinchaku_ep'] = shinchaku_ep
    globals()['main_shinchaku'] = main_shinchaku
    globals()['shinchaku_novel'] = shinchaku_novel

    # rootウィンドウ作成
    root = tk.Tk()
    root.title("小説ビューア")
    root.geometry("1000x600")

    # tkinterのグローバル設定
    ttk.Style().configure("TButton", font=(set_font, 10))

    # 更新状態追跡用
    update_in_progress = False

    # メインフレーム
    main_frame = tk.Frame(root)
    main_frame.pack(fill="both", expand=True)

    # 左サイドパネル
    side_panel = tk.Frame(main_frame, width=200, bg="#E0E0E0")
    side_panel.pack(side="left", fill="y")
    side_panel.pack_propagate(False)  # サイズを固定

    # ヘッダーラベル
    header_label = tk.Label(
        side_panel,
        text=f"新着情報\n新着{shinchaku_novel}件,{shinchaku_ep}話",
        bg="#E0E0E0",
        font=(set_font, 12)
    )
    header_label.pack(pady=10)

    # ボタンスタイル設定
    button_style = {"width": 15, "font": (set_font, 10), "pady": 5}

    # ボタン作成
    novel_list_button = tk.Button(
        side_panel,
        text="小説一覧",
        command=lambda: root.after(50, show_novel_list),  # 非同期実行
        **button_style
    )
    novel_list_button.pack(pady=5)

    updated_novels_button = tk.Button(
        side_panel,
        text="更新された小説",
        command=lambda: root.after(50, show_updated_novels),
        **button_style
    )
    updated_novels_button.pack(pady=5)

    settings_button = tk.Button(
        side_panel,
        text="設定",
        command=lambda: root.after(50, show_settings),
        **button_style
    )
    settings_button.pack(pady=5)

    input_button = tk.Button(
        side_panel,
        text="コマンド入力",
        command=lambda: root.after(50, show_command_prompt()),
        **button_style
    )
    input_button.pack(pady=5)

    # 進捗状況ラベル
    progress_label = tk.Label(side_panel, text="", bg="#E0E0E0", wraplength=180)
    progress_label.pack(pady=10, side="bottom")

    # メインコンテンツフレーム
    list_frame = tk.Frame(main_frame, bg="#F0F0F0")
    list_frame.pack(side="right", fill="both", expand=True)

    # 処理能力の最適化
    def optimize_performance():
        # tkinterの描画更新頻度を調整
        root.update_idletasks()

        # GUIイベントを処理
        root.update()

        # メモリ使用状況を表示（デバッグ用）
        if DEBUG_MODE:
            import psutil
            process = psutil.Process()
            memory_info = process.memory_info()
            print(f"Memory usage: {memory_info.rss / (1024 * 1024):.2f} MB")

        # 定期的に実行
        root.after(1000, optimize_performance)

    # パフォーマンス最適化タスク開始
    DEBUG_MODE = False  # デバッグモードフラグ
    root.after(1000, optimize_performance)

    # 初期表示
    show_novel_list()

    # イベントループ開始
    root.mainloop()

    # アプリケーション終了時の処理
    db.close_all_connections()


# データベースからの一括読み込みを避けるためのページング型小説一覧取得
def get_novel_list_paged(page=0, items_per_page=100):
    """
    ページング処理を使用した小説一覧取得

    Args:
        page (int): ページ番号（0から開始）
        items_per_page (int): 1ページあたりの項目数

    Returns:
        tuple: (小説リスト, 総ページ数)
    """
    # 総数を取得
    count_query = 'SELECT COUNT(*) FROM novels_descs'
    total_count = db.execute_query(count_query, fetch=True, fetch_all=False)[0]

    # 総ページ数を計算
    total_pages = (total_count + items_per_page - 1) // items_per_page

    # 指定ページのデータを取得
    offset = page * items_per_page
    query = 'SELECT * FROM novels_descs ORDER BY updated_at DESC LIMIT ? OFFSET ?'
    novels = db.execute_query(query, (items_per_page, offset), fetch=True)

    return novels, total_pages


# メインウィンドウ更新を最小限に抑えるヘルパー関数
def schedule_ui_update(update_func, delay=100):
    """
    UI更新処理をスケジュールする

    Args:
        update_func (callable): UI更新関数
        delay (int): 遅延時間（ミリ秒）
    """
    root.after(delay, update_func)


# データベース接続プールを拡張して並列処理に対応
class EnhancedDatabaseHandler(DatabaseHandler):
    """拡張データベースハンドラクラス"""

    def __init__(self):
        super().__init__()
        self._read_connection_pool = {}  # 読み取り専用接続プール

    def get_read_connection(self):
        """読み取り専用の接続を取得（並列処理対応）"""
        thread_id = threading.get_ident()

        if thread_id not in self._read_connection_pool:
            conn = sqlite3.connect(self.db_path)
            conn.execute('PRAGMA journal_mode=WAL')
            conn.text_factory = str
            # 読み取り専用モードを設定
            conn.execute('PRAGMA query_only=ON')
            self._read_connection_pool[thread_id] = conn

        return self._read_connection_pool[thread_id]

    def execute_read_query(self, query, params=None, fetch=True, fetch_all=True):
        """読み取り専用クエリの実行（ロックなし）"""
        conn = self.get_read_connection()
        cursor = conn.cursor()

        try:
            if params is None:
                cursor.execute(query)
            else:
                cursor.execute(query, params)

            if fetch:
                if fetch_all:
                    return cursor.fetchall()
                else:
                    return cursor.fetchone()

            return cursor.rowcount

        except sqlite3.Error as e:
            logger.error(f"読み取りクエリエラー: {e}, クエリ: {query}")
            raise


# キャッシュ関連のクラスと関数

class NovelCache:
    """小説データキャッシュクラス"""

    def __init__(self, cache_size=500):
        self.cache = {}  # {ncode: novel_data}
        self.cache_size = cache_size
        self.access_times = {}  # {ncode: last_access_time}

    def get(self, ncode):
        """キャッシュからデータを取得"""
        if ncode in self.cache:
            self.access_times[ncode] = time.time()
            return self.cache[ncode]
        return None

    def put(self, ncode, data):
        """キャッシュにデータを格納"""
        # キャッシュがいっぱいの場合、最も古いエントリを削除
        if len(self.cache) >= self.cache_size:
            oldest_ncode = min(self.access_times.items(), key=lambda x: x[1])[0]
            del self.cache[oldest_ncode]
            del self.access_times[oldest_ncode]

        self.cache[ncode] = data
        self.access_times[ncode] = time.time()

    def clear(self):
        """キャッシュをクリア"""
        self.cache.clear()
        self.access_times.clear()


# 最適化されたデータベース取得関数
def get_optimized_novel_list(offset=0, limit=100):
    """
    ページング処理を使用して最適化された小説リストを取得

    Args:
        offset (int): 開始位置
        limit (int): 取得する最大項目数

    Returns:
        list: 小説データのリスト
    """
    # キャッシュキー
    cache_key = f"novel_list_{offset}_{limit}"

    # キャッシュからデータを取得
    cached_data = app_cache.get(cache_key)
    if cached_data:
        return cached_data

    # データベースから取得
    query = 'SELECT * FROM novels_descs ORDER BY updated_at DESC LIMIT ? OFFSET ?'
    novels = db.execute_query(query, (limit, offset), fetch=True)

    # キャッシュに保存
    app_cache.put(cache_key, novels)

    return novels


# 最適化されたエピソードリスト表示
def show_optimized_episode_list(episodes, ncode):
    """
    エピソード一覧を仮想化されたリストで表示する

    Args:
        episodes (list): エピソードデータのリスト
        ncode (str): 小説コード
    """
    global scrollable_frame, scroll_canvas

    # エピソード番号でソート
    episodes.sort(key=lambda episode: int(episode[0]))

    # スクロール位置をリセット
    scroll_canvas.yview_moveto(0)

    # 既存のウィジェットをクリア
    for widget in scrollable_frame.winfo_children():
        widget.destroy()

    # 仮想リスト管理用の変数
    visible_items = {}  # {index: widget}
    item_heights = 30  # 各項目の推定高さ（ピクセル）

    # プレースホルダーキャンバス（全体の高さを確保するためのもの）
    total_height = len(episodes) * item_heights
    placeholder = tk.Frame(scrollable_frame, height=total_height, bg="#F0F0F0")
    placeholder.pack(fill="x")

    # スクロールイベントハンドラ
    def update_visible_items(event=None):
        # 現在表示されている範囲を特定
        top = int(scroll_canvas.yview()[0] * total_height)
        bottom = int(scroll_canvas.yview()[1] * total_height)

        # 表示範囲内のアイテムインデックスを計算
        start_idx = max(0, top // item_heights - 5)  # バッファとして前後5項目も表示
        end_idx = min(len(episodes), (bottom // item_heights) + 5)

        # 範囲外の項目を削除
        to_remove = []
        for idx in visible_items:
            if idx < start_idx or idx >= end_idx:
                visible_items[idx].destroy()
                to_remove.append(idx)

        for idx in to_remove:
            del visible_items[idx]

        # 新しい項目を表示
        for i in range(start_idx, end_idx):
            if i not in visible_items and i < len(episodes):
                episode = episodes[i]
                frame = tk.Frame(scrollable_frame, bg="#F0F0F0")
                frame.place(x=0, y=i * item_heights, width=scroll_canvas.winfo_width(), height=item_heights)

                # エピソードラベル
                episode_label = tk.Label(frame, text=f"Episode {episode[0]}: {episode[1]}",
                                         bg="#F0F0F0", anchor="w")
                episode_label.pack(side="left", padx=5, fill="x", expand=True)

                # クリックイベントをラベルにバインド
                episode_label.bind("<Button-1>", lambda e, ep=episode: on_episode_click(e, ep, ncode))

                visible_items[i] = frame

    # スクロールイベントにハンドラを追加
    scroll_canvas.bind("<Configure>", update_visible_items)
    scroll_canvas.bind_all("<MouseWheel>", update_visible_items)

    # 初期表示
    scroll_canvas.after(100, update_visible_items)


# アプリケーション初期化時にキャッシュを作成
def init_application():
    """アプリケーション初期化処理"""
    global app_cache
    app_cache = NovelCache(cache_size=1000)  # キャッシュサイズを適切に設定

    # その他の初期化処理
    # ...


# アニメーション/トランジション付きのウィジェット更新
def animate_widget_update(widget, new_text, duration=500):
    """
    ウィジェットのテキスト更新にアニメーションを追加

    Args:
        widget (tk.Widget): 更新するウィジェット
        new_text (str): 新しいテキスト
        duration (int): アニメーション時間（ミリ秒）
    """
    # 現在の背景色を保存
    original_bg = widget.cget("bg")

    # 一度背景色を変更
    widget.config(bg="#E0E0FF")

    # テキストを更新
    widget.config(text=new_text)

    # 元の背景色に徐々に戻す
    def fade_back(remaining):
        if remaining <= 0:
            widget.config(bg=original_bg)
            return

        # RGB値を計算（E0E0FFからoriginal_bgへのグラデーション）
        r = int(0xE0 - (0xE0 - int(original_bg[1:3], 16)) * (1 - remaining / duration))
        g = int(0xE0 - (0xE0 - int(original_bg[3:5], 16)) * (1 - remaining / duration))
        b = int(0xFF - (0xFF - int(original_bg[5:7], 16)) * (1 - remaining / duration))

        color = f"#{r:02x}{g:02x}{b:02x}"
        widget.config(bg=color)

        widget.after(50, fade_back, remaining - 50)

    widget.after(50, fade_back, duration)
