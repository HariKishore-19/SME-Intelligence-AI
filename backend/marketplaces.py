"""Marketplace-specific discovery. Daraz uses indexed search; eBay optionally uses Browse API."""
import os
from urllib.parse import urlparse
import httpx

DOMAINS={'daraz':['daraz.lk'],'ebay':['ebay.com','ebay.co.uk','ebay.com.au'],'web':[]}

def platform_for(url):
    host=(urlparse(url).hostname or '').lower()
    for name,domains in DOMAINS.items():
        if domains and any(host==d or host.endswith('.'+d) for d in domains):
            return name
    return 'web'

class EbayProvider:
    async def search(self,query,token,marketplace='EBAY_US'):
        if marketplace not in ('EBAY_US','EBAY_GB','EBAY_AU'):
            raise ValueError('Unsupported eBay marketplace')
        async with httpx.AsyncClient(timeout=30,trust_env=False,follow_redirects=False) as client:
            r=await client.get('https://api.ebay.com/buy/browse/v1/item_summary/search',
                headers={'Authorization':'Bearer '+token,'X-EBAY-C-MARKETPLACE-ID':marketplace},
                params={'q':query,'limit':'6','filter':'buyingOptions:{FIXED_PRICE}'})
        if not r.is_success:
            raise ValueError(f'eBay Browse returned HTTP {r.status_code}; check production token and API access')
        hits=[]
        for item in r.json().get('itemSummaries',[]):
            seller=item.get('seller',{});location=item.get('itemLocation',{});shipping=item.get('shippingOptions') or []
            hits.append(dict(title=item.get('title',''),url=item.get('itemWebUrl',''),content=item.get('shortDescription') or item.get('title',''),
                details=dict(listing_price=item.get('price'),seller=seller.get('username'),seller_feedback=seller.get('feedbackPercentage'),
                    seller_feedback_score=seller.get('feedbackScore'),image_url=item.get('image',{}).get('imageUrl'),condition=item.get('condition'),
                    location=', '.join(str(location[k]) for k in ('city','country') if location.get(k)),
                    shipping_price=shipping[0].get('shippingCost') if shipping else None,
                    shipping_note='Marketplace-default destination quote, not a confirmed Sri Lanka landed cost. Taxes and import costs excluded.',
                    availability='Returned in Browse search; purchase availability must be checked on the listing',item_id=item.get('itemId'),
                    marketplace=marketplace,source='eBay Browse API')))
        return hits
