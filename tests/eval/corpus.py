"""Synthetic corpus simulating a regulated financial platform knowledge base.

Designed to test BM25 retrieval weaknesses:
- Vocabulary mismatch (synonyms, paraphrases)
- Multi-concept queries (crossing domains)
- Generic headings (ambiguous chunk titles)
- Pre-H2 content loss
- Tag-only discoverability
"""

CORPUS = [
    # ── Settlement domain ──────────────────────────────────────────────
    {
        "path": "post-trade/settlement-lifecycle.md",
        "content": (
            "---\n"
            "title: Settlement Lifecycle for Equity Trades\n"
            "category: post-trade\n"
            "tags: settlement, clearing, T+2, DVP, CNMV\n"
            "aliases:\n"
            "  - trade settlement\n"
            "  - post-trade processing\n"
            "  - clearing and settlement\n"
            "  - liquidación de operaciones\n"
            "answers:\n"
            "  - How are equity trades settled on the platform?\n"
            "  - What is the T+2 settlement cycle?\n"
            "  - What happens when a settlement fails?\n"
            "relates_to:\n"
            "  - path: order-management/matching-engine.md\n"
            "    relation: receives_from\n"
            "  - path: compliance/cnmv-reporting.md\n"
            "    relation: triggers\n"
            "---\n"
            "\n"
            "# Settlement Lifecycle for Equity Trades\n"
            "\n"
            "The settlement process (also known as trade settlement, clearing and\n"
            "settlement, post-trade processing) manages the final exchange of\n"
            "securities and cash after an equity trade is executed on the\n"
            "multilateral trading facility (MTF). This document covers the complete\n"
            "settlement lifecycle, T+2 settlement cycles, central counterparty\n"
            "clearing, failed trade handling, and CNMV regulatory requirements.\n"
            "\n"
            "## Settlement Phases\n"
            "\n"
            "The settlement lifecycle for equity trades on the platform consists\n"
            "of four phases: trade confirmation, clearing through the central\n"
            "counterparty (CCP), settlement instruction generation, and final\n"
            "delivery-versus-payment (DVP) execution. Each phase must complete\n"
            "within the T+2 regulatory window mandated by CNMV.\n"
            "\n"
            "## Failed Settlement Handling\n"
            "\n"
            "When a settlement fails (partial delivery, insufficient securities,\n"
            "cash shortfall), the system triggers an automatic buy-in procedure.\n"
            "The failed trade is reported to CNMV within 24 hours. Penalty\n"
            "charges apply per the CSDR settlement discipline regime.\n"
            "\n"
            "## DVP Mechanics\n"
            "\n"
            "Delivery versus payment ensures atomic settlement: securities and\n"
            "cash transfer simultaneously. The platform supports DVP Model 1\n"
            "(gross settlement) for all equity trades. Settlement finality is\n"
            "achieved when Iberclear confirms the transfer.\n"
        ),
    },
    # ── Order Management domain ────────────────────────────────────────
    {
        "path": "order-management/matching-engine.md",
        "content": (
            "---\n"
            "title: Order Matching Engine\n"
            "category: order-management\n"
            "tags: matching, order-book, price-time-priority, FIX\n"
            "aliases:\n"
            "  - trade execution engine\n"
            "  - order book system\n"
            "  - execution venue\n"
            "answers:\n"
            "  - How are orders matched on the platform?\n"
            "  - What order types does the exchange support?\n"
            "relates_to:\n"
            "  - path: post-trade/settlement-lifecycle.md\n"
            "    relation: feeds_into\n"
            "---\n"
            "\n"
            "# Order Matching Engine\n"
            "\n"
            "The order matching engine is the core component of the multilateral\n"
            "trading facility. It receives orders via FIX protocol from members\n"
            "and executes matches using price-time priority.\n"
            "\n"
            "## Price-Time Priority Algorithm\n"
            "\n"
            "Orders are ranked first by price (best price first), then by\n"
            "timestamp within the same price level. Buy orders are ranked\n"
            "highest-price-first, sell orders lowest-price-first. This\n"
            "ensures fair and transparent execution following MiFID II rules.\n"
            "\n"
            "## Order Types Supported\n"
            "\n"
            "The matching engine accepts the following order types: limit\n"
            "orders, market orders, stop orders, and iceberg orders. Each\n"
            "order type has specific validation rules enforced before\n"
            "entering the order book. Market orders execute immediately\n"
            "at the best available price.\n"
            "\n"
            "## FIX Protocol Integration\n"
            "\n"
            "Members connect via FIX 4.4 protocol. The platform supports\n"
            "New Order Single (35=D), Order Cancel Request (35=F), and\n"
            "Execution Report (35=8) message types. Session-level heartbeat\n"
            "monitoring ensures connection reliability.\n"
        ),
    },
    # ── Compliance domain ──────────────────────────────────────────────
    {
        "path": "compliance/cnmv-reporting.md",
        "content": (
            "---\n"
            "title: CNMV Regulatory Reporting\n"
            "category: compliance\n"
            "tags: CNMV, reporting, MiFID, transaction-reporting, RTS25\n"
            "relates_to:\n"
            "  - path: post-trade/settlement-lifecycle.md\n"
            "    relation: monitors\n"
            "  - path: compliance/market-surveillance.md\n"
            "    relation: receives_from\n"
            "---\n"
            "\n"
            "# CNMV Regulatory Reporting\n"
            "\n"
            "## Transaction Reporting Requirements\n"
            "\n"
            "All executed trades must be reported to CNMV within T+1 as\n"
            "mandated by MiFID II Article 26. Reports include instrument\n"
            "identifiers (ISIN), counterparty LEI codes, execution venue\n"
            "MIC, price, quantity, and timestamp. The platform generates\n"
            "reports automatically from the trade execution log.\n"
            "\n"
            "## Reference Data Obligations\n"
            "\n"
            "Under RTS 25, the platform must submit daily reference data\n"
            "for all instruments admitted to trading. This includes\n"
            "instrument classification (CFI code), trading parameters\n"
            "(tick size, lot size), and market segment identifiers.\n"
            "\n"
            "## Suspicious Transaction Reports (STR)\n"
            "\n"
            "When the market surveillance system detects potential market\n"
            "abuse, the compliance team must file a Suspicious Transaction\n"
            "Report with CNMV within 48 hours. The STR includes the\n"
            "detected pattern, involved parties, and supporting evidence.\n"
        ),
    },
    {
        "path": "compliance/market-surveillance.md",
        "content": (
            "---\n"
            "title: Market Surveillance System\n"
            "category: compliance\n"
            "tags: surveillance, market-abuse, MAR, alerts\n"
            "relates_to:\n"
            "  - path: compliance/cnmv-reporting.md\n"
            "    relation: feeds_into\n"
            "  - path: order-management/matching-engine.md\n"
            "    relation: monitors\n"
            "---\n"
            "\n"
            "# Market Surveillance System\n"
            "\n"
            "## Detection Algorithms\n"
            "\n"
            "The market surveillance system monitors all trading activity\n"
            "in real-time to detect potential market abuse as required by\n"
            "the Market Abuse Regulation (MAR). Detection algorithms\n"
            "cover: insider trading patterns, market manipulation\n"
            "(layering, spoofing, wash trading), and unusual price\n"
            "movements. Each algorithm generates alerts scored by severity.\n"
            "\n"
            "## Alert Investigation Workflow\n"
            "\n"
            "When an alert triggers, the compliance team reviews the\n"
            "trading pattern, checks member communications, and\n"
            "determines if escalation to CNMV is required. The workflow\n"
            "tracks investigation status from open to closed with full\n"
            "audit trail.\n"
        ),
    },
    # ── Architecture domain ────────────────────────────────────────────
    {
        "path": "architecture/platform-overview.md",
        "content": (
            "---\n"
            "title: Platform Architecture Overview\n"
            "category: architecture\n"
            "tags: architecture, microservices, Java, Spring-Boot, MTF\n"
            "relates_to:\n"
            "  - path: order-management/matching-engine.md\n"
            "    relation: contains\n"
            "  - path: architecture/api-gateway.md\n"
            "    relation: contains\n"
            "---\n"
            "\n"
            "# Platform Architecture Overview\n"
            "\n"
            "The Portfolio Stock Exchange platform is built as a set of\n"
            "microservices running on Java 21 with Spring Boot 3. The\n"
            "architecture follows a hexagonal pattern with clear domain\n"
            "boundaries between order management, post-trade, compliance,\n"
            "and member management.\n"
            "\n"
            "## Service Topology\n"
            "\n"
            "The platform consists of the following core services:\n"
            "poex-gateway (API gateway and authentication), poex-matching\n"
            "(order matching engine), poex-settlement (post-trade\n"
            "processing), poex-compliance (regulatory reporting and\n"
            "surveillance), and poex-backoffice (administrative interface).\n"
            "Services communicate via asynchronous message queues (RabbitMQ)\n"
            "for event-driven workflows and synchronous REST for queries.\n"
            "\n"
            "## Technology Stack\n"
            "\n"
            "Backend: Java 21, Spring Boot 3, PostgreSQL 16, RabbitMQ.\n"
            "Frontend: Vue 3, TypeScript, Nuxt 4, Pinia.\n"
            "Infrastructure: Docker, Kubernetes, GitLab CI/CD.\n"
            "Monitoring: Prometheus, Grafana, ELK stack.\n"
        ),
    },
    {
        "path": "architecture/api-gateway.md",
        "content": (
            "---\n"
            "title: API Gateway and Authentication\n"
            "category: architecture\n"
            "tags: gateway, authentication, OAuth2, JWT, rate-limiting\n"
            "aliases:\n"
            "  - login system\n"
            "  - API security\n"
            "  - access control\n"
            "answers:\n"
            "  - How do users log in to the platform?\n"
            "  - What are the API rate limits?\n"
            "relates_to:\n"
            "  - path: architecture/platform-overview.md\n"
            "    relation: part_of\n"
            "---\n"
            "\n"
            "# API Gateway and Authentication\n"
            "\n"
            "## Authentication Flow\n"
            "\n"
            "The API gateway handles all external authentication using\n"
            "OAuth 2.0 with JWT tokens. Members authenticate via client\n"
            "credentials grant for API access or authorization code grant\n"
            "for the web interface. Tokens expire after 30 minutes with\n"
            "refresh token rotation.\n"
            "\n"
            "## Rate Limiting\n"
            "\n"
            "API endpoints enforce rate limits per member: 100 requests\n"
            "per second for order submission, 1000 per second for market\n"
            "data queries. Exceeding limits returns HTTP 429 with a\n"
            "Retry-After header.\n"
            "\n"
            "## Request Routing\n"
            "\n"
            "The gateway routes requests to internal microservices based\n"
            "on URL path prefixes: /api/orders to poex-matching,\n"
            "/api/settlements to poex-settlement, /api/compliance to\n"
            "poex-compliance. Health checks and circuit breakers prevent\n"
            "cascading failures.\n"
        ),
    },
    # ── Member Management domain ───────────────────────────────────────
    {
        "path": "members/onboarding.md",
        "content": (
            "---\n"
            "title: Member Onboarding Process\n"
            "category: members\n"
            "tags: onboarding, KYC, AML, member, participant\n"
            "aliases:\n"
            "  - participant registration\n"
            "  - new member signup\n"
            "  - market access application\n"
            "answers:\n"
            "  - How do new participants register on the platform?\n"
            "  - What KYC documentation is required?\n"
            "  - What are the trading fees?\n"
            "relates_to:\n"
            "  - path: compliance/cnmv-reporting.md\n"
            "    relation: required_by\n"
            "---\n"
            "\n"
            "# Member Onboarding Process\n"
            "\n"
            "New market participants must complete a multi-step onboarding\n"
            "process before being admitted to trade on the platform.\n"
            "\n"
            "## KYC and AML Verification\n"
            "\n"
            "All prospective members undergo Know Your Customer (KYC) and\n"
            "Anti-Money Laundering (AML) verification. This includes\n"
            "identity verification of beneficial owners, source of funds\n"
            "documentation, PEP (Politically Exposed Person) screening,\n"
            "and sanctions list checking. Verification must be renewed\n"
            "annually.\n"
            "\n"
            "## Technical Certification\n"
            "\n"
            "Before production access, members must pass technical\n"
            "certification: FIX connectivity testing in the UAT\n"
            "environment, order flow validation, risk parameter\n"
            "configuration, and disaster recovery drill.\n"
            "\n"
            "## Fee Structure\n"
            "\n"
            "Trading fees are structured as maker-taker: makers (limit\n"
            "orders adding liquidity) pay 0.01% per trade, takers\n"
            "(market orders removing liquidity) pay 0.03%. Annual\n"
            "membership fee covers platform access and regulatory costs.\n"
        ),
    },
    # ── Operations domain ──────────────────────────────────────────────
    {
        "path": "operations/incident-management.md",
        "content": (
            "---\n"
            "title: Incident Management Procedures\n"
            "category: operations\n"
            "tags: incidents, SLA, runbook, on-call, escalation\n"
            "aliases:\n"
            "  - outage handling\n"
            "  - system downtime procedures\n"
            "  - service disruption playbook\n"
            "relates_to:\n"
            "  - path: architecture/platform-overview.md\n"
            "    relation: operates_on\n"
            "---\n"
            "\n"
            "# Incident Management Procedures\n"
            "\n"
            "## Severity Classification\n"
            "\n"
            "Incidents are classified by severity: P1 (trading halted,\n"
            "complete outage), P2 (degraded performance, partial feature\n"
            "loss), P3 (minor issue, workaround available), P4\n"
            "(cosmetic, no trading impact). P1 incidents trigger\n"
            "immediate CNMV notification as per operating license\n"
            "requirements.\n"
            "\n"
            "## Escalation Procedures\n"
            "\n"
            "P1: On-call engineer → CTO → CEO → CNMV within 15 minutes.\n"
            "P2: On-call engineer → Team Lead within 30 minutes.\n"
            "P3/P4: Logged in Jira, addressed in next sprint.\n"
            "All incidents require post-mortem within 72 hours.\n"
            "\n"
            "## Business Continuity\n"
            "\n"
            "The disaster recovery plan includes failover to the secondary\n"
            "data center with RPO < 1 minute and RTO < 15 minutes.\n"
            "Annual DR tests validate failover procedures with CNMV\n"
            "observers present.\n"
        ),
    },
    # ── Market Data domain ─────────────────────────────────────────────
    {
        "path": "market-data/feed-specification.md",
        "content": (
            "---\n"
            "title: Market Data Feed Specification\n"
            "category: market-data\n"
            "tags: market-data, feed, FAST, level-2, order-book\n"
            "relates_to:\n"
            "  - path: order-management/matching-engine.md\n"
            "    relation: receives_from\n"
            "  - path: architecture/api-gateway.md\n"
            "    relation: served_through\n"
            "---\n"
            "\n"
            "# Market Data Feed Specification\n"
            "\n"
            "## Real-Time Feed\n"
            "\n"
            "The platform publishes real-time market data via FAST protocol\n"
            "(FIX Adapted for Streaming) over UDP multicast. The feed\n"
            "includes: best bid/offer (Level 1), full order book depth\n"
            "(Level 2), trade reports, and instrument status updates.\n"
            "Latency target is sub-millisecond from matching engine event.\n"
            "\n"
            "## Historical Data API\n"
            "\n"
            "Historical market data is available via REST API with daily\n"
            "OHLCV (open, high, low, close, volume) candles, tick-by-tick\n"
            "trade data for the last 30 days, and end-of-day settlement\n"
            "prices. Data is retained for 7 years per regulatory\n"
            "requirements.\n"
        ),
    },
    # ── Liquidity domain ───────────────────────────────────────────────
    {
        "path": "market-data/liquidity-metrics.md",
        "content": (
            "---\n"
            "title: Liquidity Metrics and Market Quality\n"
            "category: market-data\n"
            "tags: liquidity, spread, depth, market-quality, turnover\n"
            "relates_to:\n"
            "  - path: market-data/feed-specification.md\n"
            "    relation: derived_from\n"
            "  - path: order-management/matching-engine.md\n"
            "    relation: derived_from\n"
            "---\n"
            "\n"
            "# Liquidity Metrics and Market Quality\n"
            "\n"
            "## Spread Analysis\n"
            "\n"
            "The bid-ask spread is the primary indicator of market\n"
            "liquidity. The platform calculates time-weighted average\n"
            "spread (TWAS) continuously during trading hours. A narrow\n"
            "spread indicates strong liquidity and competitive pricing.\n"
            "Market makers are incentivized to maintain tight spreads\n"
            "through the fee rebate program.\n"
            "\n"
            "## Depth and Turnover\n"
            "\n"
            "Order book depth measures available liquidity at each price\n"
            "level. The platform reports cumulative depth for the top 5\n"
            "bid and ask levels. Daily turnover ratio (traded volume /\n"
            "free float) indicates how actively a security is traded.\n"
        ),
    },
]


