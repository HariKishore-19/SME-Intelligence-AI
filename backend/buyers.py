"""Buyer storefront, explicit seller offers, cash-on-delivery orders and earned points."""
import json
from datetime import datetime,timezone,timedelta
from decimal import Decimal,ROUND_FLOOR,ROUND_HALF_UP
from typing import Literal
from fastapi import Depends,HTTPException
from pydantic import BaseModel,Field,model_validator
from sqlalchemy import ForeignKey,UniqueConstraint,Numeric,String,select,update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped,mapped_column,Session

UTC=timezone.utc

def now():return datetime.now(UTC).isoformat()
def dec(v):return Decimal(str(v)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)

class OfferIn(BaseModel):
 product_id:int
 title:str=Field(min_length=1,max_length=120)
 discount_percent:Decimal=Field(gt=0,le=90,max_digits=5,decimal_places=2)
 ends_at:datetime
 starts_at:datetime|None=None
 @model_validator(mode='after')
 def dates(self):
  self.starts_at=self.starts_at or datetime.now(UTC)
  if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:raise ValueError('Offer dates must include a timezone')
  self.starts_at=self.starts_at.astimezone(UTC);self.ends_at=self.ends_at.astimezone(UTC)
  if self.ends_at<=self.starts_at or self.ends_at<=datetime.now(UTC):raise ValueError('Offer end must be after its start and in the future')
  return self

class CheckoutLine(BaseModel):
 product_id:int
 quantity:int=Field(gt=0,le=10000)
 expected_price:Decimal=Field(gt=0,max_digits=12,decimal_places=2)

class CheckoutIn(BaseModel):
 items:list[CheckoutLine]=Field(min_length=1,max_length=100)
 idempotency_key:str=Field(min_length=16,max_length=100,pattern=r'^[a-zA-Z0-9_-]+$')

class OrderStatusIn(BaseModel):
 status:Literal['completed','cancelled']


