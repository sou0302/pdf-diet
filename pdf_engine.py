"""PDF Diet の圧縮エンジン（UI非依存）。

方針:
  * 各ページを画像化してデザインを崩さない
  * 元のリンク（URL / ページ内リンク）としおりを再配置する
  * ページを1枚ずつ「描画→JPEG化→PDFへ追加」して、メモリを抑える
  * 自動最適化は、150DPI・画質85から旧版と同じ順序で段階的に下げ、目標に収まった時点で終了
"""
import io
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import pymupdf

# progress_cb(全体の進捗 0.0-1.0, 表示テキスト, 残り秒数の目安 or None)
ProgressCb = Optional[Callable[[float, str, Optional[float]], None]]

# 自動最適化の探索ルール（旧版と同じ動き）
_START_DPI, _START_QUALITY = 150, 85
_MIN_DPI, _MIN_QUALITY = 60, 10
_MAX_ATTEMPTS = 40
# 何回目のパスかに応じた、全体進捗の割り当て（成功したら即100%にする）
_PASS_RANGES = ((0.0, 0.60), (0.65, 0.88), (0.88, 0.94), (0.94, 0.97), (0.97, 0.99))


@dataclass
class Attempt:
    dpi: int
    quality: int
    size: int
    over_target: bool = False


@dataclass
class Result:
    data: bytes
    dpi: int
    quality: int
    attempts: List[Attempt] = field(default_factory=list)
    fell_back_to_original: bool = False


def _emit(cb: ProgressCb, frac: float, text: str, eta: Optional[float] = None) -> None:
    if cb:
        cb(min(max(frac, 0.0), 1.0), text, eta)


# ---------------------------------------------------------------- 1パス分の圧縮
def _run_pass(src: "pymupdf.Document", dpi: int, quality: int, *, keep_links: bool,
              keep_toc: bool, cb: ProgressCb, lo: float, hi: float, label: str) -> bytes:
    """全ページを1枚ずつ 描画→JPEG化→追加 し、PDFのバイト列を返す。"""
    zoom = dpi / 72.0
    mat = pymupdf.Matrix(zoom, zoom)
    n = src.page_count
    out = pymupdf.open()
    t0 = time.time()
    try:
        for i, page in enumerate(src):
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = pix.tobytes("jpeg", jpg_quality=quality)
            del pix  # すぐ解放してメモリを抑える
            new_page = out.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(new_page.rect, stream=img)
            if keep_links:
                for ln in page.get_links():
                    kind = ln.get("kind")
                    if kind == pymupdf.LINK_URI:
                        new_page.insert_link({"kind": kind, "from": ln["from"], "uri": ln["uri"]})
                    elif kind == pymupdf.LINK_GOTO:
                        new_page.insert_link({"kind": kind, "from": ln["from"],
                                              "page": ln.get("page", 0),
                                              "to": ln.get("to", pymupdf.Point(0, 0)),
                                              "zoom": ln.get("zoom", 0)})
            done = i + 1
            eta = (time.time() - t0) * (n - done) / done
            _emit(cb, lo + (hi - lo) * 0.92 * done / n, f"{label}（{done}/{n}ページ）", eta)
        if keep_toc:
            toc = src.get_toc()
            if toc:
                try:
                    out.set_toc(toc)
                except Exception:
                    pass
        if src.metadata:
            out.set_metadata(src.metadata)
        _emit(cb, lo + (hi - lo) * 0.95, "ファイルを書き出し中", None)
        return out.tobytes(garbage=4, clean=1, deflate=True)
    finally:
        out.close()


# ---------------------------------------------------------------- 公開API
def compress(pdf_bytes: bytes, *, dpi: int = 150, quality: int = 85,
             keep_links: bool = True, keep_toc: bool = True,
             progress_cb: ProgressCb = None) -> Result:
    """手動設定で1回だけ圧縮する。"""
    src = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        data = _run_pass(src, dpi, quality, keep_links=keep_links, keep_toc=keep_toc,
                         cb=progress_cb, lo=0.0, hi=1.0, label="圧縮中")
        _emit(progress_cb, 1.0, "完了")
        return Result(data, dpi, quality, [Attempt(dpi, quality, len(data))])
    finally:
        src.close()


def _next_params(dpi: int, q: int):
    """次に試す(DPI, 画質)。旧版と同じ順序で、画質とDPIを段階的に下げる。"""
    if dpi == 150 and q == 85:
        return dpi, 70
    if dpi == 150 and q == 70:
        return 120, 80
    if dpi == 120 and q == 80:
        return dpi, 70
    if q > 60:
        return dpi, max(_MIN_QUALITY, q - 5)
    if dpi > _MIN_DPI:
        return max(_MIN_DPI, dpi - 10), q
    return dpi, max(_MIN_QUALITY, q - 5)


def auto_compress(pdf_bytes: bytes, target_bytes: int, *, keep_links: bool = True,
                  keep_toc: bool = True, progress_cb: ProgressCb = None) -> Result:
    """目標サイズを下回るまで、DPIとJPEG画質を段階的に調整する（探索順は旧版と同じ）。"""
    # 進捗が逆戻りしないよう、常に最大値を保つ
    user_cb, high = progress_cb, [0.0]

    def progress_cb(frac, text, eta):
        high[0] = max(high[0], frac)
        if user_cb:
            user_cb(high[0], text, eta)

    src = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    attempts: List[Attempt] = []
    best: Optional[Result] = None
    dpi, q = _START_DPI, _START_QUALITY
    try:
        for n in range(1, _MAX_ATTEMPTS + 1):
            lo, hi = _PASS_RANGES[min(n - 1, len(_PASS_RANGES) - 1)]
            data = _run_pass(src, dpi, q, keep_links=keep_links, keep_toc=keep_toc,
                             cb=progress_cb, lo=lo, hi=hi,
                             label=f"試行{n}（DPI {dpi}・画質 {q}）")
            attempts.append(Attempt(dpi, q, len(data), len(data) > target_bytes))
            if best is None or len(data) < len(best.data):
                best = Result(data, dpi, q)
            if len(data) <= target_bytes:
                break
            dpi, q = _next_params(dpi, q)
            if dpi == _MIN_DPI and q == _MIN_QUALITY:
                break
        best.attempts = attempts
        _emit(progress_cb, 1.0, "完了")
        return best
    finally:
        src.close()


def finalize(result: Result, original: bytes) -> Result:
    """圧縮後の方が大きい場合は元PDFを返す。"""
    if len(result.data) >= len(original):
        return Result(original, result.dpi, result.quality, result.attempts, True)
    return result
