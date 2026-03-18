import io
from typing import Callable, Optional

import fitz  # PyMuPDF
import streamlit as st


def flatten_pdf(
    pdf_bytes: bytes,
    *,
    dpi: int = 150,
    jpeg_quality: int = 75,
    keep_uri_links: bool = True,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> bytes:
    """
    各ページを指定DPIの画像（JPEG）に変換し、新しいPDFに1ページ=1画像で再構成する。

    keep_uri_links=True の場合、元PDFの URI リンク注釈（クリック領域）を同一座標に再配置する。
    """

    in_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        out_doc = fitz.open()  # 空のPDF

        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)

        page_count = in_doc.page_count
        for page_index in range(page_count):
            page = in_doc[page_index]

            # 元ページのURIリンク注釈を取得（from: Rect, uri: str, kind: int 等）
            links = page.get_links() if keep_uri_links else []

            # 画像化（フラット化）。JPEGで保持し、新PDFに画像を埋め込む。
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            img_bytes = pix.tobytes("jpeg", jpg_quality=jpeg_quality)

            page_rect = page.rect

            # 新PDF側は「同じ座標系（同じページサイズ）」でページを作るため、
            # リンクfrom座標はそのまま再配置できる。
            new_page = out_doc.new_page(width=page_rect.width, height=page_rect.height)
            new_page.insert_image(page_rect, stream=img_bytes)

            # リンク注釈を復元（URIのみ）
            if keep_uri_links:
                for ln in links:
                    uri = ln.get("uri")
                    from_rect = ln.get("from")
                    kind = ln.get("kind")

                    if not uri or not from_rect:
                        continue

                    # kind は PDF内のリンク種別。URIリンク以外（例: launch）を誤って移すのを避ける。
                    if kind != fitz.LINK_URI:
                        continue

                    new_page.insert_link(
                        {
                            "kind": fitz.LINK_URI,
                            "from": from_rect,
                            "uri": uri,
                        }
                    )

            if progress_cb is not None:
                progress_cb(page_index + 1, page_count)

        # メタデータは不要になりやすいので削る（極力サイズを圧縮）
        try:
            out_doc.set_metadata({})
        except Exception:
            pass

        # tobytes() では最適化オプションを細かく指定できないため save() を利用
        out_buf = io.BytesIO()
        out_doc.save(
            out_buf,
            garbage=4,
            clean=1,
            deflate=True,
            deflate_images=True,
            deflate_fonts=True,
            preserve_metadata=0,
            use_objstms=True,
            compression_effort=2,
            incremental=0,
        )
        return out_buf.getvalue()
    finally:
        # 明示的に閉じる（メモリ節約）
        try:
            in_doc.close()
        except Exception:
            pass
        # out_doc は try内で生成されるため、未生成時はlocals()でガードする
        if "out_doc" in locals():
            try:
                out_doc.close()
            except Exception:
                pass


st.set_page_config(page_title="PDF Diet", layout="centered")

