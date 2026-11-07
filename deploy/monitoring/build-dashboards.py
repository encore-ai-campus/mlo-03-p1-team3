"""Rebuild business and HTTP panels inside the existing service dashboards."""
import json
from pathlib import Path

ROOT = Path(__file__).with_name('dashboards')
P = {'type': 'prometheus', 'uid': 'podobank-prometheus'}
L = {'type': 'loki', 'uid': 'podobank-loki'}
TYPES = 'deposit|withdrawal|transfer|loan_application|loan_review|loan_repayment|card_payment'
E = '{job="podobank",log_type="event",instance=~"$api"} | json | __error__="" | event_type=~"$business"'
N = '{service="nginx",log_type="access"} | regexp `"(?P<method>\\S+) (?P<path>[^ ]+) HTTP/[^"]+" (?P<status>[0-9]{3})` | __error__=""'
A = '{job="podobank",log_type="application",instance=~"$api"} | json | __error__="" | message="request_completed"'
HTTP = 'podobank_http_requests_total{job="fastapi",server=~"$api",route!~"/health|unmatched"}'
# Hide obsolete snapshots if the node is down, collection failed, or timer stopped.
FRESH = '(podobank_business_collect_success == 1) and on(instance) (up{job="node"} == 1) and on(instance) (time()-podobank_business_collect_success_timestamp_seconds < 180)'
DB = 'podobank_db_records and on(instance) (' + FRESH + ')'
MONGO = 'podobank_mongo_events and on(instance) (' + FRESH + ')'
NAV = [('overview','전체 현황'), ('api','FastAPI'), ('storage','MongoDB·이벤트'), ('mariadb','MariaDB'), ('servers','서버'), ('nginx','Nginx'), ('haproxy','HAProxy'), ('logs','로그'), ('alloy','Alloy'), ('loki','Loki')]


def variables(business=True):
    result = [{'name':'api','label':'API 서버','type':'custom','query':'api-1,api-2','multi':True,'includeAll':True,'allValue':'.*','current':{'text':'All','value':'$__all'}}]
    if business:
        result.append({'name':'business','label':'업무','type':'custom','query':TYPES.replace('|',','),'multi':True,'includeAll':True,'allValue':TYPES,'current':{'text':'All','value':'$__all'}})
    result.append({'name':'request_id','label':'요청 ID 검색 (비우면 전체)','type':'textbox','query':'','current':{'text':'','value':''}})
    return {'list':result}


def board(uid, title):
    return {'uid':'podobank-'+uid,'title':'PodoBank / '+title,'schemaVersion':39,'version':1,'timezone':'Asia/Seoul','editable':True,'tags':['podobank','business'],'refresh':'30s','time':{'from':'now-1h','to':'now'},'panels':[], 'templating':variables(uid=='business')}


