import logging
import logging.handlers
import os
import codecs
import sys
from pathlib import Path


class LoggerManager:
    """
    ロギングを統合管理するクラス
    重大度別にログファイルを生成し、各モジュールのロガーを一元管理します
    """

    _instance = None

    def __new__(cls):
        """シングルトンパターンを実装"""
        if cls._instance is None:
            cls._instance = super(LoggerManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """初期化（シングルトンなので一度だけ実行）"""
        if self._initialized:
            return

        # ログディレクトリの作成
        log_dir = Path('logs')
        log_dir.mkdir(exist_ok=True)

        # ログファイルのパス
        self.log_file_all = str(log_dir / 'log.log')
        self.log_file_info = str(log_dir / 'INFO.log')
        self.log_file_warning = str(log_dir / 'WARNING.log')
        self.log_file_error = str(log_dir / 'ERROR.log')

        # ルートロガーの設定
        self.root_logger = logging.getLogger()
        self.root_logger.setLevel(logging.DEBUG)

        # 既存のハンドラをクリア
        for handler in self.root_logger.handlers[:]:
            self.root_logger.removeHandler(handler)

        # 標準出力用ハンドラ
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        self.root_logger.addHandler(console_handler)

        # 共通のフォーマッタ
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')

        # 全ログ用ハンドラ (UTF-32)
        all_handler = self._create_file_handler(self.log_file_all, logging.DEBUG, file_formatter, 'utf-32')
        self.root_logger.addHandler(all_handler)

        # INFO以上用ハンドラ (UTF-32)
        info_handler = self._create_file_handler(self.log_file_info, logging.INFO, file_formatter, 'utf-32')
        self.root_logger.addHandler(info_handler)

        # WARNING以上用ハンドラ (UTF-32)
        warning_handler = self._create_file_handler(self.log_file_warning, logging.WARNING, file_formatter, 'utf-32')
        self.root_logger.addHandler(warning_handler)

        # ERROR以上用ハンドラ (UTF-32)
        error_handler = self._create_file_handler(self.log_file_error, logging.ERROR, file_formatter, 'utf-32')
        self.root_logger.addHandler(error_handler)

        # モジュール別ロガーの辞書
        self.loggers = {}

        self._initialized = True

        # 初期化完了ログ
        logging.info("LoggerManagerが初期化されました")

    def _create_file_handler(self, filename, level, formatter, encoding='utf-8'):
        """
        ファイルハンドラを作成

        Args:
            filename (str): ログファイル名
            level (int): ログレベル
            formatter (Formatter): フォーマッタ
            encoding (str): ファイルエンコーディング

        Returns:
            FileHandler: 設定済みのファイルハンドラ
        """
        # UTF-32エンコーディングでファイルを開く
        file_handler = logging.FileHandler(filename, encoding=encoding)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)

        # RotatingFileHandlerを使用する場合（ファイルサイズでローテーション）
        # max_bytes = 10 * 1024 * 1024  # 10MB
        # backup_count = 5
        # file_handler = logging.handlers.RotatingFileHandler(
        #     filename, maxBytes=max_bytes, backupCount=backup_count, encoding=encoding
        # )
        # file_handler.setLevel(level)
        # file_handler.setFormatter(formatter)

        return file_handler

    def get_logger(self, name):
        """
        名前付きロガーを取得

        Args:
            name (str): ロガー名（通常はモジュール名）

        Returns:
            Logger: 設定済みのロガー
        """
        if name in self.loggers:
            return self.loggers[name]

        logger = logging.getLogger(name)
        self.loggers[name] = logger
        return logger

    def shutdown(self):
        """
        ロギングシステムをシャットダウン
        アプリケーション終了時に呼び出すこと
        """
        logging.info("LoggerManagerをシャットダウンします")
        logging.shutdown()


# シングルトンインスタンスを取得する関数
def get_logger(name):
    """
    指定した名前のロガーを取得

    Args:
        name (str): ロガー名（通常はモジュール名）

    Returns:
        Logger: 設定済みのロガー
    """
    logger_manager = LoggerManager()
    return logger_manager.get_logger(name)


# 使用例
if __name__ == "__main__":
    # ロガーを取得
    logger = get_logger(__name__)

    # ログ出力のテスト
    logger.debug("これはDEBUGメッセージです")
    logger.info("これはINFOメッセージです")
    logger.warning("これはWARNINGメッセージです")
    logger.error("これはERRORメッセージです")
    logger.critical("これはCRITICALメッセージです")

    # 別のモジュール用のロガーを取得
    another_logger = get_logger("another_module")
    another_logger.info("別モジュールからのINFOメッセージです")

    # ロギングシステムをシャットダウン
    LoggerManager().shutdown()