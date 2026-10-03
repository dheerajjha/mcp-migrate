"""R013 SDK registration shapes from #310 / review on #313."""
from mcp_migrate.rules.r013_subscriptions_replaced import ResourceSubscriptionsReplaced
from mcp_migrate.scan import load_project


def test_r013_fires_on_sdk_decorator_and_constructor(tmp_path):
    (tmp_path / "server.py").write_text(
        "from mcp.server import Server\n"
        "app = Server('demo')\n"
        "\n"
        "@app.subscribe_resource()\n"
        "async def subscribe(uri):\n"
        "    return None\n"
        "\n"
        "@app.unsubscribe_resource()\n"
        "async def unsubscribe(uri):\n"
        "    return None\n"
        "\n"
        "server = Server('demo', on_subscribe_resource=subscribe,\n"
        "                on_unsubscribe_resource=unsubscribe)\n"
    )
    findings = ResourceSubscriptionsReplaced().check(load_project(tmp_path))
    snippets = [f.snippet for f in findings]
    assert any("subscribe_resource()" in (s or "") for s in snippets)
    assert any("unsubscribe_resource()" in (s or "") for s in snippets)
    assert any("on_subscribe_resource=" in (s or "") for s in snippets)
    assert any("on_unsubscribe_resource=" in (s or "") for s in snippets)
    assert all(f.rule_id == "R013" for f in findings)


def test_r013_fires_on_black_formatted_constructor(tmp_path):
    (tmp_path / "server.py").write_text(
        "from mcp.server import Server\n"
        "\n"
        "async def subscribe(uri):\n"
        "    return None\n"
        "\n"
        "server = Server(\n"
        "    \"demo\",\n"
        "    on_subscribe_resource=subscribe,\n"
        ")\n"
    )
    findings = ResourceSubscriptionsReplaced().check(load_project(tmp_path))
    assert any("on_subscribe_resource=" in (f.snippet or "") for f in findings)
    assert all(f.rule_id == "R013" for f in findings)


def test_r013_ignores_sdk_names_in_docstring_and_comment(tmp_path):
    (tmp_path / "server.py").write_text(
        '"""Registers via @app.subscribe_resource() and on_subscribe_resource=."""\n'
        "# on_unsubscribe_resource= is mentioned only here\n"
        "def health():\n"
        "    return 'ok'\n"
    )
    findings = ResourceSubscriptionsReplaced().check(load_project(tmp_path))
    assert findings == []
