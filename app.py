import json
import time
import streamlit as st
import streamlit.components.v1 as components

import pdf_engine

# --- 1. ページ設定 ---
st.set_page_config(
    page_title="PDF Diet - PDF圧縮/軽量化ツール",
    page_icon="📄",
    layout="centered"
)

# --- 2. GA イベント管理 (キューシステム) ---
if "ga_events" not in st.session_state:
    st.session_state["ga_events"] = []

def queue_ga_event(event_name, params):
    """GA4に送るイベントを一旦リストに貯める"""
    st.session_state["ga_events"].append({"name": event_name, "params": params})

# --- 4. ロジック関数 ---
def human_bytes(n: int) -> str:
    if n >= 1024 * 1024: return f"{n / (1024 * 1024):.2f} MB"
    if n >= 1024: return f"{n / 1024:.0f} KB"
    return f"{n} B"

def percent_reduction(before: int, after: int) -> float:
    return (before - after) * 100.0 / before if before > 0 else 0.0

def out_filename_from(uploaded_name: str) -> str:
    if not uploaded_name: return "pdf_diet_light.pdf"
    stem = uploaded_name[:-4] if uploaded_name.lower().endswith(".pdf") else uploaded_name
    return f"{stem}_light.pdf"

def make_progress_cb(p_bar):
    """全体の進捗(0-1)・経過時間・残り時間の目安を1本のバーに表示する。"""
    t0 = time.time()
    def _progress(frac, text, eta):
        parts = [text, f"経過 {int(time.time() - t0)}秒"]
        if eta is not None and eta >= 1:
            parts.append(f"このステップの残り 約{int(eta)}秒")
        p_bar.progress(frac, text=f"{int(frac * 100)}%  |  " + "  ・  ".join(parts))
    return _progress

# --- 5. UIのCSS (ゴースト化・重なり対策を追加) ---
st.markdown("""<style>
    /* 高速更新時のダブり（ゴースト）を防ぐため、アニメーションを強制オフ */
    div[data-testid="stVerticalBlock"] > div {
        transition: none !important;
        animation: none !important;
    }
    
    .main .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; }
    h1 { margin-top: -40px !important; margin-bottom: 0px !important; padding-bottom: 10px !important; }
    h3 { margin-top: 10px !important; margin-bottom: 5px !important; }
    .stCaption { margin-bottom: 1rem !important; }
    
    [data-testid="stFileUploader"] section > label { display: none; }
    [data-testid="stFileUploader"] section svg { display: none !important; }
    [data-testid="stFileUploader"] section div div span,
    [data-testid="stFileUploader"] section div div small { display: none !important; }
    [data-testid="stFileUploader"] section [data-testid="stFileUploaderDropzoneInstructions"] { font-size: 0 !important; }
    [data-testid="stFileUploader"] section [data-testid="stFileUploaderDropzoneInstructions"]::before {
        content: "PDFをアップロード"; display: block; font-size: 0.9rem !important; color: rgba(255, 255, 255, 0.9) !important; visibility: visible !important;
    }
    [data-testid="stFileUploader"] section [data-testid="stFileUploaderDropzoneInstructions"]::after {
        content: "最大100MB"; display: block; font-size: 0.7rem !important; color: rgba(255, 255, 255, 0.5) !important; visibility: visible !important;
    }
    [data-testid="stFileUploader"] section button[kind="secondary"] {
        font-size: 0 !important; min-width: 120px !important; height: 36px !important; display: flex !important; align-items: center !important; justify-content: center !important; margin: 0 auto !important;
    }
    [data-testid="stFileUploader"] section button[kind="secondary"] > * { display: none !important; }
    /* アップロード失敗時の英語メッセージを日本語に差し替え */
    [data-testid="stFileUploaderFileErrorMessage"] { font-size: 0 !important; }
    [data-testid="stFileUploaderFileErrorMessage"]::before {
        content: "アップロードできません。100MB以下のPDFファイルを選んでください。"; font-size: 0.85rem !important;
    }
    /* 処理中に右上へ出る英語の「Running...」表示は、独自の進捗バーがあるので隠す */
    [data-testid="stStatusWidget"] { display: none !important; }
    [data-testid="stFileUploader"] section button[kind="secondary"]::after {
        content: "ファイルを選択"; font-size: 0.9rem !important; color: white !important; visibility: visible !important;
    }
    @media (max-width: 768px) {
        [data-testid="stFileUploader"] section { padding: 8px !important; }
        [data-testid="stFileUploader"] section [data-testid="stFileUploaderDropzoneInstructions"]::before { font-size: 0.8rem !important; }
    }
    .viewerBadge_container__1QS1n, .main .element-container a.header-anchor { display: none; }
</style>""", unsafe_allow_html=True)

