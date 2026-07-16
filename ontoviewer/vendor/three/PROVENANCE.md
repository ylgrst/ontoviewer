# Vendored three.js r134

Inlined into every generated graph HTML so the output stays self-contained and
openable offline, matching the `cdn_resources="in_line"` guarantee pyvis is
configured with.

## Why r134 specifically

r134 is on the last line of three.js releases that ships **both** artifacts this
project needs:

- `build/three.min.js` — a UMD bundle that defines the global `window.THREE`.
  Minified builds were dropped from the release tarball after r149.
- `examples/js/controls/OrbitControls.js` — the pre-ESM control script that ends
  with `THREE.OrbitControls = OrbitControls;`, attaching itself to the global.
  The `examples/js/` tree was removed around r148 in favour of `examples/jsm/`
  ES modules, which cannot be inlined into a plain `<script>` tag.

Upgrading past r134 therefore means migrating to ES modules and an import map,
not just bumping a version number.

`OrbitControls.js` reads global `THREE.*` classes at definition time, so it must
be inlined **after** `three.min.js`.

## Sources

Fetched from unpkg, pinned to `three@0.134.0`:

| File | URL | sha256 |
| --- | --- | --- |
| `three.min.js` | https://unpkg.com/three@0.134.0/build/three.min.js | `74782bdbcf6518f7745ed77035968fcae95ed4ab5c9a0f90cf646a69c20785ec` |
| `OrbitControls.js` | https://unpkg.com/three@0.134.0/examples/js/controls/OrbitControls.js | `c82ab5badf4f657c7f479f15be54c5b1d6b416d85fdeec585576614db94f17d4` |
| `LICENSE` | https://unpkg.com/three@0.134.0/LICENSE | `7dddf7c5b8fd10ee654db8857d75d104b5557889aa5a91fc4ca545ea7c07062f` |

Verify with:

```bash
sha256sum ontoviewer/vendor/three/*
```

three.js is MIT licensed; see `LICENSE`.
