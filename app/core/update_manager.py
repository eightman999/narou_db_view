"""
小説の更新処理を管理するモジュールの改良
"""
import datetime
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
                    # 安全にint型に変換
                    current_ep_int = int(current_ep) if current_ep is not None else 0
                    general_all_no_int = int(general_all_no) if general_all_no is not None else 0

                    self.shinchaku_ep += (general_all_no_int - current_ep_int)
                    self.shinchaku_count += 1
                    self.shinchaku_novels.append((n_code, title, current_ep_int, general_all_no_int, rating))

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

            # 安全にint型に変換
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

            # デバッグ情報: 受け取った小説リストの構造を出力
            logger.debug(f"update_novels called with {total} novels")
            for i, novel in enumerate(novels):
                logger.debug(f"Novel {i + 1}: Type={type(novel)}, Length={len(novel)}, Content={novel}")

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
            # 全体の進捗計算
            logger.debug("進捗計算のためのエピソード情報")
            total_episodes_to_update = 0
            for i, novel in enumerate(novels):
                logger.debug(f"Novel {i + 1} for progress calc: {novel}")
                try:
                    current_ep_raw = novel[2]
                    total_ep_raw = novel[3]
                    logger.debug(
                        f"Raw values: current_ep={current_ep_raw}, total_ep={total_ep_raw}, types: {type(current_ep_raw)}, {type(total_ep_raw)}")

                    current_ep = int(current_ep_raw) if current_ep_raw is not None else 0
                    total_ep = int(total_ep_raw) if total_ep_raw is not None else 0

                    logger.debug(f"Converted values: current_ep={current_ep}, total_ep={total_ep}")

                    if total_ep > current_ep:
                        episodes_delta = total_ep - current_ep
                        total_episodes_to_update += episodes_delta
                        logger.debug(f"Adding {episodes_delta} episodes to update count")
                except (IndexError, ValueError, TypeError) as e:
                    logger.error(f"Error calculating progress for novel {i + 1}: {e}")
                    logger.error(f"Novel data: {novel}")
                    continue

            logger.debug(f"Total episodes to update: {total_episodes_to_update}")
            updated_episodes = 0

            # 現在の日時を取得（エピソード更新時に使用）
            current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            for i, novel_data in enumerate(novels):
                logger.debug(f"Processing novel {i + 1}/{total}: {novel_data}")

                try:
                    # インデックスエラーを避けるための処理
                    if len(novel_data) < 5:
                        logger.error(f"Novel data has insufficient elements: {novel_data}")
                        continue

                    n_code = novel_data[0]
                    title = novel_data[1]
                    current_ep_raw = novel_data[2]
                    total_ep_raw = novel_data[3]
                    rating = novel_data[4]

                    logger.debug(f"Extracted values: n_code={n_code}, title={title}, "
                                 f"current_ep_raw={current_ep_raw}, total_ep_raw={total_ep_raw}, "
                                 f"rating={rating}")

                    try:
                        current_ep = int(current_ep_raw) if current_ep_raw is not None else 0
                        total_ep = int(total_ep_raw) if total_ep_raw is not None else 0
                        logger.debug(f"Converted episode numbers: current_ep={current_ep}, total_ep={total_ep}")
                    except (ValueError, TypeError) as e:
                        logger.error(f"Error converting episode numbers: {e}")
                        logger.error(f"Raw values: current_ep={current_ep_raw}, total_ep={total_ep_raw}")
                        continue

                    novel_progress = (i / total) * 100

                    if progress_queue:
                        progress_queue.put({
                            'percent': int(novel_progress),
                            'message': f"[{i + 1}/{total}] {title}(ID:{n_code}) の更新を開始します..."
                        })

                    # 不足しているエピソードを取得
                    episode_count = total_ep - current_ep
                    logger.debug(f"Episodes to fetch: {episode_count}")

                    # 更新があるかどうかのフラグ
                    has_update = False

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
                        logger.debug(f"Fetching episode {ep_no} for novel {n_code}")
                        episode_content, episode_title = catch_up_episode(n_code, ep_no, rating)

                        # データベースに保存
                        if episode_content and episode_title:
                            # タイムスタンプ付きでエピソードを保存
                            logger.debug(f"Saving episode {ep_no} with title: {episode_title}")
                            self.db_manager.insert_episode(n_code, ep_no, episode_content, episode_title, current_time)
                            has_update = True
                        else:
                            logger.warning(f"Failed to get content for episode {ep_no}")

                        updated_episodes += 1

                    # 更新があった場合、小説テーブルのupdate_atを更新
                    if has_update:
                        logger.debug(f"Updating timestamp for novel {n_code}")
                        self.db_manager.execute_query(
                            "UPDATE novels_descs SET updated_at = ? WHERE n_code = ?",
                            (current_time, n_code)
                        )

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
                    logger.error(
                        f"小説 {novel_data[0] if len(novel_data) > 0 else 'unknown'} の更新中にエラーが発生しました: {e}")
                    logger.error(f"Novel data: {novel_data}")
                    if progress_queue:
                        progress_queue.put({
                            'message': f"[{i + 1}/{total}] 更新中にエラーが発生しました: {e}"
                        })

            if progress_queue:
                progress_queue.put({
                    'percent': 100,
                    'message': "すべての更新処理が完了しました。"
                })

        except Exception as e:
            logger.error(f"複数小説の更新エラー: {e}")
            import traceback
            logger.error(f"詳細エラー情報: {traceback.format_exc()}")
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
                    'message': f"{total_missing}個の欠落エピソードを取得します...\n欠落エピソード: {', '.join(map(str, missing_episodes))}"
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
                    # 現在の日時を取得してタイムスタンプとして使用
                    current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    self.db_manager.insert_episode(ncode, ep_no, episode_content, episode_title, current_time)

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

            # 安全にint型に変換
            general_all_no_int = int(general_all_no) if general_all_no is not None else 0

            if not general_all_no or general_all_no_int <= 0:
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
                    'message': f"既存のエピソードを削除しました。全{general_all_no_int}話を再取得します..."
                })

            # すべてのエピソードを取得して保存
            for i, ep_no in enumerate(range(1, general_all_no_int + 1)):
                # 進捗率計算
                progress_percent = int((i / general_all_no_int) * 100)

                if progress_queue:
                    progress_queue.put({
                        'percent': progress_percent,
                        'message': f"エピソード {ep_no}/{general_all_no_int} を取得中... ({progress_percent}%)"
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

    def update_specific_episodes(self, ncode, episode_list, progress_queue=None, on_complete=None):
        """
        指定された小説の特定エピソードのみを更新

        Args:
            ncode (str): 小説コード
            episode_list (list): 更新するエピソード番号のリスト
            progress_queue (Queue, optional): 進捗状況を通知するキュー
            on_complete (callable, optional): 完了時に呼び出すコールバック関数
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

                if on_complete:
                    on_complete()
                return

            title = novel[1]
            rating = novel[4] if len(novel) > 4 else None

            # 指定されたエピソードが空の場合
            if not episode_list:
                if progress_queue:
                    progress_queue.put({
                        'show': True,
                        'percent': 100,
                        'message': f"小説 [{title}] に更新するエピソードはありません"
                    })

                if on_complete:
                    on_complete()
                return

            total_episodes = len(episode_list)

            if progress_queue:
                progress_queue.put({
                    'show': True,
                    'percent': 0,
                    'message': f"小説 [{title}] の {total_episodes} 話を更新します"
                })

            # 現在の日時を取得（エピソード更新時に使用）
            current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # エピソードを取得して保存
            for i, ep_no in enumerate(episode_list):
                # 進捗率計算
                progress_percent = int((i / total_episodes) * 100)

                if progress_queue:
                    progress_queue.put({
                        'percent': progress_percent,
                        'message': f"エピソード {i + 1}/{total_episodes} (No.{ep_no}) を取得中... ({progress_percent}%)"
                    })

                # エピソードを取得
                episode_content, episode_title = catch_up_episode(ncode, ep_no, rating)

                # データベースに保存
                if episode_content and episode_title:
                    self.db_manager.insert_episode(ncode, ep_no, episode_content, episode_title, current_time)
                else:
                    logger.warning(f"エピソード {ncode}-{ep_no} の取得に失敗しました")

            # 総エピソード数を更新
            self.db_manager.update_total_episodes(ncode)

            # 小説テーブルのupdate_atを更新
            self.db_manager.execute_query(
                "UPDATE novels_descs SET updated_at = ? WHERE n_code = ?",
                (current_time, ncode)
            )

            # 小説キャッシュをクリア
            self.novel_manager.clear_cache(ncode)

            if progress_queue:
                progress_queue.put({
                    'percent': 100,
                    'message': f"小説 [{title}] の指定エピソード {total_episodes}話の更新が完了しました"
                })

            logger.info(f"小説 {ncode} の指定エピソード {total_episodes}話の更新が完了しました")

        except Exception as e:
            logger.error(f"指定エピソード更新エラー: {e}")
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