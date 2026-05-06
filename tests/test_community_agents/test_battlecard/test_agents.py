from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from swarm_core.base import AgentContext, AgentStatus

# ── fixtures ───────────────────────────────────────────────────────────────────

HOMEPAGE_HTML = """
<html>
<head>
  <title>Acme Corp — Ship faster</title>
  <meta name="description" content="Acme helps teams ship 10x faster.">
  <meta property="og:title" content="Acme Corp">
  <meta property="og:description" content="Ship software faster with Acme.">
  <meta property="og:site_name" content="Acme">
  <script type="application/ld+json">
  {"@type": "Organization", "name": "Acme Corp", "foundingDate": "2019",
   "description": "Ship faster", "sameAs": ["https://twitter.com/acme"]}
  </script>
</head>
<body>
  <header>
    <nav>
      <a href="/pricing">Pricing</a>
      <a href="/about">About</a>
      <a href="/customers">Customers</a>
      <a href="/careers">Careers</a>
      <a href="/blog">Blog</a>
    </nav>
  </header>
  <section class="logos">
    <img alt="Stripe" src="stripe.png">
    <img alt="Notion" src="notion.png">
    <img alt="Figma" src="figma.png">
  </section>
  <blockquote class="testimonial">
    <p>Acme saved us 40 hours a week.</p>
    <cite>Jane Doe, CTO at Startup Inc</cite>
  </blockquote>
  <footer>
    <a href="https://twitter.com/acmecorp">Twitter</a>
    <a href="https://linkedin.com/company/acme-corp">LinkedIn</a>
    <a href="https://github.com/acme">GitHub</a>
    <a href="https://youtube.com/@acmecorp">YouTube</a>
  </footer>
  <script src="https://connect.facebook.net/en_US/fbevents.js"></script>
  <script src="https://www.googletagmanager.com/gtm.js?id=GTM-XXXXX"></script>
  <script src="https://js.hs-scripts.com/12345.js"></script>
</body>
</html>
"""

PRICING_HTML = """
<html><body>
  <h1>Simple pricing for every team</h1>
  <div class="card"><h3>Free</h3><p>$0/month</p></div>
  <div class="card"><h3>Pro</h3><p>$29/month per user</p></div>
  <div class="card"><h3>Enterprise</h3><p>Contact sales</p></div>
</body></html>
"""

CAREERS_HTML = """
<html><body>
  <h1>Join our team</h1>
  <p>We're a fast-growing team. Join a rocket ship!</p>
  <li class="job">Senior Backend Engineer - Python, Kubernetes, AWS</li>
  <li class="job">Frontend Developer - React, TypeScript</li>
  <li class="job">Sales Development Representative</li>
  <li class="job">Content Marketing Manager</li>
  <li class="job">Data Analyst - dbt, Snowflake</li>
  <li class="job">Customer Success Manager</li>
</body></html>
"""

CUSTOMERS_HTML = """
<html><body>
  <section class="logos">
    <img alt="Atlassian" src="a.png">
    <img alt="GitHub" src="g.png">
  </section>
  <blockquote class="testimonial">
    <p>Best CI/CD tool we've used.</p>
    <cite>Bob Smith, VP Engineering at BigCo</cite>
  </blockquote>
  <article class="case-study">How Atlassian cut deploy times by 60%</article>
  <article class="case-study">GitHub's path to 99.99% uptime</article>
</body></html>
"""


# ── PageDiscoveryAgent ─────────────────────────────────────────────────────────


def test_page_discovery_categorizes_nav_links():
    from community_agents.battlecard.agents.page_discovery import PageDiscoveryAgent

    with patch("community_agents.battlecard.agents.page_discovery.fetch", return_value=(None, {})):
        agent = PageDiscoveryAgent()
        ctx = AgentContext(input={"url": "https://acme.com", "html": HOMEPAGE_HTML, "headers": {}})
        result = agent.run(ctx)

    assert result.status == AgentStatus.PASS
    pages = result.payload["discovered_pages"]
    assert "pricing" in pages
    assert "careers" in pages
    assert "blog" in pages


def test_page_discovery_missing_url_returns_exception():
    from community_agents.battlecard.agents.page_discovery import PageDiscoveryAgent

    agent = PageDiscoveryAgent()
    result = agent.run(AgentContext(input={"html": "<html></html>"}))
    assert result.status == AgentStatus.EXCEPTION


