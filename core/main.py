#!/usr/bin/env python3
"""
narou_db_view メインエントリーポイント（並列処理最適化版）
"""
import concurrent.futures
import threading
import time
from app.main import main
from utils.logger_manager import get_logger

# ロガーの設定
logger = get_logger('CoreMain')


def run_async(func, *args, **kwargs):
    """非同期で関数を実行し、結果を返す関数"""
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(func, *args, **kwargs)
        return future


if __name__ == "__main__":
    # 処理開始時間を記録
    start_time = time.time()

    logger.info("アプリケーション起動開始")

    # core.checkerから必要な関数をインポート
    from core.checker import dell_dl, del_yml, db_update, shinchaku_checker, load_conf
    from app.bookshelf import shelf_maker, get_last_read

    # 並列実行する初期化タスク
    logger.info("初期化処理の並列実行開始")

    # 設定ロード（依存関係が低く、他の処理と並列に実行可能）
    config_future = run_async(load_conf)

    # 古いファイルのクリーンアップ処理を並列実行
    cleanup_thread = threading.Thread(target=lambda: (dell_dl(), del_yml()))
    cleanup_thread.daemon = True
    cleanup_thread.start()

    # データベース更新（時間のかかる処理）
    db_update_future = run_async(db_update)

    # メインの本棚データを読み込む
    shelf_future = run_async(shelf_maker)

    # 各タスクの結果を取得
    main_shelf = shelf_future.result()
    set_font, novel_fontsize, bg_color = config_future.result()

    # 最後に読んだ小説情報を取得（本棚データに依存）
    last_read_novel, last_read_epno = get_last_read(main_shelf)

    # データベース更新の完了を待機
    db_update_future.result()

    # 新着チェック（データベース更新完了後に実行）
    shinchaku_ep, main_shinchaku, shinchaku_novel = shinchaku_checker()

    # クリーンアップスレッドの完了を待機（必要であれば）
    if cleanup_thread.is_alive():
        cleanup_thread.join(timeout=1.0)  # 最大1秒待機

    # 処理完了時間を記録
    elapsed_time = time.time() - start_time
    logger.info(f"初期化完了: {elapsed_time:.2f}秒")

    # メインアプリケーションを起動
    main(
        main_shelf=main_shelf,
        last_read_novel=last_read_novel,
        last_read_epno=last_read_epno,
        set_font=set_font,
        novel_fontsize=novel_fontsize,
        bg_color=bg_color,
        shinchaku_ep=shinchaku_ep,
        main_shinchaku=main_shinchaku,
        shinchaku_novel=shinchaku_novel
    )