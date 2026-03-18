# pdf-slimmer

重いPDF（例：Canva等で作成されたもの）を「各ページを画像化（フラット化）」し、さらに元のURLリンク（注釈）を同じ座標に再配置して軽量化するWebアプリです。

## ライセンス

このプロジェクトは **AGPL v3** に基づき提供されます。

## 使い方（ローカル実行）

1. 依存関係のインストール

```bash
pip install -r requirements.txt
```

2. Streamlit起動

```bash
streamlit run app.py
```

3. ブラウザで表示された画面からPDFをアップロード

## アップロード上限（最大200MB）

1GB RAM 制限を考慮し、`.streamlit/config.toml` で `maxUploadSize = 200`（MB）に設定しています。反映には `streamlit run app.py` の再起動が必要です。

## 自動最適化について

「自動最適化モード」をONにすると、まず `DPI=150, JPEG画質=85` で試し、出力が10MBを超えたら段階的に `DPI` と `JPEG画質` を下げて、可能な限り10MB未満へ近づけます。

## プライバシー / 安全性

- アップロードされたPDFは、基本的にサーバーのファイルシステムに書き出さず **メモリ上（BytesIO）** で処理します。
- 画像化とPDF再構成のため、サーバー側のCPU/メモリを使用します。

## 対応

- 元PDF内の **URIリンク注釈** を、フラット化後PDFの同一座標に再配置します。

### 🛠 開発について

PDF Dietは、AI（Cursor / Gemini 3 Flash）を活用して作成されました。