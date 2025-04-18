#!/usr/bin/env python3
"""
小説データをHTML形式にエクスポートするメインスクリプト
"""
import os
import sys
from pathlib import Path

# ルートディレクトリをパスに追加
current_dir = Path(__file__).parent
root_dir = current_dir.parent
sys.path.insert(0, str(root_dir))

from app.utils.exporters.html_exporter import HTMLExporter, run_export
from app.utils.logger_manager import get_logger

# ロガーの設定
logger = get_logger('ExportScript')


def main():
    """メイン処理"""
    import argparse

    # コマンドライン引数の解析
    parser = argparse.ArgumentParser(description='小説データをHTML形式にエクスポートするツール')
    parser.add_argument('--dir', default='html_export', help='エクスポート先ディレクトリ')
    parser.add_argument('--no-zip', action='store_true', help='ZIPファイルを作成しない')
    parser.add_argument('--ncode', help='特定の小説だけをエクスポート')

    args = parser.parse_args()

    # エクスポート処理を実行
    try:
        if args.ncode:
            # 特定の小説のみエクスポート
            exporter = HTMLExporter(args.dir)
            result = exporter.export_novel(args.ncode)

            if result:
                logger.info(f"小説 {args.ncode} のエクスポートが完了しました")
                print(f"小説 {args.ncode} のエクスポートが完了しました。ディレクトリ: {args.dir}")
            else:
                logger.error(f"小説 {args.ncode} のエクスポートに失敗しました")
                print(f"小説 {args.ncode} のエクスポートに失敗しました。ログを確認してください。")

            if not args.no_zip:
                zip_path = exporter.export_as_zip(f"{args.ncode}_export.zip")
                print(f"ZIPファイルを作成しました: {zip_path}")
        else:
            # 全小説をエクスポート
            result = run_export(args.dir, not args.no_zip)

            if result:
                print("エクスポートが正常に完了しました")
            else:
                print("エクスポートに失敗しました。ログを確認してください。")

        return 0 if result else 1

    except KeyboardInterrupt:
        print("\nエクスポート処理を中断しました")
        return 130
    except Exception as e:
        logger.error(f"予期しないエラーが発生しました: {e}")
        import traceback
        logger.error(traceback.format_exc())
        print(f"エラー: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())