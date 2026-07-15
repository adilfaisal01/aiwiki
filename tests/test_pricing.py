def test_pricing_page_renders_four_plans(client):
    response = client.get("/pricing")
    assert response.status_code == 200
    assert "pricing-grid" in response.text
    assert 'class="pricing-card' in response.text
    assert response.text.count('class="pricing-plan-name"') == 4
    assert "pricing-card-featured" in response.text
    assert "Free" in response.text
    assert "Pay as you go" in response.text
    assert "Pro" in response.text
    assert "Team" in response.text
    assert "server-side invokes" in response.text.lower() or "Server-Invokes" in response.text


def test_pricing_page_has_billing_toggle(client):
    response = client.get("/pricing")
    assert response.status_code == 200
    assert 'id="pricing-billing-toggle"' in response.text
    assert 'data-billing="monthly"' in response.text
    assert 'data-billing="annual"' in response.text
    assert 'data-annual="€120"' in response.text or 'data-annual="120 €"' in response.text
    assert "pricing_billing.js" in response.text


def test_pricing_plans_include_annual_and_payg():
    from web.pricing import pricing_plans

    plans = {plan["id"]: plan for plan in pricing_plans("en")}
    assert plans["payg"]["usage_based"] is True
    assert plans["payg"]["price_monthly"] == "€0.005"
    assert plans["payg"]["period_monthly"] == "per server invoke"
    assert plans["pro"]["price_monthly"] == "€12"
    assert plans["pro"]["price_annual"] == "€120"
    assert plans["pro"]["annual_equiv"] == "€10 / month, billed annually"
    assert plans["team"]["price_annual"] == "€490"


def test_header_links_to_pricing(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'href="/pricing"' in response.text
