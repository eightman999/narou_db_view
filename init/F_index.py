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
        CREATE INDEX IF NOT EXISTS idx_last_read ON last_read_novel (
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


def cleanup_invalid_episode_counts():
    """エピソード数フィールドの不正な値をクリーンアップする"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        # 不正なエピソード数を持つ小説を特定
        cursor.execute("""
            SELECT n_code, total_ep FROM novels_descs 
            WHERE total_ep IS NOT NULL AND total_ep != '' AND CAST(total_ep AS INTEGER) != total_ep
        """)

        invalid_records = cursor.fetchall()

        for n_code, total_ep in invalid_records:
            # 正しいエピソード数を取得（例：エピソードテーブルから最大値を取得）
            cursor.execute("SELECT MAX(CAST(episode_no AS INTEGER)) FROM episodes WHERE ncode = ?", (n_code,))
            correct_count = cursor.fetchone()[0] or 0

            # 修正
            cursor.execute("UPDATE novels_descs SET total_ep = ? WHERE n_code = ?", (correct_count, n_code))

        conn.commit()
        print(f"{len(invalid_records)}件の不正なエピソード数を修正しました")

    except Exception as e:
        print(f"エラー: {e}")
        conn.rollback()
    finally:
        conn.close()
if __name__ == "__main__":
    cleanup_invalid_episode_counts()