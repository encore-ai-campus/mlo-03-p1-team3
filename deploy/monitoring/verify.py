"""Read-only checks for snapshot freshness, provisioned dashboards and their queries."""
import argparse
import base64
import concurrent.futures
import json
from pathlib import Path
import shlex
import subprocess
import time
import urllib.parse
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def get(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=30) as r:
        return json.load(r)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', required=True)
    args=parser.parse_args()
    result=subprocess.run(['ansible-inventory','-i',args.inventory,'--list'], capture_output=True,text=True,check=True)
    inventory=json.loads(result.stdout); hosts=inventory['_meta']['hostvars']
    def endpoint(group,port):return 'http://'+hosts[inventory[group]['hosts'][0]]['ansible_host']+':'+str(port)
    prom,loki,grafana=endpoint('prometheus',9090),endpoint('loki',3100),endpoint('grafana',3000)
    query='podobank_business_collect_success == 1 and on(instance) (up{job="node"} == 1) and on(instance) (time()-podobank_business_collect_success_timestamp_seconds < 180)'
    for _ in range(40):
        samples=get(prom+'/api/v1/query?'+urllib.parse.urlencode({'query':query}))['data']['result']
        if len(samples)==3:break
        time.sleep(2)
    else:raise RuntimeError('Three fresh successful business snapshots not available')
    print('PASS: primary, replica and MongoDB aggregate snapshots healthy and fresh',flush=True)
    query='count by(store)(podobank_db_records)'
    samples=get(prom+'/api/v1/query?'+urllib.parse.urlencode({'query':query}))['data']['result']
    assert {s['metric']['store']:int(float(s['value'][1])) for s in samples}=={'mariadb':30,'mongodb':2}
    print('PASS: 30 SQL aggregate series and 2 MongoDB collection counts exported',flush=True)
    private={}
    for line in (ROOT/'deploy/vm/monitoring.env').read_text().splitlines():
        if '=' not in line or line.lstrip().startswith('#'):continue
        key,value=line.split('=',1);parts=shlex.split(value);private[key]=parts[0] if parts else ''
    headers={'Authorization':'Basic '+base64.b64encode(('admin:'+private['GRAFANA_ADMIN_PASSWORD']).encode()).decode()}
    boards=[json.loads(p.read_text()) for p in sorted((ROOT/'deploy/monitoring/dashboards').glob('*.json'))]
    def signature(board):
        return [(p['title'],p['type'],[t.get('expr') for t in p.get('targets',[])],p.get('transformations',[]),p['gridPos'],p.get('fieldConfig',{})) for p in board['panels']]
    for board in boards:
        # File provisioning polls every 30 seconds; deployment must wait for this revision.
        for _ in range(30):
            saved=get(grafana+'/api/dashboards/uid/'+board['uid'],headers)
            if (saved['dashboard']['title']==board['title'] and signature(saved['dashboard'])==signature(board)
                    and saved['meta'].get('provisioned')):
                break
            time.sleep(2)
        else:raise RuntimeError(board['uid']+' did not load the current repository definition')
    for uid in ('podobank-business','podobank-http'):
        try:get(grafana+'/api/dashboards/uid/'+uid,headers)
        except urllib.error.HTTPError as exc:
            if exc.code!=404:raise
        else:raise RuntimeError('Retired dashboard still exists: '+uid)
    assert len(boards)==10 and all(p['type']!='text' for b in boards for p in b['panels'])
    print('PASS: all '+str(len(boards))+' repository dashboards provisioned and read back',flush=True)
    def check(item):
        panel,target=item;q=target['expr']
        for key,value in [('$__rate_interval','1m'),('$__range','1h'),('$__interval','1m'),('$__auto','1m'),('${instance:regex}','.*'),('$api','.*'),('$business','deposit|withdrawal|transfer|loan_application|loan_review|loan_repayment|card_payment'),('${request_id:doublequote}','""')]:q=q.replace(key,value)
        is_loki=panel['datasource']['type']=='loki'
        path='/loki/api/v1/' if is_loki else '/api/v1/'
        parameters={'query':q}
        if is_loki and panel['type']=='logs':
            path+='query_range';parameters.update(start=str(time.time_ns()-3600_000_000_000),end=str(time.time_ns()),limit=1)
        else:path+='query'
        result=get((loki if is_loki else prom)+path+'?'+urllib.parse.urlencode(parameters))
        assert result['status']=='success',panel['title']
        return len(result['data']['result'])
    items=[(p,t) for b in boards for p in b['panels'] for t in p.get('targets',[]) if 'expr' in t]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:counts=list(pool.map(check,items))
    print(f'PASS: {len(items)} dashboard queries execute without errors; {sum(n==0 for n in counts)} empty results (no matching activity is allowed)',flush=True)


if __name__=='__main__':main()
