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

from config import DATABASE_PATH, DOWNLOAD_DIR, YML_DIR

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:54.0) Gecko/20100101 Firefox/54.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) AppleWebKit/602.3.12 (KHTML, like Gecko) Version/10.0.3 Safari/602.3.12',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.2403.157 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_1 like Mac OS X) AppleWebKit/603.1.30 (KHTML, like Gecko) Version/10.0 Mobile/14E304 Safari/602.1'
    'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
    'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:54.0) Gecko/20100101 Firefox/54.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) AppleWebKit/602.3.12 (KHTML, like Gecko) Version/10.0.3 Safari/602.3.12',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.2403.157 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_1 like Mac OS X) AppleWebKit/603.1.30 (KHTML, like Gecko) Version/10.0 Mobile/14E304 Safari/602.1'
    'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
    'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:54.0) Gecko/20100101 Firefox/54.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) AppleWebKit/602.3.12 (KHTML, like Gecko) Version/10.0.3 Safari/602.3.12',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.2403.157 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_1 like Mac OS X) AppleWebKit/603.1.30 (KHTML, like Gecko) Version/10.0 Mobile/14E304 Safari/602.1'
]


def load_conf():
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

#0:作者によって削除 1:18禁 2:通常 4:作者退会&&作者によって削除
def existence_check(ncode):
    rating = 0
    n_url = f"https://ncode.syosetu.com/{ncode}"
    n18_url = f"https://novel18.syosetu.com/{ncode}"
    now_url = ""
    print(f"Checking {ncode}...({n_url} or {n18_url})")

    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument(f'user-agent={random.choice(USER_AGENTS)}')

    driver = webdriver.Chrome( options=options)
    driver.get(n18_url)
    now_url = driver.current_url
    # print(now_url)

    # Check if redirected to age authentication page
    if "ageauth" in now_url:
        try:
            enter_link = driver.find_element(By.LINK_TEXT, "Enter")
            enter_link.click()
            now_url = driver.current_url
            print(f"Redirected to: {now_url}")
        except:
            print("Enter link not found")
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

    print(f"{ncode}'s rating: {rating}, url: {now_url}")
    driver.quit()
    return rating


def update_check(ncode, rating):
    if rating == 0:
        print(f"{ncode} is deleted by author")
        return
    elif rating == 1:
        print(f"{ncode} is 18+")
        n_api_url = f"https://api.syosetu.com/novel18api/api/?of=t-w-ga-s-ua&ncode={ncode}&gzip=5&json"
    elif rating == 2:
        print(f"{ncode} is normal")
        n_api_url = f"https://api.syosetu.com/novelapi/api/?of=t-w-ga-s-ua&ncode={ncode}&gzip=5&json"
    elif rating == 4:
        print(f"{ncode} is deleted by author or author is deleted")
        return
    else:
        print(f"Error: {ncode}'s rating is {rating}")
        return

    response = requests.get(n_api_url)
    if response.status_code == 200:
        file_path = os.path.join('dl', f"{ncode}.gz")
        with open(file_path, 'wb') as file:
            file.write(response.content)
        print(f"File saved to {file_path}")
    else:
        print(f"Failed to download file: {response.status_code}")

def Thawing_gz():
    dl_dir = DOWNLOAD_DIR
    for filename in os.listdir(dl_dir):
        if filename.endswith('.gz'):
            gz_path = os.path.join(dl_dir, filename)
            yml_path = os.path.join(YML_DIR, filename[:-3] + '.yml')

            with gzip.open(gz_path, 'rt', encoding='utf-8') as gz_file:
                content = gz_file.read()

            with open(yml_path, 'w', encoding='utf-8') as yml_file:
                yml_file.write(content)

            print(f"Decompressed and saved: {yml_path}")



def db_update():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    print("Connected to database")
    cursor.execute("SELECT n_code, rating FROM novels_descs")
    n_codes_ratings = cursor.fetchall()

    conn.commit()
    conn.close()

    def process_n_code_rating(n_code_rating):
        n_code, rating = n_code_rating
        print(f"Checking {n_code}...")
        update_check(n_code, rating)

    with ThreadPoolExecutor(max_workers=10) as executor:
        executor.map(process_n_code_rating, n_codes_ratings)

    Thawing_gz()
    print("Thawing gz files...")
    yml_parse_time(n_codes_ratings)
    print("Updated database successfully")



