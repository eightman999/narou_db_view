import sqlite3
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import random
from core.checker import USER_AGENTS
from config import DATABASE_PATH


# Connect to the database
def shelf_maker():
    conn = sqlite3.connect('database/novel_status.db')
    cursor = conn.cursor()

    # Select data from novels_descs table
    cursor.execute('SELECT * FROM novels_descs')

    # Fetch all rows from the query
    rows = cursor.fetchall()

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

    # Close the connection
    conn.close()
    novels = 0
    # Print the sub_shelf list
    for novel in sub_shelf:
        novels += 1
        print(novel)

    print(f"Total number of novels: {novels}")

    return sub_shelf



def input_last_read(rast_read_novel, episode_no):
    # Connect to the database
    conn = sqlite3.connect('database/novel_status.db')
    cursor = conn.cursor()

    # Create the rast_read_novel table if it does not exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS rast_read_novel (
        ncode TEXT,
        date TEXT,
        episode_no INTEGER
    )
    ''')

    # Get the current date and time
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Insert the ncode, current date, and episode_no into the rast_read_novel table
    cursor.execute('''
    INSERT INTO rast_read_novel (ncode, date, episode_no)
    VALUES (?, ?, ?)
    ''', (rast_read_novel, current_time, episode_no))

    # Commit the transaction and close the connection
    conn.commit()
    conn.close()

def get_last_read(shelf):
    # Connect to the database
    conn = sqlite3.connect('database/novel_status.db')
    cursor = conn.cursor()

    # Select the last read novel from the rast_read_novel table
    cursor.execute('''
    SELECT ncode, episode_no
    FROM rast_read_novel
    ORDER BY date DESC
    LIMIT 1
    ''')

    # Fetch the last read novel
    last_read_novel = cursor.fetchone()

    # Close the connection
    conn.close()

    if last_read_novel:
        last_read_ncode = last_read_novel[0]
        last_read_episode_no = last_read_novel[1]
        # Compare with the shelf rows
        for row in shelf:
            if row[0] == last_read_ncode:
                return row, last_read_episode_no

    return None, None
def episode_getter(n_code):
    # Connect to the database
    conn = sqlite3.connect('database/novel_status.db')
    cursor = conn.cursor()

    # Select the episode_no and e_title from the novels_episodes table
    cursor.execute('''
    SELECT episode_no, e_title,body
    FROM episodes
    WHERE ncode = ?
    ORDER BY episode_no
    ''', (n_code,))

    # Fetch all rows from the query
    rows = cursor.fetchall()

    # Close the connection
    conn.close()

    # Print the episodes
    for row in rows:
        print(row)

    return rows




