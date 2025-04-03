import sqlite3
import asyncio
import aiohttp
import random
from bs4 import BeautifulSoup
from checker import USER_AGENTS
from concurrent.futures import ThreadPoolExecutor


# 非同期キュー
class AsyncQueue:
    def __init__(self):
        self._queue = asyncio.Queue()

    async def put(self, item):
        await self._queue.put(item)

    async def get(self):
        return await self._queue.get()

    async def task_done(self):
        self._queue.task_done()

    async def join(self):
        await self._queue.join()

    async def empty(self):
        return self._queue.empty()


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


# 非同期キューの初期化
fetch_queue = AsyncQueue()
update_queue = AsyncQueue()

# カウンター
fetch_counter = 0


async def fetch_episodes(offset, limit=10):
    """指定されたオフセットから複数のエピソードを取得する非同期関数"""
    global fetch_counter
    print(f"Fetching episodes from offset {offset}...")

    async with AsyncConnection('database/novel_status.db') as db:
        cursor = await db.execute('''
        SELECT ncode, episode_no
        FROM episodes
        WHERE e_title IS NULL OR e_title = '' OR body IS NULL OR body = '' OR body = 'No content found in the specified div.'
        LIMIT ? OFFSET ?
        ''', (limit, offset))

        episodes = await db.fetchall(cursor)
        fetch_counter += 1
        return episodes


async def catch_up_episode(ncode, episode_no, rating):
    """エピソードを取得する非同期関数"""
    title = ""
    episode = ""

    # URLの設定
    EP_url = f"https://ncode.syosetu.com/{ncode}/{episode_no}/"
    if rating == 1:
        EP_url = f"https://novel18.syosetu.com/{ncode}/{episode_no}/"

    headers = {'User-Agent': random.choice(USER_AGENTS)}

    # リトライロジック
    max_retries = 3

    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(EP_url, headers=headers) as response:
                    # レスポンスが成功した場合
                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')

                        novel_body = soup.find('div', class_='p-novel__body')
                        title_tag = soup.find('h1', class_='p-novel__title')

                        if title_tag:
                            title = title_tag.get_text(strip=True)
                        if novel_body:
                            episode = ''.join(str(p) for p in novel_body.find_all('p'))
                        else:
                            episode = "No content found in the specified div."

                        return episode, title
                    else:
                        print(f"Error: HTTP {response.status} for {ncode} episode {episode_no}")

        except Exception as e:
            print(f"Error fetching episode {episode_no} for {ncode}: {e}")

        # 失敗した場合はリトライ前に待機
        await asyncio.sleep(1)

    # すべてのリトライが失敗した場合
    return "Failed to retrieve the episode after multiple attempts.", "Error"


async def single_episode(ncode, rating):
    """単一エピソードの小説を取得する非同期関数"""
    # URLの設定
    EP_url = f"https://ncode.syosetu.com/{ncode}"
    if rating == 1:
        EP_url = f"https://novel18.syosetu.com/{ncode}"

    headers = {'User-Agent': random.choice(USER_AGENTS)}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(EP_url, headers=headers) as response:
                # レスポンスが成功した場合
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')

                    novel_body = soup.find('div', class_='p-novel__body')
                    title_tag = soup.find('h1', class_='p-novel__title')

                    if title_tag:
                        title = title_tag.get_text(strip=True)
                    else:
                        title = ""

                    if novel_body:
                        episode = ''.join(str(p) for p in novel_body.find_all('p'))
                    else:
                        episode = "No content found in the specified div."

                    return episode, title
                else:
                    return "", ""
    except Exception as e:
        print(f"Error fetching single episode for {ncode}: {e}")
        return "", ""


async def process_episode(ncode, episode_no):
    """エピソードを処理する非同期関数"""
    print(f"Recovering episode {episode_no} of novel {ncode}...")
    episode, title = await catch_up_episode(ncode, episode_no, 1)
    await update_queue.put((episode, title, ncode, episode_no))


async def db_writer():
    """データベースに書き込む非同期関数"""
    while True:
        try:
            async with AsyncConnection('database/novel_status.db') as db:
                print("Starting database writer task...")
                updates = []

                # キューからアイテムを取得
                while not await update_queue.empty():
                    updates.append(await update_queue.get())

                # 更新があれば実行
                if updates:
                    for update in updates:
                        await db.execute('''
                        UPDATE episodes
                        SET body = ?, e_title = ?
                        WHERE ncode = ? AND episode_no = ?
                        ''', update)

                    await db.commit()
                    print(f"Updated {len(updates)} episodes in database")

            # 一定間隔で実行するため待機
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Error in database writer: {e}")
            await asyncio.sleep(5)


async def recover_novel():
    """小説を復元する非同期関数"""
    offset = 0
    limit = 10

    while True:
        episodes_to_recover = await fetch_episodes(offset, limit)
        if not episodes_to_recover:
            break

        # 非同期タスクのリスト
        tasks = []
        for ncode, episode_no in episodes_to_recover:
            task = asyncio.create_task(process_episode(ncode, episode_no))
            tasks.append(task)

        # すべてのタスクが完了するのを待つ
        if tasks:
            await asyncio.gather(*tasks)

        offset += limit


