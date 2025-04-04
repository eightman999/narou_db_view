import sqlite3

from ohanashi_salvager import OhanashiSalvager

novels = 0
# Connect to the source database
source_conn = sqlite3.connect('database/novel_master.db')
source_cursor = source_conn.cursor()

# Connect to the destination database
dest_conn = sqlite3.connect('database/novel_status.db')
dest_cursor = dest_conn.cursor()

# Create the novels_descs table in the destination database
dest_cursor.execute('''
CREATE TABLE IF NOT EXISTS novels_descs (
    n_code TEXT,
    title TEXT,
    author TEXT,
    Synopsis TEXT,
    main_tag TEXT,
    sub_tag TEXT
)
''')

# Select the required data from the source database
source_cursor.execute('''
SELECT c13 AS n_code, c20 AS title, c23 AS author, c19 AS Synopsis, c7 AS main_tag, c11 AS sub_tag
FROM lost_and_found
WHERE c13 IS NOT NULL
''')

# Fetch all rows from the query
rows = source_cursor.fetchall()

# Convert rows to the desired format and print
noveldatas = [[row[0], row[1], row[2], row[3], row[4], row[5]] for row in rows]

# Select ncode and title from downloadjob table
source_cursor.execute('''
SELECT ncode, title
FROM downloadjob
''')

# Fetch all rows from the query
downloadjob_rows = source_cursor.fetchall()

# Add ncode and title to noveldatas, filling other elements with half-width spaces
for row in downloadjob_rows:
    noveldatas.append([row[0], row[1], ' ', ' ', ' ', ' '])
# Connect to the additional database
additional_conn = sqlite3.connect('database/novel_dddd.db')
additional_cursor = additional_conn.cursor()

# Select ncode and title from novel_status table
additional_cursor.execute('''
SELECT ncode, COALESCE(title, ' ')
FROM novels_status
''')

# Fetch all rows from the query
additional_rows = additional_cursor.fetchall()

# Add ncode and title to noveldatas, filling other elements with half-width spaces
for row in additional_rows:
    noveldatas.append([row[0], row[1], ' ', ' ', ' ', ' '])

# Insert the data into the destination database
dest_cursor.executemany('''
INSERT INTO novels_descs (n_code, title, author, Synopsis, main_tag, sub_tag)
VALUES (?, ?, ?, ?, ?, ?)
''', noveldatas)

# Commit the transaction and close the connections
dest_conn.commit()
source_conn.close()
dest_conn.close()
additional_conn.close()

# Print the noveldatas
for row in noveldatas:
    novels += 1
    print(f"{row[0]}-{row[1]}-{row[2]}")

print(f"Total novels: {novels}")

OhanashiSalvager(noveldatas)