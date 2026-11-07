"""Offline integrity checks against cached source snapshots and measured corpus."""
import hashlib
import json
from pathlib import Path

from collect_planetary import DATA, ROOT, normalized
from pipeline import Corpus


def main():
    corpus = json.loads((DATA/'corpus.json').read_text(encoding='utf-8'))
    stats = json.loads((DATA/'statistics.json').read_text(encoding='utf-8'))
    evidence = json.loads((DATA/'link_evidence.json').read_text(encoding='utf-8'))
    questions = json.loads((DATA/'questions.json').read_text(encoding='utf-8'))['questions']
    docs = corpus['docs']; metadata = corpus['metadata']; links = corpus['links']
    assert len(docs) >= 30 and len(questions) >= 8
    assert set(docs) == set(links) == set(metadata)
    assert sum(map(len, docs.values())) == stats['total_characters']
    assert len(docs) == stats['document_count']
    assert len(set(m['sha256_text'] for m in metadata.values())) == len(docs)
    for key, text in docs.items():
        m = metadata[key]
        assert len(text) == m['chars'] and len(text) >= 700
        assert hashlib.sha256(text.encode()).hexdigest() == m['sha256_text']
        assert (ROOT / m['raw_path']).is_file()
        assert 'Keep Exploring' not in text
        assert len(links[key]) == len(set(links[key]))
        assert all(t in docs and t != key for t in links[key])
    actual = {(s,t) for s,targets in links.items() for t in targets}
    assert actual == {(e['source'],e['target']) for e in evidence}
    assert len(evidence) == len(actual) == stats['directed_edges']
    extracted = json.loads((DATA/'extracted.json').read_text(encoding='utf-8'))
    if (DATA/'pdf_extracted.json').exists():extracted+=json.loads((DATA/'pdf_extracted.json').read_text(encoding='utf-8'))
    by_id = {r['source']['id']:r for r in extracted if 'text' in r}
    for e in evidence:
        r = by_id[metadata[e['source']]['source_id']]
        assert any(a['url'] == e['observed_href'] and a['label'] == e['anchor_label'] for a in r['article_links'])
        m = metadata[e['target']]
        assert e['observed_href'] in {normalized(m['requested_url']),normalized(m['final_url'])}
    assert len({q['id'] for q in questions}) == len(questions)
    assert any(not q['division_expected'] for q in questions)
    for q in questions:
        assert q['why_divide_or_not'] and all(t in docs for t in q['source_hints'])
    loaded = Corpus.load(DATA)
    assert loaded.docs == docs and loaded.links == links
    assert stats['context_gate']['exceeds_context'] == (stats['body_tokens_sum'] > stats['context_gate']['provider_context_tokens'])
    print(json.dumps({'integrity':'PASS','original_pipeline_corpus_loader':'PASS','documents':len(docs),'questions':len(questions),'observed_edges':len(actual),'context_gate':stats['context_gate']['status']},ensure_ascii=False))


if __name__=='__main__':
    main()
