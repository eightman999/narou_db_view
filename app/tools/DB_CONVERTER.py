import sqlite3

def migrate_novels_descs_schema(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 1. 一時テーブルにデータをバックアップ
        cursor.execute("ALTER TABLE novels_descs RENAME TO novels_descs_old;")

        # 2. 新しいスキーマでテーブルを作成（Expectedの構造に合わせる）
        cursor.execute('''
            CREATE TABLE novels_descs (
                n_code TEXT PRIMARY KEY NOT NULL DEFAULT 'undefined',
                main_tag TEXT DEFAULT 'undefined',
                total_ep INTEGER DEFAULT 'undefined',
                updated_at TEXT DEFAULT 'undefined',
                author TEXT NOT NULL DEFAULT 'undefined',
                rating INTEGER DEFAULT 'undefined',
                title TEXT NOT NULL DEFAULT 'undefined',
                Synopsis TEXT DEFAULT 'undefined',
                sub_tag TEXT DEFAULT 'undefined',
                last_update_date TEXT DEFAULT 'undefined',
                general_all_no INTEGER DEFAULT 'undefined'
            );
        ''')

        # 3. インデックスを再作成
        cursor.execute('''
            CREATE INDEX idx_novels_last_update ON novels_descs (last_update_date ASC);
        ''')
        cursor.execute('''
            CREATE INDEX idx_novels_update_check ON novels_descs (
                n_code ASC, rating ASC, total_ep ASC, general_all_no ASC, updated_at ASC
            );
        ''')

        # 4. 古いデータを新しいテーブルへ移行
        cursor.execute('''
            INSERT INTO novels_descs (
                n_code, main_tag, total_ep, updated_at, author,
                rating, title, Synopsis, sub_tag,
                last_update_date, general_all_no
            )
            SELECT
                n_code, main_tag, total_ep, updated_at, author,
                rating, title, Synopsis, sub_tag,
                last_update_date, general_all_no
            FROM novels_descs_old;
        ''')

        # 5. 古いテーブルを削除
        cursor.execute("DROP TABLE novels_descs_old;")

        conn.commit()
        print("スキーマの移行が完了しました。")
    except sqlite3.Error as e:
        print("エラーが発生しました:", e)
        conn.rollback()
    finally:
        conn.close()

# 使用例
migrate_novels_descs_schema("your_database_path.sqlite")
