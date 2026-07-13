"""Pricing page data and route."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from core import config
from web.i18n import t
from web.template_env import render_template

router = APIRouter(tags=["pricing"])

PLAN_ORDER = ("free", "payg", "pro", "team")


def pricing_plans(locale: str) -> list[dict]:
    plans = []
    for plan_id in PLAN_ORDER:
        prefix = f"pricing.plan.{plan_id}"
        features = []
        index = 1
        while True:
            key = f"{prefix}.feature.{index}"
            label = t(locale, key)
            if label == key:
                break
            features.append(label)
            index += 1

        cta_href = t(locale, f"{prefix}.cta_href")
        if cta_href == f"{prefix}.cta_href":
            cta_href = "/register-agent"
        if cta_href == "__donation__":
            cta_href = config.DONATION_URL or "/register-agent"

        annual_equiv = t(locale, f"{prefix}.annual_equiv")
        if annual_equiv == f"{prefix}.annual_equiv":
            annual_equiv = ""

        plans.append({
            "id": plan_id,
            "name": t(locale, f"{prefix}.name"),
            "price_monthly": t(locale, f"{prefix}.price_monthly"),
            "price_annual": t(locale, f"{prefix}.price_annual"),
            "period_monthly": t(locale, f"{prefix}.period_monthly"),
            "period_annual": t(locale, f"{prefix}.period_annual"),
            "annual_equiv": annual_equiv,
            "description": t(locale, f"{prefix}.description"),
            "features": features,
            "cta_label": t(locale, f"{prefix}.cta"),
            "cta_href": cta_href,
            "featured": plan_id == "pro",
            "usage_based": plan_id == "payg",
        })
    return plans


@router.get("/pricing", response_class=HTMLResponse)
async def pricing_page(request: Request):
    locale = getattr(request.state, "locale", "en")
    return render_template(
        request,
        "pricing.html",
        {
            "plans": pricing_plans(locale),
            "pricing_note": t(locale, "pricing.footer_note"),
            "billing_monthly_label": t(locale, "pricing.billing.monthly"),
            "billing_annual_label": t(locale, "pricing.billing.annual"),
            "billing_save_label": t(locale, "pricing.billing.save"),
            "billing_toggle_label": t(locale, "pricing.billing.toggle_label"),
        },
    )
