import sqlite3
import asyncio
from datetime import datetime
import aiohttp
from bs4 import BeautifulSoup
import random
from checker import USER_AGENTS


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
        cursor = self.conn.cursor()
        await run_in_thread(cursor.execute, sql, params)
        return cursor

    async def fetchall(self, cursor):
        """カーソルから全ての結果を取得する非同期メソッド"""
        return await run_in_thread(cursor.fetchall)

    async def commit(self):
        """変更をコミットする非同期メソッド"""
        await run_in_thread(self.conn.commit)


# Connect to the database
async def shelf_maker():
    async with AsyncConnection('database/novel_status.db') as db:
        # Select data from novels_descs table
        cursor = await db.execute('SELECT * FROM novels_descs')
        rows = await db.fetchall(cursor)

        # Store the data in novel_shelf list
        novel_shelf = [list(row) for row in rows]

        # Create a dictionary to store the best row for each n_code
        best_rows = {}

        for row in novel_shelf:
            n_code = row[0]
            # Count the number of non-space elements in the row
            non_space_count = sum(1 for element in row if isinstance(element, str) and element.strip() != '')

            if n_code not in best_rows:
                best_rows[n_code] = (non_space_count, row)
            else:
                # Update the best row if the current row has more non-space elements
                if non_space_count > best_rows[n_code][0]:
                    best_rows[n_code] = (non_space_count, row)

        # Extract the best rows
        sub_shelf = [row for _, row in best_rows.values()]

    novels = 0
    # Print the sub_shelf list
    for novel in sub_shelf:
        novels += 1
        print(novel)

    print(f"Total number of novels: {novels}")

    return sub_shelf


async def input_last_read(rast_read_novel, episode_no):
    async with AsyncConnection('database/novel_status.db') as db:
        # Create the rast_read_novel table if it does not exist
        await db.execute('''
        CREATE TABLE IF NOT EXISTS rast_read_novel (
            ncode TEXT,
            date TEXT,
            episode_no INTEGER
        )
        ''')

        # Get the current date and time
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Insert the ncode, current date, and episode_no into the rast_read_novel table
        await db.execute('''
        INSERT INTO rast_read_novel (ncode, date, episode_no)
        VALUES (?, ?, ?)
        ''', (rast_read_novel, current_time, episode_no))

        # コミット
        await db.commit()


async def get_last_read(shelf):
    async with AsyncConnection('database/novel_status.db') as db:
        # Select the last read novel from the rast_read_novel table
        cursor = await db.execute('''
        SELECT ncode, episode_no
        FROM rast_read_novel
        ORDER BY date DESC
        LIMIT 1
        ''')
        result = await db.fetchall(cursor)
        last_read_novel = result[0] if result else None

        if last_read_novel:
            last_read_ncode = last_read_novel[0]
            last_read_episode_no = last_read_novel[1]
            # Compare with the shelf rows
            for row in shelf:
                if row[0] == last_read_ncode:
                    return row, last_read_episode_no

    return None, None


async def episode_getter(n_code):
    async with AsyncConnection('database/novel_status.db') as db:
        # Select the episode_no and e_title from the novels_episodes table
        cursor = await db.execute('''
        SELECT episode_no, e_title, body
        FROM episodes
        WHERE ncode = ?
        ORDER BY episode_no
        ''', (n_code,))
        rows = await db.fetchall(cursor)

    # Print the episodes
    for row in rows:
        print(row)

    return rows


# HTTP通信を行うためのセッション管理
class HTTPSession:
    def __init__(self):
        self.session = None

    async def __aenter__(self):
        # セッションの作成
        self.session = aiohttp.ClientSession(
            headers={'User-Agent': random.choice(USER_AGENTS)}
        )
        return self.session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # セッションの終了
        if self.session:
            await self.session.close()