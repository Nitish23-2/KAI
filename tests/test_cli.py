import json

from kai.interfaces.cli import _confirm_action
from kai.tools.registry import ApprovalRequest, ToolRisk


def test_approval_prompt_shows_tool_risk_and_exact_arguments(
    monkeypatch, capsys
) -> None:
    arguments_json = '{"url":"https://example.com/"}'
    monkeypatch.setattr("builtins.input", lambda _: "yes")

    approved = _confirm_action(
        ApprovalRequest(
            tool_name="open_website",
            risk=ToolRisk.MODERATE,
            arguments_json=arguments_json,
        )
    )

    output = capsys.readouterr().out
    assert approved
    assert "open_website" in output
    assert "moderate" in output
    assert json.dumps(
        json.loads(arguments_json), ensure_ascii=True, indent=2
    ) in output


def test_approval_prompt_defaults_to_deny(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "")

    approved = _confirm_action(
        ApprovalRequest(
            tool_name="delete_memory",
            risk=ToolRisk.HIGH,
            arguments_json='{"memory_id":"memory-1"}',
        )
    )

    assert not approved
