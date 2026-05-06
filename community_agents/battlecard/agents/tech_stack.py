from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup

from swarm_core.base import AgentContext, AgentResult, BaseAgent
from swarm_core.utils import get_logger

logger = get_logger(__name__)

_TECH: dict[str, list[str]] = {
    "React": ["react.min.js", "react-dom", "/_next/", "reactjs.org"],
    "Vue.js": ["vue.min.js", "vue@", "vuejs.org"],
    "Angular": ["angular.min.js", "ng-version=", "@angular/core"],
    "Next.js": ["/_next/static", "_next/data"],
    "Nuxt.js": ["/_nuxt/", "__nuxt"],
    "Gatsby": ["/gatsby-", "gatsby-image"],
    "WordPress": ["/wp-content/", "/wp-includes/"],
    "Shopify": ["cdn.shopify.com", "shopify.com/s/files"],
    "Webflow": ["webflow.com/css", "uploads-ssl.webflow.com"],
    "Wix": ["wixsite.com", "wix-warmup-data"],
    "Squarespace": ["squarespace.com", "squarespace-cdn.com"],
    "Ghost": ["/ghost/api/", "ghost.js"],
    "Framer": ["framer.com/sites"],
    "Stripe": ["js.stripe.com"],
    "Paddle": ["paddle.com/js", "cdn.paddle.com"],
    "Chargebee": ["chargebee.com/js"],
    "Intercom": ["widget.intercom.io", "intercomcdn.com"],
    "Drift": ["js.driftt.com", "drift.com/core.js"],
    "Zendesk": ["static.zdassets.com"],
    "Crisp": ["client.crisp.chat"],
    "Salesforce": ["salesforce.com", "force.com"],
    "HubSpot CRM": ["hs-scripts.com", "hubspot.com/js/beta"],
}

_MARKETING: dict[str, list[str]] = {
    "Google Analytics": ["gtag/js?id=G-", "analytics.js", "ga('create'"],
    "Google Tag Manager": ["googletagmanager.com/gtm.js", "GTM-"],
    "Google Ads": ["gtag/js?id=AW-", "google_conversion"],
    "Meta (Facebook) Ads": ["connect.facebook.net/en_US/fbevents.js", "fbq('init'"],
    "LinkedIn Ads": ["snap.licdn.com/li.lms-analytics", "_linkedin_partner"],
    "Twitter/X Ads": ["static.ads-twitter.com/uwt.js", "twq('init'"],
    "TikTok Ads": ["analytics.tiktok.com/i18n/pixel"],
    "Pinterest Ads": ["assets.pinterest.com/js/pinit.js", "pintrk('load'"],
    "HubSpot Marketing": ["js.hs-scripts.com", "hs-analytics.net"],
    "Marketo": ["munchkin.marketo.net"],
    "Pardot": ["pi.pardot.com"],
    "Segment": ["cdn.segment.com/analytics.js"],
    "Mixpanel": ["cdn.mxpnl.com", "mixpanel.init("],
    "Hotjar": ["static.hotjar.com", "hj('create'"],
    "FullStory": ["fullstory.com/s/fs.js"],
    "Amplitude": ["cdn.amplitude.com"],
    "Heap": ["cdn.heapanalytics.com"],
    "PostHog": ["app.posthog.com", "posthog.js"],
    "Klaviyo": ["static.klaviyo.com", "klaviyo.com/onsite"],
    "ActiveCampaign": ["activehosted.com/f/"],
    "Intercom Marketing": ["intercomcdn.com", "intercom.io/widget"],
}


class TechStackAgent(BaseAgent):
    """
    Detects tech stack and marketing tools from page HTML and response headers.

    Input: ``{"html": "...", "headers": {"Server": "nginx", ...}}``
    """

    name = "tech_stack"
    description = "Detects frameworks, SaaS tools, and marketing pixels from HTML and headers."

    def run(self, context: AgentContext) -> AgentResult:
        return self._deterministic_logic(context)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        if not isinstance(context.input, dict):
            return AgentResult.exception(agent=self.name, reason="Input must be a dict with 'html'")

        html = context.input.get("html") or ""
        headers = context.input.get("headers") or {}
        raw = html.lower()

        tech = self._scan(raw, _TECH)
        marketing = self._scan(raw, _MARKETING)
        header_hints = self._from_headers(headers)
        tech = list({*tech, *header_hints})

        logger.info("tech_stack: found %d tech, %d marketing tools", len(tech), len(marketing))
        return AgentResult.passed(
            agent=self.name,
            payload={
                "tech_stack": sorted(tech),
                "marketing_tools": sorted(marketing),
                "marketing_strategy_signals": self._infer_strategy(marketing),
            },
        )

    def _scan(self, raw_html: str, patterns: dict[str, list[str]]) -> list[str]:
        found = []
        for name, signals in patterns.items():
            if any(s.lower() in raw_html for s in signals):
                found.append(name)
        return found

    def _from_headers(self, headers: dict[str, str]) -> list[str]:
        found = []
        server = headers.get("Server", headers.get("server", "")).lower()
        powered = headers.get("X-Powered-By", headers.get("x-powered-by", "")).lower()
        if "nginx" in server:
            found.append("Nginx")
        if "apache" in server:
            found.append("Apache")
        if "cloudflare" in server:
            found.append("Cloudflare")
        if "php" in powered:
            found.append("PHP")
        if "express" in powered:
            found.append("Express.js (Node)")
        return found

    def _infer_strategy(self, marketing_tools: list[str]) -> list[str]:
        signals = []
        if any("Ads" in t or "Pixel" in t for t in marketing_tools):
            signals.append("Paid advertising")
        if any(t in marketing_tools for t in ["HubSpot Marketing", "Marketo", "Pardot", "ActiveCampaign"]):
            signals.append("Marketing automation / inbound")
        if any(t in marketing_tools for t in ["Segment", "Mixpanel", "Amplitude", "Heap", "PostHog"]):
            signals.append("Product-led growth / analytics-heavy")
        if any(t in marketing_tools for t in ["Hotjar", "FullStory"]):
            signals.append("CRO / UX optimization")
        if "Klaviyo" in marketing_tools:
            signals.append("Email marketing")
        return signals
