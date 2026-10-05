"""静的ページ（site/*.template.html）に環境変数の値を差し込んで、公開用のHTMLを書き出す。

ID類をリポジトリに含めないためのスクリプト。値が未設定のブロックは、ブロックごと取り除く。

使い方:
    ADSENSE_CLIENT=ca-pub-xxxx ADSENSE_SLOT=123 GA_ID=G-XXXX SOURCE_CODE_URL=https://... \
        python build_site.py [出力先ディレクトリ(既定: site/dist)]

環境変数:
    ADSENSE_CLIENT, ADSENSE_SLOT : AdSense（両方そろったときだけ広告を出す）
    GA_ID                        : Googleアナリティクスの測定ID
    SOURCE_CODE_URL              : 「ソースコード」リンクの飛び先（AGPL-3.0のソース公開）
    HELP_URL / PRIVACY_URL / CONTACT_URL : フッターの「使い方」「プライバシーポリシー」「お問い合わせ」リンク先
                                           （未設定のリンクは表示しない）
"""
import os
import re
import shutil
import sys
from pathlib import Path

SRC = Path(__file__).parent / "site"
BLOCKS = {  # マーカー名 -> 必要な環境変数
    "GA": ("GA_ID",),
    "AD": ("ADSENSE_CLIENT", "ADSENSE_SLOT"),
    "SRC": ("SOURCE_CODE_URL",),
    "HELP": ("HELP_URL",),
    "PRIVACY": ("PRIVACY_URL",),
    "CONTACT": ("CONTACT_URL",),
}
VARS = ("GA_ID", "ADSENSE_CLIENT", "ADSENSE_SLOT", "SOURCE_CODE_URL", "HELP_URL", "PRIVACY_URL", "CONTACT_URL")


def render(text: str, env: dict) -> str:
    for name, needed in BLOCKS.items():
        pattern = re.compile(rf"[ \t]*<!--{name}:start-->.*?<!--{name}:end-->[ \t]*\n?", re.S)
        if all(env.get(v) for v in needed):
            text = pattern.sub(lambda m: re.sub(rf"[ \t]*<!--{name}:(start|end)-->[ \t]*\n?", "", m.group(0)), text)
        else:
            text = pattern.sub("", text)
    for v in VARS:
        text = text.replace("{{" + v + "}}", env.get(v, ""))
    return text


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else SRC / "dist"
    env = {v: os.environ.get(v, "").strip() for v in VARS}
    out.mkdir(parents=True, exist_ok=True)
    for tpl in SRC.glob("*.template.html"):
        name = tpl.name.replace(".template", "")
        (out / name).write_text(render(tpl.read_text(encoding="utf-8"), env), encoding="utf-8")
    for static in ("site.css", "favicon.png"):
        shutil.copy(SRC / static, out / static)
    unset = [v for v in VARS if not env[v]]
    print(f"built -> {out}" + (f" (未設定: {', '.join(unset)})" if unset else ""))


if __name__ == "__main__":
    main()
