import os
import sqlite3
import threading
from queue import Queue

from Recover_novel import DelDuplication

# Queue for episodes to be processed
episode_queue = Queue()

def fetch_episodes():
    print("Fetching episodes from the database...")
    conn = sqlite3.connect('database/novel_status.db')
    cursor = conn.cursor()
    offset = 0
    limit = 10

    while True:
        cursor.execute('SELECT ncode, episode_no, body FROM episodes LIMIT ? OFFSET ?', (limit, offset))
        episodes = cursor.fetchall()
        if not episodes:
            break
        print(f"Fetched {len(episodes)} episodes")
        for episode in episodes:
            episode_queue.put(episode)
        process_queue()
        episode_queue.join()  # Wait for the queue to be fully processed
        offset += limit

    conn.close()

def save_episode_to_file(ncode, episode_no, body):
    print(f"Saving episode {episode_no} for novel {ncode} to a file...")
    directory = f'novel_data/{ncode}'
    os.makedirs(directory, exist_ok=True)

    base_filename = f'{ncode}_{episode_no}.txt'
    filename = base_filename
    counter = 1

    # Check for file name conflicts and resolve them
    while os.path.exists(os.path.join(directory, filename)):
        filename = f'{ncode}_{episode_no}_{counter}.txt'
        counter += 1

    with open(os.path.join(directory, filename), 'w', encoding='utf-8') as file:
        file.write(body)

def worker():
    while not episode_queue.empty():
        ncode, episode_no, body = episode_queue.get()
        save_episode_to_file(ncode, episode_no, body)
        episode_queue.task_done()

def process_queue():
    print(f'Processing {episode_queue.qsize()} episodes...')
    threads = []
    for _ in range(10):  # Create 10 threads
        thread = threading.Thread(target=worker)
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()

def main():
    fetch_episodes()

if __name__ == '__main__':
    # DelDuplication()
    main()