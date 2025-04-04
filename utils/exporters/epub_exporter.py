import sqlite3
from ebooklib import epub
import zipfile

def create_epub_from_db(n_code):
    # データベースに接続
    conn = sqlite3.connect('database/novel_status.db')
    cursor = conn.cursor()

    # n_code に基づいて小説の詳細を取得
    cursor.execute('''
        SELECT title, author, Synopsis
        FROM novels_descs
        WHERE n_code = ?
    ''', (n_code,))
    novel = cursor.fetchone()

    if not novel:
        print(f"No novel found with n_code: {n_code}")
        return

    title, author, synopsis = novel

    # EPUB 本を作成
    book = epub.EpubBook()

    # メタデータを設定
    book.set_identifier(n_code)
    book.set_title(title)
    book.set_language('ja')
    book.add_author(author)

    # 章を作成
    c1 = epub.EpubHtml(title='あらすじ', file_name='chap_00000.xhtml', lang='ja')
    c1.content = f'<h1>{title}</h1><p>{synopsis}</p>'
    book.add_item(c1)

    # 目次を定義
    toc = [epub.Link('chap_01.xhtml', 'あらすじ', 'synopsis')]

    # n_code に基づいて全ての話数を取得
    cursor.execute('''
        SELECT episode_no, e_title, body
        FROM episodes
        WHERE ncode = ?
        ORDER BY episode_no
    ''', (n_code,))
    episodes = cursor.fetchall()
    print("check")
    # 各話数の XHTML を作成し、目次に追加
    for episode_no, episode_title, episode_content in episodes:
        print(episode_no, episode_title)
        file_name = f'chap_{int(episode_no):05d}.xhtml'
        chapter = epub.EpubHtml(title=episode_title, file_name=file_name, lang='ja')
        chapter.content = f'<h1>{episode_title}</h1><p>{episode_content}</p>'
        book.add_item(chapter)
        toc.append(epub.Link(file_name, episode_title, f'chap_{int(episode_no):05d}'))
    print("check2")
    # 目次を本に設定
    book.toc = tuple(toc)

    # デフォルトの NCX と Nav ファイルを追加
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # CSS スタイルを定義
    style = 'BODY { font-family: Arial, sans-serif; }'
    nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css", media_type="text/css", content=style)
    book.add_item(nav_css)

    # スパインを作成
    book.spine = ['nav'] + [chapter for chapter in book.items if isinstance(chapter, epub.EpubHtml)]

    # 一時ファイルにEPUBを書き込む
    epub_file = f'{n_code}.epub'
    epub.write_epub(epub_file, book, {})

    print("check3")
    # データベース接続を閉じる
    conn.close()

# 使用例
create_epub_from_db('n6300hz')