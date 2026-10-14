"""Isolated parser process. Native mode has no OCR or structured-table claims."""
import json
import re
import subprocess
import sys
from pathlib import Path


def native(path):
    result = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, check=True)
    pages = result.stdout.decode("utf-8", errors="replace").split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    blocks, flags = [], []
    for page, body in enumerate(pages, 1):
        if len(re.sub(r"\s", "", body)) < 80:
            flags.append({"pdf_page": page, "flag": "sparse_native_text_requires_review"})
        for paragraph in re.split(r"\n\s*\n", body):
            text = paragraph.strip()
            if text:
                blocks.append({"text": text, "pdf_page": page, "bbox": None, "kind": "text", "section": "unknown", "structured": None})
    if not blocks:
        raise ValueError("No native text; OCR review required")
    return {"page_count": len(pages), "blocks": blocks, "quality": {"flags": flags, "parser": "native", "tables_structured": False}}


def docling(path, artifact):
    from docling.document_converter import DocumentConverter
    doc = DocumentConverter().convert(path).document
    exported = doc.export_to_dict()
    blocks, sections = [], []
    for item, _ in doc.iterate_items():
        body = getattr(item, "text", "")
        raw_label = getattr(item, "label", "text")
        kind = getattr(raw_label, "value", str(raw_label))
        if kind == "section_header":
            level = getattr(item, "level", 1)
            sections = sections[:max(0, level - 1)] + [body]
        structured = None
        if kind == "table":
            structured = item.model_dump(mode="json")
            body = item.export_to_markdown(doc=doc)
            caption = item.caption_text(doc) if hasattr(item, "caption_text") else ""
            if caption:
                body = caption + "\n" + body
        elif kind == "picture":
            body = item.caption_text(doc) if hasattr(item, "caption_text") else ""
            structured = item.model_dump(mode="json")
        for prov in getattr(item, "prov", []):
            if not body:
                continue
            size = doc.pages[prov.page_no].size
            box = prov.bbox.to_top_left_origin(page_height=size.height)
            bbox = [max(0.0, min(1.0, v)) for v in [box.l / size.width, box.t / size.height, box.r / size.width, box.b / size.height]]
            span = getattr(prov, "charspan", None)
            page_text = body
            if span and kind not in ("table", "picture"):
                page_text = body[span[0]:span[1]]
            if not page_text:
                continue
            blocks.append({"text": page_text, "pdf_page": prov.page_no, "bbox": bbox,
                           "kind": kind, "section": " / ".join(sections) or "unknown", "structured": structured})
    artifact.with_suffix(".docling.json").write_text(json.dumps(exported, ensure_ascii=False))
    if not blocks:
        raise ValueError("Docling returned no source blocks")
    return {"page_count": len(doc.pages), "blocks": blocks, "quality": {"flags": [], "parser": "docling", "tables_structured": True}}


def main():
    parser, source, target, memory_mb = sys.argv[1:]
    import resource
    memory_bytes = int(memory_mb) * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    output = Path(target)
    parsed = native(Path(source)) if parser == "native" else docling(Path(source), output)
    output.write_text(json.dumps(parsed, ensure_ascii=False))


if __name__ == "__main__":
    main()
