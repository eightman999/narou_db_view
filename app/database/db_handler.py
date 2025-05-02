import os
import sqlite3
import threading
from datetime import datetime
import queue
import concurrent.futures
from config import DATABASE_PATH
from app.utils.logger_manager import get_logger

# ロガーの設定
logger = get_logger('DatabaseHandler')


class DatabaseHandler:
    """
    SQLiteデータベース操作を集約して管理するクラス
    マルチスレッド環境での安全な操作を提供します
    """

    _instance = None
    _lock = threading.RLock()  # 再入可能ロックを使用
    _connection_locks = {}  # 接続ごとのロック

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
        self._read_connection_pool = {}  # 読み取り専用コネクションプール
        self._initialized = True
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)  # 並列クエリ実行用
        self._bulk_operation_queue = queue.Queue()  # 一括操作用キュー

        # 一括操作処理スレッドを開始
        self._bulk_processing_thread = threading.Thread(target=self._process_bulk_queue, daemon=True)
        self._bulk_processing_thread.start()

        logger.info("DatabaseHandlerが初期化されました（並列処理対応版）")

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
            # キャッシュサイズを増加させてパフォーマンスを向上
            conn.execute('PRAGMA cache_size=-20000')  # 約20MBのキャッシュ
            # 同期モードを調整して書き込み速度を向上
            conn.execute('PRAGMA synchronous=NORMAL')
            # テキストをUTF-8としてエンコード
            conn.text_factory = str
            self._connection_pool[thread_id] = conn
            self._connection_locks[thread_id] = threading.Lock()
            logger.debug(f"スレッド {thread_id} に新しいDB接続を作成")

        return self._connection_pool[thread_id]

    def get_read_connection(self):
        """読み取り専用の接続を取得（並列処理のために最適化）"""
        thread_id = threading.get_ident()

        if thread_id not in self._read_connection_pool:
            conn = sqlite3.connect(self.db_path)
            # WALモードを使用
            conn.execute('PRAGMA journal_mode=WAL')
            # 読み取り専用モードでパフォーマンス向上
            conn.execute('PRAGMA query_only=ON')
            # キャッシュサイズを増加
            conn.execute('PRAGMA cache_size=-20000')
            conn.text_factory = str
            self._read_connection_pool[thread_id] = conn
            logger.debug(f"スレッド {thread_id} に読み取り専用DB接続を作成")

        return self._read_connection_pool[thread_id]

    def cleanup_wal_files(self):
        """
        WALファイルを明示的にクリーンアップ
        アプリケーション終了時に呼び出す
        """
        logger.info("WALファイルのクリーンアップを開始します")
        try:
            # 既存の接続をすべて閉じる前に新しい接続を作成
            conn = sqlite3.connect(self.db_path)

            # 完全なチェックポイントを実行（WALファイルの内容をメインDBに統合）
            conn.execute("PRAGMA wal_checkpoint(FULL)")
            logger.debug("WALチェックポイントを実行しました")

            # 通常のジャーナルモードに戻す
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.commit()
            logger.debug("ジャーナルモードをDELETEに変更しました")

            # 接続を閉じる
            conn.close()

            # .db-walと.db-shmファイルが存在する場合は削除
            wal_file = self.db_path + "-wal"
            shm_file = self.db_path + "-shm"

            if os.path.exists(wal_file):
                try:
                    os.remove(wal_file)
                    logger.info(f"WALファイル {wal_file} を削除しました")
                except OSError as e:
                    logger.warning(f"WALファイル {wal_file} の削除に失敗: {e}")

            if os.path.exists(shm_file):
                try:
                    os.remove(shm_file)
                    logger.info(f"SHMファイル {shm_file} を削除しました")
                except OSError as e:
                    logger.warning(f"SHMファイル {shm_file} の削除に失敗: {e}")

            logger.info("WALファイルのクリーンアップが完了しました")
        except Exception as e:
            logger.error(f"WALファイルのクリーンアップ中にエラーが発生しました: {e}")

    def close_all_connections(self):
        """
        全てのデータベース接続を閉じる
        アプリケーション終了時などに呼び出す
        """
        with self._lock:
            # 通常の接続プールを閉じる
            for thread_id, conn in list(self._connection_pool.items()):
                try:
                    if threading.get_ident() == thread_id:
                        conn.close()
                        logger.debug(f"スレッド {thread_id} のDB接続を閉じました")
                        del self._connection_pool[thread_id]
                except Exception as e:
                    logger.error(f"DB接続を閉じる際にエラーが発生しました: {e}")

            # 読み取り専用接続プールを閉じる
            for thread_id, conn in list(self._read_connection_pool.items()):
                try:
                    if threading.get_ident() == thread_id:
                        conn.close()
                        logger.debug(f"スレッド {thread_id} の読み取り専用DB接続を閉じました")
                        del self._read_connection_pool[thread_id]
                except Exception as e:
                    logger.error(f"読み取り専用DB接続を閉じる際にエラーが発生しました: {e}")

            # スレッドプールをシャットダウン
            self._executor.shutdown(wait=False)

            logger.info("アクセス可能なデータベース接続を閉じました")

    def shutdown(self):
        """
        データベースのシャットダウン処理
        アプリケーション終了時に呼び出す
        """
        logger.info("データベースのシャットダウンを開始します")

        # すべての接続を閉じる
        self.close_all_connections()

        # WALファイルをクリーンアップ
        self.cleanup_wal_files()

        logger.info("データベースのシャットダウンが完了しました")

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
            # キャッシュサイズを増加させてパフォーマンスを向上
            conn.execute('PRAGMA cache_size=-20000')  # 約20MBのキャッシュ
            # 同期モードを調整して書き込み速度を向上
            conn.execute('PRAGMA synchronous=NORMAL')
            # テキストをUTF-8としてエンコード
            conn.text_factory = str
            self._connection_pool[thread_id] = conn
            self._connection_locks[thread_id] = threading.Lock()
            logger.debug(f"スレッド {thread_id} に新しいDB接続を作成")

        return self._connection_pool[thread_id]

    def get_read_connection(self):
        """読み取り専用の接続を取得（並列処理のために最適化）"""
        thread_id = threading.get_ident()

        if thread_id not in self._read_connection_pool:
            conn = sqlite3.connect(self.db_path)
            # WALモードを使用
            conn.execute('PRAGMA journal_mode=WAL')
            # 読み取り専用モードでパフォーマンス向上
            conn.execute('PRAGMA query_only=ON')
            # キャッシュサイズを増加
            conn.execute('PRAGMA cache_size=-20000')
            conn.text_factory = str
            self._read_connection_pool[thread_id] = conn
            logger.debug(f"スレッド {thread_id} に読み取り専用DB接続を作成")

        return self._read_connection_pool[thread_id]

    def close_all_connections(self):
        """
        全てのデータベース接続を閉じる
        アプリケーション終了時などに呼び出す
        """
        with self._lock:
            # 通常の接続プールを閉じる
            for thread_id, conn in list(self._connection_pool.items()):
                try:
                    if threading.get_ident() == thread_id:
                        conn.close()
                        logger.debug(f"スレッド {thread_id} のDB接続を閉じました")
                        del self._connection_pool[thread_id]
                except Exception as e:
                    logger.error(f"DB接続を閉じる際にエラーが発生しました: {e}")

            # 読み取り専用接続プールを閉じる
            for thread_id, conn in list(self._read_connection_pool.items()):
                try:
                    if threading.get_ident() == thread_id:
                        conn.close()
                        logger.debug(f"スレッド {thread_id} の読み取り専用DB接続を閉じました")
                        del self._read_connection_pool[thread_id]
                except Exception as e:
                    logger.error(f"読み取り専用DB接続を閉じる際にエラーが発生しました: {e}")

            # スレッドプールをシャットダウン
            self._executor.shutdown(wait=False)

            logger.info("アクセス可能なデータベース接続を閉じました")

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
        conn = self.get_connection()
        thread_id = threading.get_ident()

        # このスレッドの接続用ロックを取得
        with self._connection_locks[thread_id]:
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
                logger.error(f"DB操作エラー: {e}, クエリ: {query}")
                if commit:  # エラーが発生したらロールバック
                    conn.rollback()
                raise

    def execute_read_query(self, query, params=None, fetch=True, fetch_all=True):
        """読み取り専用クエリの実行（最適化版）"""
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

    def execute_many(self, query, params_list):
        """
        複数のパラメータセットに対して同じクエリを実行

        Args:
            query (str): 実行するSQLクエリ
            params_list (list): パラメータのリスト

        Returns:
            int: 影響を受けた行数
        """
        conn = self.get_connection()
        thread_id = threading.get_ident()

        # このスレッドの接続用ロックを取得
        with self._connection_locks[thread_id]:
            cursor = conn.cursor()

            try:
                cursor.executemany(query, params_list)
                conn.commit()
                return cursor.rowcount

            except sqlite3.Error as e:
                logger.error(f"executemanyエラー: {e}, クエリ: {query}")
                conn.rollback()
                raise

    def execute_parallel_queries(self, queries, timeout=None):
        """
        複数のクエリを並列実行（読み取りクエリに最適）

        Args:
            queries (list): (query, params, fetch, fetch_all) の形式のタプルのリスト
            timeout (float, optional): タイムアウト秒数

        Returns:
            list: 各クエリの結果のリスト
        """
        futures = []
        for query_tuple in queries:
            if len(query_tuple) == 2:
                query, params = query_tuple
                fetch, fetch_all = True, True
            elif len(query_tuple) == 4:
                query, params, fetch, fetch_all = query_tuple
            else:
                raise ValueError("クエリタプルは2または4要素である必要があります")

            future = self._executor.submit(
                self.execute_read_query, query, params, fetch, fetch_all
            )
            futures.append(future)

        # 全てのfutureの結果を収集
        return [future.result(timeout=timeout) for future in concurrent.futures.as_completed(futures)]

    def add_bulk_operation(self, operation_type, *args):
        """
        一括処理キューに操作を追加

        Args:
            operation_type (str): 操作タイプ ('query', 'many', etc.)
            *args: 操作に必要な引数
        """
        self._bulk_operation_queue.put((operation_type, args))

    def _process_bulk_queue(self):
        """一括処理キューの処理を行うワーカースレッド"""
        while True:
            try:
                # キューから操作を取得
                operation_type, args = self._bulk_operation_queue.get(timeout=0.5)

                try:
                    if operation_type == 'query':
                        self.execute_query(*args)
                    elif operation_type == 'many':
                        self.execute_many(*args)
                    # 他の操作タイプを追加可能
                except Exception as e:
                    logger.error(f"一括処理エラー: {e}, 操作タイプ: {operation_type}")

                self._bulk_operation_queue.task_done()

            except queue.Empty:
                # タイムアウトした場合は次のループへ
                continue
            except Exception as e:
                logger.error(f"一括処理キューワーカーエラー: {e}")
                # エラーが発生しても継続して処理
                continue

    # 以下、アプリケーション固有のデータベース操作メソッド（最適化版）

    def get_all_novels(self):
        """
        全ての小説情報を取得（キャッシュ対応）

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
        指定されたncodeの全エピソードを取得（効率化版）

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
        FROM last_read_novel
        ORDER BY date DESC
        LIMIT 1
        '''
        return self.execute_read_query(query, fetch_all=False)

    def update_last_read(self, ncode, episode_no):
        """
        最後に読んだ小説情報を更新（非同期処理）

        Args:
            ncode (str): 小説コード
            episode_no (int): エピソード番号
        """
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        query = '''
        INSERT INTO last_read_novel (ncode, date, episode_no)
        VALUES (?, ?, ?)
        '''
        # 非同期で処理（UIをブロックしない）
        self.add_bulk_operation('query', query, (ncode, current_time, episode_no), False, False, True)

    def update_total_episodes(self, ncode=None):
        """
        小説の総エピソード数を更新

        Args:
            ncode (str, optional): 更新する小説のコード。Noneの場合は全ての小説を更新
        """
        if ncode:
            # 特定の小説の総エピソード数を更新（最適化版）
            query = 'SELECT MAX(CAST(episode_no AS INTEGER)) FROM episodes WHERE ncode = ?'
            result = self.execute_read_query(query, (ncode,), fetch_all=False)

            max_episode_no = result[0] if result and result[0] is not None else 0

            update_query = 'UPDATE novels_descs SET total_ep = ? WHERE n_code = ?'
            self.execute_query(update_query, (max_episode_no, ncode))
            logger.info(f"小説 {ncode} の総エピソード数を {max_episode_no} に更新しました")
        else:
            # 全ての小説の総エピソード数を更新（並列処理）
            query = 'SELECT n_code FROM novels_descs'
            ncodes = self.execute_read_query(query)

            # 並列処理で更新
            for ncode_batch in self._chunks([ncode[0] for ncode in ncodes], 10):
                futures = []
                for ncode in ncode_batch:
                    futures.append(self._executor.submit(self.update_total_episodes, ncode))

                # 完了を待機
                for future in futures:
                    future.result()

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

    def get_novels_needing_update(self):
        """
        更新が必要な小説のリストを取得（効率化版、ratingが5の小説は除外）

        Returns:
            list: 更新が必要な小説情報のリスト [(ncode, title, total_ep, general_all_no, rating), ...]
        """
        # 単一クエリで必要なデータを全て取得（JOINを活用）
        query = '''
        SELECT n.n_code, n.title, 
               COALESCE(n.total_ep, 0) as total_ep, 
               n.general_all_no, n.rating
        FROM novels_descs n
        WHERE n.general_all_no IS NOT NULL 
          AND (n.total_ep IS NULL OR n.total_ep < n.general_all_no)
          AND n.rating != 5  -- ratingが5の小説を除外
        '''
        results = self.execute_read_query(query)

        needs_update = []
        for n_code, title, total_ep, general_all_no, rating in results:
            needs_update.append((n_code, title, total_ep, general_all_no, rating))

        return needs_update

    def remove_duplicate_episodes(self):
        """
        重複するエピソードを削除し、各エピソードごとに最も長い本文を持つものだけを残す
        （パフォーマンス最適化版）
        """
        # トランザクションを開始
        conn = self.get_connection()
        thread_id = threading.get_ident()

        with self._connection_locks[thread_id]:
            cursor = conn.cursor()

            try:
                # 重複エピソードの識別と削除を一つのクエリで効率的に実行
                cursor.execute('''
                DELETE FROM episodes
                WHERE rowid NOT IN (
                    SELECT MIN(rowid)
                    FROM (
                        SELECT rowid,
                               ncode,
                               episode_no,
                               LENGTH(body) as body_length
                        FROM episodes
                    ) AS e
                    GROUP BY ncode, episode_no
                    HAVING body_length = MAX(body_length)
                )
                ''')

                # コミット
                conn.commit()
                logger.info(f"重複エピソードの削除が完了しました。削除数: {cursor.rowcount}")

            except sqlite3.Error as e:
                conn.rollback()
                logger.error(f"重複エピソード削除エラー: {e}")
                raise

    def find_missing_episodes(self, ncode):
        """
        指定された小説の欠落しているエピソードを見つける（単純化版）

        Args:
            ncode (str): 小説コード

        Returns:
            list: 欠落しているエピソード番号のリスト
        """
        try:
            # 小説の総エピソード数を取得
            novel_query = 'SELECT general_all_no FROM novels_descs WHERE n_code = ?'
            general_all_no_result = self.execute_read_query(novel_query, (ncode,), fetch_all=False)

            if not general_all_no_result or not general_all_no_result[0]:
                logger.warning(f"小説 {ncode} の general_all_no が設定されていません")
                return []

            general_all_no = general_all_no_result[0]

            # general_all_noが文字列の場合は整数に変換
            if isinstance(general_all_no, str):
                general_all_no = int(general_all_no) if general_all_no.isdigit() else 0
            else:
                general_all_no = int(general_all_no) if general_all_no is not None else 0

            # 存在するエピソード番号を取得
            episode_query = 'SELECT CAST(episode_no AS INTEGER) as ep_num FROM episodes WHERE ncode = ? ORDER BY ep_num'
            existing_episodes = self.execute_read_query(episode_query, (ncode,))

            # 既存のエピソード番号をセットに変換（高速な検索のため）
            existing_set = set(ep[0] for ep in existing_episodes)

            # 1から総エピソード数までの範囲でチェック
            missing_episodes = []
            for ep_num in range(1, general_all_no + 1):
                if ep_num not in existing_set:
                    missing_episodes.append(ep_num)

            logger.info(
                f"小説 {ncode} - 欠落エピソード: {missing_episodes} - 総エピソード数: {general_all_no} - 存在するエピソード数: {len(existing_episodes)}")
            return missing_episodes

        except Exception as e:
            logger.error(f"欠落エピソード検索エラー: {e}")
            return []

    # ヘルパーメソッド
    def _chunks(self, lst, n):
        """リストをn個ずつのチャンクに分割"""
        for i in range(0, len(lst), n):
            yield lst[i:i + n]