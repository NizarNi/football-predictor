from football_predictor.adapters.sportmonks import _as_list


def test_rounds_fixtures_traversal():
    payload = {
        "data": [
            {
                "name": "Stage 1",
                "rounds": {
                    "data": [
                        {
                            "name": "R1",
                            "fixtures": {
                                "data": [
                                    {"id": 1, "starting_at": "2025-10-25T14:00:00+00:00"}
                                ]
                            },
                        },
                        {
                            "name": "R2",
                            "fixtures": {
                                "data": [
                                    {"id": 2, "starting_at": "2025-11-02T17:30:00+00:00"}
                                ]
                            },
                        },
                    ]
                },
            }
        ]
    }

    stages = payload.get("data") or []
    fixtures = []
    for stage in stages:
        for rnd in _as_list(stage.get("rounds")):
            for fx in _as_list(rnd.get("fixtures")):
                fixtures.append(fx)

    assert {f["id"] for f in fixtures} == {1, 2}
