"""
データベース操作を管理するモジュール
"""
import sqlite3
import threading
from config import DATABASE_PATH
from app.utils.logger_manager import get_logger

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

    def close(self):
        """
        全てのデータベース接続を閉じる
        アプリケーション終了時に呼び出す
        """
        with self._lock:
            # 通常の接続プールを閉じる
            for thread_id, conn in list(self._connection_pool.items()):
                try:
                    conn.close()
                    logger.debug(f"スレッド {thread_id} のDB接続を閉じました")
                except Exception as e:
                    logger.error(f"DB接続を閉じる際にエラーが発生しました: {e}")
            self._connection_pool.clear()

            # 読み取り専用接続プールを閉じる
            for thread_id, conn in list(self._read_connection_pool.items()):
                try:
                    conn.close()
                    logger.debug(f"スレッド {thread_id} の読み取り専用DB接続を閉じました")
                except Exception as e:
                    logger.error(f"読み取り専用DB接続を閉じる際にエラーが発生しました: {e}")
            self._read_connection_pool.clear()

            logger.info("全てのデータベース接続を閉じました")

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

    # ここから追加するメソッド

    def get_all_novels(self):
        """
        全ての小説情報を取得

        Returns:
            list: 小説情報のリスト
        """
        query = 'SELECT * FROM novels_descs'
        return self.execute_read_query(query)

    def get_novel_by_ncode(self, ncode):
        """
        指定されたncodeの小説情報を取得

        Args:
            ncode (str): 検索する小説のコード

        Returns:
            tuple: 小説の情報
        """
        query = 'SELECT * FROM novels_descs WHERE n_code = ?'
        return self.execute_read_query(query, (ncode,), fetch_all=False)

    def get_episodes_by_ncode(self, ncode):
        """
        指定されたncodeの全エピソードを取得

        Args:
            ncode (str): 小説コード

        Returns:
            list: エピソード情報のリスト
        """
        query = '''
        SELECT episode_no, e_title, body
        FROM episodes
        WHERE ncode = ?
        ORDER BY CAST(episode_no AS INTEGER)
        '''
        return self.execute_read_query(query, (ncode,))

    def get_last_read_novel(self):
        """
        最後に読んだ小説の情報を取得

        Returns:
            tuple: (ncode, episode_no)
        """
        query = '''
        SELECT ncode, episode_no
        FROM rast_read_novel
        ORDER BY date DESC
        LIMIT 1
        '''
        return self.execute_read_query(query, fetch_all=False)

    def update_last_read(self, ncode, episode_no):
        """
        最後に読んだ小説情報を更新

        Args:
            ncode (str): 小説コード
            episode_no (int): エピソード番号
        """
        from datetime import datetime
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        query = '''
        INSERT INTO rast_read_novel (ncode, date, episode_no)
        VALUES (?, ?, ?)
        '''
        self.execute_query(query, (ncode, current_time, episode_no))

    def update_total_episodes(self, ncode=None):
        """
        小説の総エピソード数を更新

        Args:
            ncode (str, optional): 更新する小説のコード。Noneの場合は全ての小説を更新
        """
        if ncode:
            # 特定の小説の総エピソード数を更新
            query = 'SELECT MAX(CAST(episode_no AS INTEGER)) FROM episodes WHERE ncode = ?'
            result = self.execute_read_query(query, (ncode,), fetch_all=False)

            max_episode_no = result[0] if result and result[0] is not None else 0

            update_query = 'UPDATE novels_descs SET total_ep = ? WHERE n_code = ?'
            self.execute_query(update_query, (max_episode_no, ncode))
            logger.info(f"小説 {ncode} の総エピソード数を {max_episode_no} に更新しました")
        else:
            # 全ての小説の総エピソード数を更新
            query = 'SELECT n_code FROM novels_descs'
            ncodes = self.execute_read_query(query)

            for ncode_tuple in ncodes:
                self.update_total_episodes(ncode_tuple[0])

    def get_novels_needing_update(self):
        """
        更新が必要な小説のリストを取得

        Returns:
            list: 更新が必要な小説情報のリスト [(ncode, title, total_ep, general_all_no, rating), ...]
        """
        # 必要なデータを全て取得
        query = '''
        SELECT n.n_code, n.title, 
               COALESCE(n.total_ep, 0) as total_ep, 
               n.general_all_no, n.rating
        FROM novels_descs n
        WHERE n.general_all_no IS NOT NULL 
          AND (n.total_ep IS NULL OR n.total_ep < n.general_all_no)
        '''
        results = self.execute_read_query(query)

        needs_update = []
        for n_code, title, total_ep, general_all_no, rating in results:
            needs_update.append((n_code, title, total_ep, general_all_no, rating))

        return needs_update

    def find_missing_episodes(self, ncode):
        """
        指定された小説の欠落しているエピソードを見つける

        Args:
            ncode (str): 小説コード

        Returns:
            list: 欠落しているエピソード番号のリスト
        """
        # 小説の総エピソード数を取得
        novel_query = 'SELECT general_all_no FROM novels_descs WHERE n_code = ?'
        general_all_no_result = self.execute_read_query(novel_query, (ncode,), fetch_all=False)

        if not general_all_no_result or not general_all_no_result[0]:
            logger.warning(f"小説 {ncode} の general_all_no が設定されていません")
            return []

        general_all_no = general_all_no_result[0]

        # 存在するエピソード番号を取得
        episode_query = 'SELECT episode_no FROM episodes WHERE ncode = ?'
        existing_episodes = self.execute_read_query(episode_query, (ncode,))

        # int型に変換
        existing_episode_numbers = set(int(ep[0]) for ep in existing_episodes)

        # 欠落しているエピソードを計算
        all_episode_numbers = set(range(1, general_all_no + 1))
        missing_episodes = sorted(list(all_episode_numbers - existing_episode_numbers))

        return missing_episodes

    def insert_episode(self, ncode, episode_no, body, title):
        """
        エピソードをデータベースに挿入（重複チェック付き）

        Args:
            ncode (str): 小説コード
            episode_no (int): エピソード番号
            body (str): エピソード本文
            title (str): エピソードタイトル
        """
        # 既存のエピソードをチェック
        check_query = 'SELECT rowid FROM episodes WHERE ncode = ? AND episode_no = ?'
        existing = self.execute_read_query(check_query, (ncode, episode_no), fetch_all=False)

        if existing:
            # 既存のエピソードを更新
            update_query = '''
            UPDATE episodes SET body = ?, e_title = ?
            WHERE ncode = ? AND episode_no = ?
            '''
            self.execute_query(update_query, (body, title, ncode, episode_no))
        else:
            # 新規エピソードを挿入
            insert_query = '''
            INSERT INTO episodes (ncode, episode_no, body, e_title)
            VALUES (?, ?, ?, ?)
            '''
            self.execute_query(insert_query, (ncode, episode_no, body, title))