def panel(d,title,q,kind='timeseries',source=P,unit='short',w=12,h=7,description='',legend='{{server}}',instant=None):
    panels=d['panels']; y=max((p['gridPos']['y']+p['gridPos']['h'] for p in panels),default=0)
    if panels:
        last=panels[-1]['gridPos']
        if last['w']+last['x']+w<=24:y=last['y'];x=last['x']+last['w']
        else:x=0
    else:x=0
    p={'id':max([p['id'] for p in panels]+[999])+1,'title':title,'type':kind,'description':description,'gridPos':{'x':x,'y':y,'w':w,'h':h}}
    if kind=='text':p['options']={'mode':'markdown','content':q}
    else:
        p['datasource']=source
        instant = kind in ('stat','table') if instant is None else instant
        p['targets']=[{'refId':'A','expr':q,'legendFormat':legend,'instant':instant,'range':not instant,'queryType':'instant' if instant else 'range',**({'format':'table'} if kind=='table' else {})}]
        defaults={'unit':unit,'decimals':0 if unit=='short' else 1,'min':0,'noValue':'—','mappings':[{'type':'special','options':{'match':'null','result':{'text':'—','color':'gray'}}}],'color':{'mode':'palette-classic'}}
        p['fieldConfig']={'defaults':defaults,'overrides':[]}
        if kind=='stat':p['options']={'colorMode':'value','graphMode':'none','textMode':'value_and_name','reduceOptions':{'calcs':['lastNotNull'],'values':True},'text':{'valueSize':28,'titleSize':12}}
        elif kind=='logs':
            p['options']={'showTime':True,'showLabels':False,'wrapLogMessage':True,'enableLogDetails':True,'sortOrder':'Descending','dedupStrategy':'none'}
            p['targets'][0]['maxLines']=200
        elif kind=='table':
            p['options']={'showHeader':True,'cellHeight':'sm','sortBy':[{'displayName':'Value','desc':True}]}
            p['transformations']=[{'id':'organize','options':{
                'excludeByName':{k:True for k in ['Time','__name__','instance','job','server','store']},
                'renameByName':{'method':'메서드','route':'API 경로','status_code':'HTTP 코드','error_code':'오류 코드','event_type':'업무','outcome':'결과','reason':'사유','properties_result':'상환 결과','dataset':'저장 대상','kind':'구분','Value':'건수','Value #A':'건수'}}}]
            for field,values in [('구분',{'deposit':'입금','withdrawal':'출금','transfer_out':'송금 출금','transfer_in':'송금 입금','card_payment':'카드 결제','loan_disbursement':'대출 지급','loan_repayment':'대출 상환','pending':'심사 대기','repaying':'상환 중','rejected':'반려','repaid':'상환 완료','scheduled':'예정','paid':'납부','overdue':'연체'}),('결과',{'success':'성공','failure':'실패'}),('저장 대상',{'ledger_entries':'거래 원장','loan_applications':'대출 신청','loan_repayments':'대출 상환 회차'})]:
                p['fieldConfig']['overrides'].append({'matcher':{'id':'byName','options':field},'properties':[{'id':'mappings','value':[{'type':'value','options':{k:{'text':v} for k,v in values.items()}}]}]})
        else:
            defaults['custom']={'drawStyle':'line','lineWidth':2,'fillOpacity':5,'showPoints':'never','spanNulls':False}
            p['options']={'legend':{'displayMode':'table','placement':'bottom','calcs':['lastNotNull']},'tooltip':{'mode':'multi','sort':'desc'}}
    if title.startswith('DB 집계 성공 여부'):
        p['fieldConfig']['defaults']['color']={'mode':'thresholds'}
        p['fieldConfig']['defaults']['thresholds']={'mode':'absolute','steps':[{'color':'red','value':None},{'color':'green','value':1}]}
    if title.startswith('DB 마지막 성공 집계 경과'):
        p['fieldConfig']['defaults']['color']={'mode':'thresholds'}
        p['fieldConfig']['defaults']['thresholds']={'mode':'absolute','steps':[{'color':'green','value':None},{'color':'orange','value':120},{'color':'red','value':180}]}
    panels.append(p)
    return p


def note(d,text):panel(d,'읽는 방법',text,'text',w=24,h=5)



