import sqlite3
from app.core.checker import catch_up_episode

# ロガーの設定
from app.utils.logger_manager import get_logger

# ロガーの設定
logger = get_logger('EpisodeCleanup')

from config import DATABASE_PATH

def analyze_episode_duplicates(ncode):
    """
    指定された小説のエピソードの重複と品質を分析する

    Args:
        ncode (str): 小説コード

    Returns:
        dict: エピソード番号ごとの重複エピソード情報
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        # 指定された小説の同一エピソード番号を持つエピソードを取得
        query = '''
        SELECT episode_no, rowid, body, e_title, 
               LENGTH(body) as body_length,
               (CASE 
                   WHEN body LIKE '%エラー%' OR body LIKE '%Error%' 
                   THEN 1 
                   ELSE 0 
               END) as has_error
        FROM episodes 
        WHERE ncode = ? 
        ORDER BY episode_no, has_error, body_length DESC
        '''
        cursor.execute(query, (ncode,))
        rows = cursor.fetchall()

        # エピソード番号ごとの重複エントリを分類
        duplicates = {}
        current_ep_no = None
        current_ep_entries = []

        for row in rows:
            episode_no, rowid, body, title, body_length, has_error = row

            if episode_no != current_ep_no:
                # 前のエピソード番号のエントリを処理
                if current_ep_entries:
                    duplicates[current_ep_no] = current_ep_entries

                # 新しいエピソード番号の処理を開始
                current_ep_no = episode_no
                current_ep_entries = [row]
            else:
                current_ep_entries.append(row)

        # 最後のエピソード番号のエントリを追加
        if current_ep_entries:
            duplicates[current_ep_no] = current_ep_entries

        return duplicates

    except sqlite3.Error as e:
        logger.error(f"データベース処理中にエラーが発生しました: {e}")
        return {}

    finally:
        conn.close()

def clean_duplicate_episodes(ncode, rating):
    """
    重複するエピソードをクリーンアップし、最適なエピソードを残す

    Args:
        ncode (str): 小説コード
        rating (int): 小説のレーティング
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        # 重複エピソードを分析
        duplicates = analyze_episode_duplicates(ncode)
        logger.info(f"小説 {ncode} の重複エピソードを分析しました")

        # 各エピソード番号の重複エントリを処理
        for episode_no, entries in duplicates.items():
            if len(entries) > 1:
                # エラーのない、最も長い本文を持つエピソードを選択
                best_entry = max(
                    [entry for entry in entries if 'エラー' not in entry[2] and 'Error' not in entry[2]], 
                    key=lambda x: len(x[2]) if x[2] else 0
                )

                if best_entry is None:
                    # すべてのエントリにエラーがある場合、最初のエントリを保持
                    best_entry = entries[0]
                    logger.warning(f"エピソード {ncode}-{episode_no} のすべてのエントリにエラーがあります")

                # 最良のエントリ以外を削除
                rowids_to_remove = [entry[1] for entry in entries if entry[1] != best_entry[1]]
                
                if rowids_to_remove:
                    # 不要なエントリを削除
                    remove_query = 'DELETE FROM episodes WHERE rowid IN ({})'.format(
                        ','.join(map(str, rowids_to_remove))
                    )
                    cursor.execute(remove_query)
                    logger.info(f"小説 {ncode} のエピソード {episode_no} から {len(rowids_to_remove)} 個のエントリを削除")

                    # エラーのあるエントリを削除した後、再取得が必要な場合
                    if 'エラー' in best_entry[2] or 'Error' in best_entry[2]:
                        logger.info(f"エピソード {ncode}-{episode_no} を再取得します")
                        new_body, new_title = catch_up_episode(ncode, episode_no, rating)
                        
                        if new_body and new_title:
                            # 再取得したエピソードで更新
                            update_query = '''
                            UPDATE episodes 
                            SET body = ?, e_title = ? 
                            WHERE rowid = ?
                            '''
                            cursor.execute(update_query, (new_body, new_title, best_entry[1]))
                            logger.info(f"エピソード {ncode}-{episode_no} を再取得して更新しました")

        # 変更をコミット
        conn.commit()
        logger.info(f"小説 {ncode} のエピソードクリーンアップが完了しました")

    except sqlite3.Error as e:
        logger.error(f"エピソードクリーンアップ中にエラーが発生しました: {e}")
        conn.rollback()

    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {e}")
        conn.rollback()

    finally:
        conn.close()

def clean_all_novels_episodes():
    """
    すべての小説のエピソードをクリーンアップする
    """
    conn = sqlite3.connect(DATABASE_PATH)
    
    try:
        # すべての小説のncodeとratingを取得
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT n_code, rating FROM novels_descs')
        novels = cursor.fetchall()

        for ncode, rating in novels:
            logger.info(f"小説 {ncode} のエピソードクリーンアップを開始")
            clean_duplicate_episodes(ncode, rating)

    except sqlite3.Error as e:
        logger.error(f"データベース処理中にエラーが発生しました: {e}")

    finally:
        conn.close()


def clean_single_novel(ncode):
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT rating FROM novels_descs WHERE n_code = ? LIMIT 1', (ncode,))
        row = cursor.fetchone()
        rating = row[0] if row else 0

        logger.info(f"Starting cleanup for novel {ncode}")
        clean_duplicate_episodes(ncode, rating)
    except sqlite3.Error as e:
        logger.error(f"Database error occurred: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    # すべての小説のエピソードをクリーンアップ
    clean_all_novels_episodes()
