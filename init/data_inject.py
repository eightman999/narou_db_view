import sqlite3
from tkinter import Tk
from tkinter.filedialog import askopenfilename

def inject_data():
    # Hide the root window
    Tk().withdraw()

    # Open a file dialog to select the database file
    db_path = askopenfilename(title="Select Database File", filetypes=[("SQLite Database Files", "*.db")])

    if not db_path:
        print("No file selected.")
        return

    # Connect to the selected database with text factory set to bytes
    source_conn = sqlite3.connect(db_path)
    source_conn.text_factory = bytes
    source_cursor = source_conn.cursor()

    # Connect to the target database
    target_conn = sqlite3.connect('database/novel_status.db')
    target_cursor = target_conn.cursor()

    # Fetch data from the novel table
    source_cursor.execute('SELECT username, title, story, rating, keyword, genre, ncode FROM novel')
    novels = source_cursor.fetchall()

    # Insert data into the novels_descs table
    for novel in novels:
        username, title, story, rating, keyword, genre, ncode = novel
        target_cursor.execute('''
            INSERT INTO novels_descs (author, title, Synopsis, rating, sub_tag, main_tag, n_code)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (username, title, story, rating, keyword, genre, ncode))

    # Fetch data from the period table
    source_cursor.execute('SELECT no, title, ncode, text FROM period')
    periods = source_cursor.fetchall()

    # Insert data into the episodes table
    for period in periods:
        no, title, ncode, text = period
        # Decode text to UTF-8, ignoring errors
        text = text.decode('utf-8', 'ignore')
        target_cursor.execute('''
            INSERT INTO episodes (episode_no, e_title, ncode, body)
            VALUES (?, ?, ?, ?)
        ''', (no, title, ncode, text))

    # Commit the transaction and close the connections
    target_conn.commit()
    source_conn.close()
    target_conn.close()

if __name__ == '__main__':
    inject_data()