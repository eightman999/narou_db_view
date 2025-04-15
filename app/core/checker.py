import concurrent
import configparser
import datetime
import gzip
import sqlite3

import yaml
from bs4 import BeautifulSoup
from selenium import webdriver
import requests
import os
from selenium.webdriver.chrome.service import Service
from concurrent.futures import ThreadPoolExecutor
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import random

from config import DOWNLOAD_DIR, YML_DIR, DATABASE_PATH
from app.database.db_handler import DatabaseHandler
from app.utils.logger_manager import get_logger

# ロガー設定
logger = get_logger('Checker')

# データベースハンドラの取得
db = DatabaseHandler()

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:54.0) Gecko/20100101 Firefox/54.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) AppleWebKit/602.3.12 (KHTML, like Gecko) Version/10.0.3 Safari/602.3.12',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.2403.157 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_1 like Mac OS X) AppleWebKit/603.1.30 (KHTML, like Gecko) Version/10.0 Mobile/14E304 Safari/602.1',
    'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
    'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:54.0) Gecko/20100101 Firefox/54.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) AppleWebKit/602.3.12 (KHTML, like Gecko) Version/10.0.3 Safari/602.3.12',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.2403.157 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_1 like Mac OS X) AppleWebKit/603.1.30 (KHTML, like Gecko) Version/10.0 Mobile/14E304 Safari/602.1'
]


def load_conf():
    """
    設定ファイルを読み込む

    Returns:
        tuple: (font, fontsize, backgroundcolor)
    """
    import os
    config = configparser.ConfigParser()

    # 設定ファイルのパス
    config_file = 'settings.ini'

    # デフォルト設定
    default_font = "YuKyokasho Yoko"
    default_fontsize = 14
    default_backgroundcolor = "#FFFFFF"

    # 設定ファイルが存在するか確認
    if os.path.exists(config_file):
        config.read(config_file)

    # Settings セクションが存在しない場合は作成
    if not config.has_section('Settings'):
        config.add_section('Settings')
        config.set('Settings', 'font', default_font)
        config.set('Settings', 'fontsize', str(default_fontsize))
        config.set('Settings', 'backgroundcolor', default_backgroundcolor)

        # 設定を保存
        with open(config_file, 'w') as f:
            config.write(f)

        return default_font, default_fontsize, default_backgroundcolor

    # 設定を読み込み
    try:
        font = config.get('Settings', 'font')
        fontsize = config.getint('Settings', 'fontsize')
        backgroundcolor = config.get('Settings', 'backgroundcolor')
    except (configparser.NoOptionError, ValueError):
        # オプションが存在しないか、値の変換に失敗した場合はデフォルト値を使用
        if not config.has_option('Settings', 'font'):
            config.set('Settings', 'font', default_font)
            font = default_font
        else:
            font = config.get('Settings', 'font')

        if not config.has_option('Settings', 'fontsize'):
            config.set('Settings', 'fontsize', str(default_fontsize))
            fontsize = default_fontsize
        else:
            try:
                fontsize = config.getint('Settings', 'fontsize')
            except ValueError:
                config.set('Settings', 'fontsize', str(default_fontsize))
                fontsize = default_fontsize

        if not config.has_option('Settings', 'backgroundcolor'):
            config.set('Settings', 'backgroundcolor', default_backgroundcolor)
            backgroundcolor = default_backgroundcolor
        else:
            backgroundcolor = config.get('Settings', 'backgroundcolor')

        # 変更された設定を保存
        with open(config_file, 'w') as f:
            config.write(f)

    return font, fontsize, backgroundcolor

def process_n_code_rating(n_code_rating):
    """個別の小説コードとレーティングを処理"""
    n_code, rating = n_code_rating
    logger.info(f"Checking {n_code}...")
    update_check(n_code, rating)

