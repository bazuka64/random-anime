# Random Anime Tiles

`tkinter`で歴代アニメをランダムにタイル表示するデスクトップアプリです。

- Jikan APIからアニメ一覧とサムネ画像をランダム取得
- 日本語タイトルを優先して表示
- サムネ付きでタイル状に表示
- タイルクリックでブラウザ検索: `英語タイトル free video`

## セットアップ

JikanのJPGサムネ画像を表示するため、画像変換に`Pillow`を使います。

```bash
pip install -r requirements.txt
```

## 実行方法

```bash
python main.py
```

うまく起動しない場合は、Pythonに`tkinter`が含まれているか確認してください。
