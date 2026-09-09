# narou_db_view — RETIRED

> **Status: retired (2026-09-09).**
>
> 「なろう小説」DBの管理・閲覧を試した旧アプリケーションです。新規開発は終了し、役割は現在の `eightman999/Novel_reader_app` に統合されています。

## Distilled lessons

旧DB viewer / builder群から残すべきデータ保全則は以下へ蒸留しました。

- `eightman999/Novel_reader_app/docs/legacy-narou-distillation-2026-09-09.md`

特に次を現行側の不変条件として残しています。

- remote総話数はlocal完全性の証明ではない
- `MAX(episode_no)` だけで途中欠番を見逃さない
- fetch failure / not found / restrictedを同一状態に潰さない
- source由来データの再取得でfavorite / last-read / progressを消さない
- 通常updateとrepairを区別する

コードと履歴はhistorical prototypeとして残しますが、仕様・実装の正典ではありません。
