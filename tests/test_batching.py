import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

from steam_price_polisher.batching import (BatchPolicy, CachedBatchPriceService, SteamBatchProvider,
    browse_url, price_url, plan_batches, parse_browse, parse_prices, parse_offer, regular_discount)
from steam_price_polisher.cache import SQLiteCache
from steam_price_polisher.configuration import ComparisonConfig, RegionConfig
from steam_price_polisher.analysis import AnalysisRunner
from steam_price_polisher.http_client import HttpClientError
from steam_price_polisher.models import RegionalPriceResult, StorePrice, WishlistItem, SkipCategory
from steam_price_polisher.request_policy import RetryPolicy, RetryingJsonHttpClient
from steam_price_polisher.steam_access import SteamAccessError, SteamProtocolError, SteamTemporaryError
from tests.batch_fixtures import BatchHttpFixture


def price(app_id, region, currency):
    return replace(RegionalPriceResult.available(StorePrice(region, currency, 10, 20, 50), 'Game ' + app_id),
                   developers=('Studio',), publishers=())


def entry(app_id=1, **kwargs):
    return dict(id=app_id, appid=app_id, item_type=0, success=1, name='Game', basic_info={}, **kwargs)


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.now = 10000
        self.cache = SQLiteCache(Path(self.temp.name)/'cache.sqlite3', clock=lambda:self.now)
        self.http = BatchHttpFixture(price)
        self.provider = SteamBatchProvider(self.http)
        self.service = CachedBatchPriceService(self.provider, self.cache, clock=lambda:self.now)
        self.regions = (RegionConfig('pl','PLN'), RegionConfig('us','USD'), RegionConfig('de','EUR'))

    def test_planner_obeys_size_url_budget_deduplicates_and_handles_empty(self):
        builder = lambda ids:browse_url(ids,'pl')
        budget = len(builder(['123456789012','234567890123']).encode('ascii'))
        chunks = list(plan_batches(['123456789012','123456789012','234567890123','345678901234'],builder,100,budget))
        self.assertEqual([len(x) for x in chunks],[2,1])
        self.assertEqual(list(plan_batches([],builder,100,budget)),[])
        with self.assertRaises(ValueError):list(plan_batches(['1'],builder,100,3))
        with self.assertRaises(ValueError):BatchPolicy(price_size=0)

    def test_same_pipeline_for_one_and_200_games_and_five_storefronts(self):
        for count in (1,200):
            with self.subTest(count=count):
                http=BatchHttpFixture(price); service=CachedBatchPriceService(SteamBatchProvider(http),self.cache,clock=lambda:self.now)
                ids=[str(i+1000*count) for i in range(count)]
                regions=(*self.regions,RegionConfig('no','NOK'),RegionConfig('gb','GBP'))
                service.prepare(ids,regions)
                self.assertEqual(len(http.calls),10*((count+99)//100))
                self.assertEqual(service.get_regional_price(ids[0],'pl','PLN').result.price.amount,10)
                self.assertEqual(len(service.best_offers(ids[0],regions)),5)

    def test_retrieval_is_not_hard_coded_to_three_or_five_countries(self):
        regions=(*self.regions, SimpleNamespace(region='fr',currency='EUR'),SimpleNamespace(region='es',currency='EUR'),SimpleNamespace(region='it',currency='EUR'))
        self.service.prepare(['1'],regions)
        self.assertEqual(len(self.service.best_offers('1',regions)),6)
        self.assertEqual(len(self.http.calls),12)

    def test_cache_reuse_and_independent_metadata_price_offer_freshness(self):
        self.service.prepare(['1'],self.regions)
        self.assertEqual(len(self.http.calls),6)
        self.service.prepare(['1'],self.regions)
        self.assertEqual(len(self.http.calls),6)
        self.now+=901
        self.service.prepare(['1'],self.regions)
        self.assertEqual(len(self.http.calls),12) # Sale and best-offer TTL expired.
        self.assertEqual(self.service.get_regional_price('1','pl','PLN').result.publishers,())

    def test_metadata_enriches_legacy_price_without_refreshing_its_age(self):
        self.cache.put_price('1','pl','PLN',RegionalPriceResult.available(StorePrice('pl','PLN',12,12,0),'Old'))
        self.now+=100
        self.service.prepare(['1'],self.regions[:1])
        self.assertEqual(len(self.http.calls),1)
        self.assertIn('GetItems',self.http.calls[0])
        self.assertEqual(self.cache.get_price('1','pl','PLN').fetched_at,10000)
        result=self.service.get_regional_price('1','pl','PLN').result
        self.assertEqual(result.price.amount,12); self.assertEqual(result.developers,('Studio',))

    def test_missing_reordered_duplicate_and_wrong_type_metadata(self):
        payload={'response':{'store_items':[entry(2),entry(1),entry(1),entry(99)]}}
        parsed=parse_browse(payload,['1','2','3'],'pl','PLN')
        self.assertIsInstance(parsed['1'],SteamProtocolError)
        self.assertEqual(parsed['2']['metadata']['name'],'Game')
        self.assertIsInstance(parsed['3'],SteamProtocolError)
        item=entry();item['item_type']=1
        self.assertIsInstance(parse_browse({'response':{'store_items':[item]}},['1'],'pl','PLN')['1'],SteamProtocolError)

    def test_restricted_and_free_metadata_are_distinct(self):
        restricted=entry();restricted['success']=15
        parsed=parse_browse({'response':{'store_items':[restricted,entry(2,is_free=True)]}},['1','2'],'de','EUR')
        self.assertIsNone(parsed['1']['metadata'])
        self.assertTrue(parsed['2']['metadata']['is_free'])
        self.assertEqual(parsed['1']['offer']['status'],'unavailable')

    def test_empty_array_is_no_price_not_free_and_wrong_currency_fails(self):
        payload={'1':{'success':True,'data':[]},'2':{'success':True,'data':{'price_overview':{'currency':'USD','initial':19900,'final':5970,'discount_percent':0}}}}
        parsed=parse_prices(payload,['1','2','3'],'pl','PLN')
        self.assertIsNone(parsed['1'].is_free)
        self.assertEqual(parsed['2'].category,SkipCategory.REGION_MISMATCH)
        self.assertIsInstance(parsed['3'],SteamProtocolError)
        payload['2']['data']['price_overview']['currency']='PLN'
        self.assertEqual(parse_prices(payload,['2'],'pl','PLN')['2'].price.discount_percent,70)

    def test_steam_discount_is_preserved_with_normal_rounding(self):
        self.assertEqual(regular_discount(99.99, 66.66, 33), 33)
        self.assertEqual(regular_discount(100, 66.1, 33), 33)
        self.assertEqual(regular_discount(199, 59.70, 70), 70)
        self.assertEqual(regular_discount(10, 10, 0), 0)
        self.assertEqual(regular_discount(10, 0, 100), 100)

    def test_discount_calculation_is_only_a_fallback_with_known_regular_base(self):
        for reported in (0, 10, None, True, float('nan')):
            with self.subTest(reported=reported):
                self.assertEqual(regular_discount(199, 59.70, reported), 70)
        self.assertIsNone(regular_discount(None, 59.70, 0))
        self.assertEqual(regular_discount(100, 99, 0), 1)
        self.assertEqual(regular_discount(100, 1, 100), 99)

    def test_live_cached_and_best_offer_paths_preserve_reported_discount(self):
        payload={'1':{'success':True,'data':{'price_overview':{
            'currency':'PLN','initial':9999,'final':6666,'discount_percent':33}}}}
        result=parse_prices(payload,['1'],'pl','PLN')['1']
        self.assertEqual(result.price.discount_percent,33)
        self.cache.put_price('1','pl','PLN',result)
        self.service.prepare(['1'],self.regions[:1])
        self.assertEqual(self.service.get_regional_price('1','pl','PLN').result.price.discount_percent,33)
        option={'packageid':1,'purchase_option_name':'Game','final_price_in_cents':'6666',
                'original_price_in_cents':'9999','discount_pct':33}
        self.assertEqual(parse_offer(option,'us','USD')['price']['discount_percent'],33)
        option['discount_pct']=0
        self.assertEqual(parse_offer(option,'us','USD')['price']['discount_percent'],33)
        option['hide_discount_pct_for_compliance']=True
        self.assertIsNone(parse_offer(option,'pl','PLN')['price']['discount_percent'])

    def test_calculated_discount_is_floored_and_provenance_survives_cache_and_conversion(self):
        from steam_price_polisher.comparison import compare_game
        payload={'1':{'success':True,'data':{'price_overview':{
            'currency':'PLN','initial':10000,'final':6666,'discount_percent':0}}}}
        result=parse_prices(payload,['1'],'pl','PLN')['1']
        self.assertEqual(result.price.discount_percent,33)
        self.assertTrue(result.price.discount_calculated)
        self.cache.put_price('1','pl','PLN',result)
        self.service.prepare(['1'],self.regions[:1])
        cached=self.service.get_regional_price('1','pl','PLN').result.price
        self.assertTrue(cached.discount_calculated)
        self.assertEqual(cached.discount_percent,33)
        converted=compare_game('1','Game',cached,[replace(cached,region='us',currency='USD')],{'USD':4})
        self.assertTrue(converted.alternatives[0].discount_calculated)
        self.assertEqual(regular_discount(100,99.5,None),0)
        self.assertEqual(regular_discount(199,59.7,None),70)

    def test_best_offer_keeps_bundle_identity_and_never_uses_game_base(self):
        option={'bundleid':22978,'purchase_option_name':'Complete edition','final_price_in_cents':'1999','original_price_in_cents':'7999','discount_pct':75}
        offer=parse_offer(option,'pl','PLN')
        self.assertEqual(offer['kind'],'bundle'); self.assertEqual(offer['price']['amount'],19.99)
        self.assertIsNone(offer['price']['base_amount']); self.assertIsNone(offer['price']['discount_percent'])
        self.assertIn('not supplied',offer['currency_basis'])

    def test_compliance_reference_is_not_used_as_regular_price(self):
        option={'packageid':1,'purchase_option_name':'Game','final_price_in_cents':'5970','original_price_in_cents':'5970','hide_discount_pct_for_compliance':True}
        self.assertIsNone(parse_offer(option,'pl','PLN')['price']['discount_percent'])
        option.update(hide_discount_pct_for_compliance=False,original_price_in_cents='19900')
        self.assertEqual(parse_offer(option,'us','USD')['price']['discount_percent'],70)
        option['recurrence_info']={'billing_agreement_type':1}
        self.assertEqual(parse_offer(option,'us','USD')['status'],'subscription_unsupported')

    def test_malformed_offer_cannot_poison_default_prices(self):
        self.service.prepare(['1'],self.regions)
        self.service.offers[('1','pl')]={'status':'invalid_response'}
        self.assertEqual(self.service.get_regional_price('1','pl','PLN').result.price.amount,10)
        self.assertEqual(parse_offer({'packageid':1,'purchase_option_name':'Game','final_price_in_cents':'NaN'},'pl','PLN')['status'],'invalid_response')

    def test_missing_siblings_recovered_without_refetching_valid_sibling(self):
        calls=[]
        def respond(url,headers=None):
            ids=parse_qs(urlsplit(url).query)['appids'][0].split(','); calls.append(ids)
            return {value:{'success':True,'data':[]} for value in (ids[:1] if len(calls)==1 else ids)}
        provider=SteamBatchProvider(SimpleNamespace(get_json=respond))
        result=list(provider.fetch('prices',['1','2','3'],'pl','PLN'))[0]
        self.assertEqual(calls,[['1','2','3'],['2'],['3']])
        self.assertTrue(all(isinstance(x,RegionalPriceResult) for x in result.values()))

    def test_persistent_malformed_batches_and_retry_attempts_have_shared_ceiling(self):
        raw=Mock();raw.get_json.side_effect=[HttpClientError('Retry',transient=True),{}]*20
        client=RetryingJsonHttpClient(raw,policy=RetryPolicy(max_attempts=3),sleep=lambda _:None)
        provider=SteamBatchProvider(client,policy=BatchPolicy(attempt_budget=5,recovery_calls=7))
        result=list(provider.fetch('prices',[str(i) for i in range(100)],'pl','PLN'))[0]
        self.assertEqual(raw.get_json.call_count,5)
        self.assertEqual(len(result),100)
        self.assertTrue(all(isinstance(x,SteamAccessError) for x in result.values()))

    def test_rate_limit_does_not_trigger_split_requests(self):
        raw=Mock();raw.get_json.side_effect=HttpClientError('Busy',status_code=429,transient=True,retry_after=1)
        provider=SteamBatchProvider(RetryingJsonHttpClient(raw,policy=RetryPolicy(max_attempts=3),sleep=lambda _:None))
        result=list(provider.fetch('prices',['1','2'],'pl','PLN'))[0]
        self.assertEqual(raw.get_json.call_count,3)
        self.assertTrue(all(isinstance(x,SteamTemporaryError) for x in result.values()))

    def test_stale_fallback_is_only_for_temporary_errors_not_local_denial(self):
        self.service.prepare(['1'],self.regions[:1]);self.now+=1000
        self.http.get_json=Mock(side_effect=HttpClientError('Busy',transient=True))
        self.service.prepare(['1'],self.regions[:1])
        self.assertEqual(self.service.get_regional_price('1','pl','PLN').source,'stale cache')
        self.http.get_json.side_effect=HttpClientError('Denied',network_access_denied=True)
        with self.assertRaises(SteamAccessError) as caught:self.service.prepare(['1'],self.regions[:1])
        self.assertEqual(caught.exception.category,SkipCategory.NETWORK_ACCESS_DENIED)

    def test_cancellation_keeps_completed_country_cache(self):
        def cancel():
            if len(self.http.calls)>=2:raise RuntimeError('cancelled')
        self.provider.check=cancel
        with self.assertRaisesRegex(RuntimeError,'cancelled'):self.service.prepare(['1'],self.regions)
        self.assertIsNotNone(self.cache.get_price('1','pl','PLN'))
        self.assertIsNone(self.cache.get_price('1','us','USD'))

    def test_ordered_progress_counts_shared_requests_once_and_returns_both_comparisons(self):
        runner=AnalysisRunner(self.service,home=self.regions[0],alternatives=self.regions[1:])
        items=[WishlistItem('2',priority=2),WishlistItem('1',priority=1)]
        result=list(runner.run(items,{'USD':4,'EUR':4}))
        self.assertEqual([x.app_id for x in result],['1','2'])
        self.assertEqual(sum(x.live_requests for x in result),6)
        self.assertTrue(all(x.comparison and x.best_offer_comparison for x in result))
        self.assertEqual(result[0].developers,('Studio',))
        again=list(runner.run(items,{'USD':4,'EUR':4},order='name'))
        self.assertEqual(sum(x.live_requests for x in again),0)
        self.assertTrue(all(x.cache_hits==3 for x in again))

    def test_name_prefetch_requests_are_counted_and_reused(self):
        runner=AnalysisRunner(self.service,home=self.regions[0],alternatives=self.regions[1:])
        result=list(runner.run([WishlistItem('2'),WishlistItem('1')],{'USD':4,'EUR':4},order='name'))
        self.assertEqual([x.app_id for x in result],['1','2'])
        self.assertEqual(sum(x.live_requests for x in result),6)
        self.assertEqual(len(self.http.calls),6)


if __name__=='__main__':unittest.main()
