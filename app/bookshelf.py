import sqlite3
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import random
from core.checker import USER_AGENTS
from database.db_handler import DatabaseHandler

# データベースハンドラのインスタンスを取得
db = DatabaseHandler()


def shelf_maker():
    """
    小説棚（小説一覧）を作成する関数

    Returns:
        list: n_codeごとに最も情報が充実している行のみを含んだ小説リスト
    """
    # 全ての小説情報を取得
    novel_shelf = db.get_all_novels()

    # n_codeごとに最も情報が充実している行を選択する
    best_rows = {}

    for row in novel_shelf:
        n_code = row[0]
        # 空白でない要素の数をカウント
        non_space_count = sum(1 for element in row if isinstance(element, str) and element.strip() != '')

        if n_code not in best_rows:
            best_rows[n_code] = (non_space_count, row)
        else:
            # 現在の行の方が情報が多い場合は更新
            if non_space_count > best_rows[n_code][0]:
                best_rows[n_code] = (non_space_count, row)

    # 最良の行のみを抽出
    sub_shelf = [row for _, row in best_rows.values()]

    novels = 0
    # 小説情報を表示
    for novel in sub_shelf:
        novels += 1
        print(novel)

    print(f"Total number of novels: {novels}")

    return sub_shelf


def input_last_read(rast_read_novel, episode_no):
    """
    最後に読んだ小説とエピソード番号を記録する

    Args:
        rast_read_novel (str): 小説コード
        episode_no (int): エピソード番号
    """
    db.update_last_read(rast_read_novel, episode_no)


def get_last_read(shelf):
    """
    最後に読んだ小説情報を取得する

    Args:
        shelf (list): 小説一覧

    Returns:
        tuple: (小説情報, エピソード番号)
    """
    # 最後に読んだ小説情報を取得
    last_read = db.get_last_read_novel()

    if last_read:
        last_read_ncode = last_read[0]
        last_read_episode_no = last_read[1]

        # 棚データと比較して対応する小説情報を返す
        for row in shelf:
            if row[0] == last_read_ncode:
                return row, last_read_episode_no

    return None, None


def episode_getter(n_code):
    """
    指定された小説のエピソード一覧を取得

    Args:
        n_code (str): 小説コード

    Returns:
        list: エピソード情報のリスト [(episode_no, title, body), ...]
    """
    # データベースからエピソード情報を取得
    episodes = db.get_episodes_by_ncode(n_code)

    # エピソード情報を表示
    for row in episodes:
        print(row)

    return episodes