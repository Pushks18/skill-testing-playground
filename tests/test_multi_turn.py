# tests/test_multi_turn.py
import pytest
import eval.run_task as rt


def test_looks_like_question():
    assert rt._looks_like_question("Could you provide your booking reference?")
    assert not rt._looks_like_question("Done. Your flight is rebooked to FL123.")


def test_simulator_prompt_reveals_only_when_asked(monkeypatch):
    captured = {}

    class _FakeResp:
        class _C:
            class _M:
                content = "It's BK7Q2R8T."
            message = _M()
        choices = [_C()]

    class _FakeClient:
        def __init__(self, **kw): pass
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    captured.update(kw)
                    return _FakeResp()

    import openai
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: _FakeClient())
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    task = {"instruction": "My flight is delayed.",
            "expected": {"hidden_details": "booking ref BK7Q2R8T; wants rebooking"}}
    reply = rt._simulate_user_reply(task, "What is your booking reference?")
    assert reply == "It's BK7Q2R8T."
    sys_msg = captured["messages"][0]["content"]
    assert "BK7Q2R8T" in sys_msg and "ONLY what is asked" in sys_msg


def test_multi_turn_loop_accumulates(monkeypatch, tmp_path):
    """Two-round conversation: agent asks, simulator answers, agent acts."""
    rounds = []

    class _FakeAgent:
        def invoke(self, state, config=None):
            rounds.append(state)
            if len(rounds) == 1:
                return {"messages": state["messages"] + [{"role": "assistant", "content": "What is your booking reference?"}],
                        "response": "What is your booking reference?",
                        "tools_called": [], "step_timings": [], "steps": 1,
                        "tokens_used": 100, "input_tokens": 90, "output_tokens": 10}
            return {"messages": [], "response": "Rebooked you on FL123.",
                    "tools_called": [{"name": "modify_booking", "params": {"booking_id": "BK7Q2R8T"}}],
                    "step_timings": [{"tool": "modify_booking", "latency_ms": 5, "tokens": 0}],
                    "steps": 2, "tokens_used": 200, "input_tokens": 150, "output_tokens": 50}

    monkeypatch.setattr(rt, "build_travel_agent", lambda **kw: _FakeAgent())
    monkeypatch.setattr(rt, "_simulate_user_reply", lambda task, q: "It's BK7Q2R8T.")

    task_dir = tmp_path / "mt-001"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text(
        '[task]\nid = "mt-001"\ndomain = "disruption"\nskill = "disruption-handling"\n'
        'verifier = "tool_call_check"\nweight = 2.0\nmulti_turn = true\n\n'
        '[expected]\ntools = ["modify_booking"]\nhidden_details = "ref BK7Q2R8T"\n')
    (task_dir / "instruction.md").write_text("My flight is delayed, please fix it.")

    r = rt.run_task(str(task_dir), None, "no_skill", "http://unused")
    assert len(rounds) == 2                         # asked once, answered, acted
    assert "modify_booking" in r.tools_called       # union of tools seen by verifier
    assert r.passed_verifier
    assert r.input_tokens == 240                    # 90 + 150 accumulated


def test_run_task_orchestrated_routes(monkeypatch, tmp_path):
    """orchestrated mode: router picks the agent; skill_path/condition ignored."""
    import eval.run_task as rt

    class _FakeAgent:
        def invoke(self, state, config=None):
            return {"messages": [], "response": "done",
                    "tools_called": [{"name": "add_ancillary", "params": {}}],
                    "step_timings": [], "steps": 1,
                    "tokens_used": 10, "input_tokens": 8, "output_tokens": 2}

    class _FakeRouter:
        def route(self, text):
            return "ancillery-skill", _FakeAgent()

    monkeypatch.setattr(rt, "_get_agent_router", lambda url: _FakeRouter())

    task_dir = tmp_path / "anc-001"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text(
        '[task]\nid = "anc-001"\ndomain = "ancillery"\nskill = "ancillery-skill"\n'
        'verifier = "tool_call_check"\nweight = 1.5\n\n[expected]\ntools = ["add_ancillary"]\n')
    (task_dir / "instruction.md").write_text("Add a bag to booking BK1A2B3C")

    r = rt.run_task(str(task_dir), None, "no_skill", "http://unused", agent_mode="orchestrated")
    assert r.skill_name == "ancillery-skill"      # the ROUTED skill is recorded
    assert r.passed_verifier
