"""
設定画面のUIコンポーネント
"""
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser
import tkinter.font as tkFont
from app.utils.logger_manager import get_logger

# ロガーの設定
logger = get_logger('SettingsPanel')


class SettingsPanel(ttk.Frame):
    """設定画面のビュークラス"""

    def __init__(self, parent, settings_manager, on_change_callback):
        """
        初期化

        Args:
            parent: 親ウィジェット
            settings_manager: 設定マネージャ
            on_change_callback: 設定変更時のコールバック関数
        """
        super().__init__(parent)
        self.parent = parent
        self.settings_manager = settings_manager
        self.on_change_callback = on_change_callback

        # UIコンポーネント
        self.font_dropdown = None
        self.size_entry = None
        self.bg_entry = None
        self.bg_preview = None

        # UIの初期化
        self.init_ui()

    def init_ui(self):
        """UIコンポーネントの初期化"""
        # 見出し
        header_label = tk.Label(
            self,
            text="表示設定",
            font=("", 14, "bold"),
            bg="#F0F0F0"
        )
        header_label.pack(pady=10)

        # 設定用のフレーム
        setting_frame = tk.Frame(self, bg="#F0F0F0")
        setting_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # フォント選択
        font_label = tk.Label(setting_frame, text="フォント:", bg="#F0F0F0", anchor="w")
        font_label.grid(row=0, column=0, sticky="w", pady=5)

        self.font_var = tk.StringVar()
        self.font_dropdown = ttk.Combobox(setting_frame, textvariable=self.font_var, values=sorted(tkFont.families()))
        self.font_dropdown.grid(row=0, column=1, sticky="ew", pady=5)

        # フォントサイズ
        size_label = tk.Label(setting_frame, text="文字サイズ:", bg="#F0F0F0", anchor="w")
        size_label.grid(row=1, column=0, sticky="w", pady=5)

        self.size_var = tk.IntVar()
        self.size_entry = tk.Spinbox(setting_frame, textvariable=self.size_var, from_=8, to=32, increment=1, width=5)
        self.size_entry.grid(row=1, column=1, sticky="w", pady=5)

        # 背景色
        bg_label = tk.Label(setting_frame, text="背景色:", bg="#F0F0F0", anchor="w")
        bg_label.grid(row=2, column=0, sticky="w", pady=5)

        bg_frame = tk.Frame(setting_frame, bg="#F0F0F0")
        bg_frame.grid(row=2, column=1, sticky="ew", pady=5)

        self.bg_var = tk.StringVar()
        self.bg_entry = tk.Entry(bg_frame, textvariable=self.bg_var, width=10)
        self.bg_entry.pack(side="left", padx=(0, 5))

        # 色選択ボタン
        color_button = ttk.Button(bg_frame, text="選択", command=self.choose_color)
        color_button.pack(side="left")

        # 色プレビュー
        self.bg_preview = tk.Frame(bg_frame, width=20, height=20, relief="solid", borderwidth=1)
        self.bg_preview.pack(side="left", padx=5)

        # 適用ボタン
        apply_button = ttk.Button(setting_frame, text="適用", command=self.apply_settings)
        apply_button.grid(row=3, column=0, columnspan=2, pady=10)

        # 設定グリッドの列の重みを設定
        setting_frame.columnconfigure(1, weight=1)

    def show_settings(self, font_name, font_size, bg_color):
        """
        現在の設定を表示

        Args:
            font_name: フォント名
            font_size: フォントサイズ
            bg_color: 背景色
        """
        # 値をセット
        self.font_var.set(font_name)
        self.size_var.set(font_size)
        self.bg_var.set(bg_color)

        # 背景色プレビューを更新
        self.bg_preview.config(bg=bg_color)

    def choose_color(self):
        """カラーピッカーを表示して背景色を選択"""
        color = colorchooser.askcolor(initialcolor=self.bg_var.get())
        if color[1]:  # [1]はカラーコード (#RRGGBB)
            self.bg_var.set(color[1])
            self.bg_preview.config(bg=color[1])

    def apply_settings(self):
        """設定を適用する"""
        try:
            # 入力値を取得
            font_name = self.font_var.get()
            font_size = self.size_var.get()
            bg_color = self.bg_var.get()

            # 入力値の検証
            if not font_name:
                messagebox.showerror("エラー", "フォントを選択してください")
                return

            if font_size < 8 or font_size > 32:
                messagebox.showerror("エラー", "文字サイズは8から32の間で指定してください")
                return

            # 色形式の検証（#で始まる6桁の16進数）
            if not (bg_color.startswith('#') and len(bg_color) == 7):
                messagebox.showerror("エラー", "背景色は#FFFFFFのような形式で指定してください")
                return

            # 設定を保存
            if self.settings_manager.save_settings(font_name, font_size, bg_color):
                # コールバック関数を呼び出す
                if self.on_change_callback:
                    self.on_change_callback(font_name, font_size, bg_color)

                messagebox.showinfo("設定", "設定が適用されました")
            else:
                messagebox.showerror("エラー", "設定の保存に失敗しました")

        except Exception as e:
            logger.error(f"設定適用エラー: {e}")
            messagebox.showerror("エラー", f"設定の適用中にエラーが発生しました: {e}")