def existence_check(ncode):
    """
    小説が存在するかどうかを確認し、レーティングを返す
    0: 作者によって削除
    1: 18禁
    2: 通常
    4: 作者退会&&作者によって削除

    Args:
        ncode (str): 小説コード

    Returns:
        int: レーティング
    """
    rating = 0
    n_url = f"https://ncode.syosetu.com/{ncode}"
    n18_url = f"https://novel18.syosetu.com/{ncode}"
    now_url = ""
    logger.info(f"Checking {ncode}...({n_url} or {n18_url})")

    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument(f'user-agent={random.choice(USER_AGENTS)}')

    driver = webdriver.Chrome(options=options)
    driver.get(n18_url)
    now_url = driver.current_url

    # 年齢認証ページにリダイレクトされたかチェック
    if "ageauth" in now_url:
        try:
            enter_link = driver.find_element(By.LINK_TEXT, "Enter")
            enter_link.click()
            now_url = driver.current_url
            logger.info(f"Redirected to: {now_url}")
        except:
            logger.error("Enter link not found")
            driver.quit()
            return rating

    try:
        span_attention = driver.find_element(By.CSS_SELECTOR, 'span.attention')
        if span_attention.text == "エラーが発生しました。":
            rating = 4
    except:
        pass

    try:
        h1 = driver.find_element(By.CSS_SELECTOR, 'h1')
        if h1.text == "エラー":
            rating = 0
    except:
        pass

    if rating == 0:
        if now_url == n_url:
            rating = 2
        elif now_url == n18_url:
            rating = 1

    logger.info(f"{ncode}'s rating: {rating}, url: {now_url}")
    driver.quit()
    return rating


def update_check(ncode, rating):
    """
    小説の更新情報を取得してファイルに保存

    Args:
        ncode (str): 小説コード
        rating (int): レーティング
    """
    if rating == 0:
        logger.info(f"{ncode} is deleted by author")
        return
    elif rating == 1:
        logger.info(f"{ncode} is 18+")
        n_api_url = f"https://api.syosetu.com/novel18api/api/?of=t-w-ga-s-ua&ncode={ncode}&gzip=5&json"
    elif rating == 2:
        logger.info(f"{ncode} is normal")
        n_api_url = f"https://api.syosetu.com/novelapi/api/?of=t-w-ga-s-ua&ncode={ncode}&gzip=5&json"
    elif rating == 4:
        logger.info(f"{ncode} is deleted by author or author is deleted")
        return
    else:
        logger.error(f"Error: {ncode}'s rating is {rating}")
        return

    response = requests.get(n_api_url)
    if response.status_code == 200:
        file_path = os.path.join(DOWNLOAD_DIR, f"{ncode}.gz")
        with open(file_path, 'wb') as file:
            file.write(response.content)
        logger.info(f"File saved to {file_path}")
    else:
        logger.error(f"Failed to download file: {response.status_code}")


def Thawing_gz():
    """gzファイルを解凍してYAMLファイルとして保存"""
    dl_dir = DOWNLOAD_DIR
    for filename in os.listdir(dl_dir):
        if filename.endswith('.gz'):
            gz_path = os.path.join(dl_dir, filename)
            yml_path = os.path.join(YML_DIR, filename[:-3] + '.yml')

            with gzip.open(gz_path, 'rt', encoding='utf-8') as gz_file:
                content = gz_file.read()

            with open(yml_path, 'w', encoding='utf-8') as yml_file:
                yml_file.write(content)

            logger.info(f"Decompressed and saved: {yml_path}")


def db_update():
    """データベースの小説情報を更新する"""
    logger.info("データベース更新開始")

    # データベースから小説のncodeとratingを取得
    n_codes_ratings = db.execute_query(
        "SELECT n_code, rating FROM novels_descs",
        fetch=True
    )

    # ThreadPoolExecutorを使用してマルチスレッドで処理
    with ThreadPoolExecutor(max_workers=10) as executor:
        executor.map(process_n_code_rating, n_codes_ratings)

    # gzファイルを解凍
    Thawing_gz()
    logger.info("Thawing gz files...")

    # YAMLファイルからデータを更新
    yml_parse_time(n_codes_ratings)
    logger.info("Updated database successfully")

