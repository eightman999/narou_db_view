import sqlite3
import time
import random
from app.core.checker import catch_up_episode
from app.utils.logger_manager import get_logger

# ロガーの設定
logger = get_logger('DuplicatesHandler')


class DuplicatesHandler:
    """
    重複データを処理し、データの整合性を確保するクラス
    - 重複する小説エントリの統合
    - 壊れたエピソードの検出と再取得
    - 欠落エピソードの特定と補完
    """

    def __init__(self, db_path='database/novel_status.db', max_retries=3, retry_delay=5):
        """
        初期化

        Args:
            db_path (str): データベースファイルのパス
            max_retries (int): エピソード取得の最大再試行回数
            retry_delay (int): 再試行間の待機時間（秒）
        """
        self.db_path = db_path
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def remove_novel_duplicates(self):
        """
        重複する小説エントリを統合し、最適な情報を保持する
        """
        try:
            # データベースに接続
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 重複するn_codeを処理するためのクエリ
            query = '''
            WITH RankedEntries AS (
                SELECT 
                    rowid, n_code, title, author, Synopsis, main_tag, sub_tag,
                    -- authorが半角スペースでないものを優先、次にtitleが半角スペースでないものを優先
                    CASE 
                        WHEN TRIM(author) != '' THEN 1
                        WHEN TRIM(title) != '' THEN 2
                        ELSE 3
                    END AS priority
                FROM novels_descs
            ),
            RankedWithRowNum AS (
                -- 各n_code内で優先順位が最も高い行を見つける
                SELECT *, ROW_NUMBER() OVER (PARTITION BY n_code ORDER BY priority) AS row_num
                FROM RankedEntries
            )
            -- 最も優先順位が高い行のみを残す
            DELETE FROM novels_descs
            WHERE rowid NOT IN (
                SELECT rowid 
                FROM RankedWithRowNum
                WHERE row_num = 1
            );
            '''

            # クエリを実行
            cursor.execute(query)
            deleted_count = cursor.rowcount

            # コミットして変更を保存
            conn.commit()
            logger.info(f"小説テーブルから {deleted_count} 件の重複エントリを削除しました")

            return deleted_count

        except sqlite3.Error as e:
            logger.error(f"小説の重複削除中にエラーが発生しました: {e}")
            if conn:
                conn.rollback()
            return 0

        finally:
            if conn:
                conn.close()

    def analyze_episode_quality(self, ncode=None):
        """
        エピソードの品質（完全性）を分析し、修復が必要なエピソードを特定する

        Args:
            ncode (str, optional): 特定の小説コード。Noneの場合は全小説を分析

        Returns:
            dict: 問題のあるエピソードのリスト {n_code: [(episode_no, issue_type), ...]}
        """
        try:
            # データベースに接続
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            problematic_episodes = {}

            # 分析対象のncodeリストを取得
            if ncode:
                cursor.execute("SELECT n_code, rating FROM novels_descs WHERE n_code = ?", (ncode,))
                novels = cursor.fetchall()
            else:
                cursor.execute("SELECT n_code, rating FROM novels_descs")
                novels = cursor.fetchall()

            for n_code, rating in novels:
                # この小説のエピソードを取得
                cursor.execute("""
                    SELECT episode_no, body, e_title, rowid,
                    LENGTH(body) as body_length
                    FROM episodes 
                    WHERE ncode = ? 
                    ORDER BY CAST(episode_no AS INTEGER)
                """, (n_code,))

                episodes = cursor.fetchall()
                bad_episodes = []

                for episode in episodes:
                    episode_no, body, title, rowid, body_length = episode

                    # 問題を検出
                    if not body or body_length < 50:
                        bad_episodes.append((episode_no, "empty_or_short", rowid))
                    elif "エラー" in body or "Error" in body or "失敗" in body:
                        bad_episodes.append((episode_no, "error_content", rowid))
                    elif not title or title.strip() == "":
                        bad_episodes.append((episode_no, "missing_title", rowid))

                if bad_episodes:
                    problematic_episodes[n_code] = (bad_episodes, rating)

            return problematic_episodes

        except sqlite3.Error as e:
            logger.error(f"エピソード品質分析中にエラーが発生しました: {e}")
            return {}

        finally:
            if conn:
                conn.close()

    def repair_problematic_episodes(self, ncode=None):
        """
        問題のあるエピソードを修復する

        Args:
            ncode (str, optional): 特定の小説コード。Noneの場合は全小説を修復

        Returns:
            int: 修復したエピソードの数
        """
        # 問題のあるエピソードを分析
        problematic_dict = self.analyze_episode_quality(ncode)

        if not problematic_dict:
            logger.info("修復が必要なエピソードはありません")
            return 0

        repaired_count = 0

        # データベースに接続
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            for n_code, (bad_episodes, rating) in problematic_dict.items():
                logger.info(f"小説 {n_code} の問題エピソード {len(bad_episodes)}件を修復します")

                for episode_no, issue_type, rowid in bad_episodes:
                    logger.info(f"エピソード {n_code}-{episode_no} ({issue_type}) を再取得します")

                    # エピソードを再取得（リトライロジック付き）
                    for attempt in range(self.max_retries):
                        try:
                            # エピソードを取得
                            body, title = catch_up_episode(n_code, episode_no, rating)

                            # 正常に取得できたかチェック
                            if body and len(body) > 50 and title and "エラー" not in body and "Error" not in body:
                                # データベースを更新
                                cursor.execute("""
                                    UPDATE episodes
                                    SET body = ?, e_title = ?
                                    WHERE rowid = ?
                                """, (body, title, rowid))

                                conn.commit()
                                repaired_count += 1
                                logger.info(f"エピソード {n_code}-{episode_no} を正常に修復しました")
                                break
                            else:
                                logger.warning(
                                    f"エピソード {n_code}-{episode_no} の取得結果が不十分です (試行 {attempt + 1}/{self.max_retries})")
                                time.sleep(self.retry_delay)
                        except Exception as e:
                            logger.error(
                                f"エピソード {n_code}-{episode_no} の再取得中にエラー: {e} (試行 {attempt + 1}/{self.max_retries})")
                            time.sleep(self.retry_delay)

            logger.info(f"合計 {repaired_count} 件のエピソードを修復しました")
            return repaired_count

        except sqlite3.Error as e:
            logger.error(f"エピソード修復中にデータベースエラーが発生しました: {e}")
            conn.rollback()
            return 0

        finally:
            conn.close()

    def remove_episode_duplicates(self):
        """
        重複するエピソードエントリを削除し、最良のものを残す

        Returns:
            int: 削除した重複エピソードの数
        """
        try:
            # データベースに接続
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 重複エピソードの識別
            cursor.execute("""
                SELECT ncode, episode_no, COUNT(*) as count
                FROM episodes
                GROUP BY ncode, episode_no
                HAVING count > 1
            """)

            duplicates = cursor.fetchall()

            if not duplicates:
                logger.info("重複するエピソードはありません")
                return 0

            deleted_count = 0

            for ncode, episode_no, count in duplicates:
                # 各重複エピソードセットを処理
                cursor.execute("""
                    SELECT rowid, body, e_title, LENGTH(body) as body_length,
                    (CASE 
                        WHEN body LIKE '%エラー%' OR body LIKE '%Error%' THEN 1 
                        ELSE 0 
                    END) as has_error
                    FROM episodes 
                    WHERE ncode = ? AND episode_no = ?
                    ORDER BY has_error, body_length DESC
                """, (ncode, episode_no))

                entries = cursor.fetchall()

                if len(entries) <= 1:
                    continue

                # 先頭の（最良の）エントリを除くすべてを削除
                best_entry = entries[0]
                rowids_to_delete = [entry[0] for entry in entries[1:]]

                if rowids_to_delete:
                    placeholders = ', '.join(['?'] * len(rowids_to_delete))
                    cursor.execute(f"DELETE FROM episodes WHERE rowid IN ({placeholders})", rowids_to_delete)
                    deleted_count += len(rowids_to_delete)

                # 最良のエントリにもエラーがある場合は修復の候補としてマーク
                if best_entry[4] == 1:  # has_error フラグがセットされている
                    logger.warning(
                        f"エピソード {ncode}-{episode_no} の最良エントリにもエラーがあります（後で修復が必要）")

            conn.commit()
            logger.info(f"合計 {deleted_count} 件の重複エピソードを削除しました")
            return deleted_count

        except sqlite3.Error as e:
            logger.error(f"エピソードの重複削除中にエラーが発生しました: {e}")
            if conn:
                conn.rollback()
            return 0

        finally:
            if conn:
                conn.close()

    def run_full_cleanup(self):
        """
        完全なデータクリーンアップを実行
        1. 小説テーブルの重複削除
        2. エピソードテーブルの重複削除
        3. 問題のあるエピソードの修復

        Returns:
            tuple: (削除した小説の数, 削除したエピソードの数, 修復したエピソードの数)
        """
        logger.info("完全なデータクリーンアップを開始します")

        # 1. 小説テーブルの重複削除
        novel_deletions = self.remove_novel_duplicates()
        logger.info(f"小説テーブルから {novel_deletions} 件の重複を削除しました")

        # 2. エピソードテーブルの重複削除
        episode_deletions = self.remove_episode_duplicates()
        logger.info(f"エピソードテーブルから {episode_deletions} 件の重複を削除しました")

        # 3. 問題のあるエピソードの修復
        repaired_count = self.repair_problematic_episodes()
        logger.info(f"{repaired_count} 件のエピソードを修復しました")

        logger.info("データクリーンアップが完了しました")
        return (novel_deletions, episode_deletions, repaired_count)


# 単独実行時のエントリポイント
if __name__ == "__main__":
    handler = DuplicatesHandler()
    results = handler.run_full_cleanup()
    print(
        f"クリーンアップ結果: 小説重複削除: {results[0]}件, エピソード重複削除: {results[1]}件, エピソード修復: {results[2]}件")