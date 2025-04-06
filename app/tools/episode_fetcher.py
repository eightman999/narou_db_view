import threading
import queue
from concurrent.futures import ThreadPoolExecutor
from app.database.db_handler import DatabaseHandler
from app.utils.logger_manager import get_logger

# ロガーの設定
logger = get_logger('EpisodeFetcher')


class EpisodeFetcher:
    """
    マルチスレッドでエピソードを取得・保存するクラス
    """

    def __init__(self, max_workers=10):
        """
        Args:
            max_workers (int): 同時に実行するスレッドの最大数
        """
        self.max_workers = max_workers
        self.db = DatabaseHandler()
        self.fetch_queue = queue.Queue()  # 取得待ちのエピソード情報を格納
        self.result_queue = queue.Queue()  # 取得結果を格納
        self.stop_event = threading.Event()  # スレッド停止用のイベント

    def fetch_episode(self, ncode, episode_no, rating):
        """
        指定されたエピソードを取得

        Args:
            ncode (str): 小説コード
            episode_no (int): エピソード番号
            rating (int): 小説の年齢制限レーティング

        Returns:
            tuple: (episode_content, episode_title)
        """
        from app.core.checker import catch_up_episode

        try:
            logger.info(f"エピソード取得開始: {ncode} - {episode_no}")
            episode_content, episode_title = catch_up_episode(ncode, episode_no, rating)
            logger.info(f"エピソード取得完了: {ncode} - {episode_no} - タイトル: {episode_title}")

            # 取得結果をキューに入れる
            self.result_queue.put((ncode, episode_no, episode_content, episode_title))

        except Exception as e:
            logger.error(f"エピソード取得エラー: {ncode} - {episode_no} - {str(e)}")

    def save_episode_worker(self):
        """
        取得したエピソードをデータベースに保存するワーカースレッド
        """
        while not (self.stop_event.is_set() and self.result_queue.empty()):
            try:
                # タイムアウト付きでキューからデータを取得
                ncode, episode_no, content, title = self.result_queue.get(timeout=1)

                try:
                    # データベースに保存
                    self.db.insert_episode(ncode, episode_no, content, title)
                    logger.info(f"エピソード保存完了: {ncode} - {episode_no}")
                except Exception as e:
                    logger.error(f"エピソード保存エラー: {ncode} - {episode_no} - {str(e)}")

                self.result_queue.task_done()

            except queue.Empty:
                # タイムアウトした場合は次のループへ
                continue

    def update_novel_episodes(self, ncode, current_ep, target_ep, rating):
        """
        指定された小説の不足しているエピソードを更新

        Args:
            ncode (str): 小説コード
            current_ep (int): 現在保存されているエピソード数
            target_ep (int): 目標エピソード数
            rating (int): 小説の年齢制限レーティング

        Returns:
            bool: 処理が成功したかどうか
        """
        if target_ep <= current_ep:
            logger.info(f"小説 {ncode} は既に最新です (現在: {current_ep}, 目標: {target_ep})")
            return True

        logger.info(f"小説 {ncode} の更新開始 (現在: {current_ep}, 目標: {target_ep})")

        # 保存用ワーカースレッドを開始
        save_thread = threading.Thread(target=self.save_episode_worker)
        save_thread.daemon = True
        save_thread.start()

        # エピソード取得をThreadPoolExecutorで実行
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 不足しているエピソードの取得をスケジュール
            for ep_num in range(current_ep + 1, target_ep + 1):
                executor.submit(self.fetch_episode, ncode, ep_num, rating)

        # すべてのエピソード取得が完了するのを待つ
        self.stop_event.set()
        save_thread.join()

        # 総エピソード数を更新
        self.db.update_total_episodes(ncode)

        logger.info(f"小説 {ncode} の更新完了 ({target_ep - current_ep}話追加)")
        return True

    def update_missing_episodes(self, ncode, rating):
        """
        指定された小説の欠落しているエピソードを更新

        Args:
            ncode (str): 小説コード
            rating (int): 小説の年齢制限レーティング

        Returns:
            list: 新たに追加されたエピソード番号のリスト
        """
        # 欠落しているエピソードを検索
        missing_episodes = self.db.find_missing_episodes(ncode)

        if not missing_episodes:
            logger.info(f"小説 {ncode} に欠落しているエピソードはありません")
            return []

        logger.info(f"小説 {ncode} の欠落エピソード更新開始 (欠落数: {len(missing_episodes)})")

        # 保存用ワーカースレッドを開始
        save_thread = threading.Thread(target=self.save_episode_worker)
        save_thread.daemon = True
        save_thread.start()

        # エピソード取得をThreadPoolExecutorで実行
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 欠落しているエピソードの取得をスケジュール
            for ep_num in missing_episodes:
                executor.submit(self.fetch_episode, ncode, ep_num, rating)

        # すべてのエピソード取得が完了するのを待つ
        self.stop_event.set()
        save_thread.join()

        logger.info(f"小説 {ncode} の欠落エピソード更新完了 ({len(missing_episodes)}話追加)")
        return missing_episodes

    def update_all_novels(self, novel_list):
        """
        複数の小説を一括更新

        Args:
            novel_list (list): 更新する小説のリスト [(ncode, title, current_ep, target_ep, rating), ...]

        Returns:
            int: 更新された小説の数
        """
        updated_count = 0

        for ncode, title, current_ep, target_ep, rating in novel_list:
            logger.info(f"小説更新開始: {title} ({ncode})")

            try:
                if self.update_novel_episodes(ncode, current_ep, target_ep, rating):
                    updated_count += 1
            except Exception as e:
                logger.error(f"小説更新エラー: {title} ({ncode}) - {str(e)}")

        logger.info(f"一括更新完了: {updated_count}/{len(novel_list)}作品を更新")
        return updated_count