def yml_parse_time(n_codes_ratings):
    """
    YAMLファイルを解析してデータベースを更新
    更新時刻はlast_update_dateに保存し、話数の更新があった場合のみupdate_atを更新

    Args:
        n_codes_ratings (list): 小説コードとレーティングのリスト
    """
    logger.info("YAMLデータ解析開始")

    if not n_codes_ratings:
        logger.warning("No data in n_codes_ratings.")
        return

    for n_code, _ in n_codes_ratings:
        logger.info(f"Updating {n_code}...")
        yml_path = os.path.join(YML_DIR, f"{n_code}.yml")

        # ファイルパスの確認
        if not os.path.exists(yml_path):
            logger.warning(f"File not found: {yml_path}")
            continue

        try:
            with open(yml_path, 'r', encoding='utf-8') as yml_file:
                # YAMLをそのまま読み込む
                data = yaml.safe_load(yml_file)

                # データがリスト形式の場合、[1]を取得
                if isinstance(data, list):
                    if len(data) > 1:
                        data = data[1]
                    else:
                        logger.warning(f"Data in {yml_path} is not sufficient. Skipping.")
                        continue

                # データが辞書形式であるか確認
                if not isinstance(data, dict):
                    logger.warning(f"Unexpected data format in {yml_path}")
                    continue
        except yaml.YAMLError as exc:
            logger.error(f"Error parsing YAML file {yml_path}: {exc}")
            continue

        # データの取得
        general_all_no = data.get('general_all_no')
        story = data.get('story', '')
        title = data.get('title', '')
        updated_at = data.get('updated_at', None)
        writer = data.get('writer', '')

        # allcountが0の場合スキップ
        if data.get('allcount', 1) == 0:
            logger.info(f"Skipping {n_code} as allcount is 0")
            continue

        if general_all_no is None:
            logger.warning(f"Skipping {n_code}: Missing 'general_all_no'")
            continue

        # 日時型の場合は文字列に変換
        if isinstance(updated_at, datetime.datetime):
            updated_at = updated_at.strftime('%Y-%m-%d %H:%M:%S')

        try:
            # 現在のエピソード数を取得
            current_data = db.execute_query(
                "SELECT total_ep FROM novels_descs WHERE n_code = ?",
                (n_code,),
                fetch=True,
                fetch_all=False
            )

            current_total_ep = 0
            if current_data and current_data[0] is not None:
                current_total_ep = current_data[0]

            # 現在時刻を取得（実際の更新があった場合に使用）
            current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # 話数に更新があるかどうかを確認
            has_new_episodes = int(general_all_no) > current_total_ep

            # 更新するフィールドを準備
            update_fields = {
                'general_all_no': int(general_all_no),
                'Synopsis': story,
                'title': title,
                'last_update_date': updated_at,  # YMLからの更新日時はlast_update_dateに保存
                'author': writer
            }

            # 話数の更新があった場合のみupdate_atを更新
            if has_new_episodes:
                update_fields['updated_at'] = current_time
                logger.info(f"New episodes detected for {n_code}: {current_total_ep} -> {general_all_no}")

                # episodes テーブルの新しいエピソードのupdate_timeを設定するためのクエリを準備
                # この更新はエピソード取得時に適用される（catch_up_episodeなどで）

            # 動的にSQLクエリを構築
            field_names = ', '.join([f"{field} = ?" for field in update_fields.keys()])
            values = list(update_fields.values())
            values.append(n_code)  # WHERE句用

            # データベースを更新
            db.execute_query(
                f"UPDATE novels_descs SET {field_names} WHERE n_code = ?",
                tuple(values)
            )
            logger.info(f"Successfully updated {n_code}")
        except Exception as e:
            logger.error(f"Database update failed for {n_code}: {e}")