def yml_parse_time(n_codes_ratings):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    print("Connected to database")

    # n_codes_ratings の内容を確認
    print(f"n_codes_ratings: {n_codes_ratings}")
    if not n_codes_ratings:
        print("No data in n_codes_ratings.")
        return

    for n_code, _ in n_codes_ratings:
        print(f"Updating {n_code}...")
        yml_path = os.path.join(YML_DIR, f"{n_code}.yml")

        # ファイルパスの確認
        print(f"Looking for file: {yml_path}")
        if not os.path.exists(yml_path):
            print(f"File not found: {yml_path}")
            continue

        with open(yml_path, 'r', encoding='utf-8') as yml_file:
            try:
                # YAMLをそのまま読み込む
                data = yaml.safe_load(yml_file)

                # データがリスト形式の場合、[1]を取得
                if isinstance(data, list):
                    if len(data) > 1:
                        data = data[1]
                    else:
                        print(f"Data in {yml_path} is not sufficient. Skipping.")
                        continue

                # データが辞書形式であるか確認
                if not isinstance(data, dict):
                    print(f"Unexpected data format in {yml_path}")
                    continue
            except yaml.YAMLError as exc:
                print(f"Error parsing YAML file {yml_path}: {exc}")
                continue

            # データの取得
            general_all_no = data.get('general_all_no')
            allcount = data.get('allcount', 1)  # allcount が無い場合は 1 をデフォルト値とする
            story = data.get('story', '')
            title = data.get('title', '')
            updated_at = data.get('updated_at', None)
            writer = data.get('writer', '')

            # allcount が 0 の場合スキップ
            if allcount == 0:
                print(f"Skipping {n_code} as allcount is 0")
                continue

            if general_all_no is None:
                print(f"Skipping {n_code}: Missing 'general_all_no'")
                continue

            # デバッグ用出力
            print(f"Parsed data for {n_code}:")
            print(f"general_all_no: {general_all_no} (type: {type(general_all_no)})")
            print(f"updated_at: {updated_at} (type: {type(updated_at)})")

            if isinstance(updated_at, datetime.datetime):
                # updated_at を文字列に変換
                updated_at = updated_at.strftime('%Y-%m-%d %H:%M:%S')

            try:
                cursor.execute("""
                    UPDATE novels_descs
                    SET general_all_no = ?, Synopsis = ?, title = ?, updated_at = ?, author = ?
                    WHERE n_code = ?
                """, (int(general_all_no), story, title, updated_at, writer, n_code))

                # 更新行数を確認
                if cursor.rowcount == 0:
                    print(f"No rows updated for n_code = {n_code}. Check if the row exists.")
                else:
                    print(f"Successfully updated {n_code}: {cursor.rowcount} rows affected.")
            except sqlite3.Error as e:
                print(f"Database update failed for {n_code}: {e}")
            cursor.execute("SELECT * FROM novels_descs WHERE n_code = ?", (n_code,))
            row = cursor.fetchone()
            if not row:
                print(f"No row found with n_code = {n_code}. Skipping update.")
            else:
                print(f"Row found for n_code = {n_code}: {row}")
            # print(f"Updated {n_code} successfully({general_all_no}, {story}, {title}, {updated_at}, {writer})")

    conn.commit()
    conn.close()

def ncode_title(n_code):
    # Connect to the database
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # Select the title from the novels_descs table
    cursor.execute('''
    SELECT title
    FROM novels_descs
    WHERE n_code = ?
    ''', (n_code,))

    # Fetch the title
    title = cursor.fetchone()

    # Close the connection
    conn.close()

    if title:
        return title[0]

    return None