def test_page_discovery_non_dict_returns_exception():
    from community_agents.battlecard.agents.page_discovery import PageDiscoveryAgent

    result = PageDiscoveryAgent().run(AgentContext(input="https://acme.com"))
    assert result.status == AgentStatus.EXCEPTION


# ── CompanyProfileAgent ────────────────────────────────────────────────────────


def test_company_profile_extracts_og_and_jsonld():
    from community_agents.battlecard.agents.company_profile import CompanyProfileAgent

    ctx = AgentContext(input={"url": "https://acme.com", "html": HOMEPAGE_HTML, "headers": {}})
    result = CompanyProfileAgent().run(ctx)

    assert result.status == AgentStatus.PASS
    assert result.payload["name"] == "Acme Corp"
    assert result.payload["founded"] == "2019"
    assert isinstance(result.payload["social_links"], list)


def test_company_profile_empty_html_returns_nd():
    from community_agents.battlecard.agents.company_profile import CompanyProfileAgent

    ctx = AgentContext(input={"url": "https://acme.com", "html": "", "headers": {}})
    result = CompanyProfileAgent().run(ctx)
    assert result.status == AgentStatus.PASS
    assert result.payload["name"]["data"] is None


def test_company_profile_non_dict_returns_exception():
    from community_agents.battlecard.agents.company_profile import CompanyProfileAgent

    result = CompanyProfileAgent().run(AgentContext(input="raw string"))
    assert result.status == AgentStatus.EXCEPTION


# ── TechStackAgent ─────────────────────────────────────────────────────────────


def test_tech_stack_detects_marketing_pixels():
    from community_agents.battlecard.agents.tech_stack import TechStackAgent

    ctx = AgentContext(input={"html": HOMEPAGE_HTML, "headers": {"Server": "nginx"}})
    result = TechStackAgent().run(ctx)

    assert result.status == AgentStatus.PASS
    assert "Meta (Facebook) Ads" in result.payload["marketing_tools"]
    assert "Google Tag Manager" in result.payload["marketing_tools"]
    assert "HubSpot Marketing" in result.payload["marketing_tools"]
    assert "Nginx" in result.payload["tech_stack"]


def test_tech_stack_infers_strategy():
    from community_agents.battlecard.agents.tech_stack import TechStackAgent

    ctx = AgentContext(input={"html": HOMEPAGE_HTML, "headers": {}})
    result = TechStackAgent().run(ctx)

    assert "Paid advertising" in result.payload["marketing_strategy_signals"]


def test_tech_stack_empty_html_returns_empty_lists():
    from community_agents.battlecard.agents.tech_stack import TechStackAgent

    result = TechStackAgent().run(AgentContext(input={"html": "", "headers": {}}))
    assert result.status == AgentStatus.PASS
    assert result.payload["tech_stack"] == []
    assert result.payload["marketing_tools"] == []


# ── PricingAgent ───────────────────────────────────────────────────────────────


def test_pricing_extracts_tiers_and_model():
    from community_agents.battlecard.agents.pricing_extractor import PricingAgent

    ctx = AgentContext(input={"html": PRICING_HTML})
    result = PricingAgent().run(ctx)

    assert result.status == AgentStatus.PASS
    assert "Free" in result.payload["tiers"]
    assert "Pro" in result.payload["tiers"]
    assert "Enterprise" in result.payload["tiers"]
    assert result.payload["free_tier"] is True
    assert result.payload["contact_sales"] is True
    assert result.payload["pricing_model"] == "per_seat"


def test_pricing_empty_html_returns_nd():
    from community_agents.battlecard.agents.pricing_extractor import PricingAgent

    result = PricingAgent().run(AgentContext(input={"html": ""}))
    assert result.status == AgentStatus.PASS
    assert result.payload["tiers"]["data"] is None


def test_pricing_non_dict_returns_exception():
    from community_agents.battlecard.agents.pricing_extractor import PricingAgent

    result = PricingAgent().run(AgentContext(input="pricing"))
    assert result.status == AgentStatus.EXCEPTION


# ── ClientEvidenceAgent ────────────────────────────────────────────────────────