def ncode_title(n_code):
    """
    小説コードからタイトルを取得

    Args:
        n_code (str): 小説コード

    Returns:
        str: 小説タイトル
    """
    novel = db.get_novel_by_ncode(n_code)
    return novel[1] if novel else None


def shinchaku_checker():
    """
    新着小説をチェック（ratingが5の小説は除外）

    Returns:
        tuple: (新着エピソード数, 新着小説リスト, 新着小説数)
    """
    shinchaku_ep = 0
    shinchaku_novel = []
    shinchaku_novel_no = 0
    logger.info("新着小説チェック開始")

    # 更新が必要な小説を取得
    needs_update = db.get_novels_needing_update()

    for n_code, title, total_ep, general_all_no, rating in needs_update:
        # ratingが5の小説はスキップ（データベースクエリで除外済みだが念のため）
        if rating == 5:
            continue

        shinchaku_ep += (general_all_no - total_ep)
        shinchaku_novel_no += 1
        shinchaku_novel.append((n_code, title, total_ep, general_all_no, rating))

    logger.info(f"Shinchaku: {shinchaku_novel_no}件{shinchaku_ep}話")
    return shinchaku_ep, shinchaku_novel, shinchaku_novel_no
def catch_up_episode(n_code, episode_no, rating):
    """
    指定されたエピソードを取得

    Args:
        n_code (str): 小説コード
        episode_no (int): エピソード番号
        rating (int): レーティング

    Returns:
        tuple: (エピソード本文, エピソードタイトル)
    """
    # データベースから小説の総エピソード数を取得
    novel = db.get_novel_by_ncode(n_code)
    general_all_no = novel[6] if novel and len(novel) > 6 and novel[6] is not None else None

    # 一話完結小説または総エピソード数が1の場合は別のURLでアクセス
    if general_all_no == 1 and int(episode_no) == 1:
        return single_episode(n_code, rating)

    title = ""
    episode = ""
    EP_url = f"https://ncode.syosetu.com/{n_code}/{episode_no}/"

    if rating == 1 or rating is None:
        EP_url = f"https://novel18.syosetu.com/{n_code}/{episode_no}/"
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument(f'user-agent={random.choice(USER_AGENTS)}')

        driver = webdriver.Chrome(options=options)
        driver.get(EP_url)
        now_url = driver.current_url

        if "ageauth" in now_url:
            try:
                enter_link = driver.find_element(By.LINK_TEXT, "Enter")
                enter_link.click()
                now_url = driver.current_url
                logger.info(f"Redirected to: {now_url}")
            except:
                logger.error("Enter link not found")
                driver.quit()
                return "", ""

        if driver.current_url == now_url:
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            novel_body = soup.find('div', class_='p-novel__body')
            title_tag = soup.find('h1', class_='p-novel__title')
            if title_tag:
                title = title_tag.get_text(strip=True)
            if novel_body:
                # 改行を挿入して段落をつなげる
                episode = '\n\n'.join(p.get_text() for p in novel_body.find_all('p'))
            else:
                episode = "No content found in the specified div."
        else:
            episode = "Failed to retrieve the episode."
        driver.quit()
    else:
        headers = {'User-Agent': random.choice(USER_AGENTS)}
        response = requests.get(EP_url, headers=headers)

        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            novel_body = soup.find('div', class_='p-novel__body')
            title_tag = soup.find('h1', class_='p-novel__title')
            if title_tag:
                title = title_tag.get_text(strip=True)
            if novel_body:
                # 改行を挿入して段落をつなげる
                episode = '\n\n'.join(p.get_text() for p in novel_body.find_all('p'))
            else:
                episode = "No content found in the specified div."
        else:
            episode = f"Failed to retrieve the episode. Status code: {response.status_code}"

    logger.info(f"Retrieved episode {episode_no} of {n_code}: {title}")
    return episode, title


