import sqlite3

def update_novel_status_db():
    # Connect to the database
    conn = sqlite3.connect('database/novel_status.db')
    cursor = conn.cursor()

    # Add the new column 'last_update_date' to the 'novels_descs' table
    cursor.execute('ALTER TABLE novels_descs ADD COLUMN last_update_date TEXT')

    # Update all rows to set 'last_update_date' to '1999/1/1'
    cursor.execute('UPDATE novels_descs SET last_update_date = ?', ('1999/1/1',))

    # Commit the changes and close the connection
    conn.commit()
    conn.close()

def first_episode_last_update():
    # Connect to the database
    conn = sqlite3.connect('database/novel_status.db')
    cursor = conn.cursor()

    # Add the new column 'last_update_date' to the 'novels_descs' table
    cursor.execute('ALTER TABLE episodes ADD COLUMN update_time TEXT')

    # Update all rows to set 'last_update_date' to '1999/1/1'
    cursor.execute('UPDATE episodes SET update_time = ?', ('1999/1/1',))

    # Commit the changes and close the connection
    conn.commit()
    conn.close()
# update_novel_status_db()
# first_episode_last_update()