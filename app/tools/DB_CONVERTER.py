import sqlite3

def migrate_novels_descs_schema(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 既存のnovels_descs_oldテーブルを削除
        cursor.execute("DROP TABLE IF EXISTS novels_descs_old;")

        # 1. 一時テーブルにデータをバックアップ
        cursor.execute("ALTER TABLE novels_descs RENAME TO novels_descs_old;")

        # 2. 新しいスキーマでテーブルを作成
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

def migrate_episodes_schema(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 既存の episodes_old テーブルを削除
        cursor.execute("DROP TABLE IF EXISTS episodes_old;")
        # 1. テーブル名を一時変更してバックアップ
        cursor.execute("ALTER TABLE episodes RENAME TO episodes_old;")

        # 2. 新しいスキーマのテーブル作成（Expected に合わせる）
        cursor.execute('''
            CREATE TABLE episodes (
                episode_no TEXT NOT NULL DEFAULT 'undefined',
                update_time TEXT DEFAULT 'undefined',
                e_title TEXT DEFAULT 'undefined',
                body TEXT DEFAULT 'undefined',
                ncode TEXT NOT NULL DEFAULT 'undefined',
                PRIMARY KEY (ncode, episode_no)
            );
        ''')

        # 3. インデックスの再作成
        cursor.execute('''
            CREATE INDEX idx_episodes_ncode ON episodes (ncode ASC, episode_no ASC);
        ''')

        # 4. データ移行（null 対応が必要なら COALESCE 追加）
        cursor.execute('''
            INSERT INTO episodes (
                episode_no, update_time, e_title, body, ncode
            )
            SELECT
                episode_no, update_time, e_title, body, ncode
            FROM episodes_old;
        ''')

        # 5. 古いテーブル削除
        cursor.execute("DROP TABLE episodes_old;")

        conn.commit()
        print("episodes テーブルのスキーマ移行が完了しました。")
    except sqlite3.Error as e:
        print("エラーが発生しました:", e)
        conn.rollback()
    finally:
        conn.close()


def migrate_last_read_novel_schema(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 既存の last_read_novel_old テーブルを削除
        cursor.execute("DROP TABLE IF EXISTS last_read_novel_old;")

        # 1. テーブルのバックアップ
        cursor.execute("ALTER TABLE last_read_novel RENAME TO last_read_novel_old;")

        # 2. 新スキーマのテーブル作成
        cursor.execute('''
            CREATE TABLE last_read_novel (
                date TEXT DEFAULT 'undefined',
                episode_no INTEGER DEFAULT 'undefined',
                ncode TEXT NOT NULL DEFAULT 'undefined',
                PRIMARY KEY (ncode, date)
            );
        ''')

        # 3. インデックスの再作成
        cursor.execute('''
            CREATE INDEX idx_last_read ON last_read_novel (ncode ASC, date ASC);
        ''')

        # 4. データ移行（必要なら COALESCEでnull防止）
        cursor.execute('''
            INSERT INTO last_read_novel (
                date, episode_no, ncode
            )
            SELECT
                date, episode_no, ncode
            FROM last_read_novel_old;
        ''')

        # 5. 古いテーブルを削除
        cursor.execute("DROP TABLE last_read_novel_old;")

        conn.commit()
        print("last_read_novel テーブルのスキーマ移行が完了しました。")
    except sqlite3.Error as e:
        print("エラーが発生しました:", e)
        conn.rollback()
    finally:
        conn.close()


def migrate_novels_descs_schema_2(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 既存の novels_descs_old テーブルを削除
        cursor.execute("DROP TABLE IF EXISTS novels_descs_old;")
        # 1. テーブルの名前をリネームしてバックアップ
        cursor.execute("ALTER TABLE novels_descs RENAME TO novels_descs_old;")

        # 2. 新しいテーブル（Expectedスキーマ）を作成
        cursor.execute('''
            CREATE TABLE novels_descs (
                n_code TEXT NOT NULL DEFAULT 'undefined' PRIMARY KEY,
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

        # 3. インデックスの作成
        cursor.execute('''
            CREATE INDEX idx_novels_last_update ON novels_descs (last_update_date ASC);
        ''')
        cursor.execute('''
            CREATE INDEX idx_novels_update_check 
            ON novels_descs (n_code ASC, rating ASC, total_ep ASC, general_all_no ASC, updated_at ASC);
        ''')

        # 4. データ移行（念のため null 対策をしてもOK）
        cursor.execute('''
            INSERT INTO novels_descs (
                n_code, main_tag, total_ep, updated_at, author, rating,
                title, Synopsis, sub_tag, last_update_date, general_all_no
            )
            SELECT 
                n_code, main_tag, total_ep, updated_at, author, rating,
                title, Synopsis, sub_tag, last_update_date, general_all_no
            FROM novels_descs_old;
        ''')

        # 5. 古いテーブルを削除
        cursor.execute("DROP TABLE novels_descs_old;")

        conn.commit()
        print("novels_descs テーブルのスキーマ移行が完了しました。")
    except sqlite3.Error as e:
        print("エラーが発生しました:", e)
        conn.rollback()
    finally:
        conn.close()


# 使用例
migrate_novels_descs_schema("novel_status.db")

migrate_episodes_schema("novel_status.db")

migrate_last_read_novel_schema("novel_status.db")
migrate_novels_descs_schema_2("novel_status.db")