def single_episode(n_code, rating):
    """
    一話完結小説用のエピソード取得

    Args:
        n_code (str): 小説コード
        rating (int): レーティング

    Returns:
        tuple: (エピソード本文, エピソードタイトル)
    """
    title = ""
    episode = ""
    EP_url = f"https://ncode.syosetu.com/{n_code}/"
    logger.info(f"Checking {n_code}...(rating: {rating}) as single episode novel")

    if rating == 1:
        EP_url = f"https://novel18.syosetu.com/{n_code}/"
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument(f'user-agent={random.choice(USER_AGENTS)}')

        driver = webdriver.Chrome(options=options)
        driver.get(EP_url)
        now_url = driver.current_url

        if "ageauth" in now_url:
            try:
                enter_link = driver.find_element(By.LINK_TEXT, "Enter")
                enter_link.click()
                now_url = driver.current_url
                logger.info(f"Redirected to: {now_url}")
            except:
                logger.error("Enter link not found")
                driver.quit()
                return "", ""

        if driver.current_url == now_url:
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            novel_body = soup.find('div', class_='p-novel__body')
            title_tag = soup.find('h1', class_='p-novel__title')
            if title_tag:
                title = title_tag.get_text(strip=True)
            if novel_body:
                # 改行を挿入して段落をつなげる
                episode = '\n\n'.join(p.get_text() for p in novel_body.find_all('p'))
            else:
                episode = "No content found in the specified div."
                logger.warning(episode)
        else:
            episode = "Failed to retrieve the episode."
            logger.error(episode)
        driver.quit()
    else:
        headers = {'User-Agent': random.choice(USER_AGENTS)}
        response = requests.get(EP_url, headers=headers)

        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            novel_body = soup.find('div', class_='p-novel__body')
            title_tag = soup.find('h1', class_='p-novel__title')
            if title_tag:
                title = title_tag.get_text(strip=True)
            if novel_body:
                # 改行を挿入して段落をつなげる
                episode = '\n\n'.join(p.get_text() for p in novel_body.find_all('p'))
            else:
                episode = "No content found in the specified div."
        else:
            episode = f"Failed to retrieve the episode. Status code: {response.status_code}"

    logger.info(f"Retrieved single episode of {n_code}: {title}")
    return episode, title


def dell_dl():
    """ダウンロードディレクトリの.gzファイルを削除"""
    dl_dir = DOWNLOAD_DIR
    for filename in os.listdir(dl_dir):
        if filename.endswith('.gz') or filename.endswith('.yml'):
            os.remove(os.path.join(dl_dir, filename))
            logger.info(f"Deleted {filename}")


def del_yml():
    """YMLディレクトリの.ymlファイルを削除"""
    yml_dir = YML_DIR
    for filename in os.listdir(yml_dir):
        if filename.endswith('.yml'):
            os.remove(os.path.join(yml_dir, filename))
            logger.info(f"Deleted {filename}")


