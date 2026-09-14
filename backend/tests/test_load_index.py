from app.telemetry.load_index import calculate_load_index


def test_load_index_uses_available_metrics_and_reports_confidence():
    score, confidence, inputs = calculate_load_index(
        {"latency_ms": 80, "packet_loss_pct": 4, "download_mbps": 20}
    )

    assert 0 <= score <= 100
    assert confidence == "High"
    assert set(inputs) == {"latency", "packet_loss", "throughput"}


def test_load_index_does_not_invent_data_without_inputs():
    assert calculate_load_index({}) == (None, None, {})


def test_cellular_signal_inputs_increase_model_confidence():
    score, confidence, inputs = calculate_load_index(
        {"signal_strength_dbm": -110, "sinr_db": 2}
    )

    assert score > 50
    assert confidence == "Medium"
    assert set(inputs) == {"signal", "sinr"}
