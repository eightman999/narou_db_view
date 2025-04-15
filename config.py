import os

# プロジェクトのルートディレクトリ
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# データベース関連の設定

DATABASE_DIR = os.path.join(ROOT_DIR, 'app','database', 'db_files')
DATABASE_PATH = os.path.join(DATABASE_DIR, 'novel_status.db')

# 設定ファイル
SETTINGS_FILE = os.path.join(ROOT_DIR, 'settings.ini')

# ダウンロードディレクトリ
DOWNLOAD_DIR = os.path.join(ROOT_DIR, 'dl')
YML_DIR = os.path.join(ROOT_DIR, 'yml')

# 作成するディレクトリの確認
REQUIRED_DIRS = [
    DATABASE_DIR,
    DOWNLOAD_DIR,
    YML_DIR,
    os.path.join(ROOT_DIR, 'novel_data')
]

# 必要なディレクトリの作成
for directory in REQUIRED_DIRS:
    if not os.path.exists(directory):
        os.makedirs(directory)