from datetime import datetime,timedelta,timezone
from fastapi.testclient import TestClient
from test_api import app


def seller(c):
 return {'Authorization':'Bearer '+c.post('/api/auth/login',json={'email':'demo@sme.lk','password':'Demo@12345','role':'seller'}).json()['access_token']}

def signup(c,tag):
 d={'email':tag+'@example.com','username':tag,'password':'Buyer@12345','name':'Test Buyer','phone':'0771234567','role':'buyer'}
 r=c.post('/api/auth/register',json=d);assert r.status_code==200,r.text
 return {'Authorization':'Bearer '+r.json()['access_token']},d

def test_buyer_signup_and_role_permissions():
 with TestClient(app) as c:
  h,d=signup(c,'rolebuyer')
  me=c.get('/api/auth/me',headers=h).json()
  assert me['role']=='buyer' and me['phone']=='0771234567' and me['username']=='rolebuyer'
  assert c.post('/api/auth/login',json={'username':'rolebuyer','password':d['password'],'role':'buyer'}).status_code==200
  assert c.post('/api/auth/login',json={'username':'rolebuyer','password':d['password'],'role':'seller'}).status_code==403
  assert c.get('/api/products',headers=h).status_code==403
  assert c.get('/api/store/orders',headers=h).status_code==403
  sh=seller(c)
  assert c.get('/api/buyer/catalog',headers=sh).status_code==403
  assert c.get('/api/buyer/catalog').status_code in (401,403)
  bad={**d,'email':'badphone@example.com','username':'badphone','phone':'12  -  '}
  assert c.post('/api/auth/register',json=bad).status_code==422
  bad={**d,'email':'badusername@example.com','username':'has spaces'}
  assert c.post('/api/auth/register',json=bad).status_code==422


def test_discount_purchase_completion_points_and_duplicate_protection():
 with TestClient(app) as c:
  sh=seller(c);bh,_=signup(c,'pointsbuyer')
  product={'name':'Reward Product','category':'Rewards','purchase_cost':100,'transportation_cost':0,'additional_expenses':0,'selling_price':250,'stock':10}
  p=c.post('/api/products',headers=sh,json=product).json()
  ends=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
  offer=c.post('/api/store/offers',headers=sh,json={'product_id':p['id'],'title':'20% special','discount_percent':20,'ends_at':ends})
  assert offer.status_code==200,offer.text
  listed=next(x for x in c.get('/api/buyer/catalog',headers=bh).json() if x['id']==p['id'])
  assert listed['price']==200 and listed['savings']==50 and listed['offer']['title']=='20% special'
  assert 'purchase_cost' not in listed and 'total_cost' not in listed
  data={'items':[{'product_id':p['id'],'quantity':3,'expected_price':200}],'idempotency_key':'points-order-12345678'}
  r=c.post('/api/buyer/checkout',headers=bh,json=data);assert r.status_code==200,r.text
  order=r.json();assert order['total']==600 and order['points_earned']==0 and order['pending_points']==6
  assert 'unit_cost' not in order['items'][0]
  again=c.post('/api/buyer/checkout',headers=bh,json=data).json();assert again['id']==order['id']
  stock=next(x for x in c.get('/api/products',headers=sh).json() if x['id']==p['id'])['stock'];assert stock==7
  assert c.get('/api/auth/me',headers=bh).json()['points']==0
  assert c.delete('/api/products/'+str(p['id']),headers=sh).status_code==409
  rows=c.get('/api/store/orders',headers=sh).json();assert next(x for x in rows if x['id']==order['id'])['buyer_phone']=='0771234567'
  completed=c.put('/api/store/orders/'+str(order['id'])+'/status',headers=sh,json={'status':'completed'})
  assert completed.status_code==200,completed.text
  assert completed.json()['points_earned']==6
  c.put('/api/store/orders/'+str(order['id'])+'/status',headers=sh,json={'status':'completed'})
  assert c.get('/api/auth/me',headers=bh).json()['points']==6
  sales=[x for x in c.get('/api/sales',headers=sh).json() if x.get('customer_order_id')==order['id']]
  assert len(sales)==1 and sales[0]['profit']==300
  assert c.post('/api/buyer/orders/'+str(order['id'])+'/cancel',headers=bh).status_code==409
  assert next(x for x in c.get('/api/products',headers=sh).json() if x['id']==p['id'])['stock']==7


def test_checkout_expired_price_oversell_and_cancel_isolation():
 with TestClient(app) as c:
  sh=seller(c);bh,_=signup(c,'cancelbuyer');other,_=signup(c,'otherbuyer')
  p=c.post('/api/products',headers=sh,json={'name':'Cancel Product','category':'Test','purchase_cost':50,'selling_price':299,'stock':2}).json()
  data={'items':[{'product_id':p['id'],'quantity':1,'expected_price':298}],'idempotency_key':'cancel-order-123456'}
  assert c.post('/api/buyer/checkout',headers=bh,json=data).status_code==409
  data['items'][0]['expected_price']=299;data['items'][0]['quantity']=3
  assert c.post('/api/buyer/checkout',headers=bh,json=data).status_code==409
  data['items'][0]['quantity']=1
  order=c.post('/api/buyer/checkout',headers=bh,json=data).json();assert order['pending_points']==2
  assert c.get('/api/buyer/orders',headers=other).json()==[]
  assert c.post('/api/buyer/orders/'+str(order['id'])+'/cancel',headers=other).status_code==404
  assert c.post('/api/buyer/orders/'+str(order['id'])+'/cancel',headers=bh).status_code==200
  c.post('/api/buyer/orders/'+str(order['id'])+'/cancel',headers=bh)
  assert c.get('/api/auth/me',headers=bh).json()['points']==0
  assert next(x for x in c.get('/api/products',headers=sh).json() if x['id']==p['id'])['stock']==2
  assert not [x for x in c.get('/api/sales',headers=sh).json() if x.get('customer_order_id')==order['id']]


def test_store_offer_tenant_and_below_cost_guards():
 with TestClient(app) as c:
  sh=seller(c)
  p=c.post('/api/products',headers=sh,json={'name':'Offer Guard','category':'Test','purchase_cost':90,'selling_price':100,'stock':10}).json()
  end=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
  body={'product_id':p['id'],'title':'Unsafe','discount_percent':50,'ends_at':end}
  assert c.post('/api/store/offers',headers=sh,json=body).status_code==422
  reg=c.post('/api/auth/register',json={'email':'other-store@example.com','password':'Seller@12345','name':'Other Seller','business_name':'Other Store'}).json()
  other={'Authorization':'Bearer '+reg['access_token']}
  assert c.post('/api/store/offers',headers=other,json=body).status_code==404
  assert c.get('/api/store/orders',headers=other).json()==[]
  safe={**body,'discount_percent':5,'title':'Safe special'}
  offer=c.post('/api/store/offers',headers=sh,json=safe).json()
  assert c.delete('/api/store/offers/'+str(offer['id']),headers=other).status_code==404
  assert c.delete('/api/store/offers/'+str(offer['id']),headers=sh).status_code==200
  assert c.delete('/api/products/'+str(p['id']),headers=sh).status_code==200