# ==========================================
# 画面レイアウトの絶対領域（コンテナ）を定義
# ==========================================
header_area = st.container()
setting_area = st.container()
action_area = st.container()
result_area = st.container()
footer_area = st.container()

# --- 6. ヘッダー＆アップロード (header_area) ---
with header_area:

    uploaded = st.file_uploader("PDFを選択", type=["pdf"], accept_multiple_files=False)
    
    # 二重表示を防ぐための空箱
    upload_msg_box = st.empty()

    if uploaded is not None:
        upload_sig = f"{uploaded.name}_{uploaded.size}"
        if st.session_state.get("last_upload_sig") != upload_sig:
            queue_ga_event("file_upload", {"file_size_mb": round(uploaded.size / (1024 * 1024), 2)})
            st.session_state["last_upload_sig"] = upload_sig

        file_size_mb = uploaded.size / (1024 * 1024)
        if file_size_mb > 100:
            upload_msg_box.error(f"【サイズ超過】{file_size_mb:.1f}MBあります。100MB以下にしてください。")
            st.stop()
        upload_msg_box.success(f"アップロード完了: {uploaded.name} ({file_size_mb:.1f}MB)")

# --- 7. 設定エリア (setting_area) ---
# 設定を変えても、ページ全体（広告など）を再実行しないよう fragment にする。
# 値は key で session_state に保存し、ボタン側から読む。
@st.fragment
def settings_fragment():
    st.subheader("設定", anchor=False)
    auto = st.checkbox("自動最適化モード", value=True, key="auto_optimize", help="目標サイズを下回るまで、DPIとJPEG画質を段階的に調整します。ONのときは手動設定は無効になります。")
    st.checkbox("リンクを保持する", value=True, key="keep_uri_links", help="PDF内のクリック可能なリンク（URL・ページ内リンク）としおりを維持します。")

    if auto:
        st.number_input("目標ファイルサイズ (MB)", 1, 50, value=10, key="target_size_mb", help="このサイズを下回るまで自動調整します。")

    col1, col2 = st.columns(2)
    with col1:
        st.slider("出力DPI", 100, 250, 150, step=10, key="dpi", disabled=auto, help="高いほど鮮明ですがサイズが大きくなります。標準は150です。")
    with col2:
        st.slider("JPEG画質 (1-100)", 1, 100, 85, step=1, key="jpeg_quality", disabled=auto, help="高いほどノイズが減ります。70-80が推奨です。")

    st.divider()

with setting_area:
    settings_fragment()

# fragment 内のウィジェット値を取り出す（初回描画前は既定値）
auto_optimize = st.session_state.get("auto_optimize", True)
keep_uri_links = st.session_state.get("keep_uri_links", True)
target_size_mb = st.session_state.get("target_size_mb", 10) if auto_optimize else 10
dpi = st.session_state.get("dpi", 150)
jpeg_quality = st.session_state.get("jpeg_quality", 85)

# --- 8. 実行ボタン (action_area) ---
with action_area:
    start_clicked = st.button("軽量化を開始する", type="primary", disabled=(uploaded is None))
    signature = (auto_optimize, keep_uri_links, dpi, jpeg_quality, target_size_mb, uploaded.name if uploaded else None, getattr(uploaded, "size", None))

