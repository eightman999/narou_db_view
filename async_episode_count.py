import sqlite3
import asyncio


# データベース操作を非同期で行うためのヘルパー関数
async def run_in_thread(func, *args, **kwargs):
    """SQLiteのような同期的なコードを非同期環境で実行するためのヘルパー関数"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


# 非同期データベース接続のコンテキストマネージャ
class AsyncConnection:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None

    async def __aenter__(self):
        # 同期処理を非同期で実行
        self.conn = await run_in_thread(sqlite3.connect, self.db_path)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            await run_in_thread(self.conn.close)

    async def execute(self, sql, params=None):
        """SQL実行用の非同期メソッド"""
        if params is None:
            params = []

        # カーソルの作成とSQL実行を同じスレッドで行う
        def execute_sql():
            cursor = self.conn.cursor()
            cursor.execute(sql, params)
            return cursor

        return await run_in_thread(execute_sql)

    async def fetchall(self, cursor):
        """カーソルから全ての結果を取得する非同期メソッド"""
        return await run_in_thread(cursor.fetchall)

    async def commit(self):
        """変更をコミットする非同期メソッド"""
        await run_in_thread(self.conn.commit)


async def update_total_episodes():
    """全ての小説のエピソード数を更新する非同期関数"""
    # データベースに接続
    async with AsyncConnection('database/novel_status.db') as db:
        # 全てのn_codeを取得
        cursor = await db.execute('SELECT n_code FROM novels_descs')
        ncodes = await db.fetchall(cursor)

        # 各n_codeに対してエピソード数を更新
        for ncode in ncodes:
            ncode = ncode[0]
            await update_total_episodes_single(ncode)

        # 変更をコミット
        await db.commit()

    print('Total episodes updated successfully')


async def update_total_episodes_single(ncode):
    """指定したn_codeの小説のエピソード数を更新する非同期関数"""
    # データベースに接続
    async with AsyncConnection('database/novel_status.db') as db:
        print(f"Updating {ncode}'s episodes")

        # 指定されたn_codeの全てのepisode_noを取得
        cursor = await db.execute('SELECT episode_no FROM episodes WHERE ncode = ?', (ncode,))
        episode_nos = await db.fetchall(cursor)

        # episode_noを配列に格納し、整数に変換
        episode_no_array = [int(ep[0]) for ep in episode_nos]

        # 配列の最大値を取得
        if not episode_no_array:
            max_episode_no = 0
        else:
            max_episode_no = max(episode_no_array)

        # total_ep列を最大エピソード番号で更新
        await db.execute('UPDATE novels_descs SET total_ep = ? WHERE n_code = ?', (max_episode_no, ncode))

        # 変更をコミット
        await db.commit()


# メイン関数
async def main():
    await update_total_episodes()


# スクリプトが直接実行された場合
if __name__ == "__main__":
    asyncio.run(main())