import configparser
import datetime
import gzip
import yaml
from bs4 import BeautifulSoup
from selenium import webdriver
import requests
import os
import threading
from selenium.webdriver.chrome.service import Service
from concurrent.futures import ThreadPoolExecutor
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import random

from config import DATABASE_PATH, DOWNLOAD_DIR, YML_DIR
from database.db_handler import DatabaseHandler
from utils.logger_manager import get_logger

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

    def process_n_code_rating(n_code_rating):
        n_code, rating = n_code_rating
        logger.info(f"Checking {n_code}...")
        update_check(n_code, rating)

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
            # データベースを更新
            db.execute_query(
                """
                UPDATE novels_descs
                SET general_all_no = ?, Synopsis = ?, title = ?, updated_at = ?, author = ?
                WHERE n_code = ?
                """,
                (int(general_all_no), story, title, updated_at, writer, n_code)
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
    新着小説をチェック

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
                episode = ''.join(str(p) for p in novel_body.find_all('p'))
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
                episode = ''.join(str(p) for p in novel_body.find_all('p'))
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
    EP_url = f"https://ncode.syosetu.com/{n_code}"
    logger.info(f"Checking {n_code}...(rating: {rating})")

    if rating == 1:
        EP_url = f"https://novel18.syosetu.com/{n_code}"
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
                episode = ''.join(str(p) for p in novel_body.find_all('p'))
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
                episode = ''.join(str(p) for p in novel_body.find_all('p'))
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