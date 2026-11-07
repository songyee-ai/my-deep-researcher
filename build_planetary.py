"""Build and audit the offline planetary corpus from collected HTML snapshots."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from tokenizers import Tokenizer

from collect_planetary import DATA, normalized


def dump(name, value):
    (DATA / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def shingles(text):
    words = re.findall(r'\w+', text.lower())
    return {tuple(words[i:i+7]) for i in range(len(words)-6)}


def main():
    records = json.loads((DATA / 'extracted.json').read_text(encoding='utf-8'))
    pdf_records=DATA/'pdf_extracted.json'
    if pdf_records.exists():records+=json.loads(pdf_records.read_text(encoding='utf-8'))
    excluded = []
    accepted = []
    hashes = set()
    urls = set()
    # Planet landing pages are mostly discovery cards. Keep full Facts articles.
    hubs = {'extra-025', 'extra-028', 'extra-031', 'extra-034'}
    for r in records:
        if 'error' in r:
            excluded.append({'source_id': r['source']['id'], 'url': r['source']['url'], 'reason': r['error']})
            continue
        reason = None
        if r['source']['id'] in hubs:
            reason = 'Topic discovery landing page excluded in favour of full Facts article'
        elif r['sha256_text'] in hashes or normalized(r['final_url']) in urls:
            reason = 'Duplicate content hash or final URL'
        if reason:
            excluded.append({'source_id': r['source']['id'], 'url': r['source']['url'], 'reason': reason})
            continue
        hashes.add(r['sha256_text']); urls.add(normalized(r['final_url'])); accepted.append(r)
    tokenizer = Tokenizer.from_file(str(DATA / 'tokenizer.json'))
    tokenizer.no_truncation(); tokenizer.no_padding()
    docs = {}
    metadata = {}
    aliases = {}
    for r in accepted:
        key = f"{r['source']['planet']} | {r['title']}"
        if key in docs:
            key += f" [{r['source']['id']}]"
        r['doc_id'] = key
        docs[key] = r['text']
        metadata[key] = {k: r.get(k) for k in ('title','requested_url','final_url','retrieved_at','published_at','modified_at','publication_date_label','raw_path','sha256_raw','sha256_text','selector','chars')}
        metadata[key].update({'source_id': r['source']['id'], 'planet': r['source']['planet'], 'document_type': r['source']['type'], 'language': 'en', 'tokens': len(tokenizer.encode(r['text'], add_special_tokens=False).ids), 'temporal_note': 'Read source dates and tense: planned objectives are not proof of achieved results; collection date is not publication date.'})
        if 'pdf_pages' in r:
            metadata[key].update(pdf_pages=r['pdf_pages'],page_offsets=r['page_offsets'],normalization=r['normalization'])
        aliases[normalized(r['requested_url'])] = key
        aliases[normalized(r['final_url'])] = key
    links = {key: [] for key in docs}
    evidence = []
    for r in accepted:
        seen = set()
        for a in r['article_links']:
            target = aliases.get(a['url'])
            if target and target != r['doc_id'] and target not in seen:
                seen.add(target); links[r['doc_id']].append(target)
                evidence.append({'source': r['doc_id'], 'target': target, 'anchor_label': a['label'], 'observed_href': a['url'], 'rule': 'Observed anchor in retained article container; no inferred/reverse edges'})
    similar = []
    sets = {k: shingles(v) for k,v in docs.items()}
    keys = list(docs)
    for i,a in enumerate(keys):
        for b in keys[i+1:]:
            union = sets[a] | sets[b]
            j = len(sets[a] & sets[b]) / len(union) if union else 0
            if j >= .25:
                similar.append({'a':a,'b':b,'seven_word_shingle_jaccard':round(j,4)})
    model = json.loads((DATA / 'model_context.json').read_text(encoding='utf-8'))
    total_tokens = sum(m['tokens'] for m in metadata.values())
    zero_out = [k for k,v in links.items() if not v]
    incoming = Counter(t for targets in links.values() for t in targets)
    zero_in = [k for k in docs if incoming[k] == 0]
    isolated = sorted(set(zero_in) & set(zero_out))
    stats = {'document_count':len(docs), 'total_characters':sum(map(len,docs.values())), 'body_tokens_sum':total_tokens,
             'tokenizer':{'repository':model['model']['hugging_face_id'],'file_sha256':hashlib.sha256((DATA/'tokenizer.json').read_bytes()).hexdigest(),'add_special_tokens':False,'note':'Exact local body tokenization, not chat prompt overhead or provider billing.'},
             'by_planet':{p:{'documents':sum(m['planet']==p for m in metadata.values()),'characters':sum(m['chars'] for m in metadata.values() if m['planet']==p),'tokens':sum(m['tokens'] for m in metadata.values() if m['planet']==p)} for p in ['수성','금성','화성','목성']},
             'directed_edges':sum(map(len,links.values())), 'zero_outgoing':zero_out,'zero_incoming':zero_in,'fully_isolated':isolated,
             'duplicate_hash_count':len(docs)-len({m['sha256_text'] for m in metadata.values()}), 'similar_pairs_ge_025':similar,
             'context_gate':{'model':model['model']['id'],'provider_context_tokens':model['model']['context_length'],'body_tokens_sum':total_tokens,'exceeds_context':total_tokens>model['model']['context_length'],'status':'PASS' if total_tokens>model['model']['context_length'] else 'NOT_MET','note':'Do not claim assignment size condition met, or substitute an artificial input truncation limit. Expand relevant material or explicitly select and verify a suitable smaller-context model for all conditions.'},
             'unresolved_links_policy':'Only collected source targets retained. No invented links. Incoming-zero documents require seed assignment or the existing all-document fallback; do not claim they are reachable by link-only traversal.',
             'review_status':'Machine extraction checked; human full-text/citation review still required.'}
    assert len(docs)>=30
    assert stats['duplicate_hash_count']==0
    assert all(t in docs and t!=s for s,targets in links.items() for t in targets)
    assert len(evidence)==stats['directed_edges']
    dump('corpus.json',{'_description':'Official-source planetary exploration corpus, original English text. Local educational research snapshot.','_collected':'2026-11-06','docs':docs,'links':links,'metadata':metadata})
    dump('link_evidence.json',evidence); dump('collection_audit.json',{'excluded':excluded,'statistics':stats}); dump('statistics.json',stats)
    print(json.dumps({k:stats[k] for k in ['document_count','total_characters','body_tokens_sum','by_planet','directed_edges','context_gate']},ensure_ascii=False))


if __name__=='__main__':
    main()
