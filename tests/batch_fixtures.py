"""Deterministic Steam HTTP fixtures for production batch integration tests."""
import json
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from steam_price_polisher.batching import SteamBatchProvider
from steam_price_polisher.http_client import HttpClientError
from steam_price_polisher.models import PriceStatus
from steam_price_polisher.steam_access import SteamAccessError


class BatchHttpFixture:
    def __init__(self, price):
        self.price = price
        self.values = {}
        self.calls = []

    def get_json(self, url, headers=None):
        self.calls.append(url)
        query = parse_qs(urlsplit(url).query)
        browse = 'input_json' in query
        if browse:
            request = json.loads(query['input_json'][0])
            ids = [str(item['appid']) for item in request['ids']]
            region = request['context']['country_code'].lower()
        else:
            ids, region = query['appids'][0].split(','), query['cc'][0]
        currency = {'pl':'PLN', 'us':'USD', 'de':'EUR', 'no':'NOK', 'gb':'GBP'}.get(region, 'EUR')
        values = {}
        for app_id in ids:
            key = (app_id, region)
            if key not in self.values:
                try:
                    self.values[key] = self.price(app_id, region, currency)
                except SteamAccessError as exc:
                    raise HttpClientError('Fixture request failed', transient=exc.retryable) from exc
            values[app_id] = self.values[key]
        if browse:
            return {'response': {'store_items': [dict(id=int(app_id), appid=int(app_id), item_type=0, success=1,
                name=value.game_name or 'Game', is_free=value.is_free or False,
                basic_info={'developers':[{'name':n} for n in value.developers or ()],
                            'publishers':[{'name':n} for n in value.publishers or ()]},
                **({'best_purchase_option':{'packageid':int(app_id)+100, 'purchase_option_name':value.game_name or 'Game',
                    'final_price_in_cents':str(round(value.price.amount*100)),
                    'original_price_in_cents':str(round((value.price.base_amount if value.price.base_amount is not None else value.price.amount)*100))}}
                   if value.price else {})) for app_id,value in values.items()]}}
        return {app_id:{'success':value.status is not PriceStatus.APP_UNAVAILABLE,
            'data':{'price_overview': {'currency':currency,'final':round(value.price.amount*100),
                'initial':round((value.price.base_amount if value.price.base_amount is not None else value.price.amount)*100),
                'discount_percent':int(value.price.discount_percent or 0)}} if value.price else []}
            for app_id,value in values.items()}


def mock_batch_prices(price):
    return patch('steam_price_polisher.web_app.SteamBatchProvider',
        side_effect=lambda http, **kwargs: SteamBatchProvider(BatchHttpFixture(price), **kwargs))
