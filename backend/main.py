import os, json, secrets, statistics, asyncio, contextlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from contextlib import asynccontextmanager
from typing import Annotated, Literal
import jwt, httpx
from pwdlib import PasswordHash
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import create_engine, ForeignKey, String, select, event, UniqueConstraint, inspect, text, or_
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session
try:
 from dotenv import load_dotenv
 load_dotenv()
except ImportError: pass
engine=create_engine(os.getenv('DATABASE_URL','sqlite:///./sme.db'),connect_args={'check_same_thread':False} if os.getenv('DATABASE_URL','sqlite:').startswith('sqlite') else {})
if engine.dialect.name=='sqlite':
 @event.listens_for(engine,'connect')
 def pragma(db,_): db.execute('PRAGMA foreign_keys=ON')
DB=sessionmaker(engine,expire_on_commit=False)
class Base(DeclarativeBase): pass
class User(Base):
 __tablename__='users'
 id:Mapped[int]=mapped_column(primary_key=True)
 email:Mapped[str]=mapped_column(String(255),unique=True)
 name:Mapped[str]
 password:Mapped[str]
 role:Mapped[str]=mapped_column(String(20),default='seller')
 username:Mapped[str|None]=mapped_column(String(100),unique=True,nullable=True)
 phone:Mapped[str|None]=mapped_column(String(30),nullable=True)
 points:Mapped[int]=mapped_column(default=0)
class Business(Base):
 __tablename__='businesses'
 id:Mapped[int]=mapped_column(primary_key=True)
 user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),unique=True)
 name:Mapped[str]; category:Mapped[str]; location:Mapped[str]; currency:Mapped[str]=mapped_column(default='LKR')
class Record(Base):
 __tablename__='records'
 id:Mapped[int]=mapped_column(primary_key=True)
 business_id:Mapped[int]=mapped_column(ForeignKey('businesses.id'),index=True)
 kind:Mapped[str]=mapped_column(index=True)
 data:Mapped[str]
 created_at:Mapped[str]=mapped_column(default=lambda:datetime.now(timezone.utc).isoformat())
# Business-owned collections use one indexed relational record table; typed payloads are validated at the API boundary.
passwords=PasswordHash.recommended(); secret=os.getenv('JWT_SECRET') or secrets.token_hex(32)
def money(v): return float(Decimal(str(v)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP))
def cost(p): return money(sum(Decimal(str(p.get(k,0))) for k in ['purchase_cost','transportation_cost','additional_expenses']))
def enrich(r):
 d=json.loads(r.data); d.update(id=r.id,created_at=r.created_at)
 if r.kind=='product':
  c=cost(d); profit=money(Decimal(str(d['selling_price']))-Decimal(str(c))); d.update(total_cost=c,profit=profit,margin=money(profit/d['selling_price']*100) if d['selling_price'] else 0)
 return d
class ProductIn(BaseModel):
 name:str=Field(min_length=1,max_length=150); category:str=Field(min_length=1,max_length=100)
 description:str=''; image_url:str=''
 purchase_cost:Decimal=Field(ge=0,max_digits=12,decimal_places=2); transportation_cost:Decimal=Field(default=0,ge=0,max_digits=12,decimal_places=2)
 additional_expenses:Decimal=Field(default=0,ge=0,max_digits=12,decimal_places=2); selling_price:Decimal=Field(gt=0,max_digits=12,decimal_places=2)
 stock:int=Field(ge=0)
class Auth(BaseModel):
 email:str=Field(default='',max_length=255)
 username:str=Field(default='',max_length=255)
 password:str=Field(min_length=8,max_length=128)
 role:Literal['seller','buyer']='seller'
class Register(Auth):
 name:str=Field(min_length=1,max_length=150)
 business_name:str=Field(default='',max_length=150)
 phone:str=Field(default='',max_length=30)
class BusinessIn(BaseModel):
 name:str=Field(min_length=1); category:str; location:str; currency:str=Field(pattern='^[A-Z]{3}$')
class CompetitorIn(BaseModel):
 name:str=Field(min_length=1); location:str=''
class PriceIn(BaseModel):
 product_id:int; competitor_id:int; price:Decimal=Field(gt=0,max_digits=12,decimal_places=2)
class SaleLine(BaseModel):
 product_id:int; quantity:int=Field(gt=0,le=100000)
class SaleIn(BaseModel):
 items:list[SaleLine]=Field(min_length=1,max_length=100)
class PricingIn(BaseModel):
 margin:float=Field(default=25,gt=0,lt=95)
