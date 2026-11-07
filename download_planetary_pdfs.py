"""Cache official technical PDFs, without model calls or credentials."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

import requests

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data/planetary_exploration'
SOURCES=[
    {'id':'pdf-messenger-2011','planet':'수성','title':'MESSENGER Mercury Orbit Insertion Press Kit (2011)','url':'https://www.nasa.gov/wp-content/uploads/2015/04/525164main_mercurymoi_pk.pdf','date_label':'2011-03'},
    {'id':'pdf-curiosity-landing-2012','planet':'화성','title':'Mars Science Laboratory Curiosity Landing Press Kit (2012)','url':'https://science.nasa.gov/wp-content/uploads/2024/03/44747_MSL-Landing.pdf','date_label':'2012-07'},
    {'id':'pdf-perseverance-landing-2021','planet':'화성','title':'Mars 2020 Perseverance Landing Press Kit (2021)','url':'https://mars.nasa.gov/system/downloadable_items/45585_mars_2020_landing_press_kit.pdf','date_label':'2021-01'},
    {'id':'pdf-europa-clipper-2024','planet':'목성','title':'Europa Clipper Press Kit (2024)','url':'https://science.nasa.gov/wp-content/uploads/2024/09/europa-clipper-press-kit.pdf','date_label':'2024-09'},
    {'id':'pdf-juno-telecom-2017','planet':'목성','title':'Juno Telecommunications Design and Performance Summary (2017)','url':'https://descanso.jpl.nasa.gov/DPSummary/Descanso16_Juno_RevA.pdf','date_label':'2017; verify cover'},
    {'id':'pdf-venus-express-brochure','planet':'금성','title':'Venus Express ESA Mission Brochure','url':'https://esamultimedia.esa.int/docs/VENUSEXPRESSLR.pdf','date_label':'verify cover'},
]
ALLOWED={'www.nasa.gov','science.nasa.gov','mars.nasa.gov','assets.science.nasa.gov','descanso.jpl.nasa.gov','esamultimedia.esa.int'}


def fetch(source):
    folder=DATA/'raw_pdf';folder.mkdir(exist_ok=True)
    path=folder/(source['id']+'.pdf');meta=folder/(source['id']+'.json')
    try:
        if path.exists() and meta.exists():return json.loads(meta.read_text(encoding='utf-8'))
        if urlsplit(source['url']).hostname not in ALLOWED:raise ValueError('Unapproved host')
        response=requests.get(source['url'],timeout=90)
        response.raise_for_status()
        if urlsplit(response.url).hostname not in ALLOWED:raise ValueError('Unapproved redirect host')
        if not response.content.startswith(b'%PDF'):raise ValueError('Response is not a PDF')
        path.write_bytes(response.content)
        result={'source':{**source,'type':'historical_design_press_kit_or_technical_report'},'requested_url':source['url'],
                'final_url':response.url,'retrieved_at':datetime.now(timezone.utc).isoformat(),'http_status':200,
                'bytes':len(response.content),'raw_path':str(path.relative_to(ROOT)),'sha256_raw':hashlib.sha256(response.content).hexdigest()}
        meta.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        return result
    except (requests.RequestException,ValueError) as exc:
        return {'source':source,'error':str(exc)[:200]}


if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=3) as pool:records=list(pool.map(fetch,SOURCES))
    (DATA/'pdf_downloads.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps([{'id':r['source']['id'],'bytes':r.get('bytes'),'error':r.get('error')} for r in records],ensure_ascii=False))
