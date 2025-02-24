import sqlite3

def update_total_episodes():
    # Connect to the SQLite database
    conn = sqlite3.connect('database/novel_status.db')
    cursor = conn.cursor()

    # Add the total_ep column to the novels_descs table if it doesn't exist


    # Get all ncodes from the novels_descs table
    cursor.execute('SELECT n_code FROM novels_descs')
    ncodes = cursor.fetchall()

    # For each ncode, count the matching entries in the episodes table and update the total_ep column
    for ncode in ncodes:
        # print(ncode)
        ncode = ncode[0]
        update_total_episodes_single(ncode)
    # Commit the changes and close the connection
    conn.commit()
    conn.close()
    print('Total episodes updated successfully')

def update_total_episodes_single(ncode):
    # Connect to the SQLite database
    conn = sqlite3.connect('database/novel_status.db')
    cursor = conn.cursor()
    print(f"Updating {ncode}'s episodes")

    # Fetch all episode_no values for the given ncode
    cursor.execute('SELECT episode_no FROM episodes WHERE ncode = ?', (ncode,))
    episode_nos = cursor.fetchall()

    # Store the episode_no values in an array and convert to integers
    episode_no_array = [int(ep[0]) for ep in episode_nos]
    # print(f"Episode numbers: {episode_no_array}")

    # Find the maximum value in the array
    if not episode_no_array:
        # print(f"No episodes found for {ncode}")
        max_episode_no = 0
    else:
        max_episode_no = max(episode_no_array)
    # print(f"Max episode_no: {max_episode_no}")

    # Update the total_ep column with the maximum episode_no
    cursor.execute('UPDATE novels_descs SET total_ep = ? WHERE n_code = ?', (max_episode_no, ncode))

    # Commit the changes and close the connection
    conn.commit()
    conn.close()
update_total_episodes()