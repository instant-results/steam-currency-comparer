"""Bounded multi-game retrieval; prices and Steam-selected offers stay separate.

StoreBrowse has one country context, not a list of currencies. All calls use the
same paced/retrying client as other Steam traffic. No size-specific fast path.
"""
from __future__ import annotations

import json
import math
import re
import time
from contextlib import nullcontext
from dataclasses import asdict, dataclass, replace
from decimal import Decimal, ROUND_FLOOR
from urllib.parse import urlencode

from .event_log import emit
from .http_client import HttpClientError, NETWORK_ACCESS_MESSAGE
from .models import PriceStatus, RegionalPriceResult, SkipCategory, StorePrice
from .price_service import PriceLookup
from .steam_access import (SteamClient, SteamAccessError, SteamProtocolError,
                           SteamTemporaryError, SteamRequestError)


@dataclass(frozen=True)
class BatchPolicy:
    metadata_size: int = 100
    price_size: int = 100
    url_bytes: int = 6000
    recovery_calls: int = 7
    attempt_budget: int = 21

    def __post_init__(self):
        if any(type(value) is not int or value < 1 for value in asdict(self).values()):
            raise ValueError("Batch limits must be positive integers")


def price_url(ids, country):
    return 'https://store.steampowered.com/api/appdetails?' + urlencode({
        'appids': ','.join(ids), 'cc': country, 'filters': 'price_overview', 'l': 'english'})


def browse_url(ids, country):
    return 'https://api.steampowered.com/IStoreBrowseService/GetItems/v1/?' + urlencode({
        'input_json': json.dumps({'ids': [{'appid': int(value)} for value in ids],
            'context': {'country_code': country.upper(), 'language': 'english'},
            'data_request': {'include_basic_info': True, 'include_best_purchase_option': True}},
            separators=(',', ':'))})


def plan_batches(ids, make_url, maximum, url_bytes):
    """Stable deduplication with the actual fully encoded request length."""
    batch = []
    for app_id in dict.fromkeys(str(value) for value in ids):
        if not re.fullmatch(r'[0-9]{1,12}', app_id):
            raise ValueError('Invalid app ID')
        candidate = [*batch, app_id]
        if batch and (len(candidate) > maximum or len(make_url(candidate).encode('ascii')) > url_bytes):
            yield tuple(batch)
            batch = []
        batch.append(app_id)
        if len(make_url(batch).encode('ascii')) > url_bytes:
            raise ValueError('One item exceeds the encoded URL budget')
    if batch:
        yield tuple(batch)


def protocol(app_id, country):
    return SteamProtocolError('Invalid or incomplete Steam batch response', app_id=app_id, region=country)


def request_error(exc, app_id, country):
    if exc.network_access_denied:
        return SteamAccessError(NETWORK_ACCESS_MESSAGE, app_id=app_id, region=country,
                                category=SkipCategory.NETWORK_ACCESS_DENIED, retryable=False)
    kind = SteamProtocolError if exc.invalid_response else SteamTemporaryError if exc.transient else SteamRequestError
    return kind('Steam batch request failed', app_id=app_id, region=country)


def discount_details(base, current, reported):
    """Prefer Steam's percentage when consistent with the known regular price.

    Accept integer rounding/truncation and one minor unit of price rounding.
    Check implied price bounds first; calculate a replacement only on mismatch
    or missing data. Callers must establish that base is a regular-price reference.
    """
    if base is None:
        return None, False
    valid = type(reported) in {int, float} and math.isfinite(reported) and 0 <= reported <= 100
    if valid:
        if base == current and reported == 0:
            return reported, False
        if base > 0 and current == 0 and reported == 100:
            return reported, False
        if base > current > 0 and 0 < reported < 100:
            integer = float(reported).is_integer()
            lower = max(0, reported - (0.5 if integer else 0.005))
            upper = min(100, reported + (1 if integer else 0.005))
            if base * (1 - upper / 100) - 0.01 < current <= base * (1 - lower / 100) + 0.01:
                return reported, False
    # Decimal avoids turning an exact 70% into 69% through binary rounding.
    percent = (Decimal(str(base)) - Decimal(str(current))) * 100 / Decimal(str(base)) if base else Decimal(0)
    return int(percent.to_integral_value(rounding=ROUND_FLOOR)), True


