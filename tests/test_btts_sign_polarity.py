from pathlib import Path


def test_btts_summary_adjusts_market_probability_label():
    template = Path('football_predictor/templates/index.html').read_text(encoding='utf-8')
    assert 'const displayedMarket = marketProbYES != null' in template
    assert "label === 'YES' ? marketProbYES : 100 - marketProbYES" in template
    assert 'Market ${label}: ${displayedMarket.toFixed(1)}%' in template


def test_btts_summary_adjusts_xg_probability_label():
    template = Path('football_predictor/templates/index.html').read_text(encoding='utf-8')
    assert 'const displayedXG = xgProbYES != null' in template
    assert "label === 'YES' ? xgProbYES : 100 - xgProbYES" in template
    assert 'xG ${label}: ${displayedXG.toFixed(1)}%' in template