def test_client_evidence_extracts_logos_and_testimonials():
    from community_agents.battlecard.agents.client_evidence import ClientEvidenceAgent

    ctx = AgentContext(input={
        "homepage_html": HOMEPAGE_HTML,
        "customers_html": CUSTOMERS_HTML,
        "case_studies_html": None,
    })
    result = ClientEvidenceAgent().run(ctx)

    assert result.status == AgentStatus.PASS
    clients = result.payload["known_clients"]
    assert isinstance(clients, list)
    assert any("Stripe" in c or "Atlassian" in c for c in clients)


def test_client_evidence_empty_html_returns_nd():
    from community_agents.battlecard.agents.client_evidence import ClientEvidenceAgent

    result = ClientEvidenceAgent().run(AgentContext(input={
        "homepage_html": "", "customers_html": None, "case_studies_html": None,
    }))
    assert result.status == AgentStatus.PASS
    assert result.payload["known_clients"]["data"] is None


# ── CareerSignalsAgent ─────────────────────────────────────────────────────────


def test_career_signals_counts_roles_and_infers_size():
    from community_agents.battlecard.agents.career_signals import CareerSignalsAgent

    ctx = AgentContext(input={"html": CAREERS_HTML, "base_url": "https://acme.com"})
    result = CareerSignalsAgent().run(ctx)

    assert result.status == AgentStatus.PASS
    assert isinstance(result.payload["open_roles"], int)
    assert result.payload["open_roles"] > 0
    assert "Engineering" in result.payload["departments"]
    assert "python" in result.payload["tech_signals"] or "react" in result.payload["tech_signals"]
    assert result.payload["growth_signal"] == "High-growth / actively scaling"


def test_career_signals_empty_html_returns_nd():
    from community_agents.battlecard.agents.career_signals import CareerSignalsAgent

    result = CareerSignalsAgent().run(AgentContext(input={"html": "", "base_url": "https://acme.com"}))
    assert result.status == AgentStatus.PASS
    assert result.payload["open_roles"]["data"] is None


# ── SocialPresenceAgent ────────────────────────────────────────────────────────


def test_social_presence_detects_profiles():
    from community_agents.battlecard.agents.social_presence import SocialPresenceAgent

    with patch("community_agents.battlecard.agents.social_presence.fetch", return_value=(None, {})):
        ctx = AgentContext(input={"html": HOMEPAGE_HTML, "domain": "acme.com"})
        result = SocialPresenceAgent().run(ctx)

    assert result.status == AgentStatus.PASS
    profiles = result.payload["profiles"]
    assert isinstance(profiles, dict)
    assert "twitter" in profiles
    assert "linkedin" in profiles
    assert "github" in profiles


def test_social_presence_empty_html_returns_nd():
    from community_agents.battlecard.agents.social_presence import SocialPresenceAgent

    result = SocialPresenceAgent().run(AgentContext(input={"html": "", "domain": "acme.com"}))
    assert result.status == AgentStatus.PASS
    assert result.payload["profiles"]["data"] is None


# ── RedditSignalsAgent ─────────────────────────────────────────────────────────


def test_reddit_signals_parses_posts():
    from community_agents.battlecard.agents.reddit_signals import RedditSignalsAgent

    fake_response = {
        "data": {
            "children": [
                {"data": {"title": "Acme is amazing and easy to use", "score": 120, "subreddit": "devops", "url": "", "num_comments": 5}},
                {"data": {"title": "Acme is terrible and broken", "score": 10, "subreddit": "programming", "url": "", "num_comments": 2}},
                {"data": {"title": "Love using Acme for deployments", "score": 88, "subreddit": "devops", "url": "", "num_comments": 8}},
            ]
        }
    }

    with patch("community_agents.battlecard.agents.reddit_signals.fetch_json", return_value=fake_response):
        result = RedditSignalsAgent().run(AgentContext(input={"company_name": "Acme", "domain": "acme.com"}))

    assert result.status == AgentStatus.PASS
    reddit = result.payload["reddit"]
    assert reddit["mention_count"] == 3
    assert reddit["sentiment"] in ("positive", "mixed", "negative", "neutral")
    assert "devops" in reddit["top_subreddits"]


def test_reddit_signals_no_data_returns_nd():
    from community_agents.battlecard.agents.reddit_signals import RedditSignalsAgent

    with patch("community_agents.battlecard.agents.reddit_signals.fetch_json", return_value=None):
        result = RedditSignalsAgent().run(AgentContext(input={"company_name": "Acme"}))

    assert result.status == AgentStatus.PASS
    assert result.payload["reddit"]["data"] is None