async def check_NoDiv():
    """欠損したエピソードの数を数える非同期関数"""
    async with AsyncConnection('database/novel_status.db') as db:
        cursor = await db.execute('''
        SELECT COUNT(*)
        FROM episodes
        WHERE e_title IS NULL OR e_title = '' OR body IS NULL OR body = '' OR body = 'No content found in the specified div.'
        ''')
        result = await db.fetchall(cursor)
        return result[0][0]


async def check_Duplication_ep():
    """重複したエピソードを検索する非同期関数"""
    async with AsyncConnection('database/novel_status.db') as db:
        cursor = await db.execute('''
        SELECT ncode, episode_no, COUNT(*)
        FROM episodes
        GROUP BY ncode, episode_no
        HAVING COUNT(*) > 1
        ''')
        duplicates = await db.fetchall(cursor)
        return duplicates


async def DelDuplication():
    """欠損または無効なコンテンツを持つ重複エピソードを削除する非同期関数"""
    async with AsyncConnection('database/novel_status.db') as db:
        print("Deleting duplicated episodes with missing or invalid content...")

        # 全削除処理
        await db.execute('''
        DELETE FROM episodes
        WHERE e_title IS NULL OR e_title = '' OR body IS NULL OR body = '' OR body = 'No content found in the specified div.'
        ''')

        await db.commit()

    print("Deleted all episodes with missing or invalid content.")


async def fetch_missing_episodes(ncode, episode_no):
    """欠落しているエピソードを取得する非同期関数"""
    print(f"Fetching missing episode {episode_no} for novel {ncode}...")
    episode, title = await catch_up_episode(ncode, episode_no, 1)
    await fetch_queue.put((ncode, episode_no, episode, title))


async def save_fetched_episodes():
    """取得したエピソードをデータベースに保存する非同期関数"""
    async with AsyncConnection('database/novel_status.db') as db:
        print("Saving fetched episodes to the database...")

        while not await fetch_queue.empty():
            ncode, episode_no, episode, title = await fetch_queue.get()
            await db.execute('''
                INSERT INTO episodes (ncode, episode_no, body, e_title)
                VALUES (?, ?, ?, ?)
            ''', (ncode, episode_no, episode, title))
            await db.commit()

    print("Fetched episodes have been saved to the database.")


async def find_missing_episodes(ncode, general_all_no):
    """指定したn_codeのエピソードで欠落しているものを見つける非同期関数"""
    print(f"Finding missing episodes for {ncode}...")

    # 単一エピソードの小説の場合
    if general_all_no == 1:
        episode, title = await single_episode(ncode, 1)
        await fetch_queue.put((ncode, 1, episode, title))
    else:
        # 複数エピソードの小説の場合
        async with AsyncConnection('database/novel_status.db') as db:
            cursor = await db.execute('SELECT episode_no FROM episodes WHERE ncode = ? ORDER BY episode_no', (ncode,))
            episodes_result = await db.fetchall(cursor)
            episodes = [int(ep[0]) for ep in episodes_result]
            print(f"Found {len(episodes)} episodes but max is {general_all_no}")

            # 欠落しているエピソード番号を見つける
            missing_episodes = []
            for i in range(1, general_all_no + 1):
                if i not in episodes:
                    missing_episodes.append(i)

            # 欠落しているエピソードを非同期で取得
            tasks = []
            for episode_no in missing_episodes:
                task = asyncio.create_task(fetch_missing_episodes(ncode, episode_no))
                tasks.append(task)

            # すべてのタスクが完了するのを待つ
            if tasks:
                await asyncio.gather(*tasks)

    # 取得したエピソードを保存
    await save_fetched_episodes()
    print(f"Missing episodes for novel {ncode} have been fetched and saved.")


async def find_missing_all():
    """すべての小説の欠落エピソードを見つける非同期関数"""
    async with AsyncConnection('database/novel_status.db') as db:
        print("Finding missing episodes for all novels...")

        # すべてのユニークなn_code値を取得
        cursor = await db.execute('SELECT DISTINCT n_code, general_all_no FROM novels_descs')
        n_codes = await db.fetchall(cursor)

        for n_code, general_all_no in n_codes:
            if general_all_no is None:
                print(f"Skipping novel {n_code} as general_all_no is None.")
                continue

            print(f"Finding missing episodes for novel {n_code} with general_all_no {general_all_no}...")
            await find_missing_episodes(n_code, general_all_no)

    print("Missing episodes for all novels have been fetched and saved.")


# メイン関数
async def main():
    # データベースライタータスクを開始
    db_writer_task = asyncio.create_task(db_writer())

    # 欠損エピソードの数を確認
    no_div_count = await check_NoDiv()
    print(f"Number of episodes with missing or invalid content: {no_div_count}")

    # 復元処理の実行
    await recover_novel()

    # データベースライタータスクをキャンセル
    db_writer_task.cancel()
    try:
        await db_writer_task
    except asyncio.CancelledError:
        pass


# スクリプトが直接実行された場合
if __name__ == "__main__":
    asyncio.run(main())