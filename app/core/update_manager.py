"""
小説の更新処理を管理するモジュールの改良
"""
import threading
from app.utils.logger_manager import get_logger
from app.core.checker import catch_up_episode

# ロガーの設定
logger = get_logger('UpdateManager')


class UpdateManager:
    """小説の更新処理を管理するクラス"""

    def __init__(self, db_manager, novel_manager):
        """
        初期化

        Args:
            db_manager: データベースマネージャのインスタンス
            novel_manager: 小説マネージャのインスタンス
        """
        self.db_manager = db_manager
        self.novel_manager = novel_manager
        self.lock = threading.RLock()

        # 更新情報のキャッシュ
        self.shinchaku_ep = 0
        self.shinchaku_novels = []
        self.shinchaku_count = 0

    def check_shinchaku(self):
        """
        新着小説をチェック

        Returns:
            tuple: (新着エピソード数, 新着小説リスト, 新着小説数)
        """
        with self.lock:
            try:
                # 更新が必要な小説を取得
                needs_update = self.db_manager.get_novels_needing_update()

                self.shinchaku_ep = 0
                self.shinchaku_count = 0
                self.shinchaku_novels = []

                for n_code, title, current_ep, general_all_no, rating in needs_update:
                    self.shinchaku_ep += (general_all_no - current_ep)
                    self.shinchaku_count += 1
                    self.shinchaku_novels.append((n_code, title, current_ep, general_all_no, rating))

                logger.info(f"新着: {self.shinchaku_count}件{self.shinchaku_ep}話")
                return self.shinchaku_ep, self.shinchaku_novels, self.shinchaku_count

            except Exception as e:
                logger.error(f"新着チェックエラー: {e}")
                return 0, [], 0

    def update_novel(self, novel, progress_queue=None, on_complete=None):
        """
        単一の小説を更新

        Args:
            novel: 小説データ (n_code, title, ...)
            progress_queue: 進捗状況を通知するキュー
            on_complete: 完了時に呼び出すコールバック関数
        """
        try:
            n_code = novel[0]
            title = novel[1] if len(novel) > 1 else "不明なタイトル"

            current_ep = int(novel[5]) if len(novel) > 5 and novel[5] is not None else 0
            total_ep = int(novel[6]) if len(novel) > 6 and novel[6] is not None else 0
            rating = novel[4] if len(novel) > 4 else None

            if progress_queue:
                progress_queue.put({
                    'show': True,
                    'percent': 0,
                    'message': f"小説 [{title}] (ID:{n_code}) の更新を開始します..."
                })

            # 更新が必要なエピソードを取得
            if total_ep <= current_ep:
                if progress_queue:
                    progress_queue.put({
                        'percent': 100,
                        'message': f"小説 [{title}] は既に最新です"
                    })
                return

            # 不足しているエピソード数
            missing_episode_count = total_ep - current_ep

            # 不足しているエピソードを取得
            for i, ep_no in enumerate(range(current_ep + 1, total_ep + 1)):
                # 進捗率計算
                progress_percent = int((i / missing_episode_count) * 100)

                if progress_queue:
                    progress_queue.put({
                        'percent': progress_percent,
                        'message': f"エピソード {ep_no}/{total_ep} を取得中... ({progress_percent}%)"
                    })

                # エピソードを取得
                episode_content, episode_title = catch_up_episode(n_code, ep_no, rating)

                # データベースに保存
                if episode_content and episode_title:
                    self.db_manager.insert_episode(n_code, ep_no, episode_content, episode_title)
                else:
                    logger.warning(f"エピソード {n_code}-{ep_no} の取得に失敗しました")

            # 総エピソード数を更新
            self.db_manager.update_total_episodes(n_code)

            # 小説キャッシュをクリア
            self.novel_manager.clear_cache(n_code)

            if progress_queue:
                progress_queue.put({
                    'percent': 100,
                    'message': f"小説 [{title}] の更新が完了しました"
                })

            logger.info(f"小説 {n_code} ({title}) の更新が完了しました")

        except Exception as e:
            logger.error(f"小説更新エラー: {e}")
            if progress_queue:
                progress_queue.put({
                    'percent': 0,
                    'message': f"エラー: {e}"
                })

        finally:
            # 更新情報を再チェック
            self.check_shinchaku()

            # 完了コールバックの呼び出し
            if on_complete:
                on_complete()

    def update_novels(self, novels, progress_queue=None, on_complete=None):
        """
        複数の小説を更新

        Args:
            novels: 小説データのリスト [(n_code, title, current_ep, total_ep, rating), ...]
            progress_queue: 進捗状況を通知するキュー
            on_complete: 完了時に呼び出すコールバック関数
        """
        try:
            total = len(novels)

            if total == 0:
                if progress_queue:
                    progress_queue.put({
                        'show': True,
                        'percent': 100,
                        'message': "更新が必要な小説がありません。"
                    })

                if on_complete:
                    on_complete()
                return

            if progress_queue:
                progress_queue.put({
                    'show': True,
                    'percent': 0,
                    'message': f"合計 {total} 件の小説を更新します。"
                })

            # 全体の進捗計算用
            total_episodes_to_update = sum(
                novel[3] - novel[2] for novel in novels if novel[3] > novel[2]
            )
            updated_episodes = 0

            for i, novel_data in enumerate(novels):
                n_code, title, current_ep, total_ep, rating = novel_data

                novel_progress = (i / total) * 100

                if progress_queue:
                    progress_queue.put({
                        'percent': int(novel_progress),
                        'message': f"[{i + 1}/{total}] {title}(ID:{n_code}) の更新を開始します..."
                    })

                try:
                    # 不足しているエピソードを取得
                    episode_count = total_ep - current_ep

                    for j, ep_no in enumerate(range(current_ep + 1, total_ep + 1)):
                        # 個別の小説の進捗と全体の進捗を計算
                        episode_progress = j / episode_count if episode_count > 0 else 1
                        overall_progress = novel_progress + (episode_progress * (100 / total))

                        if progress_queue:
                            progress_queue.put({
                                'percent': int(overall_progress),
                                'message': f"[{i + 1}/{total}] {title} - エピソード {ep_no}/{total_ep} を取得中..."
                            })

                        # エピソードを取得
                        episode_content, episode_title = catch_up_episode(n_code, ep_no, rating)

                        # データベースに保存
                        if episode_content and episode_title:
                            self.db_manager.insert_episode(n_code, ep_no, episode_content, episode_title)

                        updated_episodes += 1

                    # 総エピソード数を更新
                    self.db_manager.update_total_episodes(n_code)

                    # 小説キャッシュをクリア
                    self.novel_manager.clear_cache(n_code)

                    if progress_queue:
                        progress_queue.put({
                            'percent': int(novel_progress + (100 / total)),
                            'message': f"[{i + 1}/{total}] {title} - 更新完了"
                        })

                    logger.info(f"小説 {n_code} ({title}) の更新が完了しました")

                except Exception as e:
                    logger.error(f"小説 {n_code} の更新中にエラーが発生しました: {e}")
                    if progress_queue:
                        progress_queue.put({
                            'message': f"[{i + 1}/{total}] {title} の更新中にエラーが発生しました: {e}"
                        })

            if progress_queue:
                progress_queue.put({
                    'percent': 100,
                    'message': "すべての更新処理が完了しました。"
                })

        except Exception as e:
            logger.error(f"複数小説の更新エラー: {e}")
            if progress_queue:
                progress_queue.put({
                    'percent': 0,
                    'message': f"エラー: {e}"
                })

        finally:
            # 更新情報を再チェック
            self.check_shinchaku()

            # 完了コールバックの呼び出し
            if on_complete:
                on_complete()

    def update_all_novels(self, progress_queue=None, on_complete=None):
        """
        全ての更新可能な小説を更新

        Args:
            progress_queue: 進捗状況を通知するキュー
            on_complete: 完了時に呼び出すコールバック関数
        """
        try:
            # 更新が必要な小説を取得
            needs_update = self.db_manager.get_novels_needing_update()

            if not needs_update:
                if progress_queue:
                    progress_queue.put({
                        'show': True,
                        'percent': 100,
                        'message': "更新が必要な小説がありません。"
                    })

                if on_complete:
                    on_complete()
                return

            # 更新処理を実行
            self.update_novels(needs_update, progress_queue, on_complete)

        except Exception as e:
            logger.error(f"全小説の更新エラー: {e}")
            if progress_queue:
                progress_queue.put({
                    'percent': 0,
                    'message': f"エラー: {e}"
                })

            # 完了コールバックの呼び出し
            if on_complete:
                on_complete()

    def fetch_missing_episodes(self, ncode, progress_queue=None, on_complete=None):
        """
        欠落しているエピソードを取得

        Args:
            ncode: 小説コード
            progress_queue: 進捗状況を通知するキュー
            on_complete: 完了時に呼び出すコールバック関数
        """
        try:
            # この小説のデータを取得
            novel = self.novel_manager.get_novel(ncode)
            if not novel:
                if progress_queue:
                    progress_queue.put({
                        'show': True,
                        'percent': 0,
                        'message': f"エラー: 小説 {ncode} が見つかりません"
                    })
                return

            title = novel[1]
            rating = novel[4] if len(novel) > 4 else None

            if progress_queue:
                progress_queue.put({
                    'show': True,
                    'percent': 0,
                    'message': f"小説 [{title}] の欠落エピソード検索中..."
                })

            # 欠落エピソードを検索
            missing_episodes = self.db_manager.find_missing_episodes(ncode)

            if not missing_episodes:
                if progress_queue:
                    progress_queue.put({
                        'show': True,
                        'percent': 100,
                        'message': f"小説 [{title}] に欠落エピソードはありません"
                    })

                if on_complete:
                    on_complete()
                return

            total_missing = len(missing_episodes)

            if progress_queue:
                progress_queue.put({
                    'show': True,
                    'percent': 0,
                    'message': f"{total_missing}個の欠落エピソードを取得します..."
                })

            # 欠落エピソードを取得して保存
            for i, ep_no in enumerate(missing_episodes):
                # 進捗率計算
                progress_percent = int((i / total_missing) * 100)

                if progress_queue:
                    progress_queue.put({
                        'percent': progress_percent,
                        'message': f"エピソード {i + 1}/{total_missing} (No.{ep_no}) を取得中... ({progress_percent}%)"
                    })

                # エピソードを取得
                episode_content, episode_title = catch_up_episode(ncode, ep_no, rating)

                # データベースに保存
                if episode_content and episode_title:
                    self.db_manager.insert_episode(ncode, ep_no, episode_content, episode_title)

            # 総エピソード数を更新
            self.db_manager.update_total_episodes(ncode)

            # 小説キャッシュをクリア
            self.novel_manager.clear_cache(ncode)

            if progress_queue:
                progress_queue.put({
                    'percent': 100,
                    'message': f"小説 [{title}] の欠落エピソード {total_missing}個を取得しました"
                })

            logger.info(f"小説 {ncode} の欠落エピソード {total_missing}個を取得しました")

        except Exception as e:
            logger.error(f"欠落エピソード取得エラー: {e}")
            if progress_queue:
                progress_queue.put({
                    'percent': 0,
                    'message': f"エラー: {e}"
                })

        finally:
            # 更新情報を再チェック
            self.check_shinchaku()

            # 完了コールバックの呼び出し
            if on_complete:
                on_complete()

    def refetch_all_episodes(self, ncode, progress_queue=None, on_complete=None):
        """
        すべてのエピソードを再取得

        Args:
            ncode: 小説コード
            progress_queue: 進捗状況を通知するキュー
            on_complete: 完了時に呼び出すコールバック関数
        """
        try:
            # この小説のデータを取得
            novel = self.novel_manager.get_novel(ncode)
            if not novel:
                if progress_queue:
                    progress_queue.put({
                        'show': True,
                        'percent': 0,
                        'message': f"エラー: 小説 {ncode} が見つかりません"
                    })
                return

            title = novel[1]
            rating = novel[4] if len(novel) > 4 else None
            general_all_no = novel[6] if len(novel) > 6 else None

            if not general_all_no or general_all_no <= 0:
                if progress_queue:
                    progress_queue.put({
                        'show': True,
                        'percent': 0,
                        'message': f"エラー: 小説 {ncode} のエピソード総数が不明です"
                    })

                if on_complete:
                    on_complete()
                return

            if progress_queue:
                progress_queue.put({
                    'show': True,
                    'percent': 0,
                    'message': f"小説 [{title}] の全エピソード再取得中..."
                })

            # 既存のエピソードを削除
            self.db_manager.execute_query("DELETE FROM episodes WHERE ncode = ?", (ncode,))

            if progress_queue:
                progress_queue.put({
                    'percent': 0,
                    'message': f"既存のエピソードを削除しました。全{general_all_no}話を再取得します..."
                })

            # すべてのエピソードを取得して保存
            for i, ep_no in enumerate(range(1, general_all_no + 1)):
                # 進捗率計算
                progress_percent = int((i / general_all_no) * 100)

                if progress_queue:
                    progress_queue.put({
                        'percent': progress_percent,
                        'message': f"エピソード {ep_no}/{general_all_no} を取得中... ({progress_percent}%)"
                    })

                # エピソードを取得
                episode_content, episode_title = catch_up_episode(ncode, ep_no, rating)

                # データベースに保存
                if episode_content and episode_title:
                    self.db_manager.insert_episode(ncode, ep_no, episode_content, episode_title)

            # 総エピソード数を更新
            self.db_manager.update_total_episodes(ncode)

            # 小説キャッシュをクリア
            self.novel_manager.clear_cache(ncode)

            if progress_queue:
                progress_queue.put({
                    'percent': 100,
                    'message': f"小説 [{title}] の全エピソード再取得が完了しました"
                })

            logger.info(f"小説 {ncode} の全エピソード再取得が完了しました")

        except Exception as e:
            logger.error(f"全エピソード再取得エラー: {e}")
            if progress_queue:
                progress_queue.put({
                    'percent': 0,
                    'message': f"エラー: {e}"
                })

        finally:
            # 更新情報を再チェック
            self.check_shinchaku()

            # 完了コールバックの呼び出し
            if on_complete:
                on_complete()