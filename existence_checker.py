
import sqlite3
from checker import existence_check
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

# データベースのパス
DB_PATH = 'database/novel_status.db'

# 並列処理の設定
MAX_WORKERS = 8

# 書き込み用プールとロック
write_pool = []
write_pool_lock = Lock()

# 処理中の未完了カウンタ
nokori_update = 0
nokori_update_lock = Lock()


def update_rating(n_code):
    """指定されたn_codeのratingを返す"""
    global nokori_update

    try:
        # 備考: 関数 existence_check を呼び出し rating を取得
        rating = existence_check(n_code)
        return n_code, rating
    except Exception as e:
        print(f"Error processing n_code: {n_code}, Error: {str(e)}\n")
        return n_code, None  # エラー時は None を返す
    finally:
        # 処理が終わったらnokori_updateを-1する
        with nokori_update_lock:
            nokori_update -= 1
            print(f"Remaining updates: {nokori_update}\n")


def main():
    global write_pool
    global nokori_update

    # データベース接続を開始して全ての n_code を取得
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT n_code FROM novels_descs")
    n_codes = [row[0] for row in cursor.fetchall()]
    conn.close()

    # n_codesの数をグローバル変数nokori_updateに設定
    with nokori_update_lock:
        nokori_update = len(n_codes)
        print(f"Initial updates to process: {nokori_update}\n")

    # ThreadPoolExecutor を使用して並列処理を実行
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        results = list(executor.map(update_rating, n_codes))

    # スレッドセーフにプールを更新
    with write_pool_lock:
        write_pool.extend([result for result in results if result[1] is not None])

    # 全ての結果が収集されたら一括でデータベースに書き込む
    flush_write_pool()

def flush_write_pool():
    """プールされているデータを一括でデータベースに書き込む"""
    global write_pool

    with write_pool_lock:  # スレッドセーフにプールへアクセス
        if not write_pool:
            return  # プールが空ならスキップ

        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.executemany(
                "UPDATE novels_descs SET rating = ? WHERE n_code = ?", write_pool
            )
            conn.commit()
            conn.close()
            print(f"Flushed {len(write_pool)} records to the database.")
        except Exception as e:
            print(f"Error while writing to database: {str(e)}")
        finally:
            write_pool = []  # プールをクリア


if __name__ == "__main__":
    main()
# ```
#
# ### 修正のポイント
# 1. **`update_rating` 関数の変更**:
# - 各 `n_code` に対して `rating` を取得し、`(n_code, rating)` の組み合わせを返す。
# - エラー発生時にはログを出力し、`None` を返すことでスキップする設計としました。
#
# 2. **メイン処理の変更**:
# - 並列処理で結果を収集し、`write_pool` に一括で追加。
# - 全ての `n_code` に対する結果が収集された後でまとめて `flush_write_pool` を呼び出しデータベースに書き込み。
#
# 3. **安全性と効率性の確保**:
# - `write_pool` へのアクセスはスレッドセーフに操作。
# - すべての `n_code` データが処理された時点で一括書き込みを行うことで、データベース操作の負荷削減。
#
# ### 実行の流れ
# 1. 全ての `n_code` に対して並列処理を行い、`rating` を取得。
# 2. 各 `n_code` に対応する `(n_code, rating)` ペアを `write_pool` に収集。
# 3. 処理完了後、`flush_write_pool` を呼び出して全てのデータをデータベースへ一括で書き込む。
#
# これで「全ての `n_code` に対して `rating` が収集された後にまとめて書き込む」仕様が実現可能です！
