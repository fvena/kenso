# CHANGELOG


## v1.4.0 (2026-03-16)

### Features

- **cli**: Add --json flag to kenso ingest for structured output
  ([`1fcf201`](https://github.com/fvena/kenso/commit/1fcf201204b517886786223573aad7a6765d2d2f))

- **cli**: Integrate lint report into kenso ingest output
  ([`2034990`](https://github.com/fvena/kenso/commit/20349900e3347231402cfaf4144a27a3d92b06f3))


## v1.3.0 (2026-03-16)

### Features

- **ingest**: Add predicted_queries frontmatter field for vocabulary bridging
  ([`e8cb613`](https://github.com/fvena/kenso/commit/e8cb613d414151f705c43eb7f0366d7582a46ccb))

- **search**: Detect unlinked mentions for automatic relates_to suggestions
  ([`fc8e8b0`](https://github.com/fvena/kenso/commit/fc8e8b0e9dee7c5bd255e46c4c3b0caa0466fe8a))


## v1.2.0 (2026-03-15)

### Features

- **cli**: Add kenso lint command with retrieval quality scoring
  ([`833216f`](https://github.com/fvena/kenso/commit/833216fb4668e783a8044878b72c7cc71d3d6bca))


## v1.1.0 (2026-03-15)

### Features

- **ingest**: Merge short preambles, clean stale entries, and support .kensoignore
  ([`3ee62a6`](https://github.com/fvena/kenso/commit/3ee62a652a62249bdb1234b3fbdb9b18227e99e4))

- **search**: Add configurable synonym expansion via .kenso/synonyms.yml
  ([`995597e`](https://github.com/fvena/kenso/commit/995597e14a0e0b2cdca5550d44cd0d677e6bcff3))

- **search**: Add fuzzy matching fallback for typo tolerance
  ([`84b97b3`](https://github.com/fvena/kenso/commit/84b97b3f05772bb4e9406dd2bef444bd8c6cfe60))

- **search**: Expand compound terms in indexed content and filter stop words from queries
  ([`78b8bbd`](https://github.com/fvena/kenso/commit/78b8bbd0da15433e74911c08a5d43a62e1d9a916))

- **search**: Generate context-aware snippets from matching column
  ([`c3d1041`](https://github.com/fvena/kenso/commit/c3d1041d611d183d23f280ead91b0a85d4804c92))


## v1.0.0 (2026-03-15)

### Bug Fixes

- **ci**: Update semantic-release changelog config for v10 compatibility
  ([`56bd0ac`](https://github.com/fvena/kenso/commit/56bd0ac4b9e5ed66edb582506491042839ecbfab))

### Features

- **backend**: Add SQLite FTS5 search and storage engine
  ([`8fd43b5`](https://github.com/fvena/kenso/commit/8fd43b51f1899e95a6ec87d439ca57f6323798c2))

- **cli**: Add command-line interface
  ([`f892a31`](https://github.com/fvena/kenso/commit/f892a31dc3bcda6df3320c0ad7b8ab54fbcf4599))

- **config**: Add environment-based configuration
  ([`bbffdac`](https://github.com/fvena/kenso/commit/bbffdac5c17ee549c9a97e763a0226f4df612b9b))

- **eval**: Add search quality evaluation harness
  ([`821a4ea`](https://github.com/fvena/kenso/commit/821a4eabd2764c7ea0f42f0d7c72da19c0d91dec))

- **ingest**: Add Markdown parsing and chunking pipeline
  ([`5611636`](https://github.com/fvena/kenso/commit/5611636a9698042c20958b0673563d4bf11b3ac0))

- **schema**: Add SQLite FTS5 database schema
  ([`c739df1`](https://github.com/fvena/kenso/commit/c739df12b778f95dcea70ba3293fa19ec2b738af))

- **server**: Add MCP server with search and document tools
  ([`bb80065`](https://github.com/fvena/kenso/commit/bb80065d35375c85661faae2b88147fc25840faa))