def test_reddit_signals_missing_input_returns_exception():
    from community_agents.battlecard.agents.reddit_signals import RedditSignalsAgent

    result = RedditSignalsAgent().run(AgentContext(input={}))
    assert result.status == AgentStatus.EXCEPTION


# ── ReviewAggregatorAgent ──────────────────────────────────────────────────────


def test_review_aggregator_returns_nd_on_fetch_failure():
    from community_agents.battlecard.agents.review_aggregator import ReviewAggregatorAgent

    with patch("community_agents.battlecard.agents.review_aggregator.fetch", return_value=(None, {})):
        result = ReviewAggregatorAgent().run(AgentContext(input={"company_name": "Acme", "domain": "acme.com"}))

    assert result.status == AgentStatus.PASS
    assert result.payload["g2"]["data"] is None
    assert result.payload["capterra"]["data"] is None


def test_review_aggregator_extracts_rating_from_html():
    from community_agents.battlecard.agents.review_aggregator import ReviewAggregatorAgent

    fake_html = """
    <html><body>
      <div class="product-card">
        <span>4.7 / 5 based on 1,230 reviews</span>
        <ul><li>Easy to set up</li><li>Great support</li></ul>
      </div>
    </body></html>
    """
    with patch("community_agents.battlecard.agents.review_aggregator.fetch", return_value=(fake_html, {})):
        result = ReviewAggregatorAgent().run(AgentContext(input={"company_name": "Acme", "domain": "acme.com"}))

    assert result.status == AgentStatus.PASS
    assert result.payload["g2"]["rating"] == "4.7"
    assert result.payload["g2"]["review_count"] == "1230"


# ── GoogleReviewsAgent ─────────────────────────────────────────────────────────


def test_google_reviews_returns_nd_on_blocked():
    from community_agents.battlecard.agents.google_reviews import GoogleReviewsAgent

    with patch("community_agents.battlecard.agents.google_reviews.fetch", return_value=(None, {})):
        result = GoogleReviewsAgent().run(AgentContext(input={"company_name": "Acme", "domain": "acme.com"}))

    assert result.status == AgentStatus.PASS
    assert result.payload["google_reviews"]["data"] is None


def test_google_reviews_extracts_rating_if_present():
    from community_agents.battlecard.agents.google_reviews import GoogleReviewsAgent

    fake_html = "<html><body>Acme Corp · 4.8 stars · 320 reviews on Google</body></html>"
    with patch("community_agents.battlecard.agents.google_reviews.fetch", return_value=(fake_html, {})):
        result = GoogleReviewsAgent().run(AgentContext(input={"company_name": "Acme", "domain": "acme.com"}))

    assert result.status == AgentStatus.PASS
    assert result.payload["google_reviews"]["rating"] == "4.8"


# ── BattlecardComposerAgent ────────────────────────────────────────────────────


def _make_full_input() -> dict:
    return {
        "user_context": {
            "company_name": "MyBiz",
            "what_you_do": "We provide transparent deployment automation",
            "icp": "Mid-market engineering teams",
            "differentiators": ["transparent pricing", "free tier", "offline-first"],
        },
        "company": {"name": "Acme Corp", "tagline": "Ship faster", "url": "https://acme.com", "founded": "2019"},
        "tech_stack": {"tech_stack": ["React", "Nginx"], "marketing_tools": ["Google Tag Manager"], "marketing_strategy_signals": ["Paid advertising"]},
        "pricing": {"pricing_model": "contact_sales", "tiers": ["Enterprise"], "free_tier": False, "contact_sales": True},
        "clients": {"known_clients": ["Stripe", "Notion"], "testimonials": [], "case_study_count": 3},
        "reviews": {"g2": {"rating": "4.5", "review_count": "800"}, "capterra": {"data": None, "note": "Not enough public data"}},
        "google_reviews": {"google_reviews": {"data": None, "note": "Not enough public data"}},
        "social": {"profiles": {"twitter": {"handle": "acmecorp", "url": "https://twitter.com/acmecorp"}}},
        "reddit": {"reddit": {"mention_count": 10, "sentiment": "positive", "top_subreddits": ["devops"]}},
        "hn": {"hn": {"story_count": 5, "sentiment": "mixed", "key_themes": ["pricing / cost concerns"]}},
        "careers": {"open_roles": 15, "departments": {"Engineering": 8, "Sales": 3}, "size_estimate": "Mid-size (50–300 employees)", "growth_signal": "High-growth / actively scaling"},
        "web_search": {"results": {}, "engine": "none", "hits": 0, "misses": 0},
    }


