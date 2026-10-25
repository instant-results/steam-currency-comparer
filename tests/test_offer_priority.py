import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from steam_price_polisher.analysis import AnalysisRunner
from steam_price_polisher.batching import BatchPolicy, CachedBatchPriceService, SteamBatchProvider
from steam_price_polisher.cache import SQLiteCache
from steam_price_polisher.configuration import RegionConfig
from steam_price_polisher.models import RegionalPriceResult, StorePrice, WishlistItem, WishlistFailure, WishlistResult, ExchangeRate
from steam_price_polisher.offer_selection import primary_price
from steam_price_polisher.steam_access import SteamClient
from tests.batch_fixtures import BatchHttpFixture, mock_batch_prices
from steam_price_polisher.configuration import ComparisonConfig
from steam_price_polisher.web_app import JobManager, validate_request, InputError, Cancelled


class OfferPriorityTests(unittest.TestCase):
    def test_effective_discount_uses_regular_game_price_not_bundle_discount(self):
        game = dict(amount=60, base_amount=100, currency='PLN')
        bundle = dict(status='available', kind='bundle', id=42,
                      price=dict(amount=45, base_amount=50, currency='PLN', discount_percent=10))
        chosen = primary_price(game, bundle, 'best')
        self.assertAlmostEqual(chosen['discount_percent'], 55)
        self.assertTrue(chosen['effective_discount'])
        self.assertEqual(chosen['base_amount'], 100)
        self.assertIs(primary_price(game, bundle), game)
        self.assertIsNone(primary_price(None, bundle, 'best')['discount_percent'])
        for changes in ({'amount': 60}, {'amount': 80}, {'amount': float('nan')}, {'currency': 'USD'}):
            altered = {**bundle, 'price': {**bundle['price'], **changes}}
            self.assertIs(primary_price(game, altered, 'best'), game)
        self.assertIs(primary_price(game, {**bundle, 'id': True}, 'best'), game)

    def make_runner(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        amounts = {'1': 60, '2': 40, '3': 40, '4': 80}
        def price(app_id, region, currency):
            return RegionalPriceResult.available(StorePrice(region, currency, amounts[app_id], 100, 100-amounts[app_id]), 'Game '+app_id)
        class Offers(BatchHttpFixture):
            def get_json(self, url, headers=None):
                data = super().get_json(url, headers)
                if 'GetItems' in url:
                    for item in data['response']['store_items']:
                        if item['appid'] == 1:
                            item['best_purchase_option'].update(packageid=0, bundleid=42, final_price_in_cents='2000')
                return data
        http = Offers(price)
        provider = SteamBatchProvider(http, policy=BatchPolicy(price_size=2))
        service = CachedBatchPriceService(provider, SQLiteCache(Path(temp.name)/'cache.sqlite3'))
        runner = AnalysisRunner(service, home=RegionConfig('pl','PLN'), alternatives=(RegionConfig('us','USD'),))
        return runner, http, service

    def test_price_and_discount_sort_on_selected_basis_with_stable_ties(self):
        for order in ('price', 'discount'):
            for basis, expected in [('game', ['2','3','1','4']), ('best', ['1','2','3','4'])]:
                with self.subTest(order=order,basis=basis):
                    runner, http, _ = self.make_runner()
                    results = list(runner.run(tuple(WishlistItem(str(n)) for n in range(1,5)), {'USD':1}, order=order, offer_basis=basis))
                    self.assertEqual([r.app_id for r in results], expected)
                    self.assertEqual(sum(r.live_requests for r in results),len(http.calls))
                    self.assertEqual(results[0].default_prices['pl']['currency'],'PLN')
                    # Baseline prefetch never fetches a price/offer twice across reordered windows.
                    for endpoint in ('appdetails','GetItems'):
                        baseline_ids = []
                        for url in http.calls:
                            query = parse_qs(urlsplit(url).query)
                            if endpoint not in url:
                                continue
                            if 'input_json' in query:
                                request = json.loads(query['input_json'][0])
                                if request['context']['country_code'].lower() == 'pl':
                                    baseline_ids.extend(str(item['appid']) for item in request['ids'])
                            elif query['cc'] == ['pl']:
                                baseline_ids.extend(query['appids'][0].split(','))
                        self.assertCountEqual(baseline_ids, ['1','2','3','4'])

    def test_baseline_is_complete_before_first_result_and_currency_updates_preserve_order(self):
        runner, http, service = self.make_runner()
        items = tuple(WishlistItem(str(n)) for n in range(1,5))
        stream = runner.run(items, {'USD':1}, order='price', offer_basis='game')
        next(stream)
        self.assertEqual(len(service.prefetched_lookups),4)
        list(stream)
        runner, http, service = self.make_runner()
        result = list(runner.run(items, {'USD':1}, order='price', preserve_order=True, offer_basis='best'))
        self.assertEqual([r.app_id for r in result], ['1','2','3','4'])
        self.assertFalse(service.prefetched_lookups)

    def test_cancellation_during_prefetch_emits_no_rows(self):
        runner, http, service = self.make_runner()
        def cancel():
            if http.calls:
                raise Cancelled()
        service.provider.check = cancel
        with self.assertRaises(Cancelled):
            next(runner.run((WishlistItem('1'),WishlistItem('2')), {'USD':1}, order='price'))


class WishlistOrderingTests(unittest.TestCase):
    def client(self, payload):
        class Http:
            calls = []
            def get_json(self, url, headers=None):
                self.calls.append(url)
                return payload
        http = Http()
        return SteamClient(http_client=http), http

    def test_reconciliation_preserves_membership_and_original_metadata(self):
        items = tuple(WishlistItem(str(n), name='Game '+str(n), priority=n) for n in range(1,5))
        for order in (5,6,7):
            client, http = self.client({'response': {'items': [{'appid':3},{'appid':1},{'appid':99}]}})
            result = client.get_wishlist_order('76561198000000000', items, order, 'de')
            self.assertIsNone(result.failure)
            self.assertEqual(result.items, (items[2],items[0],items[1],items[3]))
            request = json.loads(parse_qs(urlsplit(http.calls[0]).query)['input_json'][0])
            self.assertEqual(request['context']['country_code'],'DE')
            self.assertEqual(request['filters'],{})
            self.assertEqual(request['sort_order'],order)
            self.assertEqual(request['page_size'],0)
            self.assertEqual(request['data_request'],{})

    def test_empty_sorted_subset_retains_basic_and_malformed_responses_fail(self):
        items = (WishlistItem('1'),WishlistItem('2'))
        client, _ = self.client({'response':{}})
        self.assertEqual(client.get_wishlist_order('76561198000000000',items,5,'pl').items,items)
        for payload in ({}, [], {'response':{'items':'bad'}}, {'response':{'items':[{'appid':True}]}},
                        {'response':{'items':[{'appid':1},{'appid':1}]}}, {'response':{'items':[{'appid':4294967296}]}}):
            client, _ = self.client(payload)
            self.assertEqual(client.get_wishlist_order('76561198000000000',items,5,'pl').failure,WishlistFailure.INVALID_RESPONSE)

    def test_job_uses_sorted_source_then_preserves_it_for_currency_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            manager=JobManager(directory,start_worker=False)
            config=ComparisonConfig(home=RegionConfig('pl','PLN'),alternatives=(RegionConfig('us','USD'),))
            with patch('steam_price_polisher.web_app.SteamClient') as steam, patch('steam_price_polisher.web_app.NbpExchangeRateProvider') as nbp, mock_batch_prices(
                    lambda app,region,currency:RegionalPriceResult.available(StorePrice(region,currency,10,20,50),'Game '+app)):
                base=(WishlistItem('1'),WishlistItem('2'),WishlistItem('3'))
                steam.return_value.get_wishlist.return_value=WishlistResult(base,'test')
                steam.return_value.get_wishlist_order.return_value=WishlistResult((base[2],base[0],base[1]),'test')
                nbp.return_value.get_rate_details.return_value={'USD':ExchangeRate('USD',4,'2026-10-25')}
                job=manager.submit('76561198000000000',config,'test',order='top_selling',offer_basis='best')
                manager.execute(job)
                self.assertEqual(job.snapshot()['state'],'complete')
                self.assertEqual([x['app_id'] for x in job.snapshot()['items']],['3','1','2'])
                self.assertEqual(job.snapshot()['offer_basis'],'best')
                update=manager.submit('76561198000000000',config,'test',source_job=job)
                manager.execute(update)
                self.assertEqual([x['app_id'] for x in update.snapshot()['items']],['3','1','2'])
                self.assertEqual(update.offer_basis,'best')
                self.assertEqual(steam.return_value.get_wishlist_order.call_count,1)
                self.assertEqual(steam.return_value.get_wishlist.call_count,1)
                steam.return_value.get_wishlist_order.return_value=WishlistResult((),'test',failure=WishlistFailure.REQUEST)
                failed=manager.submit('76561198000000000',config,'test',order='review_score')
                manager.execute(failed)
                self.assertEqual(failed.snapshot()['state'],'failed')
                self.assertFalse(failed.snapshot()['items'])

    def test_request_accepts_all_orders_and_rejects_unknown_basis(self):
        for order in ('priority','name','date_added','price','discount','top_selling','release_date','review_score'):
            validate_request({'identifier':'example','regions':['us'],'order':order,'offer_basis':'best'})
        for basis in (None,True,[],{},'bundle'):
            with self.assertRaises(InputError):
                validate_request({'identifier':'example','regions':['us'],'offer_basis':basis})


if __name__ == '__main__':
    unittest.main()
