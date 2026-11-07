"""Question-aware extractive cards; no model calls or fabricated summaries."""
import re


def document_cards(corpus,question,term_groups,limit=250):
    terms=[]
    for group in term_groups:
        if any(term.casefold() in question.casefold() for term in group['triggers']):
            terms.extend(group['source_terms'])
    rows=[]
    for title,body in corpus.docs.items():
        text=re.sub(r'\s+',' ',body).strip();snippets=[];positions=[];matched=[]
        for term in terms:
            match=re.search(re.escape(term),text,re.IGNORECASE)
            if match and all(abs(match.start()-p)>90 for p in positions):
                positions.append(match.start());matched.append(term)
                snippets.append(text[max(0,match.start()-35):match.start()+100])
                if len(snippets)==2:break
        excerpt=(text[:50]+' … '+' … '.join(snippets))[:limit] if snippets else text[:limit]
        rows.append(f'- {title} [관련 용어: {", ".join(matched) or "직접 일치 없음"}]: {excerpt}')
    return '\n'.join(rows)
