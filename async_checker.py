import asyncio
import aiohttp
import random
import gzip
import sqlite3
import os
import yaml
import logging
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import urlparse

# 元のchecker.pyからのインポート
from checker import USER_AGENTS, load_conf

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("async_novel_updates.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("async_checker")


class NovelUpdater:
    def __init__(self, db_path='database/novel_status.db'):
        self.db_path = db_path
        self.session = None
        self.progress_callback = None
        self.cancel_flag = False

    async def initialize(self):
        """初期化処理とaiohttp sessionの作成"""
        # セッションのタイムアウト設定（総合的な待機時間）
        # ClientSessionは初期化時にのみタイムアウトを設定する
        timeout = aiohttp.ClientTimeout(total=60, connect=30, sock_connect=30, sock_read=30)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def close(self):
        """セッションの終了処理"""
        if self.session:
            await self.session.close()

    def set_progress_callback(self, callback):
        """進捗通知用のコールバック関数を設定"""
        self.progress_callback = callback

    def cancel_operation(self):
        """実行中の操作をキャンセル"""
        self.cancel_flag = True
        logger.info("操作がキャンセルされました")

    def _update_progress(self, current, total, message="更新中"):
        """進捗状況の更新"""
        if self.progress_callback:
            progress = int((current / total) * 100) if total > 0 else 0
            self.progress_callback(progress, message)

    async def existence_check(self, ncode):
        """小説の存在チェックを非同期で行う"""
        rating = 0
        n_url = f"https://ncode.syosetu.com/{ncode}"
        n18_url = f"https://novel18.syosetu.com/{ncode}"

        logger.info(f"Checking {ncode}...({n_url} or {n18_url})")

        headers = {'User-Agent': random.choice(USER_AGENTS)}

        # まず通常の小説URLをチェック
        try:
            # asyncio.wait_forを使用して全体のリクエストにタイムアウトを設定
            async with asyncio.timeout(30):  # Python 3.11+ ではそのまま使用可能
                async with self.session.get(n_url, headers=headers, allow_redirects=True) as response:
                    if response.status == 200:
                        text = await response.text()
                        if "エラーが発生しました" in text:
                            rating = 4
                        elif "エラー" in text:
                            rating = 0
                        else:
                            rating = 2
                            return rating
        except asyncio.TimeoutError:
            logger.warning(f"Timeout checking normal URL for {ncode}")
        except Exception as e:
            logger.error(f"Error checking normal URL for {ncode}: {e}")

        # 18禁小説URLをチェック
        try:
            async with asyncio.timeout(30):
                async with self.session.get(n18_url, headers=headers, allow_redirects=False) as response:
                    if response.status == 200:
                        text = await response.text()
                        if "ageauth" not in text and "エラー" not in text:
                            rating = 1
        except asyncio.TimeoutError:
            logger.warning(f"Timeout checking R18 URL for {ncode}")
        except Exception as e:
            logger.error(f"Error checking R18 URL for {ncode}: {e}")

        logger.info(f"{ncode}'s rating: {rating}")
        return rating

    async def update_check(self, ncode, rating):
        """小説情報の更新確認を非同期で行う"""
        if rating == 0:
            logger.info(f"{ncode} is deleted by author")
            return None
        elif rating == 1:
            logger.info(f"{ncode} is 18+")
            n_api_url = f"https://api.syosetu.com/novel18api/api/?of=t-w-ga-s-ua&ncode={ncode}&gzip=5&json"
        elif rating == 2:
            logger.info(f"{ncode} is normal")
            n_api_url = f"https://api.syosetu.com/novelapi/api/?of=t-w-ga-s-ua&ncode={ncode}&gzip=5&json"
        elif rating == 4:
            logger.info(f"{ncode} is deleted by author or author is deleted")
            return None
        else:
            logger.error(f"Error: {ncode}'s rating is {rating}")
            return None

        try:
            headers = {'User-Agent': random.choice(USER_AGENTS)}
            async with asyncio.timeout(30):
                async with self.session.get(n_api_url, headers=headers) as response:
                    if response.status == 200:
                        content = await response.read()
                        file_path = os.path.join('dl', f"{ncode}.gz")
                        os.makedirs('dl', exist_ok=True)

                        with open(file_path, 'wb') as file:
                            file.write(content)
                        logger.info(f"File saved to {file_path}")
                        return file_path
                    else:
                        logger.error(f"Failed to download file: {response.status}")
                        return None
        except asyncio.TimeoutError:
            logger.warning(f"Timeout downloading API data for {ncode}")
            return None
        except Exception as e:
            logger.error(f"Error updating {ncode}: {e}")
            return None

    async def catch_up_episode(self, ncode, episode_no, rating):
        """エピソードを取得する非同期関数 - asyncio.timeoutを使用"""
        title = ""
        episode = ""

        EP_url = f"https://ncode.syosetu.com/{ncode}/{episode_no}/"
        if rating == 1:
            EP_url = f"https://novel18.syosetu.com/{ncode}/{episode_no}/"

        headers = {'User-Agent': random.choice(USER_AGENTS)}

        # リトライロジックを追加
        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                # asyncio.timeoutを使用してタイムアウトを設定
                async with asyncio.timeout(30):
                    async with self.session.get(EP_url, headers=headers, allow_redirects=True) as response:
                        if response.status == 200:
                            html = await response.text()
                            soup = BeautifulSoup(html, 'html.parser')

                            novel_body = soup.find('div', class_='p-novel__body')
                            title_tag = soup.find('h1', class_='p-novel__title')

                            if title_tag:
                                title = title_tag.get_text(strip=True)
                            if novel_body:
                                episode = ''.join(str(p) for p in novel_body.find_all('p'))
                            else:
                                episode = "No content found in the specified div."
                                logger.warning(f"No novel body found for {ncode} episode {episode_no}")
                        else:
                            episode = f"Failed to retrieve the episode. Status code: {response.status}"
                            logger.error(f"Failed to get episode for {ncode} episode {episode_no}: {response.status}")

                # 成功したらループを抜ける
                break

            except asyncio.TimeoutError:
                logger.warning(
                    f"Timeout fetching episode {episode_no} for {ncode} (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    # 再試行前に少し待機
                    await asyncio.sleep(retry_delay)
                else:
                    episode = f"Error: Timeout after {max_retries} attempts"
                    logger.error(f"Failed to fetch episode {episode_no} for {ncode} after {max_retries} attempts")

            except Exception as e:
                logger.error(f"Error fetching episode {episode_no} for {ncode}: {e}")
                episode = f"Error: {str(e)}"

                # 致命的なエラーの場合は再試行しない
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    break

        return episode, title

    async def single_episode(self, ncode, rating):
        """単一エピソードの小説を取得する非同期関数 - asyncio.timeoutを使用"""
        EP_url = f"https://ncode.syosetu.com/{ncode}"
        if rating == 1:
            EP_url = f"https://novel18.syosetu.com/{ncode}"

        headers = {'User-Agent': random.choice(USER_AGENTS)}

        # リトライロジックを追加
        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                # asyncio.timeoutを使用してタイムアウトを設定
                async with asyncio.timeout(30):
                    async with self.session.get(EP_url, headers=headers, allow_redirects=True) as response:
                        if response.status == 200:
                            html = await response.text()
                            soup = BeautifulSoup(html, 'html.parser')

                            novel_body = soup.find('div', class_='p-novel__body')
                            title_tag = soup.find('h1', class_='p-novel__title')

                            if title_tag:
                                title = title_tag.get_text(strip=True)
                            else:
                                title = ""

                            if novel_body:
                                episode = ''.join(str(p) for p in novel_body.find_all('p'))
                            else:
                                episode = "No content found in the specified div."
                                logger.warning(f"No novel body found for single-episode novel {ncode}")

                            return episode, title
                        else:
                            logger.error(f"Failed to get single episode for {ncode}: {response.status}")
                            if attempt < max_retries - 1:
                                await asyncio.sleep(retry_delay)
                            else:
                                return "", ""

            except asyncio.TimeoutError:
                logger.warning(f"Timeout fetching single episode for {ncode} (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    # 再試行前に少し待機
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"Failed to fetch single episode for {ncode} after {max_retries} attempts")
                    return "", ""

            except Exception as e:
                logger.error(f"Error fetching single episode for {ncode}: {e}")

                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    return "", ""

        # ループを抜けてもここに到達した場合は失敗
        return "", ""

    async def new_episode(self, ncode, past_ep, general_all_no, rating):
        """新しいエピソードを取得する非同期関数"""
        if self.cancel_flag:
            return []

        new_eps = []
        logger.info(f"Checking {ncode} for new episodes...")

        # トランザクション管理の改善
        conn = None

        try:
            # SQLiteの接続を作成
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 単一エピソード小説の場合
            if general_all_no == 1:
                episode, title = await self.single_episode(ncode, rating)
                if episode and title:
                    new_eps.append([ncode, 1, episode, title])

                    # DBに保存
                    cursor.execute("""
                        INSERT OR REPLACE INTO episodes (ncode, episode_no, body, e_title)
                        VALUES (?, ?, ?, ?)
                    """, (ncode, 1, episode, title))
                    conn.commit()
            else:
                # 複数エピソード小説の場合
                total_new_episodes = general_all_no - past_ep

                # 各エピソードを処理
                for i in range(total_new_episodes):
                    if self.cancel_flag:
                        break

                    current_ep_no = past_ep + i + 1
                    self._update_progress(
                        i + 1,
                        total_new_episodes,
                        f"{ncode}: エピソード {current_ep_no}/{general_all_no} 取得中"
                    )

                    # エピソードを取得（タイムアウトエラー対策済みの関数）
                    episode, title = await self.catch_up_episode(ncode, current_ep_no, rating)

                    if episode and title:
                        new_eps.append([ncode, current_ep_no, episode, title])

                        # 10エピソードごとにDBに保存して進捗を維持（20→10に減らして処理頻度増加）
                        if len(new_eps) >= 10:
                            try:
                                for ep in new_eps:
                                    cursor.execute("""
                                        INSERT OR REPLACE INTO episodes (ncode, episode_no, body, e_title)
                                        VALUES (?, ?, ?, ?)
                                    """, (ep[0], ep[1], ep[2], ep[3]))
                                conn.commit()
                                logger.info(f"Saved batch of {len(new_eps)} episodes for {ncode}")
                                new_eps = []
                            except sqlite3.Error as e:
                                logger.error(f"Database error while saving batch: {e}")
                                # コミットに失敗してもエピソード取得は継続

                    # スリープを入れて連続アクセスによるブロックを回避
                    # より長めのスリープで安全性を確保
                    await asyncio.sleep(2.0)

            # 残りのエピソードをDBに保存
            if new_eps:
                try:
                    for ep in new_eps:
                        cursor.execute("""
                            INSERT OR REPLACE INTO episodes (ncode, episode_no, body, e_title)
                            VALUES (?, ?, ?, ?)
                        """, (ep[0], ep[1], ep[2], ep[3]))
                    conn.commit()
                    logger.info(f"Saved final batch of {len(new_eps)} episodes for {ncode}")
                except sqlite3.Error as e:
                    logger.error(f"Database error while saving final batch: {e}")

            # total_epを更新
            try:
                cursor.execute("""
                    UPDATE novels_descs
                    SET total_ep = ?
                    WHERE n_code = ?
                """, (general_all_no, ncode))
                conn.commit()
                logger.info(f"Updated {ncode} total_ep to {general_all_no}")
            except sqlite3.Error as e:
                logger.error(f"Database error while updating total_ep: {e}")

            logger.info(f"Completed update for {ncode} with new episodes.")
            return new_eps

        except Exception as e:
            logger.error(f"Error in new_episode for {ncode}: {e}", exc_info=True)
            return []

        finally:
            # 確実に接続を閉じる
            if conn:
                try:
                    conn.close()
                except:
                    pass

    async def thawing_gz(self):
        """GZファイルを展開する非同期関数"""
        dl_dir = 'dl'
        os.makedirs('yml', exist_ok=True)

        # ThreadPoolExecutorを使用してファイル操作を別スレッドで行う
        with ThreadPoolExecutor() as executor:
            loop = asyncio.get_event_loop()
            tasks = []

            for filename in os.listdir(dl_dir):
                if filename.endswith('.gz'):
                    tasks.append(loop.run_in_executor(
                        executor,
                        self._process_gz_file,
                        os.path.join(dl_dir, filename),
                        os.path.join('yml', filename[:-3] + '.yml')
                    ))

            if tasks:
                # 進捗表示
                self._update_progress(0, len(tasks), "GZファイルを展開中...")
                completed = 0

                for future in asyncio.as_completed(tasks):
                    await future
                    completed += 1
                    self._update_progress(completed, len(tasks), "GZファイルを展開中...")

    def _process_gz_file(self, gz_path, yml_path):
        """GZファイルを処理する同期関数（ThreadPoolExecutorで実行）"""
        try:
            with gzip.open(gz_path, 'rt', encoding='utf-8') as gz_file:
                content = gz_file.read()

            with open(yml_path, 'w', encoding='utf-8') as yml_file:
                yml_file.write(content)

            logger.info(f"Decompressed and saved: {yml_path}")
            return True
        except Exception as e:
            logger.error(f"Error processing GZ file {gz_path}: {e}")
            return False

    async def yml_parse_time(self, n_codes_ratings):
        """YMLファイルを解析して小説情報を更新する非同期関数"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            total = len(n_codes_ratings)
            self._update_progress(0, total, "小説情報を更新中...")

            with ThreadPoolExecutor() as executor:
                loop = asyncio.get_event_loop()
                tasks = []

                for i, (n_code, _) in enumerate(n_codes_ratings):
                    if self.cancel_flag:
                        break

                    yml_path = os.path.join('yml', f"{n_code}.yml")
                    if not os.path.exists(yml_path):
                        logger.warning(f"File not found: {yml_path}")
                        continue

                    tasks.append(loop.run_in_executor(
                        executor,
                        self._process_yml_file,
                        yml_path,
                        n_code,
                        cursor
                    ))

                    # 進捗更新
                    self._update_progress(i + 1, total, f"小説情報を更新中: {n_code}")

                # 完了を待つ
                for future in asyncio.as_completed(tasks):
                    result = await future

            # 変更をコミット
            conn.commit()
            logger.info("Updated novel information from YML files")

        except Exception as e:
            logger.error(f"Error in yml_parse_time: {e}")
        finally:
            conn.close()

    def _process_yml_file(self, yml_path, n_code, cursor):
        """YMLファイルを処理する同期関数（ThreadPoolExecutorで実行）"""
        try:
            with open(yml_path, 'r', encoding='utf-8') as yml_file:
                try:
                    data = yaml.safe_load(yml_file)

                    # データがリスト形式の場合、[1]を取得
                    if isinstance(data, list):
                        if len(data) > 1:
                            data = data[1]
                        else:
                            logger.warning(f"Data in {yml_path} is not sufficient. Skipping.")
                            return False

                    # データが辞書形式であるか確認
                    if not isinstance(data, dict):
                        logger.warning(f"Unexpected data format in {yml_path}")
                        return False

                except yaml.YAMLError as exc:
                    logger.error(f"Error parsing YAML file {yml_path}: {exc}")
                    return False

                # データの取得
                general_all_no = data.get('general_all_no')
                allcount = data.get('allcount', 1)
                story = data.get('story', '')
                title = data.get('title', '')
                updated_at = data.get('updated_at', None)
                writer = data.get('writer', '')

                # allcount が 0 の場合スキップ
                if allcount == 0:
                    logger.info(f"Skipping {n_code} as allcount is 0")
                    return False

                if general_all_no is None:
                    logger.warning(f"Skipping {n_code}: Missing 'general_all_no'")
                    return False

                if isinstance(updated_at, datetime):
                    # updated_at を文字列に変換
                    updated_at = updated_at.strftime('%Y-%m-%d %H:%M:%S')

                try:
                    cursor.execute("""
                        UPDATE novels_descs
                        SET general_all_no = ?, Synopsis = ?, title = ?, updated_at = ?, author = ?
                        WHERE n_code = ?
                    """, (int(general_all_no), story, title, updated_at, writer, n_code))

                    return True

                except sqlite3.Error as e:
                    logger.error(f"Database update failed for {n_code}: {e}")
                    return False

        except Exception as e:
            logger.error(f"Error processing YML file {yml_path}: {e}")
            return False

    async def shinchaku_checker(self):
        """新着エピソードをチェックする非同期関数"""
        shinchaku_ep = 0
        shinchaku_novel = []
        shinchaku_novel_no = 0

        logger.info("Check_shinchaku...")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT n_code, total_ep, general_all_no, rating FROM novels_descs")
            novels = cursor.fetchall()

            total = len(novels)
            self._update_progress(0, total, "新着小説をチェック中...")

            for i, (n_code, total_ep, general_all_no, rating) in enumerate(novels):
                if self.cancel_flag:
                    break

                self._update_progress(i + 1, total, f"新着チェック中: {n_code}")

                if total_ep is None:
                    total_ep = 0
                if general_all_no is None:
                    logger.warning(f"Skipping {n_code}: Missing 'general_all_no'")
                    continue

                # 新着エピソードの確認
                if total_ep > general_all_no:
                    logger.warning(
                        f"Why? {n_code} has {total_ep} episodes but {general_all_no} episodes are available.")
                elif total_ep < general_all_no:
                    logger.info(f"New episode found in {n_code}: {total_ep} -> {general_all_no}")
                    shinchaku_ep += (general_all_no - total_ep)
                    shinchaku_novel_no += 1

                    # タイトルを取得
                    cursor.execute("SELECT title FROM novels_descs WHERE n_code = ?", (n_code,))
                    title_row = cursor.fetchone()
                    title = title_row[0] if title_row else "Unknown Title"

                    shinchaku_novel.append((n_code, title, total_ep, general_all_no, rating))

                # 少し待機してCPU負荷を下げる
                await asyncio.sleep(0.01)

            logger.info(f"Shinchaku: {shinchaku_novel_no}件{shinchaku_ep}話")
            return shinchaku_ep, shinchaku_novel, shinchaku_novel_no

        except Exception as e:
            logger.error(f"Error in shinchaku_checker: {e}")
            return 0, [], 0
        finally:
            conn.close()

    async def update_all_novels(self, shinchaku_novels):
        """すべての新着小説を更新する非同期関数"""
        if not shinchaku_novels:
            return {
                "shinchaku_ep": 0,
                "main_shinchaku": [],
                "shinchaku_novel": 0,
                "updated_count": 0
            }

        total = len(shinchaku_novels)
        updated = 0
        results = []

        self._update_progress(0, total, "小説を更新中...")

        # 更新するノベルの最大数に制限を追加（大量更新を避ける）
        max_novels_to_update = min(30, total)

        for i, row in enumerate(shinchaku_novels[:max_novels_to_update]):
            if self.cancel_flag:
                break

            n_code, title, past_ep, general_all_no, rating = row

            logger.info(f"Update novel {n_code} ({i + 1}/{max_novels_to_update}) (rating:{rating})")
            self._update_progress(i, max_novels_to_update, f"更新中 ({i + 1}/{max_novels_to_update}): {title}")

            try:
                # エピソード数の差が大きすぎる場合は最新のみ取得
                ep_diff = general_all_no - past_ep
                if ep_diff > 50:  # 50話以上の差がある場合
                    logger.info(f"{n_code} has too many new episodes ({ep_diff}). Getting only the latest 10.")
                    # 最新10話だけ取得
                    adjusted_past_ep = general_all_no - 10
                    result = await self.new_episode(n_code, adjusted_past_ep, general_all_no, rating)
                else:
                    result = await self.new_episode(n_code, past_ep, general_all_no, rating)

                if result:
                    updated += 1
                    results.append(result)

                # データベースの更新を個別に行う
                await self._update_total_episodes_single(n_code)
            except Exception as e:
                logger.error(f"Error updating novel {n_code}: {e}")
                # エラーが発生しても続行

            # レート制限を回避するために待機
            await asyncio.sleep(1)

        self._update_progress(total, total, f"更新完了: {updated}/{max_novels_to_update}の小説を更新しました")
        logger.info(f"Updated {updated}/{max_novels_to_update} novels")

        # 新着情報を更新して返す
        try:
            shinchaku_info = await self.shinchaku_checker()
            return {
                "shinchaku_ep": shinchaku_info[0],
                "main_shinchaku": shinchaku_info[1],
                "shinchaku_novel": shinchaku_info[2],
                "updated_count": updated
            }
        except Exception as e:
            logger.error(f"Error checking updates after novel updates: {e}")
            # エラーが発生した場合でも結果を返す
            return {
                "shinchaku_ep": 0,
                "main_shinchaku": [],
                "shinchaku_novel": 0,
                "updated_count": updated
            }

    async def _update_total_episodes_single(self, ncode):
        """小説の総エピソード数を更新する非同期関数"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # その小説のすべてのエピソード番号を取得
            cursor.execute('SELECT episode_no FROM episodes WHERE ncode = ?', (ncode,))
            episode_nos = cursor.fetchall()

            # エピソード番号を配列に格納し、整数に変換
            episode_no_array = [int(ep[0]) for ep in episode_nos]

            # 配列の最大値を取得
            if not episode_no_array:
                max_episode_no = 0
            else:
                max_episode_no = max(episode_no_array)

            # total_ep列を最大エピソード番号で更新
            cursor.execute('UPDATE novels_descs SET total_ep = ? WHERE n_code = ?', (max_episode_no, ncode))
            conn.commit()

            return max_episode_no

        except Exception as e:
            logger.error(f"Error updating total episodes for {ncode}: {e}")
            return 0

        finally:
            conn.close()

    async def db_update(self):
        """データベースの更新を行う非同期関数"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 小説の一覧を取得
            cursor.execute("SELECT n_code, rating FROM novels_descs")
            n_codes_ratings = cursor.fetchall()

            if not n_codes_ratings:
                logger.warning("No novels found in database")
                return

            # 性能向上のため、更新する小説の数を制限
            max_novels_to_update = min(50, len(n_codes_ratings))
            n_codes_ratings = n_codes_ratings[:max_novels_to_update]

            total = len(n_codes_ratings)
            completed = 0
            self._update_progress(completed, total, "小説情報を更新中...")

            # 並列処理用のリスト
            tasks = []

            # 小説情報を更新（同時実行数を制限）
            batch_size = 5  # 5件ずつ処理
            for i in range(0, total, batch_size):
                if self.cancel_flag:
                    break

                batch = n_codes_ratings[i:i + batch_size]
                tasks = [self.update_check(n_code, rating) for n_code, rating in batch]
                results = await asyncio.gather(*tasks)
                completed += len(batch)
                self._update_progress(completed, total, "小説情報を更新中...")

                # API制限を回避するための待機
                await asyncio.sleep(1)

            # GZファイルを展開
            self._update_progress(0, 100, "GZファイルを展開中...")
            await self.thawing_gz()

            # YMLファイルを解析してDBを更新
            self._update_progress(0, 100, "小説情報をDBに更新中...")
            await self.yml_parse_time(n_codes_ratings)

            logger.info("Database updated successfully")
            return True

        except Exception as e:
            logger.error(f"Error in db_update: {e}")
            return False

        finally:
            conn.close()


# メイン関数（テスト用）
async def main():
    updater = await NovelUpdater().initialize()
    try:
        # 進捗コールバックの設定
        updater.set_progress_callback(lambda progress, message: print(f"{message}: {progress}%"))

        # データベース更新
        await updater.db_update()

        # 新着チェック
        shinchaku_ep, shinchaku_novel, shinchaku_novel_no = await updater.shinchaku_checker()
        print(f"新着: {shinchaku_novel_no}件{shinchaku_ep}話")

        # 更新（最初の3件のみ）
        if shinchaku_novel:
            await updater.update_all_novels(shinchaku_novel[:3])
    finally:
        await updater.close()


if __name__ == "__main__":
    asyncio.run(main())