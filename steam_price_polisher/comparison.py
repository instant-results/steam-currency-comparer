"""Pure regional-price comparison logic."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .models import ConvertedPrice, GameComparison, StorePrice


def compare_game(
    app_id: str,
    name: str,
    home_price: StorePrice,
    alternatives: Sequence[StorePrice],
    rates_to_home: Mapping[str, float],
) -> GameComparison:
    """Convert alternative prices and compare them with the home-region price."""
    if not alternatives:
        raise ValueError("At least one alternative price is required")

    converted_prices: list[ConvertedPrice] = []
    normalized_rates = {currency.upper(): rate for currency, rate in rates_to_home.items()}

    for alternative in alternatives:
        currency = alternative.currency.upper()
        try:
            rate = normalized_rates[currency]
        except KeyError as exc:
            raise ValueError(f"Missing exchange rate for {currency}") from exc
        if rate <= 0:
            raise ValueError(f"Exchange rate for {currency} must be positive")

        converted_prices.append(
            ConvertedPrice(
                region=alternative.region,
                currency=currency,
                original_amount=alternative.amount,
                rate_to_home=rate,
                amount_in_home=alternative.amount * rate,
                base_amount=alternative.base_amount,
                discount_percent=alternative.discount_percent,
                source=alternative.source,
            )
        )

    converted = tuple(converted_prices)
    is_fair = all(home_price.amount <= price.amount_in_home for price in converted)
    return GameComparison(
        app_id=str(app_id),
        name=name,
        home_price=home_price,
        alternatives=converted,
        is_fair=is_fair,
    )
