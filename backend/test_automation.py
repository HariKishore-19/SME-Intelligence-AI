import asyncio,json
import pytest
from fastapi.testclient import TestClient
from test_api import app
from main import automation,DB,Record,Business
from automation import candidate,ProviderError,UncertainError,SocialProvider
from sqlalchemy import select


def login(c):
 r=c.post('/api/auth/login',json={'email':'demo@sme.lk','password':'Demo@12345'})
 return {'Authorization':'Bearer '+r.json()['access_token']}

def test_discovery_requires_evidence_and_tenant_isolation(monkeypatch):
 monkeypatch.delenv('TAVILY_API_KEY',raising=False)
 with TestClient(app) as c:
  h=login(c)
  result=c.post('/api/automation/discover',headers=h,json={}).json()
  assert result['status']=='failed' and 'API key' in result['error']
  assert c.get('/api/automation',headers=h).json()['reports']==[]
  cfg=c.get('/api/automation',headers=h).json()['config'];cfg['marketplaces']=['web']
  c.put('/api/automation/config',headers=h,json=cfg)
  key='tvly-test-secret-not-live'
  assert c.put('/api/automation/connections',headers=h,json={'tavily_key':key}).status_code==200
  async def fake_search(p,country,token):
   assert token==key
   return [dict(title=p['name']+' supermarket',url='https://retailer.example/product',content='Price LKR 1,450.00 today'),dict(title='Different product',url='https://other.example/x',content='Rs. 999.00'),dict(title=p['name'],url='https://127.0.0.1/x',content='LKR 1.00')]
  monkeypatch.setattr(automation['search_provider'],'search',fake_search)
  p=c.get('/api/products',headers=h).json()[0]
  r=c.post('/api/automation/discover',headers=h,json={'product_id':p['id']});assert r.status_code==200,r.text
  assert r.json()['status']=='completed'
  report=c.get('/api/automation',headers=h).json()['reports'][0]
  assert report['average']==1450 and not report['verified']
  assert len(report['candidates'])==2 and report['candidates'][1]['price'] is None
  assert key not in c.get('/api/automation',headers=h).text
  accepted=c.post('/api/automation/reports/'+str(report['id'])+'/accept',headers=h,json={'candidate_index':0})
  assert accepted.status_code==200,accepted.text
  assert c.post('/api/automation/reports/'+str(report['id'])+'/accept',headers=h,json={'candidate_index':0}).json()['id']==accepted.json()['id']
  reg=c.post('/api/auth/register',json={'email':'isolated-auto@example.com','password':'Other@12345','name':'Other','business_name':'Isolated'}).json()
  other={'Authorization':'Bearer '+reg['access_token']}
  assert c.get('/api/automation',headers=other).json()['reports']==[]
  assert c.post('/api/automation/reports/'+str(report['id'])+'/accept',headers=other,json={'candidate_index':0}).status_code==404
  assert c.post('/api/automation/jobs/'+str(r.json()['id'])+'/run',headers=other).status_code==404
  assert c.post('/api/automation/discover',headers=other,json={'product_id':p['id']}).status_code==404


def test_candidate_rejects_ambiguous_prices_and_sizes():
 p={'name':'Brand Rice 5kg'}
 assert candidate(p,dict(title='Brand Rice 5 kg',url='https://store.example/x',content='Rs. 1200 Rs. 1400'))['price'] is None
 assert candidate(p,dict(title='Brand Rice 1kg',url='https://store.example/x',content='LKR 1200'))['price'] is None
 assert candidate(p,dict(title='Brand Rice 5 kg',url='https://store.example/x',content='LKR 1,200.00'))['price']==1200
 assert candidate(p,dict(title='Brand Rice 5kg',url='http://localhost/a',content='LKR 1200')) is None


