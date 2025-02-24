import sqlite3

def OhanashiSalvager(master_shelf):
    n_list = [row[0] for row in master_shelf]

    # Connect to the source database with UTF-8 encoding
    source_conn = sqlite3.connect('database/novel_master.db')
    source_conn.text_factory = lambda b: b.decode(errors='ignore')
    source_cursor = source_conn.cursor()

    # Connect to the destination database
    dest_conn = sqlite3.connect('database/novel_status.db')
    dest_cursor = dest_conn.cursor()

    # Create the episodes table in the destination database
    dest_cursor.execute('''
    CREATE TABLE IF NOT EXISTS episodes (
        ncode TEXT,
        episode_no TEXT,
        body TEXT,
        e_title TEXT
    )
    ''')

    # Select rows from lost_and_found where c6 matches any value in n_list
    query = f'''
    SELECT c6, c7, c8, c9
    FROM lost_and_found
    WHERE c6 IN ({','.join('?' for _ in n_list)})
    '''
    source_cursor.execute(query, n_list)
    rows = source_cursor.fetchall()

    # Insert the selected rows into the episodes table
    dest_cursor.executemany('''
    INSERT INTO episodes (ncode, episode_no, body, e_title)
    VALUES (?, ?, ?, ?)
    ''', rows)

    # Commit the transaction and close the connections
    dest_conn.commit()
    source_conn.close()
    dest_conn.close()