# ═══════════════════════════════════════════════════════════════════════
# EVAL CASES — organized by failure mode
# ═══════════════════════════════════════════════════════════════════════

EVAL_CASES = [
    # ── CATEGORY A: Exact keyword match (baseline — should always work) ─
    {
        "id": "A01",
        "category_label": "exact_keyword",
        "query": "settlement lifecycle",
        "expected_paths": ["post-trade/settlement-lifecycle.md"],
        "expected_chunk_keywords": ["settlement lifecycle", "four phases"],
        "description": "Exact terms from document title",
    },
    {
        "id": "A02",
        "category_label": "exact_keyword",
        "query": "order matching engine",
        "expected_paths": ["order-management/matching-engine.md"],
        "expected_chunk_keywords": ["matching engine", "price-time priority"],
        "description": "Exact terms from document title",
    },
    {
        "id": "A03",
        "category_label": "exact_keyword",
        "query": "CNMV regulatory reporting",
        "expected_paths": ["compliance/cnmv-reporting.md"],
        "expected_chunk_keywords": ["CNMV", "MiFID II"],
        "description": "Exact terms from document title",
    },
    {
        "id": "A04",
        "category_label": "exact_keyword",
        "query": "FIX protocol integration",
        "expected_paths": ["order-management/matching-engine.md"],
        "expected_chunk_keywords": ["FIX 4.4", "New Order Single"],
        "description": "Exact section heading match",
    },
    {
        "id": "A05",
        "category_label": "exact_keyword",
        "query": "bid-ask spread liquidity",
        "expected_paths": ["market-data/liquidity-metrics.md"],
        "expected_chunk_keywords": ["bid-ask spread", "liquidity"],
        "description": "Exact terms in body",
    },

    # ── CATEGORY B: Synonym / vocabulary mismatch ─────────────────────
    {
        "id": "B01",
        "category_label": "synonym",
        "query": "post-trade processing",
        "expected_paths": ["post-trade/settlement-lifecycle.md"],
        "expected_chunk_keywords": ["settlement"],
        "description": "Synonym: 'post-trade processing' → settlement lifecycle (mentioned as alias in intro)",
    },
    {
        "id": "B02",
        "category_label": "synonym",
        "query": "login authentication token",
        "expected_paths": ["architecture/api-gateway.md"],
        "expected_chunk_keywords": ["OAuth", "JWT"],
        "description": "Synonym: 'login' not in doc, 'authentication' is",
    },
    {
        "id": "B03",
        "category_label": "synonym",
        "query": "trading fees costs",
        "expected_paths": ["members/onboarding.md"],
        "expected_chunk_keywords": ["fee", "maker-taker"],
        "description": "Synonym: 'costs' not in doc, 'fee structure' is",
    },
    {
        "id": "B04",
        "category_label": "synonym",
        "query": "outage disaster recovery",
        "expected_paths": ["operations/incident-management.md"],
        "expected_chunk_keywords": ["disaster recovery", "failover"],
        "description": "Synonym: 'outage' maps to incident/business continuity",
    },
    {
        "id": "B05",
        "category_label": "synonym",
        "query": "new participant registration",
        "expected_paths": ["members/onboarding.md"],
        "expected_chunk_keywords": ["onboarding", "member"],
        "description": "Synonym: 'participant registration' → member onboarding",
    },
    {
        "id": "B06",
        "category_label": "synonym",
        "query": "how trades are cleared and settled",
        "expected_paths": ["post-trade/settlement-lifecycle.md"],
        "expected_chunk_keywords": ["settlement", "clearing"],
        "description": "Natural language paraphrase for settlement process",
    },
    {
        "id": "B07",
        "category_label": "synonym",
        "query": "market abuse detection",
        "expected_paths": ["compliance/market-surveillance.md"],
        "expected_chunk_keywords": ["market abuse", "detection"],
        "description": "Synonym: should match surveillance system",
    },

    # ── CATEGORY C: Multi-concept / cross-domain ──────────────────────
    {
        "id": "C01",
        "category_label": "multi_concept",
        "query": "CNMV settlement reporting requirements",
        "expected_paths": [
            "compliance/cnmv-reporting.md",
            "post-trade/settlement-lifecycle.md",
        ],
        "expected_chunk_keywords": ["CNMV", "settlement", "reporting"],
        "description": "Crosses compliance + post-trade domains",
    },
    {
        "id": "C02",
        "category_label": "multi_concept",
        "query": "matching engine architecture microservices",
        "expected_paths": [
            "architecture/platform-overview.md",
            "order-management/matching-engine.md",
        ],
        "expected_chunk_keywords": ["matching", "microservices"],
        "description": "Crosses architecture + order-management domains",
    },
    {
        "id": "C03",
        "category_label": "multi_concept",
        "query": "market data feed order book depth",
        "expected_paths": [
            "market-data/feed-specification.md",
            "market-data/liquidity-metrics.md",
        ],
        "expected_chunk_keywords": ["order book", "depth", "feed"],
        "description": "Crosses two market-data documents",
    },

    # ── CATEGORY D: Tag-only discoverability ──────────────────────────
    {
        "id": "D01",
        "category_label": "tag_only",
        "query": "RTS25",
        "expected_paths": ["compliance/cnmv-reporting.md"],
        "expected_chunk_keywords": ["RTS 25"],
        "description": "RTS25 is in tags AND body — should match regardless",
    },
    {
        "id": "D02",
        "category_label": "tag_only",
        "query": "AML KYC verification",
        "expected_paths": ["members/onboarding.md"],
        "expected_chunk_keywords": ["KYC", "AML"],
        "description": "AML/KYC in tags and body",
    },
    {
        "id": "D03",
        "category_label": "tag_only",
        "query": "MAR regulation",
        "expected_paths": ["compliance/market-surveillance.md"],
        "expected_chunk_keywords": ["Market Abuse Regulation", "MAR"],
        "description": "MAR acronym in tags, expanded in body",
    },

    # ── CATEGORY E: Pre-H2 content (tests preamble capture) ──────────
    {
        "id": "E01",
        "category_label": "pre_h2_content",
        "query": "trade settlement clearing and settlement",
        "expected_paths": ["post-trade/settlement-lifecycle.md"],
        "expected_chunk_keywords": ["clearing and settlement"],
        "description": "Synonym from pre-H2 intro: 'clearing and settlement'",
    },
    {
        "id": "E02",
        "category_label": "pre_h2_content",
        "query": "multilateral trading facility MTF",
        "expected_paths": [
            "order-management/matching-engine.md",
            "post-trade/settlement-lifecycle.md",
        ],
        "expected_chunk_keywords": ["multilateral trading facility"],
        "description": "MTF mentioned in pre-H2 intros",
    },

    # ── CATEGORY F: Chunk ambiguity (generic headings) ────────────────
    {
        "id": "F01",
        "category_label": "chunk_ambiguity",
        "query": "settlement failed trade buy-in procedure",
        "expected_paths": ["post-trade/settlement-lifecycle.md"],
        "expected_chunk_keywords": ["failed", "buy-in"],
        "description": "Specific section within a multi-section document",
    },
    {
        "id": "F02",
        "category_label": "chunk_ambiguity",
        "query": "rate limiting API requests per second",
        "expected_paths": ["architecture/api-gateway.md"],
        "expected_chunk_keywords": ["rate limit", "429"],
        "description": "Specific section in gateway doc",
    },

    # ── CATEGORY G: Question-style queries (LLM typical) ─────────────
    {
        "id": "G01",
        "category_label": "question_style",
        "query": "what happens when a settlement fails",
        "expected_paths": ["post-trade/settlement-lifecycle.md"],
        "expected_chunk_keywords": ["failed", "buy-in"],
        "description": "Natural question that an LLM agent would generate",
    },
    {
        "id": "G02",
        "category_label": "question_style",
        "query": "how do members connect to the trading platform",
        "expected_paths": ["order-management/matching-engine.md"],
        "expected_chunk_keywords": ["FIX", "connect"],
        "description": "Natural question about member connectivity",
    },
    {
        "id": "G03",
        "category_label": "question_style",
        "query": "what are the incident severity levels",
        "expected_paths": ["operations/incident-management.md"],
        "expected_chunk_keywords": ["P1", "severity"],
        "description": "Natural question about operational procedures",
    },

    # ── CATEGORY H: Frontmatter enrichment (aliases/answers) ──────────
    {
        "id": "H01",
        "category_label": "frontmatter_enriched",
        "query": "liquidación de operaciones",
        "expected_paths": ["post-trade/settlement-lifecycle.md"],
        "expected_chunk_keywords": ["settlement"],
        "description": "Spanish alias only in frontmatter aliases field",
    },
    {
        "id": "H02",
        "category_label": "frontmatter_enriched",
        "query": "trade execution engine",
        "expected_paths": ["order-management/matching-engine.md"],
        "expected_chunk_keywords": ["matching"],
        "description": "Alias 'trade execution engine' only in frontmatter",
    },
    {
        "id": "H03",
        "category_label": "frontmatter_enriched",
        "query": "login system platform",
        "expected_paths": ["architecture/api-gateway.md"],
        "expected_chunk_keywords": ["authentication"],
        "description": "Alias 'login system' only in frontmatter, not in body",
    },
    {
        "id": "H04",
        "category_label": "frontmatter_enriched",
        "query": "market access application",
        "expected_paths": ["members/onboarding.md"],
        "expected_chunk_keywords": ["onboarding"],
        "description": "Alias 'market access application' only in frontmatter",
    },
    {
        "id": "H05",
        "category_label": "frontmatter_enriched",
        "query": "service disruption playbook",
        "expected_paths": ["operations/incident-management.md"],
        "expected_chunk_keywords": ["incident"],
        "description": "Alias 'service disruption playbook' only in frontmatter",
    },
    {
        "id": "H06",
        "category_label": "frontmatter_enriched",
        "query": "what KYC documentation is required",
        "expected_paths": ["members/onboarding.md"],
        "expected_chunk_keywords": ["KYC"],
        "description": "Exact question from answers field in frontmatter",
    },

    # ── CATEGORY I: Result diversity (tests deduplication) ────────────
    {
        "id": "I01",
        "category_label": "result_diversity",
        "query": "CNMV compliance reporting settlement",
        "expected_paths": [
            "compliance/cnmv-reporting.md",
            "post-trade/settlement-lifecycle.md",
            "compliance/market-surveillance.md",
        ],
        "expected_chunk_keywords": ["CNMV", "settlement", "reporting"],
        "description": "Should surface 3 distinct docs, not 3 chunks from the same doc",
    },
    {
        "id": "I02",
        "category_label": "result_diversity",
        "query": "platform services architecture gateway",
        "expected_paths": [
            "architecture/platform-overview.md",
            "architecture/api-gateway.md",
        ],
        "expected_chunk_keywords": ["microservices", "gateway"],
        "description": "Should surface both architecture docs, not multiple chunks from one",
    },
    {
        "id": "I03",
        "category_label": "result_diversity",
        "query": "member trading order access",
        "expected_paths": [
            "members/onboarding.md",
            "order-management/matching-engine.md",
        ],
        "expected_chunk_keywords": ["member", "order"],
        "description": "Should find both member and order docs with dedup",
    },

    # ── CATEGORY J: Cluster coherence (tests relation re-ranking) ─────
    {
        "id": "J01",
        "category_label": "cluster_coherence",
        "query": "settlement process regulatory",
        "expected_paths": [
            "post-trade/settlement-lifecycle.md",
            "compliance/cnmv-reporting.md",
        ],
        "expected_chunk_keywords": ["settlement", "CNMV"],
        "description": "Linked docs (settlement↔cnmv-reporting) should both rank in top results",
    },
    {
        "id": "J02",
        "category_label": "cluster_coherence",
        "query": "surveillance compliance alerts",
        "expected_paths": [
            "compliance/market-surveillance.md",
            "compliance/cnmv-reporting.md",
        ],
        "expected_chunk_keywords": ["surveillance", "alerts"],
        "description": "Linked docs (surveillance↔cnmv-reporting) should cluster together",
    },
]
