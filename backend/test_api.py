import os,tempfile
os.environ['DATABASE_URL']='sqlite:///'+tempfile.mktemp(suffix='.db')
os.environ['AUTOMATION_WORKER']='false'
from cryptography.fernet import Fernet
os.environ['SOCIAL_TOKEN_KEY']=Fernet.generate_key().decode()
os.environ['JWT_SECRET']='test-key-only-do-not-use-in-production'
from fastapi.testclient import TestClient
from main import app

def test_business_flow():
 with TestClient(app) as c:
  assert c.get('/api/health').status_code==200
  login=c.post('/api/auth/login',json={'email':'demo@sme.lk','password':'Demo@12345'})
  assert login.status_code==200,login.text
  h={'Authorization':'Bearer '+login.json()['access_token']}
  ps=c.get('/api/products',headers=h).json();p=ps[0]
  assert p['total_cost']==1150 and p['profit']==200
  a=c.post('/api/pricing/analyze/'+str(p['id']),headers=h,json={'margin':25}).json()
  assert a['strategies'][1]['price']==1533.33
  sale=c.post('/api/sales',headers=h,json={'items':[{'product_id':p['id'],'quantity':2}]})
  assert sale.status_code==200,sale.text
  assert sale.json()['profit']==400
  after=c.get('/api/products',headers=h).json()[0];assert after['stock']==p['stock']-2
  bad=c.post('/api/sales',headers=h,json={'items':[{'product_id':p['id'],'quantity':99999}]});assert bad.status_code==409
  assert c.get('/api/products',headers=h).json()[0]['stock']==after['stock']
  offer=c.post('/api/marketing/generate',headers=h,json={'product_id':p['id'],'discount':99}).json()
  assert not offer['offer']['safe'] and offer['offer']['profit']<0
  other=c.post('/api/auth/register',json={'email':'other@example.com','password':'Other@12345','name':'Other','business_name':'Other store'}).json()
  h2={'Authorization':'Bearer '+other['access_token']}
  assert c.get('/api/products',headers=h2).json()==[]
  assert c.put('/api/products/'+str(p['id']),headers=h2,json={k:v for k,v in p.items() if k not in ['id','created_at','total_cost','profit','margin']}).status_code==404
  assert c.post('/api/pricing/analyze/'+str(p['id']),headers=h2,json={}).status_code==404
  assert c.post('/api/sales',headers=h2,json={'items':[{'product_id':p['id'],'quantity':1}]}).status_code==404
  assert c.get('/api/analytics/overview',headers=h2).json()['actual']['revenue']==0
  assert c.get('/api/products').status_code in (401,403)
  assert c.post('/api/auth/login',json={'email':'demo@sme.lk','password':'wrongpass'}).status_code==401
  assert c.post('/api/products',headers=h,json={'name':'Invalid','category':'X','purchase_cost':-1,'selling_price':10,'stock':1}).status_code==422
  assert c.post('/api/ai/chat',headers=h,json={'message':'highest profit'}).status_code==200
