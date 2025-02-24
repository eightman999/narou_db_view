import sqlite3
import threading
from queue import Queue
from checker import catch_up_episode, single_episode
from concurrent.futures import ThreadPoolExecutor

fetch_queue = Queue()
db_lock = threading.Lock()
update_queue = Queue()

fetch_counter = 0

def fetch_episodes(cursor, offset, limit=10):
    global fetch_counter
    print(f"Fetching episodes from offset {offset}...")
    cursor.execute('''
    SELECT ncode, episode_no
    FROM episodes
    WHERE e_title IS NULL OR e_title = '' OR body IS NULL OR body = '' OR body = 'No content found in the specified div.'
    LIMIT ? OFFSET ?
    ''', (limit, offset))
    fetch_counter += 1
    return cursor.fetchall()

def process_episode(ncode, episode_no):
    print(f"Recovering episode {episode_no} of novel {ncode}...")
    episode, title = catch_up_episode(ncode, episode_no, 1)
    update_queue.put((episode, title, ncode, episode_no))

def db_writer():
    while True:
        conn = sqlite3.connect('database/novel_status.db')
        cursor = conn.cursor()
        print("Starting database writer thread...")
        updates = []
        while not update_queue.empty():
            updates.append(update_queue.get())
        if updates:
            with db_lock:
                cursor.executemany('''
                UPDATE episodes
                SET body = ?, e_title = ?
                WHERE ncode = ? AND episode_no = ?
                ''', updates)
                conn.commit()
        conn.close()
        print("Database writer thread finished")
        threading.Event().wait(5)  # 5秒ごとに実行

def recover_novel():
    conn = sqlite3.connect('database/novel_status.db')
    cursor = conn.cursor()
    print("Recovering novels...")
    offset = 0
    limit = 10

    while True:
        episodes_to_recover = fetch_episodes(cursor, offset, limit)
        if not episodes_to_recover:
            break

        threads = []
        for ncode, episode_no in episodes_to_recover:
            thread = threading.Thread(target=process_episode, args=(ncode, episode_no))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        offset += limit

    conn.close()

# データベースライタースレッドを開始
# db_writer_thread = threading.Thread(target=db_writer, daemon=True)
# db_writer_thread.start()

def check_NoDiv():
    conn = sqlite3.connect('database/novel_status.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT COUNT(*)
    FROM episodes
    WHERE e_title IS NULL OR e_title = '' OR body IS NULL OR body = '' OR body = 'No content found in the specified div.'
    ''')
    count = cursor.fetchone()[0]
    conn.close()
    return count


def check_Duplication_ep():
    conn = sqlite3.connect('database/novel_status.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT ncode, episode_no, COUNT(*)
    FROM episodes
    GROUP BY ncode, episode_no
    HAVING COUNT(*) > 1
    ''')
    duplicates = cursor.fetchall()
    conn.close()
    return duplicates

# no_div_count = check_NoDiv()
# print(f"Number of episodes with missing or invalid content: {no_div_count}")

def DelDuplication(batch_size=10):
    conn = sqlite3.connect('database/novel_status.db')
    cursor = conn.cursor()
    print("Deleting duplicated episodes with missing or invalid content...")

    # 全削除処理
    cursor.execute('''
    DELETE FROM episodes
    WHERE e_title IS NULL OR e_title = '' OR body IS NULL OR body = '' OR body = 'No content found in the specified div.'
    ''')
    conn.commit()
    conn.close()


def fetch_missing_episodes(ncode, episode_no):
    print(f"Fetching missing episode {episode_no} for novel {ncode}...")
    episode, title = catch_up_episode(ncode, episode_no, 1)
    fetch_queue.put((ncode, episode_no, episode, title))

def save_fetched_episodes():
    conn = sqlite3.connect('database/novel_status.db')
    cursor = conn.cursor()
    print("Saving fetched episodes to the database...")

    while not fetch_queue.empty():
        ncode, episode_no, episode, title = fetch_queue.get()
        cursor.execute('''
            INSERT INTO episodes (ncode, episode_no, body, e_title)
            VALUES (?, ?, ?, ?)
        ''', (ncode, episode_no, episode, title))
        conn.commit()

    conn.close()
    print("Fetched episodes have been saved to the database.")

def find_missing_episodes(ncode, general_all_no):
    conn = sqlite3.connect('database/novel_status.db')
    cursor = conn.cursor()
    print(f"Finding {ncode}...")

    if general_all_no == 1:
        episode, title = single_episode(ncode, 1)
        fetch_queue.put((ncode, 1, episode, title))
    else:
        cursor.execute('SELECT episode_no FROM episodes WHERE ncode = ? ORDER BY episode_no', (ncode,))
        episodes = [int(ep[0]) for ep in cursor.fetchall()]
        print(f"Episodes: {episodes}")
        episode_numbers = episodes
        print(f"Found {len(episode_numbers)} episodes but max is {general_all_no}")

        # Find missing episode numbers
        missing_episodes = []
        for i in range(1, general_all_no + 1):
            if i not in episode_numbers:
                missing_episodes.append(i)

        # Fetch missing episodes using ThreadPoolExecutor with a max of 16 threads
        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = [executor.submit(fetch_missing_episodes, ncode, episode_no) for episode_no in missing_episodes]
            for future in futures:
                future.result()  # Wait for all threads to complete

    conn.close()
    save_fetched_episodes()
    print(f"Missing episodes for novel {ncode} have been fetched.")

def find_missing_all():
    conn = sqlite3.connect('database/novel_status.db')
    cursor = conn.cursor()
    print("Finding missing episodes for all novels...")

    # Get all unique n_code values from novels_descs
    cursor.execute('SELECT DISTINCT n_code, general_all_no FROM novels_descs')
    n_codes = cursor.fetchall()

    for n_code_tuple in n_codes:
        n_code = n_code_tuple[0]
        general_all_no = n_code_tuple[1]

        if general_all_no is None:
            print(f"Skipping novel {n_code} as general_all_no is None.")
            continue

        print(f"Finding missing episodes for novel {n_code} with general_all_no {general_all_no}...")
        find_missing_episodes(n_code, general_all_no)

    conn.close()
    print("Missing episodes for all novels have been fetched and saved.")
# Example usage
# find_missing_all()
# Example usage
