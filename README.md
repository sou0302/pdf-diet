# PDF Diet

重いPDF（例：Canva等で作成されたもの）を「各ページを画像化」して軽量化し、デザインを崩さずに元のリンクを同じ位置へ再配置するWebアプリです。

https://pdf-diet.sou-is.jp/

## 特徴

- 各ページを画像化するので、レイアウトやフォントが崩れない
- URLリンク・ページ内リンク・しおりを保持
- 目標ファイルサイズ（MB）を指定すると、DPI と JPEG 画質を段階的に下げて自動で調整

## 使い方（ローカル実行）

```bash
pip install -r requirements.txt
streamlit run app.py
```

## アップロード上限（100MB）

`.streamlit/config.toml` の `maxUploadSize = 100`（MB）で設定しています。nginx 経由で公開する場合は `client_max_body_size 100M;` も合わせてください。

## 環境変数（任意）

| 変数 | 内容 |
|---|---|
| `ADSENSE_CLIENT` / `ADSENSE_SLOT` | AdSense を表示する場合のみ設定。未設定なら広告は出ません |
| `SOURCE_CODE_URL` | フッターに表示する「ソースコードはこちら」のリンク先 |

## 構成

- `app.py` : Streamlit のUI
- `pdf_engine.py` : 圧縮エンジン（UI非依存）

## プライバシー

アップロードされたPDFはサーバーのファイルシステムに書き出さず、メモリ上で処理します。

## ライセンス

[AGPL-3.0](LICENSE)。依存ライブラリの [PyMuPDF](https://github.com/pymupdf/PyMuPDF) が AGPL-3.0 のため、本アプリも同ライセンスで公開しています。

## 開発について

PDF Diet は AI を活用して作成されました。初版は Cursor（企画・指示文は Gemini）、今回の改修は Claude Code で行っています。