def test_marketing_queue_dedup_and_financial_guards(monkeypatch):
 with TestClient(app) as c:
  h=login(c)
  product=dict(name='Agent Test Product',category='Test',purchase_cost=100,transportation_cost=0,additional_expenses=0,selling_price=200,stock=30,image_url='https://cdn.example/product.jpg')
  p=c.post('/api/products',headers=h,json=product).json()
  # Ensure deterministic best selection despite seeded inventory.
  cfg=c.get('/api/automation',headers=h).json()['config'];cfg.update(minimum_margin=40,max_discount=10,minimum_stock=20)
  assert c.put('/api/automation/config',headers=h,json=cfg).status_code==200
  run=c.post('/api/automation/marketing/run',headers=h).json();assert run['status']=='completed',run
  camp_id=run['payload']['campaign_id'];camp=c.get('/api/marketing/campaigns',headers=h).json()[0]
  assert camp['product_id']==p['id'] and camp['offer']['safe'] and camp['offer']['margin']>=40
  assert str(camp['offer']['price']) in camp['facebook']
  assert c.post('/api/automation/posts',headers=h,json={'campaign_id':camp_id,'platform':'facebook'}).status_code==409
  secret='meta-test-token-not-live'
  c.put('/api/automation/connections',headers=h,json={'facebook_page_id':'12345','facebook_token':secret,'instagram_account_id':'67890','instagram_token':secret})
  with DB() as s:
   states=s.scalars(select(automation['State'])).all()
   assert all(secret not in st.credentials for st in states)
  assert secret not in c.get('/api/automation',headers=h).text
  calls=[]
  async def publish(platform,connection,payload):
   calls.append((platform,payload));return {'status':'published','remote_id':'post-123'}
  monkeypatch.setattr(automation['social'],'publish',publish)
  queued=c.post('/api/automation/posts',headers=h,json={'campaign_id':camp_id,'platform':'facebook'}).json()
  duplicate=c.post('/api/automation/posts',headers=h,json={'campaign_id':camp_id,'platform':'facebook'}).json()
  assert queued['id']==duplicate['id']
  done=c.post('/api/automation/jobs/'+str(queued['id'])+'/run',headers=h);assert done.status_code==200,done.text
  assert done.json()['status']=='published'
  c.post('/api/automation/jobs/'+str(queued['id'])+'/run',headers=h)
  assert len(calls)==1
  # Costs changing after queuing prevent a post.
  q2=c.post('/api/automation/posts',headers=h,json={'campaign_id':camp_id,'platform':'instagram'}).json()
  product['purchase_cost']=190
  assert c.put('/api/products/'+str(p['id']),headers=h,json=product).status_code==200
  blocked=c.post('/api/automation/jobs/'+str(q2['id'])+'/run',headers=h).json()
  assert blocked['status']=='failed' and len(calls)==1
  assert c.post('/api/automation/posts',headers=h,json={'campaign_id':camp_id,'platform':'tiktok'}).status_code==422


def test_scheduler_and_cancellation(monkeypatch):
 with TestClient(app) as c:
  h=login(c)
  cfg=c.get('/api/automation',headers=h).json()['config'];cfg.update(search_enabled=True,marketing_enabled=False)
  c.put('/api/automation/config',headers=h,json=cfg)
  async def fail(*args):raise ProviderError('Provider returned HTTP 401. Check key.')
  monkeypatch.setattr(automation['search_provider'],'search',fail)
  asyncio.run(automation['tick']())
  a=c.get('/api/automation',headers=h).json();n=len(a['jobs'])
  assert any(j['status']=='failed' and '401' in j['error'] for j in a['jobs'])
  asyncio.run(automation['tick']())
  assert len(c.get('/api/automation',headers=h).json()['jobs'])==n
  cfg['search_enabled']=False;c.put('/api/automation/config',headers=h,json=cfg)
  c.delete('/api/automation/connections/facebook',headers=h)
  assert not c.get('/api/automation',headers=h).json()['connections']['facebook_connected']


def test_official_adapter_requests(monkeypatch):
 import automation as mod
 calls=[]
 async def request(method,url,token,**kwargs):
  calls.append((method,url,kwargs))
  if url.endswith('/feed'):return {'id':'fb-post'}
  if url.endswith('/media'):return {'id':'ig-container'}
  if url.endswith('/ig-container'):return {'status_code':'FINISHED'}
  if url.endswith('/media_publish'):return {'id':'ig-post'}
  return {'id':'123','name':'Example'}
 monkeypatch.setattr(mod,'request_json',request)
 conn={'facebook_page_id':'123','facebook_token':'token','instagram_account_id':'456','instagram_token':'token'}
 provider=SocialProvider()
 assert asyncio.run(provider.publish('facebook',conn,{'text':'Test'}))['remote_id']=='fb-post'
 assert asyncio.run(provider.publish('instagram',conn,{'text':'Caption','image_url':'https://cdn.example/a.jpg'}))['status']=='processing'
 assert asyncio.run(provider.finish_instagram(conn,'ig-container'))['remote_id']=='ig-post'
 assert calls[-1][1].endswith('/456/media_publish')