class MarketingIn(BaseModel):
 product_id:int; objective:str='Increase sales'; discount:float=Field(default=10,ge=0,le=100)
class ChatIn(BaseModel):
 message:str=Field(min_length=1,max_length=2000)
class ExpenseIn(BaseModel):
 description:str=Field(min_length=1); amount:Decimal=Field(gt=0,max_digits=12,decimal_places=2)
def db():
 with DB() as s: yield s
S=Annotated[Session,Depends(db)]
auth=HTTPBearer()
def current_user(s:S,cred:Annotated[HTTPAuthorizationCredentials,Depends(auth)]):
 try: uid=int(jwt.decode(cred.credentials,secret,algorithms=['HS256'])['sub'])
 except Exception: raise HTTPException(401,'Invalid or expired login')
 u=s.get(User,uid)
 if not u:raise HTTPException(401,'Account not found')
 return u
U=Annotated[User,Depends(current_user)]
def tenant(s:S,u:U):
 if u.role!='seller':raise HTTPException(403,'Seller account required')
 b=s.scalar(select(Business).where(Business.user_id==u.id))
 if not b:raise HTTPException(403,'Seller business not found')
 return b
T=Annotated[Business,Depends(tenant)]
def records(s,b,k): return s.scalars(select(Record).where(Record.business_id==b.id,Record.kind==k).order_by(Record.id)).all()
def owned(s,b,i,k):
 r=s.scalar(select(Record).where(Record.id==i,Record.business_id==b.id,Record.kind==k))
 if not r: raise HTTPException(404,'Record not found')
 return r
def add(s,b,k,d):
 r=Record(business_id=b.id,kind=k,data=json.dumps(d,default=float)); s.add(r); s.flush(); return r
def token(u): return {'access_token':jwt.encode({'sub':str(u.id),'exp':datetime.now(timezone.utc)+timedelta(hours=12)},secret,algorithm='HS256'),'token_type':'bearer','role':u.role}
def seed():
 with DB.begin() as s:
  if s.scalar(select(User).where(User.email=='demo@sme.lk')): return
  u=User(email='demo@sme.lk',name='Nimal Perera',password=passwords.hash('Demo@12345')); s.add(u); s.flush()
  b=Business(user_id=u.id,name='Ceylon Retail Store',category='Retail & groceries',location='Vavuniya',currency='LKR');s.add(b);s.flush()
  for name,cat,c,t,p,st in [('Rice 5kg','Essentials',1100,50,1350,80),('Coconut Oil 1L','Essentials',650,30,850,35),('Tea Pack 500g','Beverages',550,25,750,60),('Sugar 1kg','Essentials',220,15,280,8)]:
   r=add(s,b,'product',dict(name=name,category=cat,purchase_cost=c,transportation_cost=t,additional_expenses=0,selling_price=p,stock=st,description='Quality Sri Lankan household staple',image_url=''))
   co=add(s,b,'competitor',dict(name='Local Market — '+name,location='Vavuniya'))
   add(s,b,'price',dict(product_id=r.id,competitor_id=co.id,price=money(p*1.04),source='Seeded demo'))
   for day in range(14):
    q=(day%4)+1; total=p*q; cr=add(s,b,'sale',dict(items=[dict(product_id=r.id,name=name,quantity=q,unit_price=p,unit_cost=c+t)],total=total,cost=(c+t)*q,profit=(p-c-t)*q,is_demo=True)); cr.created_at=(datetime.now(timezone.utc)-timedelta(days=day)).isoformat()
@asynccontextmanager
async def lifespan(app):
 Base.metadata.create_all(engine)
 # Non-destructive upgrade for databases created before buyer accounts were introduced.
 user_columns={c['name'] for c in inspect(engine).get_columns('users')}
 with engine.begin() as connection:
  for name,definition in [('role',"VARCHAR(20) NOT NULL DEFAULT 'seller'"),('username','VARCHAR(100)'),('phone','VARCHAR(30)'),('points','INTEGER NOT NULL DEFAULT 0')]:
   if name not in user_columns:connection.execute(text(f'ALTER TABLE users ADD COLUMN {name} {definition}'))
  connection.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)'))
 if os.getenv('SEED_DEMO','true').lower()=='true':
  seed();buyer_module['seed_demo']()
 task=None
 if os.getenv('AUTOMATION_WORKER','true').lower()=='true':
  task=asyncio.create_task(automation['worker']())
 try:
  yield
 finally:
  if task:
   task.cancel()
   with contextlib.suppress(asyncio.CancelledError):await task