def shinchaku_checker():
    shinchaku_ep = 0
    shinchaku_novel = []
    shinchaku_novel_no = 0
    print("Check_shinchaku...")

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    print("Connected to database")

    cursor.execute("SELECT n_code, total_ep, general_all_no,rating FROM novels_descs")
    novels = cursor.fetchall()

    for n_code, total_ep, general_all_no,rating in novels:
        if total_ep is None:
            total_ep = 0
        if general_all_no is None:
            print(f"Skipping {n_code}: Missing 'general_all_no'")
            continue

        elif total_ep > general_all_no:
            print(f"Why? {n_code} has {total_ep} episodes but {general_all_no} episodes are available.")
        elif total_ep < general_all_no:
            print(f"New episode found in {n_code}: {total_ep} -> {general_all_no}")
            shinchaku_ep += (general_all_no - total_ep)
            shinchaku_novel_no += 1
            shinchaku_novel.append((n_code, ncode_title(n_code),total_ep,general_all_no,rating))  # 修正箇所
        elif total_ep == general_all_no:
            print(f"{n_code} is up to date.")
    print(f"Shinchaku: {shinchaku_novel_no}件{shinchaku_ep}話")
    return shinchaku_ep, shinchaku_novel, shinchaku_novel_no

def catch_up_episode(n_code, episode_no, rating):
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
                print(f"Redirected to: {now_url}")
            except:
                print("Enter link not found")
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

    print(title)
    return episode, title

def single_episode(n_code, rating):
    title = ""
    episode = ""
    EP_url = f"https://ncode.syosetu.com/{n_code}"
    print(f"Checking {n_code}...(rating: {rating})")
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
                print(f"Redirected to: {now_url}")
            except:
                print("Enter link not found")
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
                print(episode)
        else:
            episode = "Failed to retrieve the episode."
            print(episode)
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

    print(title)
    return episode, title

def new_episode(n_code, past_ep, general_all_no, rating):
    new_eps = []
    print(f"Checking {n_code}...")
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    print("Connected to database")

    if general_all_no == 1:
        episode, title = single_episode(n_code, rating)
        if episode and title:
            new_eps.append([n_code, 1, episode, title])

    for i in range(general_all_no - past_ep):
        episode, title = catch_up_episode(n_code, past_ep + i + 1, rating)
        if episode and title:
            new_eps.append([n_code, past_ep + i + 1, episode, title])
            if i % 20 == 0:
                for ep in new_eps:
                    cursor.execute("""
                        INSERT INTO episodes (ncode, episode_no, body, e_title)
                        VALUES (?, ?, ?, ?)
                    """, (ep[0], ep[1], ep[2], ep[3]))
                conn.commit()
                new_eps = []

    for ep in new_eps:
        cursor.execute("""
            INSERT INTO episodes (ncode, episode_no, body, e_title)
            VALUES (?, ?, ?, ?)
        """, (ep[0], ep[1], ep[2], ep[3]))
    conn.commit()

    # Update total_ep in novels_descs table
    cursor.execute("""
        UPDATE novels_descs
        SET total_ep = ?
        WHERE n_code = ?
    """, (general_all_no, n_code))
    conn.commit()

    conn.close()
    print(f"Updated {n_code} with new episodes and total_ep.")

def dell_dl():
    dl_dir = DOWNLOAD_DIR
    for filename in os.listdir(dl_dir):
        if filename.endswith('.gz') or filename.endswith('.yml'):
            os.remove(os.path.join(dl_dir, filename))
            print(f"Deleted {filename}")

def del_yml():
    yml_dir = YML_DIR
    for filename in os.listdir(yml_dir):
        if filename.endswith('.yml'):
            os.remove(os.path.join(yml_dir, filename))
            print(f"Deleted {filename}")

def existence_checker():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    print("Connected to database")

    cursor.execute("SELECT n_code FROM novels_descs")
    n_codes = cursor.fetchall()

    for n_code in n_codes:
        n_code = n_code[0]
        rating = existence_check(n_code)
        cursor.execute("UPDATE novels_descs SET rating = ? WHERE n_code = ?", (rating, n_code))
        print(f"Updated {n_code} with rating {rating}")

    conn.commit()
    conn.close()
    print("All ratings have been updated.")

# existence_checker()
