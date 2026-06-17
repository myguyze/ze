from ze_eval.scenario import load_scenarios


def test_load_scenarios_returns_list() -> None:
    scenarios = load_scenarios()
    assert isinstance(scenarios, list)
    assert len(scenarios) > 0
    assert "id" in scenarios[0]