def check_and_update_missing_general_all_no(max_workers=10):
    """
    general_all_noが取得できなかった小説の存在確認と話数の取得を並列処理で行います。

    Args:
        max_workers (int): 同時に実行するスレッドの最大数
    """
    logger.info("general_all_noが不明な小説の並列確認を開始します")

    # データベース接続
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        # general_all_noが取得できていない小説の一覧を取得
        cursor.execute("""
            SELECT n_code, rating 
            FROM novels_descs 
            WHERE general_all_no IS NULL OR general_all_no = 0
        """)

        novels = cursor.fetchall()
        total_novels = len(novels)
        logger.info(f"{total_novels}件の小説のgeneral_all_noが不明です")

        if total_novels == 0:
            logger.info("処理対象の小説がありません")
            return

        # 進捗表示用のカウンタと更新情報を保持するリスト
        progress_count = 0
        results = []

        # 結果を保存するための関数
        def process_novel_existence(novel_data):
            nonlocal progress_count
            n_code, current_rating = novel_data

            try:
                logger.info(f"小説 {n_code} の存在確認を行います")

                # 小説の存在確認を行い、情報を取得
                rating, exists, max_episode = check_novel_existence(n_code, current_rating)

                # 処理カウンタを増加
                progress_count += 1
                logger.info(f"進捗: {progress_count}/{total_novels} - 小説 {n_code} の確認完了")

                # 結果を返す
                return n_code, rating, exists, max_episode
            except Exception as e:
                logger.error(f"小説 {n_code} の存在確認中にエラー: {e}")
                progress_count += 1
                return n_code, 5, False, 0  # エラー時はrating=5（存在しない）と仮定

        # ThreadPoolExecutorを使用して並列処理
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 各小説の処理を実行し、結果を集める
            future_to_novel = {executor.submit(process_novel_existence, novel): novel for novel in novels}

            for future in concurrent.futures.as_completed(future_to_novel):
                novel = future_to_novel[future]
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"小説 {novel[0]} の処理中に例外が発生: {e}")

        # 結果を一括でデータベースに更新（排他制御のため単一接続で実行）
        for n_code, rating, exists, max_episode in results:
            if exists:
                cursor.execute("""
                    UPDATE novels_descs 
                    SET rating = ?, general_all_no = ? 
                    WHERE n_code = ?
                """, (rating, max_episode, n_code))
                logger.info(f"小説 {n_code} の情報を更新しました: rating={rating}, general_all_no={max_episode}")
            else:
                cursor.execute("""
                    UPDATE novels_descs 
                    SET rating = 5
                    WHERE n_code = ?
                """, (n_code,))
                logger.info(f"小説 {n_code} は存在しないため、rating=5に設定しました")

        # コミット
        conn.commit()
        logger.info("general_all_noの並列更新が完了しました")

    except Exception as e:
        logger.error(f"general_all_no更新処理中にエラーが発生しました: {e}")
        conn.rollback()

    finally:
        conn.close()

def check_novel_existence(n_code, current_rating):
    """
    小説の存在確認と話数取得を行う関数

    Args:
        n_code (str): 小説コード
        current_rating (int): 現在のレーティング

    Returns:
        tuple: (rating, exists, max_episode) - レーティング, 存在するか, 最大話数
    """
    # 小説の存在確認
    exists = False
    max_episode = 0
    rating = current_rating

    # 一般小説URLと18禁小説URLの両方をチェック
    normal_url = f"https://ncode.syosetu.com/{n_code}/"
    r18_url = f"https://novel18.syosetu.com/{n_code}/"

    # Chromeオプション設定
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument(f'user-agent={random.choice(USER_AGENTS)}')

    driver = webdriver.Chrome(options=options)

    try:
        # まず通常URLをチェック
        driver.get(normal_url)

        # エラーページかどうか確認（p-novelcom-header__pagetitleで判定）
        try:
            page_title = driver.find_element(By.CLASS_NAME, "p-novelcom-header__pagetitle")
            normal_exists = page_title.text != "エラー"
        except:
            # 要素が見つからない場合はタイトル要素が存在するかどうかでチェック
            normal_exists = len(driver.find_elements(By.CLASS_NAME, "novel_title")) > 0

        # 18禁URLをチェック
        if not normal_exists:
            driver.get(r18_url)

            # 年齢認証ページが表示された場合
            if "ageauth" in driver.current_url:
                try:
                    enter_link = driver.find_element(By.LINK_TEXT, "Enter")
                    enter_link.click()
                except:
                    logger.error(f"小説 {n_code}: 年齢認証ページのEnterリンクが見つかりません")

            # エラーページかどうか確認（p-novelcom-header__pagetitleで判定）
            try:
                page_title = driver.find_element(By.CLASS_NAME, "p-novelcom-header__pagetitle")
                r18_exists = page_title.text != "エラー"
            except:
                # 要素が見つからない場合はタイトル要素が存在するかどうかでチェック
                r18_exists = len(driver.find_elements(By.CLASS_NAME, "novel_title")) > 0

            exists = r18_exists

            # 18禁小説の場合はratingを1に設定
            if r18_exists:
                rating = 1
        else:
            # 通常小説の場合
            exists = True
            rating = 2

        # 小説が存在する場合は話数を取得
        if exists:
            # 話数を調査（エラーが出るまでアクセス）
            episode = 1
            while True:
                try:
                    if rating == 1:
                        episode_url = f"{r18_url}{episode}/"
                    else:
                        episode_url = f"{normal_url}{episode}/"

                    driver.get(episode_url)

                    # エラーページかどうか確認（p-novelcom-header__pagetitleで判定）
                    try:
                        page_title = driver.find_element(By.CLASS_NAME, "p-novelcom-header__pagetitle")
                        if page_title.text == "エラー":
                            # エラーが出たら一つ前が最大話数
                            max_episode = episode - 1
                            break
                    except:
                        # 要素が見つからない場合は、本文要素が存在するかで判断
                        if len(driver.find_elements(By.CLASS_NAME, "novel_view")) == 0:
                            # 本文要素がない場合はエラーページと判断
                            max_episode = episode - 1
                            break

                    # 次の話数へ
                    episode += 1

                    # 念のため最大5000話までとする
                    if episode > 5000:
                        max_episode = 5000
                        logger.warning(f"小説 {n_code} は話数が5000を超えているため、調査を打ち切ります")
                        break

                except Exception as e:
                    logger.error(f"小説 {n_code} の話数調査中にエラー: {e}")
                    max_episode = episode - 1
                    break

    except Exception as e:
        logger.error(f"小説 {n_code} の存在確認中にエラー: {e}")
        # エラーの場合も、できるだけページタイトルを確認
        try:
            page_title = driver.find_element(By.CLASS_NAME, "p-novelcom-header__pagetitle")
            if page_title.text == "エラー":
                rating = 5
                exists = False
        except:
            # この時点でエラーが出ている場合は、サイトにアクセスできなかった可能性が高い
            # この場合は現在のレーティングを維持（変更しない）
            exists = False

    finally:
        # ドライバーを閉じる
        driver.quit()

    return rating, exists, max_episode

