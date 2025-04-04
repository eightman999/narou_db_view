#!/usr/bin/env python3
"""
narou_db_view メインエントリーポイント
"""
from app.main import main

if __name__ == "__main__":
    # core.checkerから必要な初期化関数をインポート
    from core.checker import dell_dl, del_yml, db_update, shinchaku_checker, load_conf
    from app.bookshelf import shelf_maker, get_last_read

    # 初期化処理
    dell_dl()
    del_yml()
    main_shelf = shelf_maker()
    last_read_novel, last_read_epno = get_last_read(main_shelf)
    set_font, novel_fontsize, bg_color = load_conf()
    db_update()
    shinchaku_ep, main_shinchaku, shinchaku_novel = shinchaku_checker()

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