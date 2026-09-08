import json

from agent.rime_ws3 import clear_frame, context_id_for, epoch_of


def test_context_id_carries_the_epoch_on_the_wire():
    assert context_id_for(3, 7) == "hb-e3-7"


def test_epoch_can_be_recovered_from_a_context_id():
    assert epoch_of(context_id_for(12, 1)) == 12
    assert epoch_of("some-other-context") is None
    assert epoch_of("hb-eX-1") is None


def test_clear_frame_is_the_one_the_stock_plugin_never_sends():
    assert json.loads(clear_frame("hb-e2-1")) == {"operation": "clear", "contextId": "hb-e2-1"}