def install(app,g):
 Base,User,Business,Record,engine=(g[k] for k in ('Base','User','Business','Record','engine'))
 owned,enrich,add=(g[k] for k in ('owned','enrich','add'))

 class Offer(Base):
  __tablename__='store_offers'
  id:Mapped[int]=mapped_column(primary_key=True)
  business_id:Mapped[int]=mapped_column(ForeignKey('businesses.id'),index=True)
  product_id:Mapped[int]=mapped_column(ForeignKey('records.id'),index=True)
  title:Mapped[str]
  discount_percent:Mapped[Decimal]=mapped_column(Numeric(5,2))
  starts_at:Mapped[str]
  ends_at:Mapped[str]
  active:Mapped[bool]=mapped_column(default=True)

 class Order(Base):
  __tablename__='customer_orders'
  __table_args__=(UniqueConstraint('buyer_id','idempotency_key'),)
  id:Mapped[int]=mapped_column(primary_key=True)
  buyer_id:Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
  business_id:Mapped[int]=mapped_column(ForeignKey('businesses.id'),index=True)
  idempotency_key:Mapped[str]=mapped_column(String(100))
  buyer_name:Mapped[str]
  buyer_phone:Mapped[str]
  business_name:Mapped[str]
  currency:Mapped[str]=mapped_column(default='LKR')
  total:Mapped[Decimal]=mapped_column(Numeric(14,2))
  status:Mapped[str]=mapped_column(default='pending',index=True)
  points_earned:Mapped[int]=mapped_column(default=0)
  items:Mapped[str]
  created_at:Mapped[str]=mapped_column(default=now)
  completed_at:Mapped[str]=mapped_column(default='')

 def buyer(u=Depends(g['current_user'])):
  if u.role!='buyer':raise HTTPException(403,'Buyer account required')
  return u

 def start_write(s):
  if engine.dialect.name=='sqlite':s.connection().exec_driver_sql('BEGIN IMMEDIATE')

 def offer_data(o):
  return dict(id=o.id,product_id=o.product_id,title=o.title,discount_percent=float(o.discount_percent),starts_at=o.starts_at,ends_at=o.ends_at,active=o.active)

 def price_for(s,p,business_id):
  regular=dec(p['selling_price']);unit_cost=dec(p['total_cost']);best=None;price=regular
  for offer in s.scalars(select(Offer).where(Offer.product_id==p['id'],Offer.business_id==business_id,Offer.active==True,Offer.starts_at<=now(),Offer.ends_at>now())):
   trial=dec(regular*(1-offer.discount_percent/100))
   if trial>0 and trial>=unit_cost and trial<price:best=offer;price=trial
  return price,offer_data(best) if best else None

 def public_order(o,seller=False):
  lines=json.loads(o.items)
  if not seller:lines=[{k:v for k,v in it.items() if k!='unit_cost'} for it in lines]
  result=dict(id=o.id,business_id=o.business_id,business_name=o.business_name,currency=o.currency,total=float(o.total),status=o.status,points_earned=o.points_earned,pending_points=int(o.total//100) if o.status=='pending' else 0,items=lines,created_at=o.created_at,completed_at=o.completed_at,payment_method='Cash on delivery / pay at collection')
  if seller:result.update(buyer_name=o.buyer_name,buyer_phone=o.buyer_phone)
  return result

 def pending_product(s,business_id,product_id):
  return any(any(i['product_id']==product_id for i in json.loads(o.items)) for o in s.scalars(select(Order).where(Order.business_id==business_id,Order.status=='pending')))

 @app.get('/api/buyer/catalog')
 def catalog(u=Depends(buyer),s:Session=Depends(g['db'])):
  out=[]
  for r,b in s.execute(select(Record,Business).join(Business,Record.business_id==Business.id).where(Record.kind=='product',Business.currency=='LKR')):
   p=enrich(r)
   if p['selling_price']<=0:continue
   price,offer=price_for(s,p,b.id)
   out.append(dict(id=p['id'],business_id=b.id,business_name=b.name,location=b.location,currency=b.currency,name=p['name'],category=p['category'],description=p.get('description',''),image_url=p.get('image_url',''),stock=p['stock'],regular_price=p['selling_price'],price=float(price),savings=float(dec(p['selling_price'])-price),offer=offer))
  return out

 @app.get('/api/buyer/orders')
 def buyer_orders(u=Depends(buyer),s:Session=Depends(g['db'])):
  return [public_order(o) for o in s.scalars(select(Order).where(Order.buyer_id==u.id).order_by(Order.id.desc()))]

 @app.post('/api/buyer/checkout')
 def checkout(d:CheckoutIn,u=Depends(buyer),s:Session=Depends(g['db'])):
  start_write(s)
  existing=s.scalar(select(Order).where(Order.buyer_id==u.id,Order.idempotency_key==d.idempotency_key).with_for_update())
  if existing:return public_order(existing)
  quantities={};expected={}
  for line in d.items:
   if line.product_id in expected and expected[line.product_id]!=line.expected_price:raise HTTPException(422,'Duplicate line has different expected prices')
   quantities[line.product_id]=quantities.get(line.product_id,0)+line.quantity;expected[line.product_id]=line.expected_price
  lines=[];total=Decimal(0);business=None
  for product_id,quantity in sorted(quantities.items()):
   r=s.scalar(select(Record).where(Record.id==product_id,Record.kind=='product').with_for_update())
   if not r:raise HTTPException(404,'Product no longer available; refresh the catalog')
   b=s.get(Business,r.business_id)
   if b.currency!='LKR':raise HTTPException(409,'Buyer purchases currently support LKR only')
   if business and business.id!=b.id:raise HTTPException(422,'Checkout one seller at a time')
   business=b;p=enrich(r)
   if quantity>p['stock']:raise HTTPException(409,'Insufficient stock for '+p['name'])
   price,offer=price_for(s,p,b.id)
   if price!=expected[product_id]:raise HTTPException(409,'Price or offer changed for '+p['name']+'. Refresh your cart before purchasing.')
   total+=price*quantity
   lines.append(dict(product_id=product_id,name=p['name'],quantity=quantity,unit_price=float(price),regular_price=p['selling_price'],unit_cost=p['total_cost'],offer_title=offer['title'] if offer else None,discount_percent=offer['discount_percent'] if offer else 0))
   raw=json.loads(r.data);raw['stock']-=quantity;r.data=json.dumps(raw)
  order=Order(buyer_id=u.id,business_id=business.id,idempotency_key=d.idempotency_key,buyer_name=u.name,buyer_phone=u.phone or '',business_name=business.name,total=total,items=json.dumps(lines),points_earned=0)
  s.add(order)
  try:s.commit()
  except IntegrityError:
   s.rollback();existing=s.scalar(select(Order).where(Order.buyer_id==u.id,Order.idempotency_key==d.idempotency_key))
   if existing:return public_order(existing)
   raise HTTPException(409,'Order conflict; refresh and retry')
  return public_order(order)

 def finish_order(s,o,status):
  if o.status==status:return
  if o.status!='pending':raise HTTPException(409,'Only pending orders can change status')
  items=json.loads(o.items)
  if status=='completed':
   o.points_earned=int((o.total/100).to_integral_value(rounding=ROUND_FLOOR))
   s.execute(update(User).where(User.id==o.buyer_id).values(points=User.points+o.points_earned))
   cost=sum(dec(i['unit_cost'])*i['quantity'] for i in items)
   b=s.get(Business,o.business_id)
   add(s,b,'sale',dict(items=items,total=float(o.total),cost=float(cost),profit=float(o.total-cost),is_demo=False,customer_order_id=o.id))
   o.completed_at=now()
  else:
   for line in sorted(items,key=lambda i:i['product_id']):
    r=s.scalar(select(Record).where(Record.id==line['product_id'],Record.business_id==o.business_id,Record.kind=='product').with_for_update())
    if r:
     p=json.loads(r.data);p['stock']+=line['quantity'];r.data=json.dumps(p)
  o.status=status

 @app.post('/api/buyer/orders/{order_id}/cancel')
 def cancel(order_id:int,u=Depends(buyer),s:Session=Depends(g['db'])):
  start_write(s)
  o=s.scalar(select(Order).where(Order.id==order_id,Order.buyer_id==u.id).with_for_update())
  if not o:raise HTTPException(404,'Order not found')
  finish_order(s,o,'cancelled');s.commit();return public_order(o)

 @app.get('/api/store/orders')
 def seller_orders(b=Depends(g['tenant']),s:Session=Depends(g['db'])):
  return [public_order(o,True) for o in s.scalars(select(Order).where(Order.business_id==b.id).order_by(Order.id.desc()))]

 @app.put('/api/store/orders/{order_id}/status')
 def set_order_status(order_id:int,d:OrderStatusIn,b=Depends(g['tenant']),s:Session=Depends(g['db'])):
  start_write(s)
  o=s.scalar(select(Order).where(Order.id==order_id,Order.business_id==b.id).with_for_update())
  if not o:raise HTTPException(404,'Order not found')
  finish_order(s,o,d.status);s.commit();return public_order(o,True)

 @app.get('/api/store/offers')
 def offers(b=Depends(g['tenant']),s:Session=Depends(g['db'])):
  return [offer_data(o) for o in s.scalars(select(Offer).where(Offer.business_id==b.id).order_by(Offer.id.desc()))]

 @app.post('/api/store/offers')
 def create_offer(d:OfferIn,b=Depends(g['tenant']),s:Session=Depends(g['db'])):
  p=enrich(owned(s,b,d.product_id,'product'))
  if b.currency!='LKR':raise HTTPException(409,'Buyer offers currently support LKR only')
  discounted=dec(dec(p['selling_price'])*(1-d.discount_percent/100))
  if discounted<=0 or discounted<dec(p['total_cost']):raise HTTPException(422,'This offer would sell below unit cost')
  o=Offer(business_id=b.id,product_id=d.product_id,title=d.title,discount_percent=d.discount_percent,starts_at=d.starts_at.isoformat(),ends_at=d.ends_at.isoformat())
  s.add(o);s.commit();return offer_data(o)

 @app.delete('/api/store/offers/{offer_id}')
 def deactivate_offer(offer_id:int,b=Depends(g['tenant']),s:Session=Depends(g['db'])):
  o=s.scalar(select(Offer).where(Offer.id==offer_id,Offer.business_id==b.id))
  if not o:raise HTTPException(404,'Offer not found')
  o.active=False;s.commit();return offer_data(o)

 def seed_demo():
  with g['DB'].begin() as s:
   if not s.scalar(select(User).where(User.email=='buyer-demo@sme.lk')):
    s.add(User(email='buyer-demo@sme.lk',name='Demo Shopper',username='demo_buyer',phone='+94770000000',password=g['passwords'].hash('Buyer@12345'),role='buyer',points=0))
   # A clearly titled demo offer makes the buyer flow reviewable without social credentials.
   demo=s.scalar(select(User).where(User.email=='demo@sme.lk'))
   b=s.scalar(select(Business).where(Business.user_id==demo.id)) if demo else None
   if b and not s.scalar(select(Offer).where(Offer.business_id==b.id)):
    product=next((r for r in s.scalars(select(Record).where(Record.business_id==b.id,Record.kind=='product')) if json.loads(r.data)['name']=='Tea Pack 500g'),None)
    if product:
     s.add(Offer(business_id=b.id,product_id=product.id,title='Demo tea special',discount_percent=Decimal('5'),starts_at=now(),ends_at=(datetime.now(UTC)+timedelta(days=7)).isoformat()))

 return dict(Offer=Offer,Order=Order,pending_product=pending_product,seed_demo=seed_demo)