def test_uncertain_publish_never_automatically_retries(monkeypatch):
 with TestClient(app) as c:
  h=login(c)
  c.put('/api/automation/connections',headers=h,json={'facebook_page_id':'123','facebook_token':'test-token'})
  p=c.post('/api/products',headers=h,json=dict(name='Queue Test',category='Test',purchase_cost=10,selling_price=100,stock=100)).json()
  camp=c.post('/api/marketing/generate',headers=h,json={'product_id':p['id'],'discount':0}).json()
  j=c.post('/api/automation/posts',headers=h,json={'campaign_id':camp['id'],'platform':'facebook'}).json()
  calls=[]
  async def uncertain(*args):calls.append(1);raise UncertainError('Provider connection interrupted. Check the account before retrying a post.')
  monkeypatch.setattr(automation['social'],'publish',uncertain)
  result=c.post('/api/automation/jobs/'+str(j['id'])+'/run',headers=h).json()
  assert result['status']=='unknown'
  c.post('/api/automation/jobs/'+str(j['id'])+'/run',headers=h)
  assert len(calls)==1
  # Future scheduled posts do not run early and can be cancelled.
  from datetime import datetime,timedelta,timezone
  future=(datetime.now(timezone.utc)+timedelta(hours=4)).isoformat()
  camp2=c.post('/api/marketing/generate',headers=h,json={'product_id':p['id'],'discount':0}).json()
  j2=c.post('/api/automation/posts',headers=h,json={'campaign_id':camp2['id'],'platform':'facebook','scheduled_at':future}).json()
  assert c.post('/api/automation/jobs/'+str(j2['id'])+'/run',headers=h).json()['status']=='queued'
  assert len(calls)==1
  assert c.delete('/api/automation/jobs/'+str(j2['id']),headers=h).status_code==200
  assert c.post('/api/automation/jobs/'+str(j2['id'])+'/run',headers=h).json()['status']=='cancelled'


def test_marketplace_source_filtering(monkeypatch):
 import automation as mod
 from automation import SearchProvider
 calls=[]
 async def fake_request(method,url,token,**kwargs):
  calls.append(kwargs['body'])
  return {'results':[
   {'title':'Brand Tea 500g','url':'https://www.daraz.lk/products/tea.html','content':'LKR 900'},
   {'title':'Brand Tea 500g','url':'https://www.ebay.com/itm/123','content':'USD 12.50'},
   {'title':'Brand Tea 500g','url':'https://daraz.lk.attacker.example/x','content':'LKR 1'},
  ]}
 monkeypatch.setattr(mod,'request_json',fake_request)
 p={'name':'Brand Tea 500g','_marketplaces':['daraz']}
 found=asyncio.run(SearchProvider().search(p,'Sri Lanka','dummy'))
 assert len(found)==1 and found[0]['url'].startswith('https://www.daraz.lk/')
 assert calls[0]['include_domains']==['daraz.lk']
 assert candidate(p,found[0])['platform']=='daraz'
 e=candidate(p,{'title':'Brand Tea 500g','url':'https://www.ebay.com/itm/123','content':'USD 12.50'})
 assert e['listing_currency']=='USD' and e['price']==12.5
 unknown=candidate(p,{'title':'Brand Tea 500g','url':'https://www.ebay.com/itm/123','content':'$12.50'})
 assert unknown['price'] is None # A bare dollar sign does not prove which dollar currency applies.


