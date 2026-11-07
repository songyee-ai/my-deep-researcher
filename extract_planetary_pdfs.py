"""Read cached official PDFs with bundled pypdf. No network or model calls."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit,urlunsplit

from pypdf import PdfReader

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data/planetary_exploration'


def normalized(url):
    p=urlsplit(url)
    return urlunsplit((p.scheme,p.netloc.lower(),p.path.rstrip('/') or '/','',''))


def main(records=None):
    if records is None:
        records=json.loads((DATA/'pdf_downloads.json').read_text(encoding='utf-8'))
    out=[]
    for r in records:
        if 'error' in r:out.append(r);continue
        if r['source']['id']=='pdf-juno-telecom-2017':r['source']['date_label']='2017-08'
        reader=PdfReader(ROOT/r['raw_path'])
        pages=[page.extract_text() or '' for page in reader.pages]
        frequency=Counter(line.strip() for page in pages for line in set(page.splitlines()) if line.strip())
        repeated={line for line,n in frequency.items() if n>=max(4,len(pages)//2) and len(line)<80
                  and re.search(r'press\s*kit|NASA|Jet Propulsion|European Space Agency',line,re.IGNORECASE)}
        pieces=[];offsets=[];position=0;links=[]
        for i,(page,text) in enumerate(zip(reader.pages,pages)):
            raw_lines=text.splitlines()
            lines=[line.rstrip() for index,line in enumerate(raw_lines) if line.strip() not in repeated
                   and not (index in (0,len(raw_lines)-1) and line.strip()==str(i+1))]
            text='\n'.join(lines).strip()
            text=re.sub(r'(?<=[a-z])-\n(?=[a-z])','',text)
            offsets.append({'page':i+1,'start':position,'end':position+len(text),'chars':len(text)})
            pieces.append(text);position+=len(text)+2
            for annotation in page.get('/Annots',[]):
                a=annotation.get_object().get('/A',{})
                uri=a.get('/URI') if hasattr(a,'get') else None
                if uri and str(uri).startswith(('http://','https://')):
                    links.append({'url':normalized(str(uri)),'label':f'PDF page {i+1} hyperlink annotation'})
        body='\n\n'.join(pieces)
        result={**r,'title':r['source']['title'],'text':body,'chars':len(body),'selector':'pypdf_plain_page_order_repeated_headers_removed',
                'published_at':None,'modified_at':None,'publication_date_label':r['source'].get('date_label'),
                'article_links':links,'discovered_links':links,'sha256_text':hashlib.sha256(body.encode()).hexdigest(),
                'pdf_pages':len(pages),'page_offsets':offsets,'removed_repeated_lines':sorted(repeated),
                'normalization':'Repeated short publisher/press-kit headers and edge page-number lines removed; numeric data lines retained; lowercase line-break hyphens joined.'}
        out.append(result)
    (DATA/'pdf_extracted.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps([{'id':r['source']['id'],'pages':r.get('pdf_pages'),'chars':r.get('chars'),'error':r.get('error')} for r in out],ensure_ascii=False))


if __name__=='__main__':main()
