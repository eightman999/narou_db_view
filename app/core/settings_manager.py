"""
アプリケーション設定を管理するモジュール
"""
import os
import configparser
from app.utils.logger_manager import get_logger

# ロガーの設定
logger = get_logger('SettingsManager')


class SettingsManager:
    """アプリケーション設定を管理するクラス"""

    def __init__(self, config_file='settings.ini'):
        """
        初期化

        Args:
            config_file (str): 設定ファイルのパス
        """
        self.config_file = config_file

        # デフォルト設定
        self.default_font = "YuKyokasho Yoko"
        self.default_fontsize = 14
        self.default_backgroundcolor = "#FFFFFF"

    def load_settings(self):
        """
        設定ファイルを読み込む

        Returns:
            tuple: (font, fontsize, backgroundcolor)
        """
        config = configparser.ConfigParser()

        # デフォルト設定
        font = self.default_font
        fontsize = self.default_fontsize
        backgroundcolor = self.default_backgroundcolor

        # 設定ファイルが存在するか確認
        if os.path.exists(self.config_file):
            config.read(self.config_file)

        # Settings セクションが存在しない場合は作成
        if not config.has_section('Settings'):
            config.add_section('Settings')
            config.set('Settings', 'font', font)
            config.set('Settings', 'fontsize', str(fontsize))
            config.set('Settings', 'backgroundcolor', backgroundcolor)

            # 設定を保存
            with open(self.config_file, 'w') as f:
                config.write(f)
        else:
            # 設定を読み込み
            try:
                font = config.get('Settings', 'font')
                fontsize = config.getint('Settings', 'fontsize')
                backgroundcolor = config.get('Settings', 'backgroundcolor')
            except (configparser.NoOptionError, ValueError):
                # オプションが存在しないか、値の変換に失敗した場合はデフォルト値を使用
                if not config.has_option('Settings', 'font'):
                    config.set('Settings', 'font', self.default_font)
                    font = self.default_font
                else:
                    font = config.get('Settings', 'font')

                if not config.has_option('Settings', 'fontsize'):
                    config.set('Settings', 'fontsize', str(self.default_fontsize))
                    fontsize = self.default_fontsize
                else:
                    try:
                        fontsize = config.getint('Settings', 'fontsize')
                    except ValueError:
                        config.set('Settings', 'fontsize', str(self.default_fontsize))
                        fontsize = self.default_fontsize

                if not config.has_option('Settings', 'backgroundcolor'):
                    config.set('Settings', 'backgroundcolor', self.default_backgroundcolor)
                    backgroundcolor = self.default_backgroundcolor
                else:
                    backgroundcolor = config.get('Settings', 'backgroundcolor')

                # 変更された設定を保存
                with open(self.config_file, 'w') as f:
                    config.write(f)

        logger.info(f"設定を読み込みました: font={font}, fontsize={fontsize}, backgroundcolor={backgroundcolor}")
        return font, fontsize, backgroundcolor

    def save_settings(self, font, fontsize, backgroundcolor):
        """
        設定を保存する

        Args:
            font (str): フォント名
            fontsize (int): フォントサイズ
            backgroundcolor (str): 背景色

        Returns:
            bool: 保存が成功したかどうか
        """
        config = configparser.ConfigParser()

        # 既存の設定ファイルを読み込む
        if os.path.exists(self.config_file):
            config.read(self.config_file)

        # Settings セクションが存在しない場合は作成
        if not config.has_section('Settings'):
            config.add_section('Settings')

        # 設定を更新
        config.set('Settings', 'font', font)
        config.set('Settings', 'fontsize', str(fontsize))
        config.set('Settings', 'backgroundcolor', backgroundcolor)

        try:
            # 設定を保存
            with open(self.config_file, 'w') as f:
                config.write(f)

            logger.info(f"設定を保存しました: font={font}, fontsize={fontsize}, backgroundcolor={backgroundcolor}")
            return True

        except Exception as e:
            logger.error(f"設定の保存に失敗しました: {e}")
            return False