#!/usr/bin/env python3
"""Copy a lab-paper archive into deduplicated LLM Wiki sources; never edit the archive."""

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote, unquote, urlparse
from urllib.request import Request, urlopen


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n'


def identity(url):
    parsed = urlparse(str(url))
    host = (parsed.hostname or '').lower()
    if host in ('arxiv.org', 'www.arxiv.org', 'export.arxiv.org'):
        match = re.fullmatch(r'/(?:pdf|abs)/((?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7}))(?:v(\d+))?(?:\.pdf)?/?', parsed.path)
        if match:
            return 'arxiv-' + match[1].replace('/', '-'), int(match[2] or 0)
    if host in ('doi.org', 'dx.doi.org'):
        doi = unquote(parsed.path).strip('/').casefold()
        if re.fullmatch(r'10\.\d{4,9}/\S+', doi):
            slug = re.sub(r'[^a-z0-9.-]+', '-', doi)[:100]
            return 'doi-' + slug + '-' + hashlib.sha256(doi.encode()).hexdigest()[:8], 0
    return None, 0


def source_path(lab, value):
    path = lab / value
    if not path.resolve().is_relative_to(lab.resolve()):
        raise ValueError(f'Source path escapes collection: {path}')
    return path


def read_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError(f'Cannot read JSON {path}: {exc}') from exc


def render_value(value, depth=0):
    if isinstance(value, dict):
        return '\n'.join('  ' * depth + '- ' + str(k).replace('_', ' ').title() + ':\n' + render_value(v, depth + 1) for k, v in value.items())
    if isinstance(value, list):
        return '\n'.join('  ' * depth + '- ' + str(v) if not isinstance(v, (dict, list)) else render_value(v, depth + 1) for v in value)
    return '  ' * depth + str(value if value is not None else 'Not reported.')


def pdf_issue(path):
    try:
        result = subprocess.run(['pdftotext', '-enc', 'UTF-8', str(path), '-'],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return str(exc)
    if result.returncode:
        return result.stderr.decode('utf-8', errors='replace').strip()[:300] or f'pdftotext exited {result.returncode}'
    if not result.stdout.strip():
        return 'No extractable text; OCR is intentionally skipped'
    return ''


def rename_outputs(destination, renames):
    """Use the local app for indexed files so IDs, annotations and extracted pages survive."""
    if not renames:
        return
    indexed = {}
    database = destination / '.llmwiki/index.db'
    if database.is_file():
        with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=30) as db:
            indexed = {relative: doc_id for doc_id, relative in db.execute('SELECT id, relative_path FROM documents')}
        first = next((old for old in renames if old in indexed), None)
        if first:
            try:
                with urlopen('http://127.0.0.1:8000/v1/documents/' + indexed[first], timeout=30) as response:
                    doc = json.load(response)
                if doc.get('relative_path') != first:
                    raise ValueError('The local server is using a different workspace')
            except OSError as exc:
                raise ValueError('Start the local LLM Wiki server for this destination before migrating indexed filenames') from exc
    for number, (old, new) in enumerate(renames.items(), 1):
        target = destination / new
        if old in indexed:
            fields = {'filename': target.name, 'path': '/' + str(Path(new).parent) + '/',
                      'title': target.stem.replace('-', ' ').replace('_', ' ').strip().title()}
            request = Request('http://127.0.0.1:8000/v1/documents/' + indexed[old],
                              data=json.dumps(fields).encode(), method='PATCH',
                              headers={'Content-Type': 'application/json'})
            with urlopen(request, timeout=60) as response:
                doc = json.load(response)
            if doc.get('relative_path') != new or not target.is_file():
                raise ValueError(f'Local API did not complete rename: {old} -> {new}')
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            os.rename(destination / old, target)
        if number % 100 == 0:
            print(f'Renamed {number}/{len(renames)} files', file=sys.stderr, flush=True)
    if any(old in indexed for old in renames):
        # shortcut: the app suppresses watcher events for two seconds; revisit if its cooldown changes.
        time.sleep(2.1)


