import configparser
import tkinter as tk
from tkinter import ttk, scrolledtext
from bookshelf import shelf_maker, get_last_read, episode_getter, input_last_read
from bs4 import BeautifulSoup
from PIL import ImageFont, Image, ImageDraw, ImageTk
import tkinter.font as tkFont

from app.bookshelf import shelf_maker, get_last_read, episode_getter, input_last_read
from core.checker import load_conf, db_update, shinchaku_checker, new_episode, dell_dl, del_yml
from database.operations import update_total_episodes_single, update_total_episodes

global scrollable_frame, scroll_canvas
main_sehelf = []
last_read_novel = []
episodes = []
last_read_epno = 0
novel_fontsize = 14
set_font = "YuKyokasho Yoko"
bg_color = "#FFFFFF"
shinchaku_ep = 0
shinchaku_novel = 0
main_shinchaku = []
def main():
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


    def show_novel_list():
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
            for row in main_sehelf
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

    def on_title_click(event, n_code):
        global episodes
        episodes = episode_getter(n_code)
        show_episode_list(episodes,n_code)

    def show_episode_list(episodes, ncode):
        global scrollable_frame, scroll_canvas
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

    def on_episode_click(event, episode, n_code):
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

        # Create a new window to display the episode content
        episode_window = tk.Toplevel()
        episode_window.title(f"Episode {episode[0]}: {episode[1]}")
        episode_window.geometry("800x600")
        input_last_read(n_code, episode[0])

        # Create a scrolled text widget to display the episode content
        scrolled_text = scrolledtext.ScrolledText(episode_window, wrap=tk.WORD, font=(set_font, novel_fontsize))
        scrolled_text.pack(fill=tk.BOTH, expand=True)

        # Show the initial episode content
        show_episode(episode)

        # Bind the left and right arrow keys to navigate episodes
        episode_window.bind("<Right>", next_episode)
        episode_window.bind("<Left>", previous_episode)

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
            novel_fontsize = size_var.get()

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

        apply_button = ttk.Button(setting_frame, text="適用", command=apply_settings)
        apply_button.grid(row=3, column=0, columnspan=2, pady=10)


    def show_input_screen():
        input_window = tk.Toplevel()
        input_window.title("入力画面")
        input_window.geometry("500x300")

        input_label = tk.Label(input_window, text="")
        input_label.pack(pady=10)

        input_text = tk.Text(input_window, height=10, width=50)
        input_text.pack(pady=5)
        #update--single--re_all
        def send_input(event=None):
            user_input = input_text.get("1.0", tk.END).strip()
            print(f"User input: {user_input}")
            if user_input == "exit":
                root.quit()
            elif "update" in user_input:
                user_input = user_input.split("update")
                if "--all" in user_input[1]:
                    update_all_novels(main_shinchaku)
                elif "--single" in user_input[1]:
                    user_input = user_input[1].split("--single")
                    if "--re_all" in user_input[1]:
                        if "--n" in user_input[1]:
                            ncode = user_input[1].split("--")[1].strip()
                            episodes = episode_getter(ncode)
                            for episode in episodes:
                                new_episode(ncode, episode[0], episode[2], episode[3])
                            update_total_episodes_single(ncode)
                            print(f"All episodes for novel {ncode} have been re-fetched.")
                            input_label.config(text=f"User input: {user_input}")
                            input_text.delete("1.0", tk.END)
                        else:
                            print("Please provide an ncode to update.")
                            input_label.config(text=f"User input: {user_input}")
                            input_text.delete("1.0", tk.END)
                    elif "--get_lost" in user_input[1]:
                        if "--n" in user_input[1]:
                            ncode = user_input[1].split("--")[1].strip()
                            episodes = episode_getter(ncode)
                            episode_numbers = [int(episode[0]) for episode in episodes]
                            max_episode = max(episode_numbers)
                            missing_episodes = [i for i in range(1, max_episode + 1) if i not in episode_numbers]
                            for episode_no in missing_episodes:
                                new_episode(ncode, episode_no, None, None)
                            update_total_episodes_single(ncode)
                            print(f"Missing episodes for novel {ncode} have been updated.")
                            input_label.config(text=f"User input: {user_input}")
                            input_text.delete("1.0", tk.END)

                        else:
                            print("Please provide an ncode to update.")
                            input_label.config(text=f"User input: {user_input}")
                            input_text.delete("1.0", tk.END)
                    else:
                        print("Invalid command.")
                        input_label.config(text=f"User input: {user_input}")
                        input_text.delete("1.0", tk.END)
                else:
                    print("Invalid command.")
                    input_label.config(text=f"User input: {user_input}")
                    input_text.delete("1.0", tk.END)
            elif "n" in user_input:
                ncode = user_input
                input_label.config(text= "ncode:"+ncode +"title:"+main_sehelf[int(ncode)][1])
            else:
                input_label.config(text=f"User input: {user_input}")
                input_text.delete("1.0", tk.END)



        def exit_input():
            input_window.destroy()

        exit_button = tk.Button(input_window, text="終了", command=exit_input)
        exit_button.pack(pady=10)
        input_text.bind("<Return>", send_input)



    def show_updated_novels():
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
            {"title": f"更新", "text": f"{row[1]}", "n_code": row[0],"ep_no":row[2], "gen_all_no":row[3],"rating":row[4]}
            for row in main_shinchaku
        ]
        scroll_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        scroll_canvas.configure(yscrollcommand=scrollbar.set)

        scroll_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Add the "一括更新" button at the top
        update_all_button = ttk.Button(scrollable_frame, text="一括更新", command=lambda: update_all_novels(main_shinchaku))
        update_all_button.pack(fill="x", pady=2)

        # Display each updated novel's title
        for data in buttons_data:
            frame = tk.Frame(scrollable_frame, bg="#F0F0F0")
            frame.pack(fill="x", pady=2)

            # Title label
            title_label = tk.Label(frame, text=data["text"], bg="#F0F0F0", anchor="w")
            title_label.pack(side="left", padx=5, fill="x", expand=True)

            # Bind click event to the label
            title_label.bind("<Button-1>", lambda e, n_code=data["n_code"],ep_no=data["ep_no"],gen_all_no=data["gen_all_no"],rating=data["rating"]: update_novel(e, n_code,ep_no,gen_all_no,rating))

    def update_all_novels(shinchaku_novels):
        n=len(shinchaku_novels)
        for row in shinchaku_novels:
            n=-1
            print(f"update_novel{row[0]}({n}-{len(shinchaku_novels)})(rating:{row[4]})")
            new_episode(row[0], row[2], row[3], row[4])
            update_total_episodes_single(row[0])
            print(f"update_novel{row[0]}()")
        shinchaku_ep, main_shinchaku, shinchaku_novel = shinchaku_checker()
        header_label.config(text=f"新着情報\n新着{shinchaku_novel}件,{shinchaku_ep}話")
        show_updated_novels()
        print("All eligible novels have been updated.")
        print("All eligible novels have been updated.")

    def update_novel(e, n_code, episode_no, general_all_no, rating):
        # Implement the logic for updating all novels
        new_episode(n_code, episode_no, general_all_no, rating)
        print(f"update_novel{n_code}")
        update_total_episodes_single(n_code)
        shinchaku_ep, main_shinchaku, shinchaku_novel = shinchaku_checker()
        header_label.config(text=f"新着情報\n新着{shinchaku_novel}件,{shinchaku_ep}話")
        show_novel_list()
        show_updated_novels()  # Re-draw the updated novels list



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

    # アプリの起動
    root.bind('<Command-@>', lambda event: show_input_screen())
    root.mainloop()

    #

# スクリプトが直接実行された場合にmain()を呼び出す
if __name__ == "__main__":
    dell_dl()
    del_yml()
    main_sehelf = shelf_maker()
    last_read_novel,last_read_epno = get_last_read(main_sehelf)
    set_font, novel_fontsize, bg_color = load_conf()
    db_update()
    shinchaku_ep, main_shinchaku,shinchaku_novel = shinchaku_checker()

    main()