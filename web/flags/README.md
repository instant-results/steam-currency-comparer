# Circular currency flags

Source: [Circle Flags](https://github.com/HatScripts/circle-flags), revision `379588b5da95482d6bbf10bd45644a35b0609ea6`.
The 37 SVGs are bundled unchanged under the [MIT license](LICENSE.md).

Upstream's eu.svg symlink is resolved to european_union.svg and bundled as eu.svg.

Only flags used by the currency pickers are included. EUR uses `eu.svg`;
its representative Steam storefront remains Germany. Flags are decorative;
currency and country text provide the accessible labels.

The application serves `web/flags.svg`, a single sprite assembled from these
sources with IDs scoped to each flag. To rebuild it after changing the artwork,
run `python tools/build_currency_flags.py` from the project root. The generated
sprite is tracked, so normal application startup needs no build step.