def test_ebay_adapter_and_currency_separation(monkeypatch):
 import marketplaces as mod
 import httpx
 original=httpx.AsyncClient
 seen=[]
 def respond(request):
  seen.append(request)
  assert request.headers['X-EBAY-C-MARKETPLACE-ID']=='EBAY_US'
  assert request.headers['Authorization']=='Bearer ebay-dummy'
  return httpx.Response(200,json={'itemSummaries':[{
   'itemId':'v1|123|0','title':'Brand Tea 500g','itemWebUrl':'https://www.ebay.com/itm/123',
   'price':{'value':'12.50','currency':'USD'},'seller':{'username':'tea-seller','feedbackPercentage':'99.2','feedbackScore':100},
   'image':{'imageUrl':'https://i.ebayimg.com/test.jpg'},'condition':'New','itemLocation':{'country':'US'},
   'shippingOptions':[{'shippingCost':{'value':'3.00','currency':'USD'}}]
  }]})
 def client(**kwargs):return original(**kwargs,transport=httpx.MockTransport(respond))
 monkeypatch.setattr(mod.httpx,'AsyncClient',client)
 results=asyncio.run(mod.EbayProvider().search('Brand Tea 500g','ebay-dummy'))
 hit=candidate({'name':'Brand Tea 500g'},results[0])
 assert hit['seller']=='tea-seller' and hit['listing_price']==12.5 and hit['source']=='eBay Browse API'
 assert hit['shipping_price']['value']=='3.00' and len(seen)==1
 with TestClient(app) as c:
  h=login(c)
  p=c.post('/api/products',headers=h,json=dict(name='Brand Tea 500g',category='Test',purchase_cost=500,selling_price=900,stock=10)).json()
  async def fake(*args):return results
  monkeypatch.setattr(automation['search_provider'],'search',fake)
  result=c.post('/api/automation/discover',headers=h,json={'product_id':p['id']}).json()
  assert result['status']=='completed'
  report=c.get('/api/automation',headers=h).json()['reports'][0]
  assert report['average'] is None and report['comparable_count']==0
  assert report['candidates'][0]['listing_price']==12.5
  assert c.post('/api/automation/reports/'+str(report['id'])+'/accept',headers=h,json={'candidate_index':0}).status_code==409


def test_single_marketplace_buttons_override_schedule_and_exclude_other_sites(monkeypatch):
 with TestClient(app) as c:
  h=login(c)
  c.put('/api/automation/connections',headers=h,json={'tavily_key':'dummy-search'})
  p=c.post('/api/products',headers=h,json=dict(name='Brand Rice 5kg',category='Food',purchase_cost=1100,transportation_cost=50,additional_expenses=0,selling_price=1350,stock=20)).json()
  cfg=c.get('/api/automation',headers=h).json()['config'];cfg['marketplaces']=['web'];c.put('/api/automation/config',headers=h,json=cfg)
  calls=[]
  async def fake(product,country,key):
   calls.append(product['_marketplaces'])
   return [dict(title='Brand Rice 5kg',url='https://www.daraz.lk/products/rice.html',content='LKR 1400'),dict(title='Brand Rice 5kg',url='https://www.ebay.com/itm/123',content='USD 15')]
  monkeypatch.setattr(automation['search_provider'],'search',fake)
  daraz=c.post('/api/automation/compare',headers=h,json={'product_id':p['id'],'marketplace':'daraz'})
  assert daraz.status_code==200,daraz.text
  d=daraz.json()['report']
  assert d['marketplaces']==['daraz'] and len(d['candidates'])==1
  assert d['candidates'][0]['platform']=='daraz' and d['average']==1400
  assert d['analysis']['difference_from_average']==-50 and d['analysis']['your_profit']==200
  assert d['analysis']['position']=='Below all observed prices'
  ebay=c.post('/api/automation/compare',headers=h,json={'product_id':p['id'],'marketplace':'ebay'})
  assert ebay.status_code==200,ebay.text
  e=ebay.json()['report'];assert e['marketplaces']==['ebay'] and len(e['candidates'])==1
  assert e['candidates'][0]['platform']=='ebay' and e['average'] is None
  assert calls==[['daraz'],['ebay']]
  assert c.get('/api/automation',headers=h).json()['config']['marketplaces']==['web']
  assert c.post('/api/automation/compare',headers=h,json={'product_id':p['id'],'marketplace':'amazon'}).status_code==422
  assert c.post('/api/automation/compare',headers=h,json={'product_id':999999,'marketplace':'daraz'}).status_code==404
