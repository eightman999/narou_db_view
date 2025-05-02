import sqlite3
from datetime import datetime

last_read_novel = "n6300hz"
last_episode = 1
conn = sqlite3.connect('database/novel_status.db')
cursor = conn.cursor()

# Create the last_read_novel table if it does not exist
cursor.execute('''
    CREATE TABLE IF NOT EXISTS last_read_novel (
        ncode TEXT,
        date TEXT,
        episode_no INTEGER
    )
    ''')

# Check if the episode_no column exists, and add it if it does not
cursor.execute("PRAGMA table_info(last_read_novel)")
columns = [column[1] for column in cursor.fetchall()]
if 'episode_no' not in columns:
    cursor.execute("ALTER TABLE last_read_novel ADD COLUMN episode_no INTEGER")

# Get the current date and time
current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# Insert the ncode and current date into the last_read_novel table
cursor.execute('''
    INSERT INTO last_read_novel (ncode, date, episode_no)
    VALUES (?, ?, ?)
    ''', (last_read_novel, current_time, last_episode))

# Commit the transaction and close the connection
conn.commit()
conn.close()