def regular_discount(base, current, reported):
    return discount_details(base, current, reported)[0]


def normalize_discount(price):
    reported = None if price.discount_calculated else price.discount_percent
    discount, calculated = discount_details(price.base_amount, price.amount, reported)
    return replace(price, discount_percent=discount, discount_calculated=calculated)


def parse_prices(payload, ids, country, currency):
    output = {}
    for app_id in ids:
        try:
            result = SteamClient.parse_regional_price(payload, app_id, country, currency, price_only=True)
            if result.price and result.price.base_amount is not None:
                result = replace(result, price=normalize_discount(result.price))
            output[app_id] = replace(result, developers=None, publishers=None, is_free=None)
        except SteamAccessError as exc:
            output[app_id] = exc
    return output


def _cents(value):
    if isinstance(value, str) and re.fullmatch(r'[0-9]{1,14}', value):
        return int(value)
    if type(value) is int and 0 <= value < 10**14:
        return value
    raise ValueError('Invalid money')


def parse_offer(option, country, currency):
    if option is None:
        return {'status': 'unavailable'}
    if not isinstance(option, dict):
        return {'status': 'invalid_response'}
    try:
        package, bundle = option.get('packageid', 0), option.get('bundleid', 0)
        if (type(package) is not int or type(bundle) is not int or
                (package > 0) == (bundle > 0) or min(package, bundle) < 0):
            raise ValueError('Invalid offer identity')
        name = option.get('purchase_option_name')
        if not isinstance(name, str) or not name.strip():
            raise ValueError('Missing offer name')
        if option.get('recurrence_info'):
            return {'status': 'subscription_unsupported'}
        amount = _cents(option.get('final_price_in_cents')) / 100
        base = discount = None
        calculated = False
        # Bundles' reference can mean component savings, not a regular bundle price.
        # Compliance/display reference prices are never our regular-price baseline.
        if not bundle and not option.get('hide_discount_pct_for_compliance') and not option.get('price_cannot_be_displayed_as_discount'):
            original = option.get('original_price_in_cents')
            if original is not None:
                base = _cents(original) / 100
                if base < amount:
                    raise ValueError('Invalid regular price')
                discount, calculated = discount_details(base, amount, option.get('discount_pct'))
            elif not option.get('discount_pct') and not option.get('active_discounts'):
                base, discount = amount, 0
        return {'status': 'available', 'kind': 'bundle' if bundle else 'package',
                'id': bundle or package, 'name': name,
                'must_purchase_as_set': bool(option.get('must_purchase_as_set')),
                'currency_basis': 'requested storefront; currency code not supplied by Steam',
                'price': asdict(StorePrice(country, currency, amount, base, discount, discount_calculated=calculated))}
    except (ValueError, TypeError):
        return {'status': 'invalid_response'}


def parse_browse(payload, ids, country, currency):
    raw = payload.get('response', {}).get('store_items') if isinstance(payload, dict) and isinstance(payload.get('response'), dict) else None
    if not isinstance(raw, list):
        return {app_id: protocol(app_id, country) for app_id in ids}
    indexed, duplicates = {}, set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        app_id = str(item.get('id'))
        if app_id not in ids:
            continue  # Never associate an unexpected item by position.
        if app_id in indexed:
            duplicates.add(app_id)
        indexed[app_id] = item
    output = {}
    for app_id in ids:
        item = indexed.get(app_id)
        if not item or app_id in duplicates or item.get('item_type', 0) != 0:
            output[app_id] = protocol(app_id, country)
            continue
        success = item.get('success')
        if type(success) is not int or success not in {1, 15}:
            output[app_id] = protocol(app_id, country)
            continue
        if success != 1:
            output[app_id] = {'metadata': None, 'offer': {'status': 'unavailable'}}
            continue
        basic, name = item.get('basic_info', {}), item.get('name')
        if not isinstance(basic, dict) or not isinstance(name, str) or not name or item.get('appid') != int(app_id):
            output[app_id] = protocol(app_id, country)
            continue
        try:
            metadata = {'name': name, 'is_free': item.get('is_free', False)}
            if type(metadata['is_free']) is not bool:
                raise ValueError('Invalid free status')
            for key in ('developers', 'publishers'):
                values = basic.get(key, [])
                if not isinstance(values, list) or any(not isinstance(v, dict) or not isinstance(v.get('name'), str) for v in values):
                    raise ValueError('Invalid credits')
                metadata[key] = list(dict.fromkeys(v['name'].strip() for v in values if v['name'].strip()))
            output[app_id] = {'metadata': metadata, 'offer': parse_offer(item.get('best_purchase_option'), country, currency)}
        except ValueError:
            output[app_id] = protocol(app_id, country)
    return output


