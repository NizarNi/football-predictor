from pathlib import Path


def test_btts_progress_loader_present():
    template = Path('football_predictor/templates/index.html').read_text(encoding='utf-8')
    assert 'btts-progress' in template
    assert 'Analyzing shots' in template
    assert 'Still computing BTTS tip…' in template
    assert 'createBttsLoader' in template