app=FastAPI(title='SME Intelligence AI',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=os.getenv('CORS_ORIGINS','http://localhost:5173,http://127.0.0.1:5173').split(','),allow_methods=['*'],allow_headers=['*'])
@app.get('/api/health')
def health():return {'status':'ok'}
@app.post('/api/auth/register')
def register(d:Register,s:S):
 import re
 email=d.email.strip().lower();username=d.username.strip().lower()
 if not email or '@' not in email:raise HTTPException(422,'Valid email required')
 if username and not re.fullmatch(r'[a-z0-9_.-]{3,40}',username):raise HTTPException(422,'Username must be 3–40 letters, numbers, dots, underscores or hyphens')
 if s.scalar(select(User).where(User.email==email)):raise HTTPException(409,'Email already registered')
 if username and s.scalar(select(User).where(User.username==username)):raise HTTPException(409,'Username already registered')
 phone=d.phone.strip()
 if d.role=='buyer':
  if not username:raise HTTPException(422,'Buyer username is required')
  phone=re.sub(r'[ -]','',phone)
  if not re.fullmatch(r'\+?[0-9]{8,15}',phone):raise HTTPException(422,'Enter a valid contact number (8–20 digits, optional +, spaces or hyphens)')
 elif not d.business_name.strip():raise HTTPException(422,'Business name is required for sellers')
 u=User(email=email,name=d.name,password=passwords.hash(d.password),role=d.role,username=username or None,phone=phone or None,points=0)
 s.add(u)
 try:
  s.flush()
  if d.role=='seller':s.add(Business(user_id=u.id,name=d.business_name,category='Retail',location='',currency='LKR'))
  s.commit()
 except Exception as e:
  s.rollback()
  from sqlalchemy.exc import IntegrityError
  if isinstance(e,IntegrityError):raise HTTPException(409,'Email or username already registered')
  raise
 return token(u)
@app.post('/api/auth/login')
def login(d:Auth,s:S):
 identity=(d.username or d.email).strip().lower()
 u=s.scalar(select(User).where(or_(User.email==identity,User.username==identity))) if identity else None
 if not u or not passwords.verify(d.password,u.password):raise HTTPException(401,'Incorrect username/email or password')
 if u.role!=d.role:raise HTTPException(403,'Choose '+u.role.title()+' on the login screen for this account')
 return token(u)
@app.get('/api/auth/me')
def me(u:U,s:S):
 b=s.scalar(select(Business).where(Business.user_id==u.id)) if u.role=='seller' else None
 return dict(id=u.id,name=u.name,email=u.email,username=u.username,phone=u.phone,role=u.role,points=u.points,business=b.name if b else None)
@app.get('/api/business')
def business(b:T):return {k:getattr(b,k) for k in ['name','category','location','currency']}
@app.put('/api/business')
def update_business(d:BusinessIn,b:T,s:S):
 for k,v in d.model_dump().items():setattr(b,k,v)
 s.commit();return business(b)
@app.get('/api/products')
def products(b:T,s:S):return [enrich(r) for r in records(s,b,'product')]
@app.post('/api/products')
def create_product(d:ProductIn,b:T,s:S):
 r=add(s,b,'product',d.model_dump());s.commit();return enrich(r)
@app.put('/api/products/{i}')
def update_product(i:int,d:ProductIn,b:T,s:S):
 r=owned(s,b,i,'product');r.data=json.dumps(d.model_dump(),default=float);s.commit();return enrich(r)
@app.delete('/api/products/{i}')
def delete_product(i:int,b:T,s:S):
 r=owned(s,b,i,'product')
 if buyer_module['pending_product'](s,b.id,i):raise HTTPException(409,'This product has a pending buyer order; complete or cancel the order before deleting it')
 for offer in s.scalars(select(buyer_module['Offer']).where(buyer_module['Offer'].product_id==i,buyer_module['Offer'].business_id==b.id)):s.delete(offer)
 s.flush()
 for price in records(s,b,'price'):
  if json.loads(price.data)['product_id']==i:s.delete(price)
 s.delete(r);s.commit();return {'deleted':True}
@app.get('/api/competitors')
def competitors(b:T,s:S):return dict(competitors=[enrich(r) for r in records(s,b,'competitor')],prices=[enrich(r) for r in records(s,b,'price')])
@app.post('/api/competitors')
def create_competitor(d:CompetitorIn,b:T,s:S):
 r=add(s,b,'competitor',d.model_dump());s.commit();return enrich(r)
