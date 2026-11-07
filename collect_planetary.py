"""Collect bounded official HTML sources. No LLM, credentials or API keys used.

Network fetches are cached for reproducible extraction. Only observed in-article
anchors become corpus edges; related-menu links are discovery candidates only.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data' / 'planetary_exploration'
CACHE = DATA / 'raw'
ALLOWED = {'science.nasa.gov', 'www.nasa.gov', 'www.jpl.nasa.gov', 'www.esa.int'}


def normalized(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip('/') or '/', '', ''))


def fetch(source, offline=False):
    url = source['url']
    if urlsplit(url).hostname not in ALLOWED:
        return {'source': source, 'error': 'non-allowlisted host'}
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(url.encode()).hexdigest()[:20]
    html_path = CACHE / f'{key}.html'
    meta_path = CACHE / f'{key}.json'
    try:
        if html_path.exists() and meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding='utf-8'))
            html = html_path.read_text(encoding='utf-8')
        else:
            if offline:
                return {'source': source, 'error': 'No cached successful HTML snapshot (offline mode)'}
            response = requests.get(url, timeout=40, headers={'User-Agent': 'PlanetaryResearchClass/1.0 (educational source collection)'})
            response.raise_for_status()
            if urlsplit(response.url).hostname not in ALLOWED:
                raise ValueError('redirect to non-allowlisted host')
            if 'text/html' not in response.headers.get('Content-Type', ''):
                raise ValueError('not HTML')
            html = response.content.decode(response.encoding or 'utf-8', errors='replace')
            meta = {'requested_url': url, 'final_url': response.url, 'retrieved_at': datetime.now(timezone.utc).isoformat(), 'http_status': response.status_code, 'sha256_raw': hashlib.sha256(response.content).hexdigest()}
            html_path.write_text(html, encoding='utf-8')
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
        return extract(source, html, meta, str(html_path.relative_to(ROOT)))
    except (requests.RequestException, ValueError) as exc:
        return {'source': source, 'error': str(exc)[:300]}


def extract(source, html, meta, raw_path):
    soup = BeautifulSoup(html, 'html.parser')
    title_tag = soup.select_one('h1') or soup.title
    title = title_tag.get_text(' ', strip=True) if title_tag else source['title']
    # Prefer article-level containers over page-wide main/navigation.
    # ESA's migrated article pages without prose modules are empty/hub pages.
    esa_prose = '.articles-modules__text-only, .articles-modules__text-image'
    if 'www.esa.int' in meta['final_url'] and not soup.select(esa_prose):
        return {'source': source, 'error': 'ESA page has no prose modules; hub/empty page excluded'}
    if 'www.esa.int' in meta['final_url'] and sum(len(n.get_text(' ', strip=True)) for n in soup.select(esa_prose)) < 700:
        return {'source': source, 'error': 'ESA prose <700 chars; exclude short/hub pages'}
    selectors = (esa_prose, '.wysiwyg_content', '.entry-content', '.article-body', '[itemprop="articleBody"]', '.wysiwyg', 'article', 'main', '#main')
    root = None
    selector = None
    for sel in selectors:
        nodes = soup.select(sel)
        if sum(len(n.get_text(' ', strip=True)) for n in nodes) >= 700:
            root = BeautifulSoup('\n'.join(str(n) for n in nodes), 'html.parser')
            selector = sel
            break
    if root is None:
        return {'source': source, 'error': 'No article container >=700 chars; needs manual review'}
    for node in root.select('script, style, nav, header, footer, aside, form, button, svg, .navigation, .social-share, .share, .related, .related-content, .image, .image-container, .interactive-media-modal, [class*="global-nav"], .hds-content-card, .latest-news-item'):
        if getattr(node, 'attrs', None) is None:
            continue
        node.decompose()
    for node in list(root.select('.hds-news-item-bubble')):
        parent = node.find_parent('a')
        (parent or node).decompose()
    # NASA's topic footer is editorial navigation, not a reference in the prose.
    for label in list(root.find_all(string=lambda s: s and s.strip() in ('Keep Exploring', 'Discover More Topics From NASA'))):
        block = getattr(label, 'parent', None)
        if block is None:
            continue
        while block.parent and block.name not in ('section', 'article') and 'entry-content' not in block.get('class', []):
            if 'entry-content' in block.parent.get('class', []):
                break
            block = block.parent
        if block.name != 'article' and 'entry-content' not in block.get('class', []):
            block.decompose()
    anchors = []
    for a in root.select('a[href]'):
        href = urljoin(meta['final_url'], a['href'])
        if urlsplit(href).scheme in ('http', 'https'):
            anchors.append({'url': normalized(href), 'label': a.get_text(' ', strip=True)[:200]})
    # Line-oriented text avoids flattening paragraphs and preserves headings.
    lines = [re.sub(r'\s+', ' ', x).strip() for x in root.get_text('\n', strip=True).splitlines()]
    text = '\n'.join(x for x in lines if x)
    if len(text) < 700:
        return {'source': source, 'error': 'Extracted article too short'}
    published = soup.select_one('meta[property="article:published_time"], meta[name="date"], meta[name="DC.date.issued"]')
    modified = soup.select_one('meta[property="article:modified_time"], meta[name="DC.date.modified"]')
    visible_date = re.search(r'\b\d{2} [A-Z]{3}\. \d{4}\b', (soup.select_one('main') or soup).get_text(' ', strip=True)[:1000])
    discovered = []
    for a in soup.select('a[href]'):
        href = urljoin(meta['final_url'], a['href'])
        if urlsplit(href).hostname in ALLOWED:
            discovered.append({'url': normalized(href), 'label': a.get_text(' ', strip=True)[:180]})
    # ESA mission hubs consist mostly of cards; do not treat them as articles.
    if 'esa.int/missions/' in meta['final_url']:
        return {'source': source, 'error': 'Mission navigation hub excluded; collect linked articles instead'}
    return {'source': source, **meta, 'title': title, 'text': text, 'chars': len(text), 'selector': selector,
            'published_at': published.get('content') if published else None,
            'modified_at': modified.get('content') if modified else None,
            'publication_date_label': visible_date.group() if visible_date else None,
            'article_links': anchors, 'discovered_links': discovered, 'raw_path': raw_path,
            'sha256_text': hashlib.sha256(text.encode()).hexdigest()}


def collect(offline=False):
    manifest = json.loads((DATA / 'source_candidates.json').read_text(encoding='utf-8'))
    extra_path = DATA / 'additional_sources.json'
    sources = manifest['sources'] + (json.loads(extra_path.read_text(encoding='utf-8')) if extra_path.exists() else [])
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(lambda s: fetch(s, offline), sources))
    failures_path = DATA / 'fetch_failures.json'
    if offline and failures_path.exists():
        previous = json.loads(failures_path.read_text(encoding='utf-8'))
        for r in records:
            if r.get('error', '').startswith('No cached'):
                r['error'] = previous.get(r['source']['id'], r['error'])
    elif not offline:
        failures_path.write_text(json.dumps({r['source']['id']:r['error'] for r in records if 'error' in r}, ensure_ascii=False, indent=2), encoding='utf-8')
    (DATA / 'extracted.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'sources': len(records), 'accepted': sum('text' in r for r in records), 'errors': [{'id': r['source']['id'], 'error': r['error']} for r in records if 'error' in r], 'by_planet': dict(Counter(r['source']['planet'] for r in records if 'text' in r))}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true', help='Re-extract successful cached snapshots only; never access the network')
    collect(parser.parse_args().offline)
