"""
データベース操作を管理するモジュール
"""
import sqlite3
import threading
from datetime import datetime
from config import DATABASE_PATH
from utils.logger_manager import get_logger

# ロガーの設定
logger = get_logger('DatabaseManager')


class DatabaseManager:
    """データベース操作を管理するクラス"""

    def __init__(self):
        """初期化"""
        self.db_path = DATABASE_PATH
        self._connection_pool = {}  # スレッドごとのコネクション管理用ディクショナリ
        self._lock = threading.RLock()  # 再入可能ロック
        self._read_connection_pool = {}  # 読み取り専用接続プール

    def connect(self):
        """データベースに接続"""
        # 既に接続済みの場合は何もしない
        if threading.get_ident() in self._connection_pool:
            return

        with self._lock:
            conn = sqlite3.connect(self.db_path)
            # WALモードを使用することでパフォーマンスとスレッドセーフ性を両立
            conn.execute('PRAGMA journal_mode=WAL')
            # テキストをUTF-8としてエンコード
            conn.text_factory = str
            self._connection_pool[threading.get_ident()] = conn
            logger.debug(f"スレッド {threading.get_ident()} に新しいDB接続を作成")

    def get_connection(self):
        """現在のスレッド用のデータベース接続を取得"""
        thread_id = threading.get_ident()

        if thread_id not in self._connection_pool:
            self.connect()

        return self._connection_pool[thread_id]

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
            logger.debug(f"スレッド {thread_id} に新しい読み取り専用DB接続を作成")

        return self._read_connection_pool[thread_id]

    def execute_query(self, query, params=None, fetch=False, fetch_all=True, commit=True):
        """
        SQLクエリを実行し、必要に応じて結果を返す汎用メソッド

        Args:
            query (str): 実行するSQLクエリ
            params (tuple|list|dict, optional): クエリパラメータ
            fetch (bool): 結果を取得するかどうか
            fetch_all (bool): 全ての結果を取得するか、一行だけ取得するか
            commit (bool): 変更をコミットするかどうか

        Returns:
            取得された結果（fetch=Trueの場合）
        """
        with self._lock:
            conn = self.get_connection()
            cursor = conn.cursor()

            try:
                if params is None:
                    cursor.execute(query)
                else:
                    cursor.execute(query, params)

                if commit:
                    conn.commit()

                if fetch:
                    if fetch_all:
                        return cursor.fetchall()
                    else:
                        return cursor.fetchone()

                return cursor.rowcount  # 影響を受けた行数を返す

            except sqlite3.Error as e:
                logger.error(f"DB操作エラー: {e}, クエリ: {query}, パラメータ: {params}")
                if commit:  # エラーが発生したらロールバック
                    conn.rollback()
                raise

    def execute_read_query(self, query, params=None, fetch_all=True):
        """
        読み取り専用クエリの実行（ロックなし）

        Args:
            query (str): 実行するSQLクエリ
            params (tuple|list|dict, optional): クエリパラメータ
            fetch_all (bool): 全ての結果を取得するか、一行だけ取得するか

        Returns:
            list/tuple: クエリ結果。fetch_all=True なら全行のリスト、False なら1行
        """
        conn = self.get_read_connection()
        cursor = conn.cursor()

        try:
            if params is None:
                cursor.execute(query)
            else:
                cursor.execute(query, params)

            if fetch_all:
                return cursor.fetchall()
            else:
                return cursor.fetchone()

        except sqlite3.Error as e:
            logger.error(f"読み取りクエリエラー: {e}, クエリ: {query}")
            raise