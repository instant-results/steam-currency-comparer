"""Choose acquisition prices without confusing bundle and game discounts."""
from math import isfinite


def primary_price(default, offer, basis="game"):
    """Return the default or a cheaper Steam-selected offer in its own currency."""
    price = (offer or {}).get("price")
    if (basis != "best" or (offer or {}).get("status") != "available"
            or (offer or {}).get("kind") not in {"bundle", "package"}
            or type((offer or {}).get("id")) is not int or offer["id"] <= 0
            or not isinstance(price, dict)
            or type(price.get("amount")) not in (int, float)
            or not isfinite(price["amount"]) or price["amount"] < 0
            or default and (price.get("currency") != default.get("currency")
                            or price["amount"] >= default["amount"])):
        return default
    base = default.get("base_amount") if default else None
    percent = ((base - price["amount"]) / base * 100
               if isinstance(base, (int, float)) and isfinite(base) and base > 0 else None)
    return {**price, "base_amount": base, "discount_percent": percent,
            "discount_calculated": True, "effective_discount": True,
            "offer_kind": offer["kind"], "offer_id": offer.get("id"),
            "offer_name": offer.get("name")}