def import_labs(labs_root, destination, dry_run=False, lab_names=(), pdf_only=False, md_only=False):
    if pdf_only and md_only:
        raise ValueError('pdf_only and md_only are mutually exclusive')

    def selected(relative):
        return not (pdf_only and relative.endswith('.md') or md_only and relative.endswith('.pdf'))

    root, dest = Path(labs_root).resolve(), Path(destination).resolve()
    if not root.is_dir():
        raise ValueError(f'Source directory does not exist: {root}')
    if dest.is_relative_to(root) or root.is_relative_to(dest):
        raise ValueError('Source and destination must not overlap')
    warnings, inputs, records, collections = [], {}, [], {}
    ignored_pdfs = {}
    for path in (dest / '.llmwiki-import', dest / '.llmwiki-import/catalog.json'):
        if path.is_symlink():
            raise ValueError(f'Destination symlink is not allowed: {path}')
    state_path = dest / '.llmwiki-import/catalog.json'
    previous = read_json(state_path) if state_path.is_file() else {}
    if previous and previous.get('source_root') != str(root):
        raise ValueError('Existing catalog belongs to a different source root')

    def fingerprint(path):
        key = str(path.relative_to(root))
        if key not in inputs:
            before = path.stat()
            cached = previous.get('inputs', {}).get(key)
            if cached and (before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (cached['size'], cached['mtime_ns'], cached['ctime_ns']):
                inputs[key] = cached
                return cached['sha256']
            sha = digest(path)
            after = path.stat()
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise ValueError(f'Source changed while reading; rerun: {path}')
            inputs[key] = {'sha256': sha, 'size': after.st_size, 'mtime_ns': after.st_mtime_ns, 'ctime_ns': after.st_ctime_ns}
        return inputs[key]['sha256']

    def source_text(path):
        expected = fingerprint(path)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f'Source changed while reading; rerun: {path}')
        return data.decode('utf-8')

    labs = sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith('.'))
    if lab_names:
        unknown = set(lab_names) - {p.name for p in labs}
        if unknown:
            raise ValueError(f'Unknown collections: {sorted(unknown)}')
        labs = [p for p in labs if p.name in lab_names]
    for lab in labs:
        print('Scanning ' + lab.name, file=sys.stderr, flush=True)
        if lab.is_symlink():
            raise ValueError(f'Symlink collection is not allowed: {lab}')
        seen = set()
        context = {}
        for name in ('topics.yaml', 'research_overview.md', 'link.txt'):
            path = source_path(lab, name)
            if path.is_file():
                context[name] = source_text(path)
        kind = re.search(r'^source_type:\s*(.+)$', context.get('topics.yaml', ''), re.M)
        collections[lab.name] = {'source_type': kind[1].strip() if kind else 'collection', 'context': context}

        def add_record(row, pdf=None, summary=None, structured=None):
            paths = {'pdf': pdf, 'summary': summary, 'structured_summary': structured}
            present = {}
            for label, path in paths.items():
                if path is not None and path.is_file():
                    source_path(lab, str(path.relative_to(lab)))
                    try:
                        fingerprint(path)
                    except OSError as exc:
                        if label != 'pdf':
                            raise
                        ignored_pdfs[str(path.relative_to(root))] = str(exc)
                        seen.update(p for p in paths.values() if p is not None and p.is_file())
                        return
                    present[label] = str(path.relative_to(root))
                    seen.add(path)
            if pdf is not None and not pdf.is_file():
                warnings.append(f'Missing PDF: {pdf.relative_to(root)}')
            text = source_text(root / present['summary']) if 'summary' in present else ''
            match = re.search(r'^- \*\*Paper:\*\*\s*(\S+)', text, re.M)
            urls = [str(row[k]) for k in ('pdf_url', 'doi_url') if row.get(k)]
            if match:
                urls.append(match[1])
            identities = [identity(u) for u in urls if identity(u)[0]]
            review_notes = []
            if len({i[0] for i in identities}) > 1:
                review_notes.append(f'Conflicting identifiers in {lab.name}: {urls}')
                warnings.extend(review_notes)
                # shortcut: conflicting metadata is not reconciled automatically; review this record.
            paper_id, version = identities[0] if identities else (None, 0)
            heading = re.search(r'^#\s+(.+)$', text, re.M)
            title = row.get('paper_title') or (heading[1] if heading else row.get('title'))
            fallback = next(iter(present.values()), row.get('pdf_path', 'Unknown paper'))
            sha = fingerprint(root / present['pdf']) if 'pdf' in present else None
            structured_data = json.loads(source_text(root / present['structured_summary'])) if 'structured_summary' in present else {}
            if not isinstance(structured_data, dict):
                raise ValueError(f'Structured summary must be an object: {present}')
            if not text and structured_data:
                text = '# ' + str(title or Path(fallback).stem) + '\n\n' + '\n\n'.join('## ' + k.replace('_', ' ').title() + '\n\n' + render_value(v) for k, v in structured_data.items()) + '\n'
            records.append({'collection': lab.name, 'paper_id': paper_id, 'version': version,
                            'title': str(title or Path(fallback).stem), 'files': present, 'metadata': row,
                            'pdf_sha256': sha, 'summary_text': text,
                            'tags': structured_data.get('index_tags', {}), 'urls': sorted(set(urls)),
                            'review_notes': review_notes})

        manifest = source_path(lab, 'papers.json')
        if manifest.is_file():
            fingerprint(manifest)
            rows = json.loads(source_text(manifest))
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError(f'Expected a list of paper objects: {manifest}')
            for row in rows:
                if not row.get('pdf_path'):
                    raise ValueError(f'Missing pdf_path in {manifest}')
                pdf = source_path(lab, row['pdf_path'])
                stem = pdf.stem
                summary = source_path(lab, row.get('summary_path') or f'summary/{stem}.md')
                structured = source_path(lab, row.get('summary_json_path') or f'summary_json/{stem}.json')
                add_record(row, pdf, summary, structured)
        for subdir, suffix in (('pdfs', '.pdf'), ('summary', '.md'), ('summary_json', '.json')):
            folder = source_path(lab, subdir)
            for path in sorted(folder.glob('*' + suffix)):
                if path in seen:
                    continue
                pdf = source_path(lab, 'pdfs/' + path.stem + '.pdf')
                summary = source_path(lab, 'summary/' + path.stem + '.md')
                structured = source_path(lab, 'summary_json/' + path.stem + '.json')
                add_record({}, pdf if pdf.exists() else None, summary, structured)

    checks = previous.get('pdf_text_checks', {})
    pending = {r['pdf_sha256']: root / r['files']['pdf'] for r in records
               if r['pdf_sha256'] and r['pdf_sha256'] not in checks}
    if pending and not shutil.which('pdftotext'):
        raise ValueError('pdftotext is required to skip unreadable PDFs; install poppler-utils')
    print(f'Checking text readability of {len(pending)} PDFs ({len(checks)} cached checks)', file=sys.stderr, flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for number, (sha, issue) in enumerate(zip(pending, pool.map(pdf_issue, pending.values())), 1):
            checks[sha] = issue
            if number % 50 == 0:
                print(f'Checked {number}/{len(pending)} PDFs', file=sys.stderr, flush=True)
    rejected = [r for r in records if r['pdf_sha256'] and checks[r['pdf_sha256']]]
    for record in rejected:
        ignored_pdfs[record['files']['pdf']] = checks[record['pdf_sha256']]
    readable_ids = {r['paper_id'] for r in records if r['pdf_sha256'] and not checks[r['pdf_sha256']]}
    rejected_ids = {r['paper_id'] for r in rejected if r['paper_id']} - readable_ids
    records = [r for r in records if (not r['pdf_sha256'] or not checks[r['pdf_sha256']]) and r['paper_id'] not in rejected_ids]
    for path, issue in ignored_pdfs.items():
        warnings.append(f'Ignored unreadable PDF and its associated record: {path}: {issue}')

    ids_by_sha = defaultdict(set)
    for record in records:
        if record['paper_id'] and record['pdf_sha256']:
            ids_by_sha[record['pdf_sha256']].add(record['paper_id'])
    groups = defaultdict(list)
    for record in records:
        key = record['paper_id']
        matching = ids_by_sha[record['pdf_sha256']] if record['pdf_sha256'] else set()
        if not key and len(matching) == 1:
            key = next(iter(matching))
        if not key:
            sha = record['pdf_sha256'] or hashlib.sha256((record['summary_text'] or json_text(record['metadata'])).encode()).hexdigest()
            key = 'sha256-' + sha[:24]
        groups[key].append(record)
    for sha, ids in ids_by_sha.items():
        if len(ids) > 1:
            note = f'Same PDF has conflicting IDs; retained separately: {sorted(ids)} ({sha})'
            warnings.append(note)
            for record in records:
                if record['pdf_sha256'] == sha:
                    record['review_notes'].append(note)

    if lab_names and set(previous.get('collections', {})) - set(lab_names):
        raise ValueError('Partial import would replace a broader catalog; use a separate destination or import all collections')
    outputs, papers, renames, rename_owners, rename_history = {}, {}, {}, {}, {}

    def migrate(old, new):
        if not selected(new):
            return
        if old and old != new and old in previous.get('outputs', {}):
            rename_owners[new] = previous['outputs'][old]
            if (dest / old).exists() or (dest / new).exists():
                rename_history[old] = new
            if (dest / old).exists():
                if (dest / new).exists():
                    raise ValueError(f'Rename target already exists: {dest / new}')
                if (dest / old).is_symlink() or not (dest / old).resolve().is_relative_to(dest):
                    raise ValueError(f'Destination symlink is not allowed: {dest / old}')
                if digest(dest / old) != previous['outputs'][old]['sha256']:
                    raise ValueError(f'Destination modified or unmanaged file conflict: {dest / old}')
                renames[old] = new

    def output(relative, content, sha=None):
        if not selected(relative):
            return
        if isinstance(content, str):
            content = content.encode('utf-8')
        outputs[relative] = (content, sha or hashlib.sha256(content).hexdigest())

    directory_owners = {}
    for key, occurrences in sorted(groups.items()):
        memberships = sorted({r['collection'] for r in occurrences})
        pdfs, summaries = {}, {}
        for r in occurrences:
            if r['pdf_sha256']:
                pdfs.setdefault(r['pdf_sha256'], r)
            if r['summary_text']:
                # The source URL/header may differ; preserve distinct accounts rather than guess.
                sha = hashlib.sha256(r['summary_text'].encode()).hexdigest()
                summaries.setdefault(sha, r)
        old = previous.get('papers', {}).get(key, {})
        primary_pdf = old.get('primary_pdf_sha256')
        if primary_pdf not in pdfs:
            primary_pdf = max(pdfs, key=lambda h: (pdfs[h]['version'], h)) if pdfs else None
        primary_summary = old.get('primary_summary_sha256')
        if primary_summary not in summaries:
            primary_summary = max(summaries, key=lambda h: (summaries[h]['version'], len(summaries[h]['summary_text']), h)) if summaries else None
        chosen = summaries.get(primary_summary) or pdfs.get(primary_pdf) or occurrences[0]
        urls = sorted({u for r in occurrences for u in r['urls']})
        original = pdfs.get(primary_pdf) or chosen
        basename = Path(original['files'].get('pdf') or original['files'].get('summary') or original['files'].get('structured_summary') or original['metadata'].get('pdf_path') or key).stem
        if re.fullmatch(r'\d{4}-(?:paper|\d{4})(?:--.*)?', basename):
            title_slug = re.sub(r'[\W_]+', '-', original['title'].lower()).strip('-').encode('utf-8')[:120].decode('utf-8', errors='ignore')
            basename = basename[:4] + '-' + (title_slug if title_slug not in ('', 'paper', basename) else key)
        if basename in ('', '.', '..'):
            raise ValueError(f'Invalid paper directory name: {basename!r}')
        base = 'sources/papers/' + basename
        while base in directory_owners:
            base += '--' + key
        directory_owners[base] = key
        pdf_outputs = []
        for sha, r in sorted(pdfs.items()):
            filename = Path(r['files']['pdf']).name
            relative = base + ('/' + filename if sha == primary_pdf else '/versions/' + sha[:24] + '/' + filename)
            output(relative, root / r['files']['pdf'], sha)
            pdf_outputs.append(relative)
            old_file = next((p for p in old.get('pdf_files', []) if previous['outputs'].get(p, {}).get('sha256') == sha), None)
            migrate(old_file, relative)
        tag_values = set()
        for r in occurrences:
            if isinstance(r['tags'], dict):
                for values in r['tags'].values():
                    if isinstance(values, list):
                        tag_values.update(str(v) for v in values)
        header = {'title': chosen['title'], 'paper_id': key, 'collections': memberships,
                  'paper_urls': urls, 'tags': sorted(tag_values),
                  'review_required': any(r['review_notes'] for r in occurrences),
                  'summary_status': 'available' if summaries else 'missing',
                  'pdf_status': 'available' if pdfs else 'missing'}
        frontmatter = '---\n' + '\n'.join(k + ': ' + json.dumps(v, ensure_ascii=False) for k, v in header.items()) + '\n---\n\n'
        provenance = '## Import provenance\n\nCollections are discovery sources, not verified author affiliations. Imported summaries are secondary accounts; verify detailed claims against the PDF.\n\n'
        review_notes = sorted({note for r in occurrences for note in r['review_notes']})
        if review_notes:
            provenance += '**Identity needs review. Do not attribute claims to a paper until these conflicts are resolved:**\n\n' + '\n'.join('- ' + note for note in review_notes) + '\n\n'
        for r in occurrences:
            provenance += '- ' + r['collection'] + ': ' + ', '.join('`' + p + '`' for p in r['files'].values()) + '\n'
        if pdf_outputs and not md_only:
            provenance += '\nPDFs: ' + ', '.join('[' + Path(p).name + '](' + quote(str(Path(p).relative_to(base))) + ')' for p in pdf_outputs) + '\n'
        summary_outputs = []
        for sha, r in sorted(summaries.items()):
            filename = Path(r['files'].get('summary') or r['files']['structured_summary']).stem + '.md'
            relative = base + ('/' + filename if sha == primary_summary else '/summaries/' + sha[:24] + '/' + filename)
            # PDF links are relative to the summary file, including alternate summaries.
            relative_provenance = provenance
            if sha != primary_summary:
                for pdf_relative in pdf_outputs:
                    target = quote(str(Path(pdf_relative).relative_to(base)))
                    link = quote(os.path.relpath(pdf_relative, Path(relative).parent))
                    relative_provenance = relative_provenance.replace('](' + target + ')', '](' + link + ')')
            output(relative, frontmatter + r['summary_text'].rstrip() + '\n\n' + relative_provenance)
            summary_outputs.append(relative)
            if sha == primary_summary:
                primary_summary_file = relative
            else:
                old_file = next((p for p in old.get('summary_files', []) if Path(p).stem.endswith(sha[:24]) or sha[:24] in Path(p).parts), None)
                migrate(old_file, relative)
        if not summaries:
            primary_summary_file = base + '/' + basename + '.md'
            output(primary_summary_file, frontmatter + '# ' + chosen['title'] + '\n\nNo existing summary is available. Read the PDF before synthesizing claims.\n\n' + provenance)
            summary_outputs.append(primary_summary_file)
        migrate(old.get('primary_summary_file'), primary_summary_file)
        papers[key] = {**header, 'pdf_files': pdf_outputs, 'summary_files': summary_outputs,
                       'basename': basename, 'primary_summary_file': primary_summary_file,
                       'primary_pdf_sha256': primary_pdf, 'primary_summary_sha256': primary_summary,
                       'occurrences': [{k: v for k, v in r.items() if k not in ('summary_text', 'tags')} for r in occurrences]}

    collection_outputs = {}
    for name, collection in sorted(collections.items()):
        slug = re.sub(r'[^\w.-]+', '-', name.casefold()).strip('.-') or 'collection'
        filename = slug + '-' + hashlib.sha256(name.encode()).hexdigest()[:8] + '.md'
        relative = 'sources/collections/' + filename
        collection_outputs[name] = relative
        text = '# ' + name + '\n\nDiscovery collection type: ' + collection['source_type'] + '. Membership does not establish paper authorship or lab affiliation.\n\n## Papers\n\n'
        for key, paper in papers.items():
            if name in paper['collections']:
                target = paper['primary_summary_file'].removeprefix('sources/')
                text += '- [' + paper['title'].replace('[', '\\[').replace(']', '\\]') + '](../' + quote(target) + ')\n'
        for filename, body in collection['context'].items():
            text += '\n## Original ' + filename + '\n\n'
            if filename == 'topics.yaml':
                text += 'Collection-level topic suggestions; not verified paper classifications.\n\n```yaml\n' + body.rstrip() + '\n```\n'
            else:
                text += body.rstrip() + '\n'
        output(relative, text)
    text = '# Robotics source catalog\n\n' + str(len(papers)) + ' canonical paper records in ' + str(len(collections)) + ' discovery collections.\n\nStart with summaries; consult the linked PDFs for verification. Do not treat collection membership as author affiliation. Preserve original sources; create synthesized pages under `/wiki/` following the MCP guide. Missing summaries are explicitly marked. Different PDF bytes and summary accounts are retained.\n\n## Collections\n\n'
    for name, relative in collection_outputs.items():
        text += '- [' + name + '](' + relative.removeprefix('sources/') + ')\n'
    text += '\nUnreadable or text-empty PDFs and their associated records are ignored. No OCR is attempted. Earlier generated copies of ignored records are kept in a hidden backup, outside the searchable sources.\n'
    text += '\n## Import details\n\nThe hidden `.llmwiki-import/catalog.json` records original paths, identifiers, metadata, file checksums, and import warnings. Re-run the importer to incorporate source changes. It never deletes files or rewrites generated wiki pages.\n'
    output('sources/catalog.md', text)

    old_outputs = previous.get('outputs', {})
    ignored_outputs = dict(previous.get('ignored_outputs', {}))
    to_hide = {}
    for old_paper in previous.get('papers', {}).values():
        if any(r['files'].get('pdf') in ignored_pdfs for r in old_paper['occurrences']):
            for relative in old_paper['pdf_files'] + old_paper['summary_files']:
                if selected(relative) and relative not in outputs and (dest / relative).exists():
                    path = dest / relative
                    if not path.resolve().is_relative_to(dest) or path.is_symlink() or digest(path) != old_outputs[relative]['sha256']:
                        raise ValueError(f'Destination modified or unmanaged file conflict: {path}')
                    hidden = '.llmwiki-import/ignored/' + old_outputs[relative]['sha256'][:24] + '/' + relative
                    if (dest / hidden).exists() and digest(dest / hidden) != old_outputs[relative]['sha256']:
                        raise ValueError(f'Destination modified or unmanaged file conflict: {dest / hidden}')
                    for ancestor in ((dest / hidden), *(dest / hidden).parents):
                        if ancestor == dest.parent:
                            break
                        if ancestor.is_symlink():
                            raise ValueError(f'Destination symlink is not allowed: {ancestor}')
                    to_hide[relative] = hidden
                    ignored_outputs[relative] = hidden
    changed, unchanged = [], 0
    for relative, (content, sha) in outputs.items():
        path = dest / relative
        for ancestor in (path, *path.parents):
            if ancestor == dest.parent:
                break
            if ancestor.is_symlink():
                raise ValueError(f'Destination symlink is not allowed: {ancestor}')
        if path.exists():
            existing = digest(path)
            if existing == sha:
                unchanged += 1
                continue
            if old_outputs.get(relative, rename_owners.get(relative, {})).get('sha256') != existing:
                raise ValueError(f'Destination modified or unmanaged file conflict: {path}')
        changed.append(relative)
    reused = {new for new in renames.values() if rename_owners[new]['sha256'] == outputs[new][1]}
    changed = [r for r in changed if r not in reused]
    stale = sorted({p for p in old_outputs if selected(p)} - set(outputs) - set(to_hide) - set(rename_history))
    if stale:
        warnings.append(f'{len(stale)} old generated files retained; nothing is deleted. See retained_files in catalog.')
    catalog = {'schema_version': 1, 'naming': 'original', 'source_root': str(root), 'papers': papers,
               'collections': {name: {'source_type': c['source_type'], 'file': collection_outputs[name]} for name, c in collections.items()},
               'inputs': inputs, 'outputs': {**{rel: info for rel, info in old_outputs.items() if not selected(rel)},
                                             **{rel: {'sha256': sha} for rel, (_, sha) in outputs.items()}},
               'retained_files': sorted((set(stale) | set(previous.get('retained_files', []))) - set(to_hide) - set(rename_history)),
               'renamed_files': {**previous.get('renamed_files', {}), **rename_history},
               'pdf_text_checks': checks, 'ignored_pdfs': ignored_pdfs,
               'ignored_outputs': ignored_outputs, 'warnings': warnings}
    report = {'papers': len(papers), 'collections': len(collections), 'pdf_files': 0 if md_only else sum(len(p['pdf_files']) for p in papers.values()),
              'summary_files': 0 if pdf_only else sum(len(p['summary_files']) for p in papers.values()),
              'papers_without_pdf': sum(not p['pdf_files'] for p in papers.values()),
              'papers_without_summary': sum(p['summary_status'] == 'missing' for p in papers.values()),
              'papers_needing_review': sum(p['review_required'] for p in papers.values()),
              'ignored_pdf_files': len(ignored_pdfs), 'files_hidden': 0 if dry_run else len(to_hide),
              'files_renamed': 0 if dry_run else len(renames), 'files_to_rename': len(renames),
              'files_written': 0 if dry_run else len(changed), 'files_to_write': len(changed),
              'files_unchanged': unchanged, 'warnings': warnings, 'dry_run': dry_run}
    report['pdf_bytes_to_copy'] = sum(content.stat().st_size for relative in changed for content, _ in [outputs[relative]] if isinstance(content, Path))
    if dry_run:
        return report
    # Check the input snapshot before the first output write, even for small metadata files.
    for relative, saved in inputs.items():
        stat = (root / relative).stat()
        if (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns) != (saved['size'], saved['mtime_ns'], saved['ctime_ns']):
            if Path(relative).suffix.lower() == '.pdf':
                raise ValueError(f'Source changed during planning; rerun: {relative}')
            warnings.append(f'Source changed after text snapshot; latest version will be picked up next run: {relative}')
    for relative, hidden in to_hide.items():
        target = dest / hidden
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(dest / relative, target)
        print('Ignored ' + relative, file=sys.stderr, flush=True)
    rename_outputs(dest, renames)
    for relative in changed:
        content, sha = outputs[relative]
        path = dest / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.import-', delete=False) as stream:
                temporary = Path(stream.name)
                if isinstance(content, Path):
                    with content.open('rb') as source:
                        shutil.copyfileobj(source, stream, 1024 * 1024)
                else:
                    stream.write(content)
            if digest(temporary) != sha:
                raise ValueError(f'Content changed while copying: {content}')
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        print('Wrote ' + relative, file=sys.stderr, flush=True)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json_text(catalog)
    if not state_path.exists() or state_path.read_text(encoding='utf-8') != payload:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=state_path.parent, prefix='.catalog-', delete=False) as stream:
            stream.write(payload)
            temporary = Path(stream.name)
        os.replace(temporary, state_path)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--labs-root', type=Path, default=Path(__file__).resolve().parent / 'labs')
    parser.add_argument('--destination', type=Path, default=Path.home() / 'research')
    parser.add_argument('--lab', action='append', default=[], help='Limit to a collection; repeat for several')
    parser.add_argument('--dry-run', action='store_true', help='Plan and validate without writing files')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--pdf_only', action='store_true', help='Export only PDFs; skip Markdown output')
    mode.add_argument('--md_only', action='store_true', help='Export only Markdown; skip PDF output')
    args = parser.parse_args()
    try:
        report = import_labs(args.labs_root, args.destination, args.dry_run, args.lab,
                             pdf_only=args.pdf_only, md_only=args.md_only)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(1, f'Import failed: {exc}\n')
    print(json_text(report), end='')


if __name__ == '__main__':
    main()