class SteamBatchProvider:
    def __init__(self, http, *, policy=BatchPolicy(), check_cancelled=lambda: None):
        self.http, self.policy, self.check = http, policy, check_cancelled
        self.logical_calls = 0

    @property
    def attempts(self):
        return getattr(self.http, 'attempts', self.logical_calls)

    def fetch(self, kind, ids, country, currency):
        builder = price_url if kind == 'prices' else browse_url
        parser = parse_prices if kind == 'prices' else parse_browse
        size = self.policy.price_size if kind == 'prices' else self.policy.metadata_size
        for batch in plan_batches(ids, lambda values: builder(values, country), size, self.policy.url_bytes):
            remaining = [self.policy.recovery_calls]
            context = self.http.limit_attempts(self.policy.attempt_budget) if hasattr(self.http, 'limit_attempts') else nullcontext()
            with context:
                result = self._recover(batch, country, currency, builder, parser, remaining)
            yield result  # Persist completed siblings before moving to the next batch.

    def _recover(self, ids, country, currency, builder, parser, remaining):
        self.check()
        if remaining[0] <= 0:
            return {value: protocol(value, country) for value in ids}
        remaining[0] -= 1
        self.logical_calls += 1
        started = time.monotonic()
        try:
            payload = self.http.get_json(builder(ids, country))
            self.check()
            results = parser(payload, ids, country, currency)
        except HttpClientError as exc:
            if exc.network_access_denied:
                raise request_error(exc, ids[0], country) from exc
            # Never split throttling, exhausted transient retries, TLS or permission errors.
            split = not exc.transient and not exc.tls_error and (exc.status_code in {400, 414} or exc.invalid_response)
            results = {value: request_error(exc, value, country) for value in ids}
            if not split:
                return results
        unresolved = [value for value in ids if isinstance(results[value], SteamProtocolError)]
        # 400/414 are request errors; they also qualify for shrinking.
        if 'split' in locals() and split:
            unresolved = list(ids)
        if len(ids) > 1 and unresolved and remaining[0] > 0:
            middle = max(1, len(unresolved) // 2)
            for child in (unresolved[:middle], unresolved[middle:]):
                if child:
                    results.update(self._recover(tuple(child), country, currency, builder, parser, remaining))
        emit('batch_completed', total=len(ids), checked=sum(not isinstance(v, SteamAccessError) for v in results.values()),
             duration_ms=(time.monotonic() - started) * 1000)
        return results


class CachedBatchPriceService:
    """Job-local prepared windows over independently timestamped shared caches."""
    def __init__(self, provider, cache, *, clock=time.time, metadata_ttl=86400):
        self.provider, self.cache, self.clock = provider, cache, clock
        self.metadata_ttl = metadata_ttl
        self.window_size = provider.policy.price_size
        self.lookups, self.metadata, self.offers = {}, {}, {}
        self.window_requests = 0

    def _fresh(self, cached):
        if cached is None:
            return False
        price = cached.result.price
        ttl = (900 if price and price.base_amount is not None and price.amount < price.base_amount else 3600) if cached.result.status != PriceStatus.APP_UNAVAILABLE else 21600
        return self.clock() - cached.fetched_at <= ttl and (not price or price.base_amount is not None)

    def prepare_metadata(self, ids, region):
        self._browse(ids, region)

    def _browse(self, ids, region):
        missing, stale = [], {}
        for app_id in ids:
            key = (app_id, region.region)
            meta = self.cache.get_observation('metadata', *key)
            offer = self.cache.get_observation('offer', *key)
            if meta:
                self.metadata[key] = {**meta[0], 'source': 'cache' if self.clock() - meta[1] <= self.metadata_ttl else 'stale cache'}
            if offer:
                stale[app_id] = offer
            if offer and offer[0].get('currency') == region.currency and self.clock() - offer[1] <= 900:
                self.offers[key] = {**offer[0], 'source': 'cache'}
            else:
                self.offers.pop(key, None)
            if key not in self.offers or not meta or self.clock() - meta[1] > self.metadata_ttl:
                missing.append(app_id)
        for batch in self.provider.fetch('browse', missing, region.region, region.currency):
            for app_id, value in batch.items():
                key = (app_id, region.region)
                if isinstance(value, SteamAccessError):
                    previous = stale.get(app_id)
                    if not isinstance(value, SteamTemporaryError) and self.metadata.get(key, {}).get('source') == 'stale cache':
                        self.metadata.pop(key, None)
                    if isinstance(value, SteamTemporaryError) and previous and previous[0].get('currency') == region.currency:
                        self.offers[key] = {**previous[0], 'source': 'stale cache'}
                    else:
                        self.offers[key] = {'status': value.category.value}
                    continue
                meta = value['metadata']
                if meta is None and not self.metadata.get(key, {}).get('name'):
                    self.cache.put_observation('metadata', *key, {'unavailable': True})
                if meta is not None:
                    self.cache.put_observation('metadata', *key, meta)
                    self.metadata[key] = {**meta, 'source': 'live'}
                offer = {**value['offer'], 'currency': region.currency}
                self.offers[key] = {**offer, 'source': 'live'}
                if offer['status'] != 'invalid_response':
                    self.cache.put_observation('offer', *key, offer)

    def prepare(self, ids, regions):
        self.lookups = {}
        started = self.provider.attempts
        for region in regions:
            self.provider.check()
            missing, stale = [], {}
            for app_id in ids:
                cached = self.cache.get_price(app_id, region.region, region.currency)
                if self._fresh(cached):
                    self.lookups[(app_id, region.region)] = PriceLookup(cached.result, 'cache')
                else:
                    missing.append(app_id)
                    stale[app_id] = cached
            for batch in self.provider.fetch('prices', missing, region.region, region.currency):
                for app_id, value in batch.items():
                    if isinstance(value, SteamTemporaryError) and stale[app_id]:
                        lookup = PriceLookup(stale[app_id].result, 'stale cache')
                    elif isinstance(value, SteamAccessError):
                        lookup = value
                    else:
                        self.cache.put_price(app_id, region.region, region.currency, value)
                        lookup = PriceLookup(value, 'live')
                    self.lookups[(app_id, region.region)] = lookup
            self._browse(ids, region)
        self.window_requests = self.provider.attempts - started

    def get_regional_price(self, app_id, region, expected_currency):
        value = self.lookups[(app_id, region)]
        if isinstance(value, SteamAccessError):
            raise value
        meta = self.metadata.get((app_id, region))
        if meta and meta.get('name'):
            value = replace(value, result=replace(value.result, game_name=meta['name'],
                is_free=meta['is_free'] if not value.result.price else False,
                developers=tuple(meta['developers']), publishers=tuple(meta['publishers'])))
        if value.result.price and value.result.price.base_amount is not None:
            value = replace(value, result=replace(value.result, price=normalize_discount(value.result.price)))
        return value

    def best_offers(self, app_id, regions):
        output = {}
        for region in regions:
            value = dict(self.offers.get((app_id, region.region), {'status': 'unavailable'}))
            default = self.lookups.get((app_id, region.region))
            if isinstance(default, SteamAccessError) and default.category is SkipCategory.REGION_MISMATCH:
                value = {'status': 'region_mismatch'}
            if value.get('price'):
                price = dict(value['price'])
                if 'discount_calculated' not in price:
                    percent = price.get('discount_percent')
                    price['discount_calculated'] = percent is not None and not float(percent).is_integer()
                value['price'] = asdict(normalize_discount(StorePrice(**{**price, 'source': value.get('source')})))
            output[region.region] = value
        return output
