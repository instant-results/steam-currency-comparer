"""Rebuild the bundled picker sprite from the licensed SVGs in web/flags/."""
from copy import deepcopy
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def build():
    root = Path(__file__).resolve().parents[1]
    registry = json.loads((root / "steam_price_polisher/storefronts.json").read_text(encoding="utf-8"))
    namespace = "http://www.w3.org/2000/svg"
    ET.register_namespace("", namespace)
    sprite = ET.Element(f"{{{namespace}}}svg")
    for region, storefront in registry.items():
        flag = "eu" if storefront["currency"] == "EUR" else region
        source = ET.parse(root / f"web/flags/{flag}.svg").getroot()
        symbol = ET.SubElement(sprite, f"{{{namespace}}}symbol", id=flag, viewBox=source.attrib["viewBox"])
        # Each source can reuse mask/clip IDs; scope them to this flag.
        identifiers = {element.attrib["id"]: f"{flag}-{element.attrib['id']}"
                       for element in source.iter() if "id" in element.attrib}
        for child in source:
            copy = deepcopy(child)
            for element in copy.iter():
                for key, value in list(element.attrib.items()):
                    if key == "id":
                        element.set(key, identifiers[value])
                    else:
                        for old, new in identifiers.items():
                            value = value.replace(f"url(#{old})", f"url(#{new})")
                            if value == f"#{old}":
                                value = f"#{new}"
                        element.set(key, value)
            symbol.append(copy)
    ET.ElementTree(sprite).write(root / "web/flags.svg", encoding="utf-8", xml_declaration=False)


if __name__ == "__main__":
    build()
