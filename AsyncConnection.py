import sqlite3
import asyncio


class AsyncConnection:
    """SQLiteデータベースへの非同期アクセスを提供するコンテキストマネージャ"""

    def __init__(self, db_path):
        """
        コンストラクタ

        Args:
            db_path: データベースファイルのパス
        """
        self.db_path = db_path
        self.conn = None

    async def __aenter__(self):
        """コンテキスト開始時にデータベース接続を行う"""

        def connect():
            conn = sqlite3.connect(self.db_path)
            return conn

        self.conn = await asyncio.to_thread(connect)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """コンテキスト終了時にデータベース接続を閉じる"""
        if self.conn:
            await asyncio.to_thread(self.conn.close)

    async def execute(self, sql, params=None):
        """
        SQLクエリを実行する

        Args:
            sql: 実行するSQLクエリ
            params: SQLクエリのパラメータ (オプション)

        Returns:
            データベースカーソル
        """
        if params is None:
            params = []

        def execute_query():
            cursor = self.conn.cursor()
            cursor.execute(sql, params)
            return cursor

        return await asyncio.to_thread(execute_query)

    async def executemany(self, sql, param_list):
        """
        複数のパラメータでSQLクエリを実行する

        Args:
            sql: 実行するSQLクエリ
            param_list: SQLクエリのパラメータのリスト

        Returns:
            データベースカーソル
        """

        def execute_many():
            cursor = self.conn.cursor()
            cursor.executemany(sql, param_list)
            return cursor

        return await asyncio.to_thread(execute_many)

    async def fetchone(self, cursor):
        """
        クエリ結果から1行を取得する

        Args:
            cursor: データベースカーソル

        Returns:
            1行の結果 (タプル)
        """
        return await asyncio.to_thread(cursor.fetchone)

    async def fetchall(self, cursor):
        """
        クエリ結果から全ての行を取得する

        Args:
            cursor: データベースカーソル

        Returns:
            全ての結果 (タプルのリスト)
        """
        return await asyncio.to_thread(cursor.fetchall)

    async def commit(self):
        """変更をデータベースにコミットする"""
        await asyncio.to_thread(self.conn.commit)

    async def rollback(self):
        """変更をロールバックする"""
        await asyncio.to_thread(self.conn.rollback)


# 使用例
async def example_usage():
    async with AsyncConnection('database/novel_status.db') as db:
        # SELECT文の実行
        cursor = await db.execute('SELECT * FROM novels_descs LIMIT 5')
        rows = await db.fetchall(cursor)

        for row in rows:
            print(row)

        # INSERT文の実行
        await db.execute(
            'INSERT INTO rast_read_novel (ncode, date, episode_no) VALUES (?, ?, ?)',
            ('test_ncode', '2023-01-01 12:00:00', 1)
        )

        # 変更のコミット
        await db.commit()


if __name__ == "__main__":
    # 非同期関数のテスト実行
    asyncio.run(example_usage())