@app.post('/api/competitors/prices')
def create_price(d:PriceIn,b:T,s:S):
 owned(s,b,d.product_id,'product');owned(s,b,d.competitor_id,'competitor');r=add(s,b,'price',dict(**d.model_dump(),source='Manually entered'));s.commit();return enrich(r)
@app.post('/api/pricing/analyze/{i}')
def pricing(i:int,d:PricingIn,b:T,s:S):
 p=enrich(owned(s,b,i,'product'));c=p['total_cost'];latest={}
 for r in records(s,b,'price'):
  observation=json.loads(r.data)
  if observation['product_id']==i:latest[observation['competitor_id']]=observation['price']
 prices=list(latest.values());avg=statistics.mean(prices) if prices else None
 target=money(c/(1-d.margin/100)); strategies=[]
 for name,v in [('Competitive',max(c+.01,avg*.98) if avg else target),('Target margin',target),('Market penetration',max(c+.01,(min(prices)*.95 if prices else target*.95)))]:
  v=money(v);strategies.append(dict(strategy=name,price=v,profit=money(v-c),margin=money((v-c)/v*100)))
 return dict(product=p['name'],minimum_profitable_price=money(c+.01),competitor_average=money(avg) if avg else None,competitor_low=min(prices) if prices else None,competitor_high=max(prices) if prices else None,strategies=strategies,explanation='Prices are calculated from your unit costs and entered competitor observations. The target-margin option meets your chosen margin; market demand is not predicted.')
@app.get('/api/sales')
def sales(b:T,s:S):return [enrich(r) for r in records(s,b,'sale')][::-1]
@app.post('/api/sales')
def sale(d:SaleIn,b:T,s:S):
 quantities={}
 for line in d.items:quantities[line.product_id]=quantities.get(line.product_id,0)+line.quantity
 items=[];total=Decimal(0);expense=Decimal(0)
 # Lock inventory rows in consistent order on PostgreSQL; SQLite obtains a write lock before reading.
 if engine.dialect.name=='sqlite':s.connection().exec_driver_sql('BEGIN IMMEDIATE')
 for i,q in sorted(quantities.items()):
  r=s.scalar(select(Record).where(Record.id==i,Record.business_id==b.id,Record.kind=='product').with_for_update())
  if not r:raise HTTPException(404,'Product not found')
  p=enrich(r)
  if q>p['stock']:raise HTTPException(409,'Insufficient stock: '+p['name'])
  unit=Decimal(str(p['selling_price']));c=Decimal(str(p['total_cost']));total+=unit*q;expense+=c*q
  items.append(dict(product_id=i,name=p['name'],quantity=q,unit_price=float(unit),unit_cost=float(c)))
  raw=json.loads(r.data);raw['stock']-=q;r.data=json.dumps(raw)
 r=add(s,b,'sale',dict(items=items,total=money(total),cost=money(expense),profit=money(total-expense),is_demo=False));s.commit();return enrich(r)
@app.get('/api/expenses')
def expenses(b:T,s:S):return [enrich(r) for r in records(s,b,'expense')]
@app.post('/api/expenses')
def expense(d:ExpenseIn,b:T,s:S):
 r=add(s,b,'expense',d.model_dump());s.commit();return enrich(r)
def analytics(b,s):
 ps=products(b,s);ss=sales(b,s);ex=expenses(b,s);actual=[x for x in ss if not x.get('is_demo')];demo=[x for x in ss if x.get('is_demo')]
 def totals(rows):
  rev=money(sum(x['total'] for x in rows));c=money(sum(x['cost'] for x in rows));e=money(sum(x['amount'] for x in ex)) if rows is actual else 0
  return dict(revenue=rev,expenses=money(c+e),profit=money(rev-c-e),sales=len(rows),margin=money((rev-c-e)/rev*100) if rev else 0)
 daily={};by={}
 for x in ss:
  day=x['created_at'][:10];a=daily.setdefault(day,dict(date=day,revenue=0,profit=0));a['revenue']=money(a['revenue']+x['total']);a['profit']=money(a['profit']+x['profit'])
  for it in x['items']:
   v=by.setdefault(it['name'],dict(name=it['name'],quantity=0,revenue=0));v['quantity']+=it['quantity'];v['revenue']=money(v['revenue']+it['quantity']*it['unit_price'])
 return dict(actual=totals(actual),demo=totals(demo),product_count=len(ps),low_stock=[p for p in ps if p['stock']<10],daily=sorted(daily.values(),key=lambda x:x['date']),best_sellers=sorted(by.values(),key=lambda x:-x['quantity']),products=ps)
