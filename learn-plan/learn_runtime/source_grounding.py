from __future__ import annotations

import html
import re
import subprocess
from pathlib import Path
from typing import Any

from learn_core.io import read_text_if_exists
from learn_core.text_utils import normalize_string_list

SKILL_DIR = Path(__file__).resolve().parents[1]


def normalize_source_text(raw_text: str) -> str:
    if not raw_text:
        return ""
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[\t \u3000]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_source_paragraphs(text: str) -> list[str]:
    if not text:
        return []
    result: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        cleaned = re.sub(r"\s+", " ", paragraph).strip()
        if cleaned:
            result.append(cleaned)
    return result


def derive_material_text_candidates(material_local_path: Any) -> list[Path]:
    if not material_local_path:
        return []
    path = Path(str(material_local_path)).expanduser()
    candidates: list[Path] = []
    for suffix in [".txt", ".md", ".html", ".htm"]:
        candidates.append(path.with_suffix(suffix))
        candidates.append(Path(f"{path}{suffix}"))
    if path.suffix.lower() == ".pdf":
        for sibling in path.parent.glob(f"{path.stem}*"):
            if sibling != path and sibling.is_file() and sibling.suffix.lower() in {".txt", ".md", ".html", ".htm"}:
                candidates.append(sibling)
    ordered: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            ordered.append(candidate)
    return ordered


def parse_pages_spec(value: Any) -> list[tuple[int, int]]:
    text = str(value or "").strip()
    if not text:
        return []
    normalized = text.replace("，", ",").replace("、", ",").replace("至", "-").replace("~", "-")
    normalized = normalized.replace("第", "").replace("页", "").replace("pages", "").replace("page", "")
    ranges: list[tuple[int, int]] = []
    for piece in [item.strip() for item in normalized.split(",") if item.strip()]:
        match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", piece)
        if match:
            start = int(match.group(1))
            end = int(match.group(2))
            if start > 0 and end >= start:
                ranges.append((start, end))
            continue
        if piece.isdigit():
            page = int(piece)
            if page > 0:
                ranges.append((page, page))
    return ranges


def resolve_segment_cache_path(material_local_path: Any, segment: dict[str, Any]) -> Path | None:
    if not material_local_path:
        return None
    material_path = Path(str(material_local_path)).expanduser()
    cache_root = SKILL_DIR / "materials_cache"
    cache_key = str(segment.get("source_cache_key") or "").strip()
    if cache_key:
        safe_parts = [re.sub(r"[^A-Za-z0-9._-]+", "-", part) for part in cache_key.split("/") if part.strip()]
        if safe_parts:
            return cache_root.joinpath(*safe_parts).with_suffix(".txt")
    material_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", material_path.stem)
    segment_id = re.sub(r"[^A-Za-z0-9._-]+", "-", str(segment.get("segment_id") or "segment"))
    return cache_root / material_stem / f"{segment_id}.txt"


def load_cached_segment_text(cache_path: Path | None) -> dict[str, Any] | None:
    if not cache_path or not cache_path.exists() or not cache_path.is_file():
        return None
    normalized = normalize_source_text(read_text_if_exists(cache_path))
    if not normalized:
        return None
    return {"status": "extracted", "source_path": str(cache_path), "source_kind": "segment-cache", "text": normalized}


def collect_segment_pdf_search_terms(segment: dict[str, Any]) -> list[str]:
    locator = segment.get("locator") if isinstance(segment.get("locator"), dict) else {}
    terms: list[str] = []
    for value in [segment.get("label"), locator.get("chapter"), segment.get("purpose")]:
        if value:
            terms.extend(re.split(r"[：:，,；;、/()（）\[\]\-\s]+", str(value)))
    terms.extend(str(item) for item in locator.get("sections") or [] if item)
    terms.extend(str(item) for item in segment.get("checkpoints") or [] if item)
    terms.extend(str(item) for item in segment.get("target_clusters") or [] if item)
    ordered: list[str] = []
    for term in terms:
        cleaned = str(term or "").strip()
        if len(cleaned) >= 3 and cleaned.lower() not in {item.lower() for item in ordered}:
            ordered.append(cleaned)
    return ordered[:24]


