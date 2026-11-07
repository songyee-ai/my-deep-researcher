"""Versioned official mission-report expansion; never modifies the active corpus.

Run each stage with the project venv (pypdf + fontTools for extraction).
The explicit manifest is selected for mission relevance, not a target token count.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
BASE = ROOT / 'data/planetary_exploration'
DEST = BASE / 'versions/engineering-v2'
INDEX = 'https://descanso.jpl.nasa.gov/DPSummary/summary.html'
REPORTS = [
    ('mgs', '화성', 'Mars Global Surveyor Telecommunications', 'MGS_07Aug01.pdf'),
    ('galileo', '목성', 'Galileo Telecommunications', 'Descanso5--Galileo_new.pdf'),
    ('odyssey', '화성', 'Odyssey Telecommunications', 'odyssey_telecom.pdf'),
    ('mer-telecom', '화성', 'Mars Exploration Rover Telecommunications', 'MER_article_cmp20051028.pdf'),
    ('mer-navigation', '화성', 'Mars Exploration Rover Navigation', 'DESCANSO_MER_NAV_051215C_low.pdf'),
    ('mro', '화성', 'Mars Reconnaissance Orbiter Telecommunications', 'MRO_092106.pdf'),
    ('msl-telecom', '화성', 'Mars Science Laboratory Telecommunications System Design', 'Descanso14_MSL_Telecom.pdf'),
    ('phoenix', '화성', 'Phoenix Telecommunications', 'PhxArticle_--RC101013DocX_COMPRESSED_AcronFixBU.pdf'),
    ('marco', '화성', 'Mars Cube One Telecommunications Subsystem Design', 'DESCANSO18_MarCO.pdf'),
]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download():
    import requests
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin
    import download_planetary_pdfs as downloader

    DEST.mkdir(parents=True, exist_ok=True)
    inputs = ['corpus.json', 'statistics.json', 'link_evidence.json', 'collection_audit.json',
              'extracted.json', 'pdf_extracted.json', 'pdf_downloads.json', 'questions.json',
              'tokenizer.json', 'model_context.json']
    snapshot = DEST / 'baseline'
    snapshot.mkdir(exist_ok=True)
    for name in inputs:
        target = snapshot / name
        if target.exists():
            if digest(target) != digest(BASE / name):
                raise ValueError(f'Baseline changed: {name}; use a new version directory')
        else:
            shutil.copy2(BASE / name, target)
        if name not in ('corpus.json', 'statistics.json', 'link_evidence.json', 'collection_audit.json',
                        'pdf_extracted.json', 'pdf_downloads.json'):
            shutil.copy2(target, DEST / name)
    write(snapshot / 'hashes.json', {name: digest(snapshot / name) for name in inputs})
    response = requests.get(INDEX, timeout=40)
    response.raise_for_status()
    if response.url != INDEX:
        raise ValueError('Unexpected index redirect')
    (DEST / 'discovery-index.html').write_bytes(response.content)
    hrefs = {urljoin(INDEX, a['href']) for a in BeautifulSoup(response.content, 'html.parser').find_all('a', href=True)}
    sources = []
    for slug, planet, title, filename in REPORTS:
        url = urljoin(INDEX, filename)
        if url not in hrefs:
            raise ValueError(f'Source not observed on official index: {url}')
        sources.append({'id': f'pdf-descanso-{slug}', 'planet': planet, 'title': title,
                        'url': url, 'date_label': 'See original report cover',
                        'discovered_from': INDEX, 'selection_reason': 'Whole mission-specific design/performance report; communications or navigation constraints and engineering evidence.'})
    write(DEST / 'extension_sources.json', sources)
    downloader.DATA = DEST
    with ThreadPoolExecutor(max_workers=3) as pool:
        added = list(pool.map(downloader.fetch, sources))
    write(DEST / 'extension_downloads.json', added)
    if any('error' in r for r in added):
        raise RuntimeError('Some downloads failed; inspect extension_downloads.json; active corpus unchanged')
    write(DEST / 'pdf_downloads.json', read(snapshot / 'pdf_downloads.json') + added)
    print(json.dumps({'downloaded': len(added), 'version': str(DEST)}, ensure_ascii=False))


def audit():
    import validate_planetary as validator
    validator.DATA = DEST
    validator.main()
    old = read(DEST / 'baseline/corpus.json')
    new = read(DEST / 'corpus.json')
    assert all(new['docs'].get(k) == v for k, v in old['docs'].items())
    assert all(set(v) <= set(new['links'][k]) for k, v in old['links'].items())
    for name, expected in read(DEST / 'baseline/hashes.json').items():
        assert digest(BASE / name) == expected, f'Active input changed: {name}'
    normalized_html = 0
    for m in new['metadata'].values():
        raw = ROOT / m['raw_path']
        if raw.suffix == '.html':
            # The legacy collector hashes HTTP bytes, then writes decoded HTML
            # in text mode on Windows (LF -> CRLF). Verify its recorded hash
            # using universal-newline UTF-8 reconstruction, without rewriting it.
            observed = hashlib.sha256(raw.read_text(encoding='utf-8').encode('utf-8')).hexdigest()
            normalized_html += 1
        else:
            observed = digest(raw)
        assert observed == m['sha256_raw'], f'Raw source hash failed: {m["source_id"]}'
    stats = read(DEST / 'statistics.json')
    added = [k for k in new['docs'] if k not in old['docs']]
    pdfs = read(DEST / 'pdf_extracted.json')
    added_ids = {new['metadata'][k]['source_id'] for k in added}
    quality = []
    for r in pdfs:
        if r['source']['id'] not in added_ids:
            continue
        text = r['text']
        quality.append({'source_id': r['source']['id'], 'pages': r['pdf_pages'], 'chars': len(text),
                        'replacement_characters': text.count('\ufffd'),
                        'pages_under_100_chars': [p['page'] for p in r['page_offsets'] if p['chars'] < 100]})
        assert len(text) > 10000 and text.count('\ufffd') / len(text) < .001
    result = {'integrity': 'PASS', 'active_corpus_unchanged': True,
              'baseline_documents_preserved': len(old['docs']), 'added_documents': len(added),
              'documents': len(new['docs']), 'characters': stats['total_characters'],
              'exact_duplicate_hashes': stats['duplicate_hash_count'],
              'raw_verification': {'pdf_byte_hashes': len(new['docs']) - normalized_html,
                                   'legacy_html_utf8_universal_newline_hashes': normalized_html},
              'similar_pairs_for_review': stats['similar_pairs_ge_025'], 'extraction_quality': quality,
              'codex_context_condition': 'NOT_REMEASURED',
              'status': 'Staged candidate only; visual and semantic review required before promotion. Existing question hints retained; additions are concentrated on Mars and do not establish balanced planetary coverage.'}
    write(DEST / 'expansion_audit.json', result)
    print(json.dumps(result, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['download', 'extract', 'build', 'audit'])
    args = parser.parse_args()
    if args.stage == 'download':
        download()
    elif args.stage == 'extract':
        import extract_planetary_pdfs as extractor
        extractor.DATA = DEST
        # Keep the exact original extraction bytes; dependency upgrades must not
        # silently rewrite the six baseline PDFs or old model inputs.
        extractor.main(records=read(DEST / 'extension_downloads.json'))
        added = read(DEST / 'pdf_extracted.json')
        write(DEST / 'pdf_extracted.json', read(DEST / 'baseline/pdf_extracted.json') + added)
    elif args.stage == 'build':
        import build_planetary as builder
        builder.DATA = DEST
        builder.main()
    else:
        audit()


if __name__ == '__main__':
    main()
