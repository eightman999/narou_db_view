import sqlite3

def get_sorted_episodes():
    # Connect to the database
    conn = sqlite3.connect('database/novel_status.db')
    cursor = conn.cursor()

    # Select and sort the episodes by episode_no in ascending order
    cursor.execute('''
    SELECT episode_no, e_title
    FROM episodes
    ORDER BY episode_no ASC
    ''')

    # Fetch all rows from the query
    episodes = cursor.fetchall()

    # Close the connection
    conn.close()

    return episodes

def format_episode_numbers(episodes):
    """
    Formats the episode numbers in the given list of episodes.

    Args:
        episodes (list of tuples): A list of episodes where each episode is a tuple (episode_no, e_title).

    Returns:
        list of tuples: A list of episodes with formatted episode numbers.
    """
    formatted_episodes = []
    for episode in episodes:
        episode_no, e_title = episode
        formatted_episode_no = f"Episode {int(episode_no):05d}"  # Convert episode_no to int and format with leading zeros
        formatted_episodes.append((formatted_episode_no, e_title))
    return formatted_episodes

if __name__ == "__main__":
    episodes = get_sorted_episodes()
    formatted_episodes = format_episode_numbers(episodes)
    for episode in formatted_episodes:
        print(episode)