# --- 9. 処理結果エリア (result_area) ---
# ※ここは広告より「絶対上」に配置されるため、重なりが発生しません。
with result_area:
    if start_clicked and uploaded:
        queue_ga_event("optimization_run", {
            "auto_mode": auto_optimize,
            "target_mb": target_size_mb if auto_optimize else None,
            "dpi": None if auto_optimize else dpi,
            "quality": None if auto_optimize else jpeg_quality
        })

        # 重い処理の前に、まず進捗表示を出す（画面が固まって見えないように）
        p_bar = st.empty()
        p_bar.progress(0.0, text="0%  |  ファイルを読み込み中…")
        pdf_bytes = uploaded.getvalue()
        before_size = len(pdf_bytes)

        try:
            cb = make_progress_cb(p_bar)
            common = dict(keep_links=keep_uri_links, keep_toc=keep_uri_links, progress_cb=cb)
            if auto_optimize:
                result = pdf_engine.auto_compress(pdf_bytes, int(target_size_mb * 1024 * 1024), **common)
            else:
                result = pdf_engine.compress(pdf_bytes, dpi=dpi, quality=jpeg_quality, **common)
            result = pdf_engine.finalize(result, pdf_bytes)
            out_bytes, used_dpi, used_quality = result.data, result.dpi, result.quality
            attempts_for_ui = [
                {"試行": i + 1, "DPI": a.dpi, "JPEG画質": a.quality,
                 "出力サイズ": human_bytes(a.size), "目標超過": "はい" if a.over_target else "いいえ"}
                for i, a in enumerate(result.attempts)
            ] if auto_optimize else []

            # 処理が終わったら進捗表示の箱を空にしてスッキリさせる
            p_bar.empty()
            
            after_size = len(out_bytes)
            
            queue_ga_event("optimization_success", {
                "after_mb": round(after_size / (1024 * 1024), 2),
                "reduction_rate": round(percent_reduction(before_size, after_size), 1),
                "attempts": len(attempts_for_ui) if auto_optimize else 1
            })

            if result.fell_back_to_original:
                st.warning("このPDFは画像化すると元より大きくなるため、元のPDFをそのまま出力します。")
            elif auto_optimize and after_size > int(target_size_mb * 1024 * 1024):
                st.warning(f"目標サイズ（{target_size_mb}MB）には届きませんでした。最小サイズ（{human_bytes(after_size)}）で出力します。")
            else:
                st.success("軽量化が完了しました。")
            m1, m2, m3 = st.columns(3)
            m1.metric("元のサイズ", human_bytes(before_size))
            m2.metric("軽量化後", human_bytes(after_size))
            m3.metric("削減率", f"{percent_reduction(before_size, after_size):.1f}%")
            
            st.download_button("軽量化済みPDFを保存する", data=out_bytes, file_name=out_filename_from(uploaded.name), mime="application/pdf")
            
            if attempts_for_ui:
                with st.expander("自動最適化の試行履歴（詳細）"):
                    st.table(attempts_for_ui)
            
            st.session_state["res_sig"] = signature
            st.session_state["res_bytes"] = out_bytes
            st.session_state["res_name"] = out_filename_from(uploaded.name)
            st.session_state["res_attempts"] = attempts_for_ui
            
        except Exception as e:
            st.exception(e)

    elif st.session_state.get("res_bytes") is not None and signature == st.session_state.get("res_sig"):
        st.subheader("前回の結果", anchor=False)
        st.download_button("軽量化済みPDFを保存する", data=st.session_state["res_bytes"], file_name=st.session_state["res_name"], mime="application/pdf")
        if st.session_state.get("res_attempts"):
            with st.expander("自動最適化の試行履歴（詳細）"):
                st.table(st.session_state["res_attempts"])

# --- 10. GA通信 (footer_area) ---
# タイトル・説明・広告・プライバシーポリシー・ソースコードのリンクは、
# Streamlit の外（静的HTML: site/）に置いている。ここでは計測イベントの送信だけを行う。
with footer_area:
    # 貯めておいたGAイベントをここで一気に送信！
    if st.session_state["ga_events"]:
        js_code = "<script>\n"
        for ev in st.session_state["ga_events"]:
            js_code += f"if(window.parent && window.parent.gtag) {{ window.parent.gtag('event', '{ev['name']}', {json.dumps(ev['params'], ensure_ascii=False)}); }}\n"
        js_code += "</script>"
        components.html(js_code, height=0)
        st.session_state["ga_events"] = []