def batch_check_novel_existence(n_codes, max_workers=10):
    """
    複数の小説の存在確認を並列処理で行う

    Args:
        n_codes (list): 小説コードのリスト
        max_workers (int): 同時に実行するスレッドの最大数

    Returns:
        dict: {n_code: (rating, exists, max_episode)} 形式の辞書
    """
    logger.info(f"{len(n_codes)}件の小説の存在確認を並列処理で開始します")
    results = {}

    # 進捗表示用のカウンタ
    processed = 0
    total = len(n_codes)

    def check_single_novel(n_code):
        nonlocal processed
        try:
            # 現在のレーティングを取得
            current_rating = db.execute_read_query(
                "SELECT rating FROM novels_descs WHERE n_code = ?",
                (n_code,),
                fetch_all=False
            )
            current_rating = current_rating[0] if current_rating else 0

            # 存在確認を実行
            result = check_novel_existence(n_code, current_rating)

            # 進捗カウンタを更新
            processed += 1
            logger.info(f"進捗: {processed}/{total} - 小説 {n_code} の確認完了")

            return n_code, result
        except Exception as e:
            logger.error(f"小説 {n_code} の処理中にエラー: {e}")
            processed += 1
            return n_code, (5, False, 0)  # エラー時はrating=5（存在しない）と仮定

    # ThreadPoolExecutorを使用して並列処理
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 各小説の処理を実行
        future_to_ncode = {executor.submit(check_single_novel, n_code): n_code for n_code in n_codes}

        for future in concurrent.futures.as_completed(future_to_ncode):
            n_code = future_to_ncode[future]
            try:
                n_code, result = future.result()
                results[n_code] = result
            except Exception as e:
                logger.error(f"小説 {n_code} の結果取得中にエラー: {e}")

    logger.info(f"全{total}件の小説の存在確認が完了しました")
    return results