def extract_pdfkit_pages_to_text(pdf_path: Path, page_ranges: list[tuple[int, int]]) -> dict[str, Any] | None:
    if not page_ranges:
        return None
    swift_source = r'''
import Foundation
import PDFKit

let args = CommandLine.arguments
if args.count < 4 { exit(2) }
let url = URL(fileURLWithPath: args[1])
guard let document = PDFDocument(url: url) else { exit(1) }
let pageCount = document.pageCount
let start = max(1, Int(args[2]) ?? 1)
let end = min(pageCount, Int(args[3]) ?? pageCount)
if start > end { exit(0) }
var chunks: [String] = []
for pageNumber in start...end {
    if let page = document.page(at: pageNumber - 1), let text = page.string {
        chunks.append("[[PAGE \(pageNumber)]]\n" + text)
    }
}
print(chunks.joined(separator: "\n\n"))
'''
    chunks: list[str] = []
    used_ranges: list[tuple[int, int]] = []
    for start, end in page_ranges:
        try:
            result = subprocess.run(["/usr/bin/swift", "-", str(pdf_path), str(start), str(end)], input=swift_source, capture_output=True, text=True, check=False, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        normalized = normalize_source_text(result.stdout or "")
        if normalized:
            chunks.append(normalized)
            used_ranges.append((start, end))
    text = normalize_source_text("\n\n".join(chunks))
    if not text:
        return None
    return {"status": "extracted", "source_path": str(pdf_path), "source_kind": "pdfkit-pages", "text": text, "page_ranges": used_ranges}


def search_pdfkit_pages_for_terms(pdf_path: Path, terms: list[str], *, min_score: int = 2, limit: int = 24) -> list[tuple[int, int]]:
    filtered_terms = [term for term in terms if term and len(term) >= 3]
    if not filtered_terms:
        return []
    swift_source = r'''
import Foundation
import PDFKit

let args = CommandLine.arguments
if args.count < 3 { exit(2) }
let url = URL(fileURLWithPath: args[1])
let needles = Array(args.dropFirst(2)).map { $0.lowercased() }
guard let document = PDFDocument(url: url) else { exit(1) }
for index in 0..<document.pageCount {
    guard let text = document.page(at: index)?.string else { continue }
    let lower = text.lowercased()
    var score = 0
    for needle in needles {
        if lower.contains(needle) { score += 1 }
    }
    if score > 0 {
        print("\(index + 1)\t\(score)")
    }
}
'''
    try:
        result = subprocess.run(["/usr/bin/swift", "-", str(pdf_path), *filtered_terms], input=swift_source, capture_output=True, text=True, check=False, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    ranked: list[tuple[int, int]] = []
    for line in (result.stdout or "").splitlines():
        parts = line.strip().split("\t")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            page = int(parts[0])
            score = int(parts[1])
            if score >= min_score:
                ranked.append((score, page))
    ranked.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    ranges: list[tuple[int, int]] = []
    seen_pages: set[int] = set()
    for _, page in ranked:
        for candidate in range(max(1, page - 1), page + 2):
            if candidate in seen_pages:
                continue
            ranges.append((candidate, candidate))
            seen_pages.add(candidate)
            if len(ranges) >= limit:
                return ranges
    return ranges


def extract_pdf_pages_to_text(pdf_path: Path, pages_spec: Any, segment: dict[str, Any] | None = None) -> dict[str, Any] | None:
    page_ranges = parse_pages_spec(pages_spec)
    if not pdf_path.exists() or not pdf_path.is_file():
        return None
    payload = extract_pdfkit_pages_to_text(pdf_path, page_ranges)
    terms = collect_segment_pdf_search_terms(segment or {})
    if payload and any(term.lower() in str(payload.get("text") or "").lower() for term in terms[:12]):
        return payload
    searched_payload = extract_pdfkit_pages_to_text(pdf_path, search_pdfkit_pages_for_terms(pdf_path, terms))
    if searched_payload:
        searched_payload["source_kind"] = "pdfkit-search-pages"
        searched_payload["requested_page_ranges"] = page_ranges
        return searched_payload
    if payload:
        return payload
    try:
        result = subprocess.run(["/usr/bin/textutil", "-convert", "txt", "-stdout", str(pdf_path)], capture_output=True, text=True, check=False)
    except OSError:
        return None
    normalized = normalize_source_text(result.stdout or "")
    if not normalized:
        return None
    return {"status": "extracted", "source_path": str(pdf_path), "source_kind": "pdf-runtime-fulltext", "text": normalized, "page_ranges": page_ranges}


def ensure_segment_source_cache(segment: dict[str, Any]) -> dict[str, Any] | None:
    material_local_path = segment.get("material_local_path")
    if not material_local_path:
        return None
    cache_path = resolve_segment_cache_path(material_local_path, segment)
    cached = load_cached_segment_text(cache_path)
    if cached:
        return cached
    material_path = Path(str(material_local_path)).expanduser()
    if material_path.suffix.lower() != ".pdf":
        return None
    extracted = extract_pdf_pages_to_text(material_path, ((segment.get("locator") or {}).get("pages") if isinstance(segment.get("locator"), dict) else None), segment)
    if not extracted or not cache_path:
        return extracted
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(str(extracted.get("text") or ""), encoding="utf-8")
    extracted["source_path"] = str(cache_path)
    extracted["source_kind"] = "segment-cache"
    return extracted


def load_material_source_text(material_local_path: Any, material_kind: Any, segment: dict[str, Any] | None = None) -> dict[str, Any]:
    path = Path(str(material_local_path)).expanduser() if material_local_path else None
    if segment:
        segment_payload = ensure_segment_source_cache(segment)
        if segment_payload and str(segment_payload.get("text") or "").strip():
            return segment_payload
    if path and path.exists() and path.is_dir():
        locator = segment.get("locator") if isinstance(segment, dict) and isinstance(segment.get("locator"), dict) else {}
        terms = collect_segment_pdf_search_terms(segment or {})
        lower_terms = " ".join(terms).lower()
        file_candidates: list[Path] = []
        if "git" in lower_terms or "版本" in lower_terms:
            file_candidates.extend([path / "_2020" / "version-control.md", path / "ch02-git-basics-chapter.asc", path / "book" / "02-git-basics" / "sections" / "getting-a-repository.asc", path / "book" / "02-git-basics" / "sections" / "recording-changes.asc"])
        for keyword in [str(locator.get("chapter") or ""), str(segment.get("label") or "") if segment else ""]:
            if "git" in keyword.lower() or "版本" in keyword:
                file_candidates.extend(path.glob("**/*git*.md"))
                file_candidates.extend(path.glob("**/*git*.asc"))
                file_candidates.extend(path.glob("**/version-control.md"))
                file_candidates.extend(path.glob("**/recording-changes.asc"))
        if not file_candidates:
            file_candidates.extend(path.glob("*.md"))
            file_candidates.extend(path.glob("*.asc"))
        seen_candidates: set[str] = set()
        chunks: list[str] = []
        sources: list[str] = []
        for candidate in file_candidates:
            key = str(candidate)
            if key in seen_candidates or not candidate.exists() or not candidate.is_file():
                continue
            seen_candidates.add(key)
            normalized = normalize_source_text(read_text_if_exists(candidate))
            if normalized:
                chunks.append(normalized[:6000])
                sources.append(str(candidate))
            if len(chunks) >= 4:
                break
        if chunks:
            return {"status": "extracted", "source_path": ";".join(sources), "source_kind": "dir-selected-files", "text": "\n\n".join(chunks)}
    if path and path.exists() and path.is_file() and path.suffix.lower() in {".md", ".txt", ".py", ".json", ".html", ".htm", ".asc"}:
        normalized = normalize_source_text(read_text_if_exists(path))
        if normalized:
            return {"status": "extracted", "source_path": str(path), "source_kind": path.suffix.lower().lstrip("."), "text": normalized}
    for candidate in derive_material_text_candidates(material_local_path):
        if candidate.exists() and candidate.is_file():
            normalized = normalize_source_text(read_text_if_exists(candidate))
            if normalized:
                return {"status": "extracted", "source_path": str(candidate), "source_kind": candidate.suffix.lower().lstrip("."), "text": normalized}
    if path and path.exists() and path.suffix.lower() == ".pdf":
        return {"status": "missing-local-content", "source_path": str(path), "source_kind": "pdf", "text": ""}
    return {"status": "missing-local-content" if material_local_path else "fallback-metadata", "source_path": str(path) if path else None, "source_kind": str(material_kind or "unknown"), "text": ""}


def extract_segment_source_context(segment: dict[str, Any], source_payload: dict[str, Any]) -> dict[str, Any]:
    source_text = str(source_payload.get("text") or "")
    status = str(source_payload.get("status") or "fallback-metadata")
    if not source_text:
        return {"source_status": status, "source_path": source_payload.get("source_path"), "source_kind": source_payload.get("source_kind"), "source_excerpt": "", "matched_terms": [], "matched_paragraphs": []}
    locator = segment.get("locator") if isinstance(segment.get("locator"), dict) else {}
    terms = [str(segment.get("label") or ""), str(segment.get("purpose") or ""), str(segment.get("material_title") or ""), str(segment.get("material_summary") or ""), str(locator.get("chapter") or ""), *(str(item) for item in locator.get("sections") or [] if item), *(str(item) for item in segment.get("checkpoints") or [] if item), *(str(item) for item in segment.get("target_clusters") or [] if item)]
    normalized_terms: list[str] = []
    for term in terms:
        for piece in re.split(r"[：:，,；;、/()（）\[\]\-\s]+", term):
            piece = piece.strip()
            if len(piece) >= 2 and piece.lower() not in {item.lower() for item in normalized_terms}:
                normalized_terms.append(piece)
    term_blob = " ".join(terms).lower()
    if "git" in term_blob or "版本" in term_blob:
        for piece in ["git", "version control", "commit", "repository", "branch"]:
            if piece not in {item.lower() for item in normalized_terms}:
                normalized_terms.append(piece)
    matched: list[str] = []
    matched_terms: list[str] = []
    for paragraph in split_source_paragraphs(source_text):
        paragraph_lower = paragraph.lower()
        hits = [term for term in normalized_terms if term.lower() in paragraph_lower]
        if hits:
            matched.append(paragraph)
            for hit in hits:
                if hit not in matched_terms:
                    matched_terms.append(hit)
        if len(matched) >= 4:
            break
    return {"source_status": "extracted" if matched else "fallback-metadata", "source_path": source_payload.get("source_path"), "source_kind": source_payload.get("source_kind"), "source_excerpt": "\n\n".join(matched[:3]), "matched_terms": matched_terms, "matched_paragraphs": matched[:4]}


def clean_source_teaching_terms(values: list[str]) -> list[str]:
    stop_terms = {"10", "11", "第", "章", "stage1", "stage2", "stage3", "stage4", "python", "文件", "异常", "json", "pathlib", "general-cs", "general cs", "tooling", "tutorial", "reference", "the", "pro", "cs", "of", "your", "learn", "data", "model", "models", "git"}
    ordered: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        normalized = cleaned.lower()
        if cleaned and normalized not in stop_terms and not normalized.isdigit() and cleaned not in ordered:
            ordered.append(cleaned)
    return ordered


def combine_source_terms(*groups: list[str], limit: int = 5) -> list[str]:
    ordered: list[str] = []
    for group in groups:
        for item in group:
            if item and item not in ordered:
                ordered.append(item)
            if len(ordered) >= limit:
                return ordered
    return ordered


def compact_source_text(text: str, limit: int = 260) -> str:
    cleaned = re.sub(r"\[\[PAGE \d+\]\]", "", str(text or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) <= limit:
        return cleaned
    candidate = cleaned[:limit]
    sentence_end = max(candidate.rfind("。"), candidate.rfind("；"), candidate.rfind("."))
    if sentence_end >= 80:
        return candidate[: sentence_end + 1]
    return candidate.rstrip() + "..."


def build_content_aware_explanation(topic_name: str, segment: dict[str, Any], source_text: str) -> str:
    topic_lower = topic_name.lower()
    if "read_text" in topic_lower:
        return "资料用 Path('numbers.json').read_text() 演示：先把路径包装成 Path 对象，再一次性读取文本内容；如果读的是 JSON 文件，下一步才把读出的字符串交给 json.loads()。"
    if "write_text" in topic_lower:
        return "资料用 Path('numbers.json').write_text(contents) 演示写文件：先把 Python 数据转换成要保存的字符串，再把字符串写入指定路径。write_text() 的重点不是解析数据，而是完成文本落盘。"
    if "json.dumps" in topic_lower:
        return "资料里的方向是：json.dumps(numbers) 把 Python 对象转换成 JSON 格式字符串；得到字符串后，才能用 Path.write_text() 保存到 .json 文件。"
    if "json.loads" in topic_lower:
        return "资料里的方向是：Path.read_text() 先读出 JSON 文本字符串，json.loads(contents) 再把这个字符串还原为 Python 对象，例如列表或用户名字符串。"
    snippet = compact_source_text(source_text)
    if snippet:
        return f"资料中和 {topic_name} 对应的原文例子是：{snippet}"
    return f"资料这一段围绕 {topic_name} 展开，重点是先看它在书中对应的例子，再理解输入、输出和边界。"


def build_content_aware_pitfall(topic_name: str, segment: dict[str, Any]) -> str:
    topic_lower = topic_name.lower()
    if "json.dumps" in topic_lower:
        return "不要把 dumps 和 loads 方向记反：dumps 是 Python 对象 -> JSON 字符串。"
    if "json.loads" in topic_lower:
        return "不要跳过 read_text()：loads 接收的是 JSON 字符串，不是 Path 对象本身。"
    if "read_text" in topic_lower:
        return "不要把 read_text() 当成 JSON 解析器；它只负责读文本，JSON 解析要交给 json.loads()。"
    if "write_text" in topic_lower:
        return "不要把 Python 列表或字典直接当成文本写入；应先用 json.dumps() 转成字符串，或明确写入普通文本。"
    checkpoints = normalize_string_list(segment.get("checkpoints") or [])
    suffix = f" {checkpoints[0]}" if checkpoints else ""
    return f"先别只背 API 名字；要能说清它在资料例子里的使用场景和边界。{suffix}".strip()


def derive_git_teaching_terms(segment: dict[str, Any], excerpt: str, matched_terms: list[str]) -> list[str]:
    blob = " ".join(str(value or "") for value in [segment.get("segment_id"), segment.get("label"), segment.get("purpose"), segment.get("material_title"), segment.get("material_summary"), excerpt, " ".join(matched_terms)]).lower()
    if "git" not in blob and "version control" not in blob and "版本控制" not in blob:
        return []
    mapping = [(["version control", "版本控制"], "版本控制"), (["snapshot", "snapshots", "快照"], "快照历史"), (["commit", "commits", "提交"], "commit / 提交"), (["repository", "repositories", "repo", "仓库"], "仓库"), (["staging", "stage", "git add", "暂存"], "git add / 暂存区"), (["working tree", "working directory", "git status", "tracking files", "track files", "stage and commit", "工作区"], "工作区与 git status"), (["branch", "branches", "分支"], "分支指针"), (["remote", "push", "pull", "远程"], "远程协作")]
    result = [label for needles, label in mapping if any(needle in blob for needle in needles)]
    return (result or ["Git 基础模型"])[:6]


def summarize_segment_teaching_points(segment: dict[str, Any], extracted_context: dict[str, Any]) -> dict[str, Any]:
    locator = segment.get("locator") if isinstance(segment.get("locator"), dict) else {}
    sections = [str(item).strip() for item in locator.get("sections") or [] if str(item).strip()]
    checkpoints = [str(item).strip() for item in segment.get("checkpoints") or [] if str(item).strip()]
    excerpt = str(extracted_context.get("source_excerpt") or "").strip()
    matched_terms = [str(item).strip() for item in extracted_context.get("matched_terms") or [] if str(item).strip()]
    paragraphs = [str(item).strip() for item in extracted_context.get("matched_paragraphs") or [] if str(item).strip()]
    key_points = derive_git_teaching_terms(segment, excerpt, matched_terms) or combine_source_terms(clean_source_teaching_terms(sections), clean_source_teaching_terms(matched_terms), clean_source_teaching_terms(checkpoints), limit=6)
    examples = [paragraph for paragraph in paragraphs if any(token in paragraph for token in ["例如", "比如", "示例", "例子", "example"])] or paragraphs[:1]
    pitfalls = [paragraph for paragraph in paragraphs if any(token.lower() in paragraph.lower() for token in ["注意", "不要", "容易", "异常", "错误", "pitfall"])] or ([f"重点边界：{checkpoints[0]}"] if checkpoints else [])
    summary_bits = key_points[:6] or clean_source_teaching_terms(sections)[:6] or clean_source_teaching_terms(checkpoints)[:3]
    return {"source_status": extracted_context.get("source_status") or "fallback-metadata", "source_path": extracted_context.get("source_path"), "source_kind": extracted_context.get("source_kind"), "source_excerpt": excerpt, "source_summary": "；".join(summary_bits) or str(segment.get("purpose") or segment.get("material_summary") or ""), "source_key_points": key_points, "source_examples": examples[:2], "source_pitfalls": pitfalls[:2]}


def build_segment_source_brief(segment: dict[str, Any]) -> dict[str, Any]:
    source_payload = load_material_source_text(segment.get("material_local_path"), segment.get("material_kind"), segment)
    extracted_context = extract_segment_source_context(segment, source_payload)
    summary = summarize_segment_teaching_points(segment, extracted_context)
    return {**segment, **summary}


def source_brief_has_substance(segment: dict[str, Any]) -> bool:
    return bool(str(segment.get("source_status") or "") == "extracted" or segment.get("source_excerpt") or segment.get("source_key_points"))


def segment_specificity(segment: dict[str, Any]) -> int:
    locator = segment.get("locator") if isinstance(segment.get("locator"), dict) else {}
    sections = normalize_string_list(locator.get("sections") or [])
    checkpoints = normalize_string_list(segment.get("checkpoints") or [])
    target_clusters = normalize_string_list(segment.get("target_clusters") or [])
    score = 0
    if sections:
        score += len(sections) * 5
    if checkpoints:
        score += len(checkpoints) * 4
    if target_clusters:
        score += len(target_clusters) * 6
    if locator.get("chapter"):
        score += 3
    if re.search(r"day\s*\d+", str(segment.get("label") or ""), flags=re.IGNORECASE):
        score += 8
    return score
