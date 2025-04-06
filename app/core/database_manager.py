"""
データベース操作を管理するモジュール
"""
import sqlite3
import threading
from config import DATABASE_PATH
from app.utils.logger_manager import get_logger
from app.database.db_handler import DatabaseHandler

# ロガーの設定
logger = get_logger('DatabaseManager')


class DatabaseManager:
    """データベース操作を管理するクラス
    db_handler.pyのDatabaseHandlerをラップして使用します
    """

    def __init__(self):
        """初期化"""
        self.db_path = DATABASE_PATH
        self.db_handler = DatabaseHandler()
        self._lock = threading.RLock()  # 再入可能ロック

    def connect(self):
        """データベースに接続"""
        # DatabaseHandler内部で接続が処理されるため、
        # ここでは何もする必要がない
        pass

    def close(self):
        """
        全てのデータベース接続を閉じる
        アプリケーション終了時に呼び出す
        """
        try:
            self.db_handler.close_all_connections()
            logger.info("全てのデータベース接続を閉じました")
        except Exception as e:
            logger.error(f"データベース接続を閉じる際にエラーが発生しました: {e}")

    # DatabaseHandlerのメソッドを委譲
    def get_all_novels(self):
        """
        全ての小説情報を取得
        Returns:
            list: 小説情報のリスト
        """
        return self.db_handler.get_all_novels()

    def get_novel_by_ncode(self, ncode):
        """
        指定されたncodeの小説情報を取得
        Args:
            ncode (str): 検索する小説のコード
        Returns:
            tuple: 小説の情報
        """
        return self.db_handler.get_novel_by_ncode(ncode)

    def get_episodes_by_ncode(self, ncode):
        """
        指定されたncodeの全エピソードを取得
        Args:
            ncode (str): 小説コード
        Returns:
            list: エピソード情報のリスト
        """
        return self.db_handler.get_episodes_by_ncode(ncode)

    def get_last_read_novel(self):
        """
        最後に読んだ小説の情報を取得
        Returns:
            tuple: (ncode, episode_no)
        """
        return self.db_handler.get_last_read_novel()

    def update_last_read(self, ncode, episode_no):
        """
        最後に読んだ小説情報を更新
        Args:
            ncode (str): 小説コード
            episode_no (int): エピソード番号
        """
        self.db_handler.update_last_read(ncode, episode_no)

    def update_total_episodes(self, ncode=None):
        """
        小説の総エピソード数を更新
        Args:
            ncode (str, optional): 更新する小説のコード。Noneの場合は全ての小説を更新
        """
        self.db_handler.update_total_episodes(ncode)

    def get_novels_needing_update(self):
        """
        更新が必要な小説のリストを取得
        Returns:
            list: 更新が必要な小説情報のリスト [(ncode, title, total_ep, general_all_no, rating), ...]
        """
        return self.db_handler.get_novels_needing_update()

    def find_missing_episodes(self, ncode):
        """
        指定された小説の欠落しているエピソードを見つける
        Args:
            ncode (str): 小説コード
        Returns:
            list: 欠落しているエピソード番号のリスト
        """
        return self.db_handler.find_missing_episodes(ncode)

    def insert_episode(self, ncode, episode_no, body, title):
        """
        エピソードをデータベースに挿入（重複チェック付き）
        Args:
            ncode (str): 小説コード
            episode_no (int): エピソード番号
            body (str): エピソード本文
            title (str): エピソードタイトル
        """
        self.db_handler.insert_episode(ncode, episode_no, body, title)

    def execute_query(self, query, params=None, fetch=False, fetch_all=True, commit=True):
        """
        SQLクエリを実行し、必要に応じて結果を返す汎用メソッド
        """
        return self.db_handler.execute_query(query, params, fetch, fetch_all, commit)