def operational_summary(d):
    """Keep the existing overview UID and service pages, independent of target IPs."""
    uid = d['uid']
    if uid == 'podobank-overview':
        d['title'] = 'PodoBank / 운영 요약'
        d['panels'] = []
        traffic = 'podobank_http_requests_total{job="fastapi",route!~"/health|unmatched"}'
        observed = 'sum(increase(podobank_http_requests_total{job="fastapi"}[$__range]))'
        total = '(sum(increase(' + traffic + '[$__range])) or (0 * ' + observed + '))'
        panel(d, 'API 요청 · 선택 기간', total, 'stat', w=6, h=4,
              description='Prometheus counter 증가량의 표본 추정치입니다. 헬스체크는 제외합니다.')
        for code, color in [('2', 'green'), ('4', 'orange'), ('5', 'red')]:
            filtered = traffic[:-1] + ',status_code=~"' + code + '.."}'
            q = 'sum(increase(' + filtered + '[$__range])) or (0 * ' + total + ')'
            item = panel(d, 'API ' + code + 'xx · 선택 기간', q, 'stat', w=6, h=4)
            item['fieldConfig']['defaults']['color'] = {'mode':'fixed','fixedColor':color}
        panel(d, 'API 요청률', '(sum(rate(' + traffic + '[$__rate_interval])) or (0 * sum(rate(podobank_http_requests_total{job="fastapi"}[$__rate_interval]))))', 'stat', unit='reqps', w=6, h=4)
        panel(d, 'API 응답 p95', '1000*histogram_quantile(0.95,sum by(le)(rate(podobank_http_request_duration_seconds_bucket{job="fastapi",route!~"/health|unmatched"}[$__rate_interval])))', 'stat', unit='ms', w=6, h=4)
        panel(d, '정상 API 백엔드 · 목표 2', 'sum(haproxy_server_status{job="haproxy",proxy="fastapi",state="UP"})', 'stat', w=6, h=4)
        item = panel(d, '수집 실패 대상', 'sum(1-up)', 'stat', w=6, h=4)
        item['fieldConfig']['defaults'].update(color={'mode':'thresholds'}, thresholds={'mode':'absolute','steps':[{'color':'green','value':None},{'color':'red','value':1}]})
        panel(d, 'HTTP 응답 추이', 'sum by(status_code)(rate(' + traffic + '[$__rate_interval]))', unit='reqps', legend='HTTP {{status_code}}', h=7)
        panel(d, '오류 API · 선택 기간', 'sum by(route,status_code)(increase(podobank_http_requests_total{job="fastapi",route!~"/health|unmatched",status_code=~"4..|5.."}[$__range])) > 0', 'table', h=7)
        for store, dataset, title in [('mariadb','ledger_entries','MariaDB 거래 원장'),('mariadb','card_payments','MariaDB 카드 결제'),('mongodb','events_bronze','MongoDB 이벤트'),('mongodb','card_payment_locations','MongoDB 카드 위치')]:
            selector = 'podobank_db_records{store="' + store + '",dataset="' + dataset + '"' + (',server!~".*replica"' if store=='mariadb' else '') + '}'
            panel(d, title, 'sum(' + selector + ' and on(instance) (' + FRESH + '))', 'stat', w=6, h=4, description='現在 저장된 누적 건수입니다. 2분 주기 읽기 전용 집계이며 집계 장애 시 수집 없음으로 표시합니다.'.replace('現在','현재'))
        panel(d, 'DB 적재 현황 · 현재 건수', 'sum by(store,dataset,kind)(podobank_db_records{server!~".*replica"} and on(instance) (' + FRESH + '))', 'table', w=12, h=9)
        panel(d, 'DB 저장 건수 추이', 'sum by(store,dataset)(podobank_db_records{server!~".*replica"} and on(instance) (' + FRESH + '))', w=12, h=9, legend='{{store}} · {{dataset}}')
        panel(d, 'DB 집계 경과', 'max by(store)(time()-podobank_business_collect_success_timestamp_seconds)', 'stat', unit='s', w=12, h=4, legend='{{store}}', description='180초 이상이면 집계 상태를 확인하세요.')
        panel(d, 'MariaDB 복제 지연', 'mysql_slave_status_seconds_behind_master{role="replica"}', 'stat', unit='s', w=12, h=4)
        panel(d, '서버별 CPU', '100*(1-avg by(server)(rate(node_cpu_seconds_total{job="node",mode="idle"}[$__rate_interval])))', unit='percent', h=8)
        panel(d, '서버별 메모리', '100*(1-node_memory_MemAvailable_bytes{job="node"}/node_memory_MemTotal_bytes{job="node"})', unit='percent', h=8)
    elif uid == 'podobank-api':
        # Financial outcomes remain in one compact table instead of six empty tiles.
        d['panels'] = [p for p in d['panels'] if not p['title'].endswith(' · 성공/실패') and p['title'] not in ['대출 심사 결과 · 승인 / 반려','대출 상환 결과 · 납부 / 연체 / 회복']]
    for item in d['panels']:
        defaults = item.get('fieldConfig', {}).get('defaults', {})
        defaults['noValue'] = '수집 없음' if item['datasource']['type'] == 'prometheus' else '기록 없음'
        defaults['mappings'] = [m for m in defaults.get('mappings', []) if m.get('type') != 'special']
        defaults['mappings'].append({'type':'special','options':{'match':'null','result':{'text':defaults['noValue'],'color':'gray'}}})
        if item['title'] == 'API 응답 p95':
            defaults['mappings'].append({'type':'special','options':{'match':'nan','result':{'text':'요청 없음','color':'gray'}}})
        if item['title'] in ['MariaDB 거래 원장','MariaDB 카드 결제','MongoDB 이벤트','MongoDB 카드 위치']:
            defaults.update(unit='none',decimals=0)
        if item['type'] == 'stat':
            item['gridPos']['h'] = 4
            item['options'].update(textMode='value', reduceOptions={'calcs':['lastNotNull'],'values':False}, text={'valueSize':30,'titleSize':14})
        if item['type'] == 'state-timeline':
            # Stable identity collapses old/new endpoint series after address changes.
            target = item['targets'][0]
            target.update(expr='max by(server,job)(' + ('up{job="node"}' if uid == 'podobank-servers' else 'up{job!="node"}') + ')', legendFormat='{{server}} · {{job}}')
            item['gridPos'].update(w=24,h=12)
            item['options'].update(showValue='never',rowHeight=0.8,mergeValues=True,perPage=10)
            item['description']='서버 역할·서비스 기준 상태입니다. 주소 변경 시 같은 역할의 응답 대상 중 하나 이상 정상일 때 UP으로 표시합니다.'
        for target in item.get('targets', []):
            legend = target.get('legendFormat','')
            if '{{instance}}' in legend:
                target['legendFormat'] = legend.replace(' {{instance}}','').replace('{{instance}}','')


