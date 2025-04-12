import sqlite3

from config import DATABASE_PATH


def add_update_check_indices():
    """更新チェックに関わるテーブルにインデックスを追加する"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        # 小説テーブルのインデックス
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_novels_update_check ON novels_descs (
            n_code, 
            rating, 
            total_ep, 
            general_all_no,
            updated_at
        );
        """)

        # 最終更新日のインデックス
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_novels_last_update ON novels_descs (
            last_update_date
        );
        """)

        # エピソードテーブルのインデックス
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_episodes_ncode ON episodes (
            ncode,
            episode_no
        );
        """)

        # 最後に読んだ小説テーブルのインデックス
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_last_read ON rast_read_novel (
            ncode,
            date
        );
        """)

        conn.commit()
        print("インデックスの追加が完了しました")

    except sqlite3.Error as e:
        print(f"インデックス作成エラー: {e}")
        conn.rollback()

    finally:
        conn.close()

if __name__ == "__main__":
    add_update_check_indices()