def test_composer_assembles_full_battlecard():
    from community_agents.battlecard.agents.battlecard_composer import BattlecardComposerAgent

    with patch("community_agents.battlecard.agents.battlecard_composer._OLLAMA_OK", False):
        result = BattlecardComposerAgent().run(AgentContext(input=_make_full_input()))

    assert result.status == AgentStatus.PASS
    card = result.payload
    assert card["snapshot"]["name"] == "Acme Corp"
    assert card["product_intel"]["pricing_model"] == "contact_sales"
    assert "Stripe" in card["market_position"]["known_clients"]
    assert isinstance(card["our_angle"], list)
    assert len(card["our_angle"]) > 0


def test_composer_our_angle_detects_contact_sales_vs_transparent():
    from community_agents.battlecard.agents.battlecard_composer import BattlecardComposerAgent

    inp = _make_full_input()
    with patch("community_agents.battlecard.agents.battlecard_composer._OLLAMA_OK", False):
        result = BattlecardComposerAgent().run(AgentContext(input=inp))

    angles = result.payload["our_angle"]
    assert any(
        "transparent" in a.get("angle", "").lower() or "pricing" in a.get("angle", "").lower()
        for a in angles
    )


def test_composer_angle_dicts_have_required_keys():
    from community_agents.battlecard.agents.battlecard_composer import BattlecardComposerAgent

    with patch("community_agents.battlecard.agents.battlecard_composer._OLLAMA_OK", False):
        result = BattlecardComposerAgent().run(AgentContext(input=_make_full_input()))

    for angle in result.payload["our_angle"]:
        assert "angle" in angle
        assert "evidence" in angle
        assert "talk_track" in angle


def test_composer_meta_block_present():
    from community_agents.battlecard.agents.battlecard_composer import BattlecardComposerAgent

    with patch("community_agents.battlecard.agents.battlecard_composer._OLLAMA_OK", False):
        result = BattlecardComposerAgent().run(AgentContext(input=_make_full_input()))

    meta = result.payload.get("meta", {})
    assert meta.get("company") == "Acme Corp"
    assert meta.get("confidence") in ("high", "medium", "low")
    assert "analyzed_at" in meta


def test_composer_non_dict_returns_exception():
    from community_agents.battlecard.agents.battlecard_composer import BattlecardComposerAgent

    result = BattlecardComposerAgent().run(AgentContext(input="not a dict"))
    assert result.status == AgentStatus.EXCEPTION


# ── QueryPlannerAgent ──────────────────────────────────────────────────────────


def test_query_planner_generates_14_template_queries():
    from community_agents.battlecard.agents.query_planner import QueryPlannerAgent

    with patch("community_agents.battlecard.agents.query_planner._OLLAMA_OK", False):
        result = QueryPlannerAgent().run(AgentContext(input={"company_name": "Acme"}))

    assert result.status == AgentStatus.PASS
    queries = result.payload["queries"]
    assert len(queries) == 14
    ids = [q["id"] for q in queries]
    assert "snapshot" in ids
    assert "pricing" in ids
    assert "competitors" in ids
    assert "controversies" in ids


def test_query_planner_interpolates_company_name():
    from community_agents.battlecard.agents.query_planner import QueryPlannerAgent

    with patch("community_agents.battlecard.agents.query_planner._OLLAMA_OK", False):
        result = QueryPlannerAgent().run(AgentContext(input={"company_name": "Acme"}))

    questions = [q["q"] for q in result.payload["queries"]]
    assert all("Acme" in q for q in questions)


def test_query_planner_falls_back_to_domain():
    from community_agents.battlecard.agents.query_planner import QueryPlannerAgent

    with patch("community_agents.battlecard.agents.query_planner._OLLAMA_OK", False):
        result = QueryPlannerAgent().run(AgentContext(input={"domain": "acme.com"}))

    assert result.status == AgentStatus.PASS
    questions = [q["q"] for q in result.payload["queries"]]
    assert all("acme" in q for q in questions)


def test_query_planner_missing_company_returns_exception():
    from community_agents.battlecard.agents.query_planner import QueryPlannerAgent

    result = QueryPlannerAgent().run(AgentContext(input={}))
    assert result.status == AgentStatus.EXCEPTION


