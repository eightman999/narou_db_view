import sqlite3
import threading
from datetime import datetime
from config import DATABASE_PATH
from utils.logger_manager import get_logger

# ロガーの設定
logger = get_logger('DatabaseHandler')


class DatabaseHandler:
    """
    SQLiteデータベース操作を集約して管理するクラス
    マルチスレッド環境での安全な操作を提供します
    """

    _instance = None
    _lock = threading.RLock()  # 再入可能ロックを使用

    def __new__(cls):
        """シングルトンパターンを実装してインスタンスを一つだけ作成"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DatabaseHandler, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        """初期化メソッド（シングルトンなので一度だけ呼ばれる）"""
        if self._initialized:
            return

        self.db_path = DATABASE_PATH
        self._connection_pool = {}  # スレッドごとのコネクション管理用ディクショナリ
        self._initialized = True
        logger.info("DatabaseHandlerが初期化されました")

    def get_connection(self):
        """
        現在のスレッド用のデータベース接続を取得
        各スレッドごとに別々の接続を持つことでスレッドセーフに
        """
        thread_id = threading.get_ident()

        if thread_id not in self._connection_pool:
            conn = sqlite3.connect(self.db_path)
            # WALモードを使用することでパフォーマンスとスレッドセーフ性を両立
            conn.execute('PRAGMA journal_mode=WAL')
            # テキストをUTF-8としてエンコード
            conn.text_factory = str
            self._connection_pool[thread_id] = conn
            logger.debug(f"スレッド {thread_id} に新しいDB接続を作成")

        return self._connection_pool[thread_id]

    def close_all_connections(self):
        """
        全てのデータベース接続を閉じる
        アプリケーション終了時などに呼び出す
        """
        with self._lock:
            for thread_id, conn in self._connection_pool.items():
                conn.close()
                logger.debug(f"スレッド {thread_id} のDB接続を閉じました")
            self._connection_pool.clear()
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

    def execute_many(self, query, params_list):
        """
        複数のパラメータセットに対して同じクエリを実行

        Args:
            query (str): 実行するSQLクエリ
            params_list (list): パラメータのリスト

        Returns:
            int: 影響を受けた行数
        """
        with self._lock:
            conn = self.get_connection()
            cursor = conn.cursor()

            try:
                cursor.executemany(query, params_list)
                conn.commit()
                return cursor.rowcount

            except sqlite3.Error as e:
                logger.error(f"executemanyエラー: {e}, クエリ: {query}")
                conn.rollback()
                raise

    # 以下、アプリケーション固有のデータベース操作メソッド

    def get_all_novels(self):
        """
        全ての小説情報を取得

        Returns:
            list: 小説情報のリスト
        """
        query = 'SELECT * FROM novels_descs'
        return self.execute_query(query, fetch=True)

    def get_novel_by_ncode(self, ncode):
        """
        指定されたncodeの小説情報を取得

        Args:
            ncode (str): 検索する小説のコード

        Returns:
            tuple: 小説の情報
        """
        query = 'SELECT * FROM novels_descs WHERE n_code = ?'
        return self.execute_query(query, (ncode,), fetch=True, fetch_all=False)

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
        ORDER BY episode_no
        '''
        return self.execute_query(query, (ncode,), fetch=True)

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
        return self.execute_query(query, fetch=True, fetch_all=False)

    def update_last_read(self, ncode, episode_no):
        """
        最後に読んだ小説情報を更新

        Args:
            ncode (str): 小説コード
            episode_no (int): エピソード番号
        """
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
            query = 'SELECT episode_no FROM episodes WHERE ncode = ?'
            episode_nos = self.execute_query(query, (ncode,), fetch=True)

            if not episode_nos:
                max_episode_no = 0
            else:
                max_episode_no = max(int(ep[0]) for ep in episode_nos)

            update_query = 'UPDATE novels_descs SET total_ep = ? WHERE n_code = ?'
            self.execute_query(update_query, (max_episode_no, ncode))
            logger.info(f"小説 {ncode} の総エピソード数を {max_episode_no} に更新しました")
        else:
            # 全ての小説の総エピソード数を更新
            query = 'SELECT n_code FROM novels_descs'
            ncodes = self.execute_query(query, fetch=True)

            for ncode_tuple in ncodes:
                self.update_total_episodes(ncode_tuple[0])

    def insert_episode(self, ncode, episode_no, body, title):
        """
        エピソードをデータベースに挿入

        Args:
            ncode (str): 小説コード
            episode_no (int): エピソード番号
            body (str): エピソード本文
            title (str): エピソードタイトル
        """
        query = '''
        INSERT INTO episodes (ncode, episode_no, body, e_title)
        VALUES (?, ?, ?, ?)
        '''
        self.execute_query(query, (ncode, episode_no, body, title))

    def get_novels_needing_update(self):
        """
        更新が必要な小説のリストを取得

        Returns:
            list: 更新が必要な小説情報のリスト [(ncode, total_ep, general_all_no, rating), ...]
        """
        query = "SELECT n_code, total_ep, general_all_no, rating FROM novels_descs"
        novels = self.execute_query(query, fetch=True)

        needs_update = []
        for n_code, total_ep, general_all_no, rating in novels:
            if total_ep is None:
                total_ep = 0
            if general_all_no is None:
                continue

            if total_ep < general_all_no:
                # タイトルも取得
                title_query = "SELECT title FROM novels_descs WHERE n_code = ?"
                title = self.execute_query(title_query, (n_code,), fetch=True, fetch_all=False)
                title = title[0] if title else "不明"

                needs_update.append((n_code, title, total_ep, general_all_no, rating))

        return needs_update

    def remove_duplicate_episodes(self):
        """
        重複するエピソードを削除し、各エピソードごとに最も長い本文を持つものだけを残す
        """
        # 一時テーブルを作成して、保持するエントリを格納
        create_temp_table_query = '''
        CREATE TEMPORARY TABLE episodes_to_keep AS
        SELECT e1.*
        FROM episodes e1
        JOIN (
            SELECT ncode, episode_no, MAX(LENGTH(body)) as max_length
            FROM episodes
            GROUP BY ncode, episode_no
        ) e2
        ON e1.ncode = e2.ncode AND e1.episode_no = e2.episode_no AND LENGTH(e1.body) = e2.max_length
        '''

        # 元のテーブルから全てのエントリを削除
        delete_query = 'DELETE FROM episodes'

        # 一時テーブルから保持するエントリを元のテーブルに挿入
        insert_query = 'INSERT INTO episodes SELECT * FROM episodes_to_keep'

        # 一時テーブルを削除
        drop_temp_table_query = 'DROP TABLE episodes_to_keep'

        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(create_temp_table_query)
            cursor.execute(delete_query)
            cursor.execute(insert_query)
            cursor.execute(drop_temp_table_query)
            conn.commit()
            logger.info("重複エピソードの削除が完了しました")
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"重複エピソード削除エラー: {e}")
            raise

    def clean_ncode_format(self):
        """
        ncodeフィールドからb'と'を削除する
        """
        # すべてのncodeを取得
        query = 'SELECT ncode FROM episodes'
        ncodes = self.execute_query(query, fetch=True)

        for ncode_tuple in ncodes:
            ncode = ncode_tuple[0]
            cleaned_ncode = ncode.replace("b'", "").replace("'", "")

            if ncode != cleaned_ncode:
                update_query = 'UPDATE episodes SET ncode = ? WHERE ncode = ?'
                self.execute_query(update_query, (cleaned_ncode, ncode))

        logger.info("ncodeフォーマットのクリーニングが完了しました")

    def remove_invalid_episodes(self):
        """
        無効または欠落しているコンテンツを持つエピソードを削除
        """
        query = '''
        DELETE FROM episodes
        WHERE e_title IS NULL OR e_title = '' OR body IS NULL OR body = '' OR body = 'No content found in the specified div.'
        '''
        count = self.execute_query(query)
        logger.info(f"{count}件の無効なエピソードを削除しました")

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
        general_all_no = self.execute_query(novel_query, (ncode,), fetch=True, fetch_all=False)

        if not general_all_no or not general_all_no[0]:
            logger.warning(f"小説 {ncode} の general_all_no が設定されていません")
            return []

        general_all_no = general_all_no[0]

        # 存在するエピソード番号を取得
        episode_query = 'SELECT episode_no FROM episodes WHERE ncode = ? ORDER BY episode_no'
        episodes = self.execute_query(episode_query, (ncode,), fetch=True)

        if not episodes:
            # 全てのエピソードが欠落
            return list(range(1, general_all_no + 1))

        episode_numbers = [int(ep[0]) for ep in episodes]

        # 欠落しているエピソード番号を見つける
        missing_episodes = [i for i in range(1, general_all_no + 1) if i not in episode_numbers]

        return missing_episodes