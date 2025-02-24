import sqlite3
import threading
from queue import Queue

def remove_duplicates():
    conn = sqlite3.connect('database/novel_status.db')
    cursor = conn.cursor()

    # Find duplicates
    cursor.execute('''
    SELECT ncode, episode_no, MAX(LENGTH(body)) as max_length
    FROM episodes
    GROUP BY ncode, episode_no
    ''')
    max_length_entries = cursor.fetchall()

    # Create a temporary table to store the entries to keep
    cursor.execute('''
    CREATE TEMPORARY TABLE episodes_to_keep AS
    SELECT e1.*
    FROM episodes e1
    JOIN (
        SELECT ncode, episode_no, MAX(LENGTH(body)) as max_length
        FROM episodes
        GROUP BY ncode, episode_no
    ) e2
    ON e1.ncode = e2.ncode AND e1.episode_no = e2.episode_no AND LENGTH(e1.body) = e2.max_length
    ''')

    # Delete all entries from the original table
    cursor.execute('DELETE FROM episodes')

    # Insert the entries to keep back into the original table
    cursor.execute('INSERT INTO episodes SELECT * FROM episodes_to_keep')

    # Drop the temporary table
    cursor.execute('DROP TABLE episodes_to_keep')

    # Commit the transaction and close the connection
    conn.commit()
    conn.close()
def clean_ncode():
    conn = sqlite3.connect('database/novel_status.db')
    cursor = conn.cursor()

    # Fetch all ncode values
    cursor.execute('SELECT ncode FROM episodes')
    ncodes = cursor.fetchall()

    # Update each ncode by removing b' and '
    for ncode_tuple in ncodes:
        ncode = ncode_tuple[0]
        cleaned_ncode = ncode.replace("b'", "").replace("'", "")
        cursor.execute('UPDATE episodes SET ncode = ? WHERE ncode = ?', (cleaned_ncode, ncode))

    # Commit the transaction and close the connection
    conn.commit()
    conn.close()


fetch_queue = Queue()
update_queue = Queue()
db_lock = threading.Lock()
all_done_event = threading.Event()


def fetch_episodes(cursor, offset, limit=20):
    print(f"Fetching episodes from offset {offset}...")
    cursor.execute('''
    SELECT episode_no, ncode, body, e_title
    FROM episodes
    LIMIT ? OFFSET ?
    ''', (limit, offset))
    return cursor.fetchall()

def process_episode(episode_no, ncode, body, e_title):
    reencoded_body = None
    reencoded_e_title = None
    print(f"Processing episode {episode_no} of novel {ncode}...")

    # Check and re-encode body if necessary
    try:
        body.decode('utf-8')
    except (AttributeError, UnicodeDecodeError):
        if isinstance(body, bytes):
            reencoded_body = body.decode('utf-8')
        else:
            reencoded_body = body

    # Check and re-encode e_title if necessary
    try:
        e_title.decode('utf-8')
    except (AttributeError, UnicodeDecodeError):
        if isinstance(e_title, bytes):
            reencoded_e_title = e_title.decode('utf-8')
        else:
            reencoded_e_title = e_title

    if reencoded_body or reencoded_e_title:
        update_queue.put((reencoded_body, reencoded_e_title, episode_no, ncode))

def db_writer():
    conn = sqlite3.connect('database/novel_status.db')
    print("Starting database writer thread...")
    cursor = conn.cursor()
    all_done_event.wait()  # Wait until all processing threads are done
    updates = []
    while not update_queue.empty():
        updates.append(update_queue.get())
        print(f"Processed {len(updates)} episodes")
        if len(updates) >= 10:
            with db_lock:
                print("Writing updates to the database...")
                cursor.executemany('''
                UPDATE episodes
                SET body = COALESCE(?, body), e_title = COALESCE(?, e_title)
                WHERE episode_no = ? AND ncode = ?
                ''', updates)
                conn.commit()
                print("Updates written to the database.")
            updates = []  # Clear the updates list after writing

    # Write any remaining updates
    if updates:
        with db_lock:
            print("Writing remaining updates to the database...")
            cursor.executemany('''
            UPDATE episodes
            SET body = COALESCE(?, body), e_title = COALESCE(?, e_title)
            WHERE episode_no = ? AND ncode = ?
            ''', updates)
            conn.commit()
            print("Remaining updates written to the database.")
    conn.close()
    print("Database connection closed.")

def reencode_episodes():
    print("Re-encoding episodes...")
    conn = sqlite3.connect('database/novel_status.db')
    cursor = conn.cursor()
    offset = 0
    limit = 20

    while True:
        episodes = fetch_episodes(cursor, offset, limit)
        if not episodes:
            break

        threads = []
        for episode_no, ncode, body, e_title in episodes:
            thread = threading.Thread(target=process_episode, args=(episode_no, ncode, body, e_title))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        offset += limit

    conn.close()
    all_done_event.set()  # Signal that all processing threads are done

if __name__ == '__main__':
    db_writer_thread = threading.Thread(target=db_writer, daemon=True)
    db_writer_thread.start()
    reencode_episodes()
    db_writer_thread.join()