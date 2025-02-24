import sqlite3

# データベースに接続
conn = sqlite3.connect('database/novel_status.db')
cursor = conn.cursor()

# 重複するn_codeを処理するためのクエリ
query = '''
WITH RankedEntries AS (
    SELECT 
        rowid, n_code, title, author, Synopsis, main_tag, sub_tag,
        -- authorが半角スペースでないものを優先、次にtitleが半角スペースでないものを優先
        CASE 
            WHEN TRIM(author) != '' THEN 1
            WHEN TRIM(title) != '' THEN 2
            ELSE 3
        END AS priority
    FROM novels_descs
),
RankedWithRowNum AS (
    -- 各n_code内で優先順位が最も高い行を見つける
    SELECT *, ROW_NUMBER() OVER (PARTITION BY n_code ORDER BY priority) AS row_num
    FROM RankedEntries
)
-- 最も優先順位が高い行のみを残す
DELETE FROM novels_descs
WHERE rowid NOT IN (
    SELECT rowid 
    FROM RankedWithRowNum
    WHERE row_num = 1
);
'''

# クエリを実行
cursor.execute(query)

# コミットして変更を保存
conn.commit()

# 接続を閉じる
conn.close()

print("authorとtitleの優先度に基づいてn_codeを統合しました。")