def test_query_planner_non_dict_returns_exception():
    from community_agents.battlecard.agents.query_planner import QueryPlannerAgent

    result = QueryPlannerAgent().run(AgentContext(input="Acme"))
    assert result.status == AgentStatus.EXCEPTION


def test_query_planner_adds_llm_queries_when_ollama_ok():
    from community_agents.battlecard.agents.query_planner import QueryPlannerAgent

    mock_resp = MagicMock()
    mock_resp.__getitem__ = lambda self, key: {"message": {"content": "Q1?\nQ2?\nQ3?"}}.get(key)

    with patch("community_agents.battlecard.agents.query_planner._OLLAMA_OK", True), \
         patch("community_agents.battlecard.agents.query_planner._ollama") as mock_ollama:
        mock_ollama.chat.return_value = {"message": {"content": "Q1?\nQ2?\nQ3?"}}
        result = QueryPlannerAgent().run(AgentContext(input={
            "company_name": "Acme",
            "user_context": {"what_you_do": "CI/CD tooling", "differentiators": ["fast deploys"]},
        }))

    assert result.status == AgentStatus.PASS
    queries = result.payload["queries"]
    assert len(queries) == 17  # 14 templates + 3 LLM
    custom_ids = [q["id"] for q in queries if q["id"].startswith("custom_")]
    assert len(custom_ids) == 3


# ── WebSearchAgent ─────────────────────────────────────────────────────────────


_SAMPLE_QUERIES = [
    {"id": "snapshot", "q": "What is Acme?"},
    {"id": "pricing", "q": "What is Acme's pricing?"},
]


def test_web_search_uses_perplexity_when_key_set():
    from community_agents.battlecard.agents.web_search import WebSearchAgent

    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json.return_value = {
        "choices": [{"message": {"content": "Acme was founded in 2019."}}],
        "citations": ["https://example.com"],
    }

    with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}), \
         patch("community_agents.battlecard.agents.web_search.requests.post", return_value=fake_resp):
        result = WebSearchAgent().run(AgentContext(input={
            "queries": _SAMPLE_QUERIES,
            "company_name": "Acme",
        }))

    assert result.status == AgentStatus.PASS
    assert result.payload["engine"] == "Perplexity"
    assert result.payload["hits"] == 2
    assert result.payload["results"]["snapshot"]["source"] == "perplexity"


def test_web_search_falls_back_to_ddg_without_key():
    from community_agents.battlecard.agents.web_search import WebSearchAgent

    def fake_fetch_json(url: str) -> dict:
        return {
            "AbstractText": "Acme Corp makes deployment tools.",
            "AbstractURL": "https://acme.com",
        }

    with patch.dict("os.environ", {}, clear=True), \
         patch("community_agents.battlecard.agents.web_search.fetch_json", side_effect=fake_fetch_json):
        result = WebSearchAgent().run(AgentContext(input={
            "queries": _SAMPLE_QUERIES,
            "company_name": "Acme",
        }))

    assert result.status == AgentStatus.PASS
    assert result.payload["engine"] == "DuckDuckGo"
    assert result.payload["hits"] == 2
    assert result.payload["results"]["snapshot"]["source"] == "duckduckgo"


def test_web_search_counts_misses_on_empty_ddg_response():
    from community_agents.battlecard.agents.web_search import WebSearchAgent

    with patch.dict("os.environ", {}, clear=True), \
         patch("community_agents.battlecard.agents.web_search.fetch_json", return_value={}):
        result = WebSearchAgent().run(AgentContext(input={
            "queries": _SAMPLE_QUERIES,
            "company_name": "Acme",
        }))

    assert result.status == AgentStatus.PASS
    assert result.payload["hits"] == 0
    assert result.payload["misses"] == 2
    assert result.payload["results"]["snapshot"]["data"] is None


def test_web_search_no_queries_returns_exception():
    from community_agents.battlecard.agents.web_search import WebSearchAgent

    result = WebSearchAgent().run(AgentContext(input={"queries": [], "company_name": "Acme"}))
    assert result.status == AgentStatus.EXCEPTION


def test_web_search_non_dict_returns_exception():
    from community_agents.battlecard.agents.web_search import WebSearchAgent

    result = WebSearchAgent().run(AgentContext(input="search for Acme"))
    assert result.status == AgentStatus.EXCEPTION
