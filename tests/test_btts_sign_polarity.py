from pathlib import Path


def test_btts_summary_inverts_yes_probability_for_no_signal():
    template = Path("football_predictor/templates/index.html").read_text(encoding="utf-8")
    assert "(leaningYes ? market.yes_probability : (1 - market.yes_probability)) * 100" in template
    assert "(leaningYes ? xgModel.yes_probability : (1 - xgModel.yes_probability)) * 100" in template

    summary_block = template.split("function buildBttsSummaryHtml", 1)[1]
    summary_block = summary_block.split("return `", 1)[0]

    assert "marketPercent.toFixed(1)" in summary_block
    assert "xgPercent.toFixed(1)" in summary_block