@app.get('/api/analytics/overview')
def overview(b:T,s:S):return analytics(b,s)
@app.get('/api/analytics/revenue')
def revenue(b:T,s:S):return analytics(b,s)['daily']
@app.get('/api/analytics/products')
def product_stats(b:T,s:S):return analytics(b,s)['best_sellers']
class AIService:
 async def explain(self,prompt,fallback):
  key=os.getenv('GEMINI_API_KEY')
  if key:
   try:
    async with httpx.AsyncClient(timeout=20) as client:
     res=await client.post('https://generativelanguage.googleapis.com/v1beta/models/'+os.getenv('GEMINI_MODEL','gemini-2.5-flash')+':generateContent',headers={'x-goog-api-key':key},json={'contents':[{'parts':[{'text':prompt+' Explain only the supplied facts. Do not add prices, discounts, budgets, predictions or financial figures.'}]}]});res.raise_for_status();return res.json()['candidates'][0]['content']['parts'][0]['text'],'Gemini'
   except Exception:pass
  return fallback,'Deterministic assistant'
ai=AIService()
@app.post('/api/marketing/generate')
async def marketing(d:MarketingIn,b:T,s:S):
 p=enrich(owned(s,b,d.product_id,'product'));saleprice=money(Decimal(str(p['selling_price']))*(1-Decimal(str(d.discount))/100));profit=money(saleprice-p['total_cost']);margin=money(profit/saleprice*100) if saleprice else 0
 safe=profit>=0;fallback=f"Promote {p['name']} to local households using Facebook and WhatsApp. Run a 7-day awareness campaign, show product quality, and track enquiries before spending on paid ads."
 explanation,provider=await ai.explain(json.dumps(dict(product=p,objective=d.objective)),fallback)
 offer=dict(discount=d.discount,price=saleprice,profit=profit,margin=margin,safe=safe,warning='' if safe else 'LOSS WARNING: this discount sells below unit cost. Do not apply it.')
 content=f"Bring home quality with {p['name']} from {b.name}! Available for {b.currency} {p['selling_price']:,.2f}. Message us to order. #ShopLocal #SriLanka"
 out=dict(product_id=p['id'],image_url=p.get('image_url',''),product=p['name'],strategy=explanation,provider=provider,offer=offer,facebook=content,instagram=content+' #LocalBusiness',headline='Everyday quality, close to home',audience='Local households and repeat customers',channels=['Facebook','WhatsApp','Instagram'],duration_days=7,budget='Start with organic posts; set paid spend only after measuring conversions.',objective=d.objective)
 r=add(s,b,'campaign',out);s.commit();return enrich(r)
@app.get('/api/marketing/campaigns')
def campaigns(b:T,s:S):return [enrich(r) for r in records(s,b,'campaign')][::-1]
@app.post('/api/ai/chat')
async def chat(d:ChatIn,b:T,s:S):
 ps=products(b,s)
 if not ps:return dict(answer='Add your first product so I can analyze costs, margins and stock.',provider='Deterministic assistant')
 best=max(ps,key=lambda p:p['profit']);low=[p['name'] for p in ps if p['margin']<20];q=d.message.lower()
 if 'discount' in q:answer='Maximum break-even discounts: '+ '; '.join(f"{p['name']}: {max(0,int((1-p['total_cost']/p['selling_price'])*100))}%" for p in ps)+'. Use a smaller discount to retain a profit.'
 elif 'stock' in q:answer='Low stock: '+(', '.join(p['name'] for p in ps if p['stock']<10) or 'None')
 elif 'campaign' in q or 'facebook' in q:answer=f"Feature {best['name']} on Facebook with a clear product photo, its current price, and a message-to-order call to action. Use the Marketing page to save a campaign and check a discount."
 else:answer=f"{best['name']} earns the highest unit profit: {b.currency} {best['profit']:,.2f}. Low-margin products (under 20%): {', '.join(low) or 'None'}. Review their costs and competitor observations before adjusting prices."
 result,provider=await ai.explain(json.dumps(dict(question=d.message,products=ps,calculated_answer=answer)),answer)
 return dict(answer=result,provider=provider)

from automation import install
automation=install(app,globals())
from buyers import install as install_buyers
buyer_module=install_buyers(app,globals())

# Packaged frontend: run only Uvicorn to use the prebuilt app at localhost:8000.
from pathlib import Path
from fastapi.staticfiles import StaticFiles
frontend_dist=Path(__file__).resolve().parent.parent/'frontend'/'dist'
if frontend_dist.exists():app.mount('/',StaticFiles(directory=str(frontend_dist),html=True),name='frontend')
