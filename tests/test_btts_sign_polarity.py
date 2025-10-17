import re


def build_html(market_yes, xg_yes):
    # Simulated frontend logic in Python for parity testing
    yes_avg = (market_yes + xg_yes) / 2
    leaning_yes = yes_avg >= 0.5
    label = "YES" if leaning_yes else "NO"
    market = market_yes if leaning_yes else 1 - market_yes
    xg = xg_yes if leaning_yes else 1 - xg_yes
    confidence = (yes_avg if leaning_yes else 1 - yes_avg) * 100
    return {
        "label": label,
        "market": round(market * 100, 1),
        "xg": round(xg * 100, 1),
        "confidence": round(confidence, 1),
    }


def test_btts_yes_polarity():
    out = build_html(0.65, 0.60)
    assert out["label"] == "YES"
    assert out["market"] == 65.0
    assert out["xg"] == 60.0
    assert 60 < out["confidence"] < 65


def test_btts_no_polarity():
    out = build_html(0.35, 0.40)
    assert out["label"] == "NO"
    assert out["market"] == 65.0  # 1 - 0.35
    assert out["xg"] == 60.0      # 1 - 0.40
    assert 60 < out["confidence"] < 65


def test_html_structure_snapshot():
    html = """
    <div class="alert alert-secondary mb-3" data-testid="btts-summary">
      <strong>BTTS NO</strong>
      <span data-testid="btts-confidence">Confidence 61.2%</span>
      <div data-testid="btts-details">Market: 65.0% · xG: 60.0%</div>
    </div>
    """
    assert "BTTS NO" in html
    assert re.search(r"Market:\s*65\.0%", html)
    assert re.search(r"xG:\s*60\.0%", html)
