# PDF Diet

重いPDF（例：Canva等で作成されたもの）を「各ページを画像化」して軽量化し、デザインを崩さずに元のリンクを同じ位置へ再配置するWebアプリです。

https://pdf-diet.sou-is.jp/

## 特徴

- 各ページを画像化するので、レイアウトやフォントが崩れない
- URLリンク・ページ内リンク・しおりを保持
- 目標ファイルサイズ（MB）を指定すると、DPI と JPEG 画質を段階的に下げて自動で調整
- 圧縮後に元より大きくなる場合は、元のPDFをそのまま返す

## 構成

| ファイル | 役割 |
|---|---|
| `app.py` | 圧縮アプリの画面（Streamlit）。アップロード・設定・進捗・結果だけを担当 |
| `pdf_engine.py` | 圧縮エンジン（UI非依存）。ページを1枚ずつ処理してメモリを抑える |
| `site/` | 静的ページ（タイトル・説明・広告・フッター）のテンプレートと CSS |
| `build_site.py` | `site/` のテンプレートに環境変数の値を差し込み、公開用HTMLを書き出す |
| `deploy/` | nginx・systemd の設定例 |

公開時は、静的ページ（`/`）の中に、Streamlit アプリ（`/app/`）を iframe で埋め込んでいます。広告や説明文を Streamlit の外に置くことで、処理中に画面全体が灰色になることを避けています。

## 使い方（ローカル実行）

```bash
pip install -r requirements.txt
streamlit run app.py
```

アプリ単体は、このコマンドだけで動きます（`http://localhost:8501`）。

## 公開する場合

```bash
# 1. 静的ページをビルド（ID・リンクは環境変数で渡す。未設定のものは表示されない）
ADSENSE_CLIENT=ca-pub-XXXX ADSENSE_SLOT=XXXX GA_ID=G-XXXX \
SOURCE_CODE_URL=https://github.com/<user>/pdf-diet \
HELP_URL=... PRIVACY_URL=... CONTACT_URL=... \
python build_site.py /var/www/pdf-diet-site

# 2. Streamlit を /app/ で起動
streamlit run app.py --server.port 8501 --server.address 127.0.0.1 \
  --server.baseUrlPath app --server.maxUploadSize 100
```

nginx と systemd の設定例は `deploy/` を参照してください。

### 環境変数（`build_site.py`）

| 変数 | 内容 |
|---|---|
| `ADSENSE_CLIENT` / `ADSENSE_SLOT` | AdSense。両方そろったときだけ広告を出す |
| `GA_ID` | Google アナリティクスの測定ID |
| `SOURCE_CODE_URL` | 「ソースコード」リンクの飛び先（AGPL-3.0のソース公開用） |
| `HELP_URL` / `PRIVACY_URL` / `CONTACT_URL` | フッターの「使い方」「プライバシーポリシー」「お問い合わせ」のリンク先 |

## アップロード上限（100MB）

`.streamlit/config.toml` の `maxUploadSize = 100`（MB）で設定しています。nginx 経由で公開する場合は `client_max_body_size 100M;` も合わせてください。

## プライバシー

アップロードされたPDFはサーバーのファイルシステムに書き出さず、メモリ上で処理します。

## ライセンス

[AGPL-3.0](LICENSE)。依存ライブラリの [PyMuPDF](https://github.com/pymupdf/PyMuPDF) が AGPL-3.0 のため、本アプリも同ライセンスで公開しています。

## 開発について

PDF Diet は AI を活用して作成されました。初版は Cursor（企画・指示文は Gemini）、今回の改修は Claude Code で行っています。