# アップローダー全体の日本語化（label / button / ドロップゾーン文言）
st.markdown(
    """
    <style>
    [data-testid="stFileUploader"] section > label { display: none; }
    [data-testid="stFileUploader"] section [data-testid="stBaseButton-secondary"] {
        font-size: 0 !important;
    }
    [data-testid="stFileUploader"] section [data-testid="stBaseButton-secondary"]::after {
        content: "ファイルを選択";
        font-size: 1rem !important;
    }
    [data-testid="stFileUploader"] section > div > span { display: none; }
    [data-testid="stFileUploader"] section > div::after {
        content: "ここにPDFをドラッグ＆ドロップ（最大200MB）";
        color: rgba(255, 255, 255, 0.7);
    }
    /* ヘッダーのリンクアイコンを非表示にする */
    .viewerBadge_container__1QS1n, .main .element-container a.header-anchor {
        display: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("PDF Diet", anchor=False)
st.caption("重いPDFを各ページ画像化して軽量化し、クリック可能なURLリンク（注釈）を同一座標に再配置します。")


def human_bytes(n: int) -> str:
    # 仕事用途で見やすいよう、MB/KB優先の簡易表示にします。
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.2f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


def percent_reduction(before: int, after: int) -> float:
    if before <= 0:
        return 0.0
    return (before - after) * 100.0 / before


def out_filename_from(uploaded_name: str) -> str:
    # 例: file.pdf -> file_light.pdf
    if not uploaded_name:
        return "pdf_diet_light.pdf"
    lower = uploaded_name.lower()
    if lower.endswith(".pdf"):
        ext = uploaded_name[len(uploaded_name) - 4 :]
        stem = uploaded_name[: -4]
        return f"{stem}_light{ext}"
    return f"{uploaded_name}_light.pdf"


uploaded = st.file_uploader("PDFを選択", type=["pdf"], help="軽量化したいPDFを選んでください。")

st.subheader("設定", anchor=False)

auto_optimize = st.checkbox(
    "自動最適化モード",
    value=True,
    help=(
        "目標サイズを下回るまで、DPIとJPEG画質を段階的に調整します。"
        "ONのときは手動のDPI/画質設定は無効（グレーアウト）になります。"
    ),
)

keep_uri_links = st.checkbox(
    "URLリンクを保持する",
    value=True,
    help="PDF内のクリック可能なリンクを維持します。",
)

if auto_optimize:
    target_size_mb = st.number_input(
        "目標ファイルサイズ (MB)",
        min_value=1,
        max_value=50,
        step=1,
        value=10,
        help="このサイズ（MB）を下回るまでDPIと画質を自動で調整します。",
    )
else:
    target_size_mb = 10

col1, col2 = st.columns(2)
with col1:
    dpi = st.slider(
        "出力DPI",
        min_value=100,
        max_value=250,
        value=150,
        step=10,
        disabled=auto_optimize,
        help="数値が高いほど画像が鮮明になりますが、ファイルサイズが大きくなります。標準は150です。",
    )
with col2:
    jpeg_quality = st.slider(
        "JPEG画質 (1-100)",
        min_value=1,
        max_value=100,
        value=85,
        step=1,
        disabled=auto_optimize,
        help="数値が高いほどノイズが減ります。70〜80がサイズと画質のバランスが良い設定です。",
    )

st.divider()


def run_with_progress(
    *,
    pdf_bytes: bytes,
    dpi: int,
    jpeg_quality: int,
    keep_uri_links: bool,
) -> bytes:
    with st.spinner(f"軽量化中…（DPI={dpi}, JPEG={jpeg_quality}）"):
        progress_bar = st.progress(0)
        status_text = st.empty()

        def _progress(done: int, total: int) -> None:
            progress_bar.progress(done / total)
            status_text.text(f"処理中: {done}/{total} ページ")

        return flatten_pdf(
            pdf_bytes,
            dpi=dpi,
            jpeg_quality=jpeg_quality,
            keep_uri_links=keep_uri_links,
            progress_cb=_progress,
        )


def auto_optimize_convert(
    pdf_bytes: bytes, keep_uri_links: bool, target_size_bytes: int
) -> tuple[bytes, int, int, list[dict]]:
    attempts: list[dict] = []

    # 指定された初手（神機能の要件）をまず試します。
    dpi_try, quality_try = 150, 85

    # それでもターゲットを下回らないケースがあり得るため、極端すぎない範囲で
    # 「target_size未満になるまで」段階的に下げ続けます。
    min_dpi = 60
    min_quality = 10
    max_attempts = 40

    best_bytes: bytes | None = None
    best_params: tuple[int, int] | None = None

    attempt_index = 0
    while attempt_index < max_attempts:
        attempt_index += 1
        st.subheader(
            f"自動最適化 試行 {attempt_index}/{max_attempts}（DPI={dpi_try}, JPEG={quality_try}）",
            anchor=False,
        )

        out_bytes = run_with_progress(
            pdf_bytes=pdf_bytes,
            dpi=dpi_try,
            jpeg_quality=quality_try,
            keep_uri_links=keep_uri_links,
        )
        out_size = len(out_bytes)

        attempts.append(
            {
                "attempt": attempt_index,
                "dpi": dpi_try,
                "jpeg_quality": quality_try,
                "output_size": human_bytes(out_size),
                "over_target": out_size > target_size_bytes,
            }
        )

        if best_bytes is None or out_size < len(best_bytes):
            best_bytes = out_bytes
            best_params = (dpi_try, quality_try)

        if out_size <= target_size_bytes:
            return out_bytes, dpi_try, quality_try, attempts

        # ここから「段階的に画質とDPIを下げて」target_size未満を狙います。
        # 要件の分岐（最初の3段階）を優先して守る。
        if dpi_try == 150 and quality_try == 85:
            quality_try = 70
        elif dpi_try == 150 and quality_try == 70:
            dpi_try, quality_try = 120, 80
        elif dpi_try == 120 and quality_try == 80:
            quality_try = 70
        else:
            # 品質を優先的に落とし、それでもだめならDPIを落とす。
            if quality_try > 60:
                quality_try = max(min_quality, quality_try - 5)
            elif dpi_try > min_dpi:
                dpi_try = max(min_dpi, dpi_try - 10)
            else:
                # DPIをこれ以上落とせない場合は品質のみ下げる。
                quality_try = max(min_quality, quality_try - 5)

        # これ以上変化がなくなった場合、抜けてベストを返します。
        if dpi_try == min_dpi and quality_try == min_quality:
            break

    # 10MBを下回らなかった場合は、最小サイズの結果をベストとして返します。
    assert best_bytes is not None and best_params is not None
    return best_bytes, best_params[0], best_params[1], attempts


signature = None
if uploaded is not None:
    # ファイルが同一かどうかは「開始時」に bytes を取得して判定するため、
    # ここでは UI 側の設定一致用として簡易署名だけ持ちます。
    signature = (
        auto_optimize,
        keep_uri_links,
        dpi,
        jpeg_quality,
        target_size_mb,
        uploaded.name,
        getattr(uploaded, "size", None),
    )


start_clicked = st.button(
    "軽量化を開始する",
    type="primary",
    disabled=(uploaded is None),
    help="PDFを選んだら、このボタンで軽量化を実行します。",
)

if start_clicked:
    if uploaded is None:
        st.error("PDFを選んでから「軽量化を開始する」を押してください。")
    else:
        pdf_bytes = uploaded.getvalue()
        before_size = len(pdf_bytes)

        st.info("設定に従って軽量化しています…")
        attempts_for_ui: list[dict] = []

        try:
            if auto_optimize:
                target_size_bytes = int(target_size_mb * 1024 * 1024)
                out_bytes, used_dpi, used_quality, attempts_for_ui = auto_optimize_convert(
                    pdf_bytes,
                    keep_uri_links=keep_uri_links,
                    target_size_bytes=target_size_bytes,
                )
            else:
                used_dpi = dpi
                used_quality = jpeg_quality
                out_bytes = run_with_progress(
                    pdf_bytes=pdf_bytes,
                    dpi=used_dpi,
                    jpeg_quality=used_quality,
                    keep_uri_links=keep_uri_links,
                )
        except Exception as e:
            st.exception(e)
            st.error("軽量化に失敗しました。DPIや画質を変えて、もう一度お試しください。")
            raise

        after_size = len(out_bytes)
        reduction = percent_reduction(before_size, after_size)

        st.success("軽量化が完了しました。")
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("元のサイズ", human_bytes(before_size))
        with m2:
            st.metric("軽量化後", human_bytes(after_size))
        with m3:
            st.metric("削減率", f"{reduction:.1f}%")

        out_filename = out_filename_from(uploaded.name)
        st.download_button(
            label="軽量化済みPDFを保存する",
            data=out_bytes,
            file_name=out_filename,
            mime="application/pdf",
        )
        st.caption(f"元のサイズ → 軽量化後（{reduction:.1f}% 削減）")

        # 自動最適化の試行履歴は折りたたみで詳しい人向けに
        if attempts_for_ui:
            with st.expander("自動最適化の試行履歴（詳細）", expanded=False):
                st.table(attempts_for_ui)

        st.info("リンクのクリック範囲は、元のPDFと同じ位置に合わせています。")

        # 結果を次回レンダリングで消えないよう保持（ただし設定が変わったら注意喚起する）
        st.session_state["result_signature"] = signature
        st.session_state["result_bytes"] = out_bytes
        st.session_state["result_out_filename"] = out_filename
        st.session_state["result_used_params"] = {
            "dpi": used_dpi,
            "jpeg_quality": used_quality,
            "keep_uri_links": keep_uri_links,
            "auto_optimize": auto_optimize,
            "target_size_mb": target_size_mb if auto_optimize else None,
        }
        st.session_state["result_attempts"] = attempts_for_ui

if (not start_clicked) and st.session_state.get("result_bytes") is not None and signature is not None:
    # 表示は「現在の設定と同じ結果だけ」を出します（勝手な自動処理を避けるため）。
    if st.session_state.get("result_signature") == signature:
        st.divider()
        used = st.session_state.get("result_used_params", {})
        st.subheader("軽量化が完了しました。", anchor=False)
        st.download_button(
            label="軽量化済みPDFを保存する",
            data=st.session_state["result_bytes"],
            file_name=st.session_state.get("result_out_filename", "pdf_diet_light.pdf"),
            mime="application/pdf",
        )

        if st.session_state.get("result_attempts"):
            with st.expander("自動最適化の試行履歴（詳細）", expanded=False):
                st.table(st.session_state["result_attempts"])

        st.caption(f"使用した設定: DPI={used.get('dpi')} / JPEG画質={used.get('jpeg_quality')} / URLリンク保持={used.get('keep_uri_links')}")
    else:
        st.caption("設定を変えた場合は、「軽量化を開始する」をもう一度押してください。")