def main():
    b=board('business','금융 업무 · 성공·실패·실제 저장')
    note(b,'**① 업무 로그 → ② 실제 DB 저장 → ③ 요청 ID 추적 순서로 확인하세요.**\n\n업무 성공 이벤트는 MariaDB 커밋 후 생성됩니다. Loki 도착이 MongoDB 저장 성공까지 보장하지는 않습니다. 아래 DB 값은 **현재 저장 건수(2분 주기)**이며 선택 기간의 요청 건수가 아닙니다. 빈 값은 0건과 다릅니다. API/업무 필터는 로그에 적용되며 DB 합계는 전체 서버·전체 업무 기준입니다. 요청 ID 검색은 하단 상세 로그에만 적용됩니다. 승인 완료와 대출 신청 성공도 구분합니다.')
    for event,label in [('deposit','입금'),('withdrawal','출금'),('transfer','송금'),('loan_application','대출 신청'),('loan_review','대출 심사'),('card_payment','카드 결제')]:
        panel(b,label+' · 성공/실패','sum by(outcome)(count_over_time('+E+' | event_type="'+event+'" [$__range]))','stat',L,w=4,h=5,legend='{{outcome}}',description='선택 기간에 Loki에 도착한 업무 이벤트 기록 수입니다. 기록 없음은 업무 미실행 또는 수집 상태를 확인하세요.')
    panel(b,'업무·결과별 이벤트 건수 · 선택 기간','sum by(event_type,outcome)(count_over_time('+E+' [$__range]))','table',L,w=12,h=8)
    panel(b,'실패 이유별 건수 · 선택 기간','sum by(event_type,reason)(count_over_time('+E+' | outcome="failure" [$__range]))','table',L,w=12,h=8,description='업무 실패 로그의 reason입니다. 인증·입력 검증 및 대출 심사 오류는 업무 이벤트 없이 HTTP 로그에만 남을 수 있습니다.')
    panel(b,'업무 성공 · 시간별','sum by(event_type)(rate('+E+' | outcome="success" [$__auto]))',source=L,unit='ops',legend='{{event_type}}')
    panel(b,'업무 실패 · 시간별','sum by(event_type,reason)(rate('+E+' | outcome="failure" [$__auto]))',source=L,unit='ops',legend='{{event_type}} · {{reason}}')
    panel(b,'대출 심사 결과 · 승인 / 반려','sum by(reason)(count_over_time({log_type="event",instance=~"$api"} | json | __error__="" | event_type="loan_review" [$__range]))','table',L,description='reason=rejected는 정상 처리된 반려입니다. outcome=success라고 대출 승인을 뜻하지 않습니다. 심사 API 오류는 같은 화면의 API 실패 표에서도 확인하세요.')
    panel(b,'대출 상환 결과 · 납부 / 연체 / 회복','sum by(outcome,reason,properties_result)(count_over_time({log_type="event",instance=~"$api"} | json | __error__="" | event_type="loan_repayment" [$__range]))','table',L)
    panel(b,'DB 집계 성공 여부 · 목표 3','podobank_business_collect_success','stat',w=12,h=4,legend='{{server}} · {{store}}')
    panel(b,'DB 마지막 성공 집계 경과 · 180초 미만','time()-podobank_business_collect_success_timestamp_seconds','stat',unit='s',w=12,h=4,legend='{{server}} · {{store}}')
    panel(b,'MariaDB 원장 · 종류별 실제 저장 건수','podobank_db_records{store="mariadb",dataset="ledger_entries",server!~".*replica"} and on(instance) ('+FRESH+')','table',description='송금 한 건은 transfer_out·transfer_in 두 원장 기록입니다. loan_disbursement는 대출 승인 후 실제 지급 기록입니다.')
    panel(b,'MariaDB 대출 · 현재 상태별 저장 건수','podobank_db_records{store="mariadb",dataset=~"loan_applications|loan_repayments",server!~".*replica"} and on(instance) ('+FRESH+')','table')
    panel(b,'MariaDB 카드 결제 · 실제 저장 건수','podobank_db_records{store="mariadb",dataset="card_payments",server!~".*replica"} and on(instance) ('+FRESH+')','stat',w=6,h=4)
    panel(b,'MongoDB 업무 이벤트 · 전체 문서 수','podobank_db_records{store="mongodb",dataset="events_bronze"} and on(instance) ('+FRESH+')','stat',w=9,h=4)
    panel(b,'MongoDB 카드 위치 · 전체 문서 수','podobank_db_records{store="mongodb",dataset="card_payment_locations"} and on(instance) ('+FRESH+')','stat',w=9,h=4)
    panel(b,'MongoDB 금융 업무 · 종류·결과별 실제 문서 수',MONGO,'table',w=24,h=9,description='로그 건수가 아닌 MongoDB 읽기 전용 집계입니다. 로그인 등 비금융 이벤트는 이 표에서 제외됩니다.')
    panel(b,'카드 결제 SQL 기록−MongoDB 위치 문서 차이','sum(podobank_db_records{store="mariadb",dataset="card_payments",server!~".*replica"} and on(instance) ('+FRESH+')) - sum(podobank_db_records{store="mongodb",dataset="card_payment_locations"} and on(instance) ('+FRESH+'))','stat',w=24,h=4,description='0이면 총 건수가 같습니다. 집계 시각 차이·별도 삭제 등도 차이를 만들 수 있어, 차이만으로 장애나 개별 문서의 일치를 확정하지 않습니다.')
    panel(b,'MariaDB Master−Replica 저장 건수 차이','sum by(dataset,kind)(podobank_db_records{store="mariadb",server!~".*replica"} and on(instance) ('+FRESH+')) - sum by(dataset,kind)(podobank_db_records{store="mariadb",server=~".*replica"} and on(instance) ('+FRESH+'))','table',description='0이면 집계 건수가 같습니다. 두 서버 집계 시각 차이로 일시적 차이가 날 수 있고, 내용 전체가 같은지를 증명하지는 않습니다.')
    panel(b,'로그·MongoDB 저장 오류 · 선택 기간','sum by(instance,message)(count_over_time({log_type="application"} | json | __error__="" | message=~"mongodb_write_failed|event_log_write_failed" [$__range]))','table',L,description='기록 없음은 오류가 관측되지 않았다는 뜻이며 저장 완전성의 증명은 아닙니다.')
    panel(b,'업무 상세 · 요청 ID 검색',E+' |= ${request_id:doublequote} | line_format "{{.event_type}} | {{.outcome}} | {{.reason}} | {{.instance}} | {{.duration_ms}}ms | request_id={{.request_id}} | event_id={{.event_id}}"','logs',L,w=24,h=10)
    panel(b,'동일 요청 API 결과',A+' |= ${request_id:doublequote} | line_format "{{.method}} {{.route}} | HTTP {{.status_code}} | {{.error_code}} | {{.duration_ms}}ms | {{.instance}} | request_id={{.request_id}}"','logs',L,w=24,h=9)

    h=board('http','HTTP·API · 요청과 실패 추적')
    note(h,'**정문 HTTP 실패와 금융 업무 실패는 다릅니다.** 4xx는 인증·입력·업무 조건 오류 등을 나누어 확인하고, 5xx는 오류 코드·요청 ID로 추적하세요. HTTP 499는 Nginx가 관측한 클라이언트 연결 종료입니다. Locust HTTP 0은 응답을 받지 못한 클라이언트 표기이므로 서버 대시보드만으로 전부 집계할 수 없습니다.\n\n상단 API 건수·경로별 표는 health·unmatched를 제외한 Loki 도착 기록 수입니다. Prometheus 표본 추정치와 구분하며 로그 누락·중복까지 검증하는 수치는 아닙니다. p95와 요청률은 Prometheus 기반입니다. 요청 ID 검색은 상세 로그에 적용됩니다.')
    activity=A+' | route!~"/health|unmatched"'
    for lower,upper,title in [(200,300,'API 2xx'),(400,500,'API 4xx'),(500,600,'API 5xx')]:
        q='sum(count_over_time('+activity+' | status_code >= '+str(lower)+' | status_code < '+str(upper)+' [$__range])) or (0 * sum(count_over_time('+activity+' [$__range])))'
        panel(h,title+' · 도착 로그 건수',q,'stat',L,w=8,h=4)
    panel(h,'어떤 요청인가 · 메서드·경로·코드','sum by(method,route,status_code)(count_over_time('+activity+' [$__range]))','table',L,w=24,h=9)
    panel(h,'실패 API · 경로·코드별 로그 건수','sum by(method,route,status_code,error_code)(count_over_time('+A+' | status_code >= 400 [$__range]))','table',L,w=24,h=8)
    panel(h,'업무별 API 지연 p95','1000*histogram_quantile(0.95,sum by(le,route)(rate(podobank_http_request_duration_seconds_bucket{job="fastapi",server=~"$api",route!~"/health|unmatched"}[$__rate_interval])))',unit='ms',legend='{{route}}')
    panel(h,'상태 코드별 요청률','sum by(status_code)(rate('+HTTP+'[$__rate_interval]))',unit='reqps',legend='{{status_code}}')
    # Nginx uses the combined access-log format on this deployment.
    panel(h,'Nginx HTTP 상태별 기록 · 선택 기간','sum by(status)(count_over_time('+N+' [$__range]))','table',L)
    panel(h,'Nginx 499 · 클라이언트 연결 종료','sum(count_over_time('+N+' | status=499 [$__range]))','stat',L,w=12,h=7)
    panel(h,'API 요청 상세 · 요청 ID 검색',A+' |= ${request_id:doublequote} | line_format "{{.method}} {{.route}} | HTTP {{.status_code}} | {{.error_code}} | {{.duration_ms}}ms | {{.instance}} | request_id={{.request_id}}"','logs',L,w=24,h=10)
    panel(h,'API 4xx·5xx 상세',A+' | status_code >= 400 |= ${request_id:doublequote} | line_format "{{.method}} {{.route}} | HTTP {{.status_code}} | {{.error_code}} | {{.duration_ms}}ms | {{.instance}} | request_id={{.request_id}}"','logs',L,w=24,h=10)
    panel(h,'Nginx 4xx·5xx 접근 로그',N+' | status >= 400','logs',L,w=24,h=8)
    # Financial and HTTP definitions are reusable panel groups, not separate dashboards.
    import copy
    def select(source, names):
        return [copy.deepcopy(p) for p in source['panels'] if p['title'] in names]
    def snapshot_panels(store, label, count):
        result=select(b,['DB 집계 성공 여부 · 목표 3','DB 마지막 성공 집계 경과 · 180초 미만'])
        result[0]['title']=label+' 집계 성공 여부 · 목표 '+str(count)
        result[0]['targets'][0]['expr']='podobank_business_collect_success{store="'+store+'"}'
        result[1]['title']=label+' 마지막 성공 집계 경과'
        result[1]['targets'][0]['expr']='time()-podobank_business_collect_success_timestamp_seconds{store="'+store+'"}'
        return result
    def pack(panels):
        x=y=row_height=0
        for index,p in enumerate(panels,1):
            w,h=p['gridPos']['w'],p['gridPos']['h']
            if x+w>24:x=0;y+=row_height;row_height=0
            p['id']=index;p['gridPos']={'x':x,'y':y,'w':w,'h':h}
            x+=w;row_height=max(row_height,h)
        return panels
    for path in ROOT.glob('*.json'):
        if path.stem in ('podobank-business','podobank-http'):
            path.unlink()  # Retired definitions are deliberately absent from deployment.
            continue
        d=json.loads(path.read_text())
        d['panels']=[p for p in d['panels'] if p['type']!='text']
        uid=d['uid']
        if uid=='podobank-api':
            base=select(d,['정상 API 수집 대상 · 목표 2','전체 요청률','서버별 처리 지연 p50 / p95 / p99','API별 요청률'])
            codes=select(h,['API 2xx · 도착 로그 건수','API 4xx · 도착 로그 건수','API 5xx · 도착 로그 건수'])
            for p in codes:p['gridPos']['w']=4
            d['panels']=base[:2]+codes+select(b,[label+' · 성공/실패' for label in ['입금','출금','송금','대출 신청','대출 심사','카드 결제']])
            d['panels']+=select(b,['업무·결과별 이벤트 건수 · 선택 기간','실패 이유별 건수 · 선택 기간','대출 심사 결과 · 승인 / 반려','대출 상환 결과 · 납부 / 연체 / 회복'])
            d['panels']+=base[2:]
            d['panels']+=select(h,['어떤 요청인가 · 메서드·경로·코드','실패 API · 경로·코드별 로그 건수','API 요청 상세 · 요청 ID 검색','API 4xx·5xx 상세'])
            d['panels']+=select(b,['업무 상세 · 요청 ID 검색'])
            d['templating']=variables()
            # Scope the retained HTTP rate/latency graphs to the API selector too.
            for p in d['panels']:
                if p['title'] in ['전체 요청률','서버별 처리 지연 p50 / p95 / p99','API별 요청률']:
                    for t in p.get('targets',[]):t['expr']=t['expr'].replace('job="fastapi"','job="fastapi",server=~"$api"') if 'server=~"$api"' not in t['expr'] else t['expr']
        elif uid=='podobank-mariadb':
            d['panels']=select(d,['DB 응답 정상 · 목표 2','복제 IO 스레드','복제 SQL 스레드','복제 지연','서버별 현재 DB 연결','쿼리 처리률','실행 중인 DB 스레드','느린 쿼리 증가량 · 선택 기간','MariaDB VM CPU','DB 연결 오류률'])+snapshot_panels('mariadb','MariaDB',2)+select(b,['MariaDB 원장 · 종류별 실제 저장 건수','MariaDB 대출 · 현재 상태별 저장 건수','MariaDB 카드 결제 · 실제 저장 건수','MariaDB Master−Replica 저장 건수 차이'])
        elif uid=='podobank-storage':
            d['panels']=select(d,['MongoDB 인증·응답','현재 연결','활성 연결','MongoDB 프로세스 메모리','MongoDB 연산률','MongoDB 연결 추이'])+snapshot_panels('mongodb','MongoDB',1)+select(b,['MongoDB 업무 이벤트 · 전체 문서 수','MongoDB 카드 위치 · 전체 문서 수','MongoDB 금융 업무 · 종류·결과별 실제 문서 수','카드 결제 SQL 기록−MongoDB 위치 문서 차이','로그·MongoDB 저장 오류 · 선택 기간','업무 상세 · 요청 ID 검색'])
            d['templating']=variables()
        elif uid=='podobank-nginx':
            additions=['Nginx HTTP 상태별 기록 · 선택 기간','Nginx 499 · 클라이언트 연결 종료','Nginx 4xx·5xx 접근 로그']
            d['panels']=[p for p in d['panels'] if p['title'] not in additions]+select(h,additions)
        if uid=='podobank-mariadb':
            order=['DB 응답 정상 · 목표 2','복제 IO 스레드','복제 SQL 스레드','복제 지연','MariaDB 집계 성공 여부 · 목표 2','MariaDB 마지막 성공 집계 경과','MariaDB 원장 · 종류별 실제 저장 건수','MariaDB 대출 · 현재 상태별 저장 건수','MariaDB 카드 결제 · 실제 저장 건수','MariaDB Master−Replica 저장 건수 차이','서버별 현재 DB 연결','쿼리 처리률','실행 중인 DB 스레드','느린 쿼리 증가량 · 선택 기간','MariaDB VM CPU','DB 연결 오류률']
            indexed={p['title']:p for p in d['panels']};d['panels']=[indexed[t] for t in order]
            indexed['MariaDB Master−Replica 저장 건수 차이']['gridPos']['w']=18
        elif uid=='podobank-storage':
            order=['MongoDB 인증·응답','현재 연결','활성 연결','MongoDB 프로세스 메모리','MongoDB 업무 이벤트 · 전체 문서 수','MongoDB 카드 위치 · 전체 문서 수','MongoDB 집계 성공 여부 · 목표 1','MongoDB 마지막 성공 집계 경과','MongoDB 금융 업무 · 종류·결과별 실제 문서 수','카드 결제 SQL 기록−MongoDB 위치 문서 차이','로그·MongoDB 저장 오류 · 선택 기간','업무 상세 · 요청 ID 검색','MongoDB 연결 추이','MongoDB 연산률']
            indexed={p['title']:p for p in d['panels']};d['panels']=[indexed[t] for t in order]
            for title in ['MongoDB 업무 이벤트 · 전체 문서 수','MongoDB 카드 위치 · 전체 문서 수']:indexed[title]['gridPos']['w']=12
            for title in ['로그·MongoDB 저장 오류 · 선택 기간','MongoDB 연산률']:indexed[title]['gridPos']['w']=24
        operational_summary(d)
        d['panels']=pack(d['panels'])
        d['links']=[{'type':'link','title':title,'url':'/d/podobank-'+slug,'keepTime':True,'targetBlank':False} for slug,title in NAV]
        path.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
