from datetime import datetime, timedelta, timezone

import httpx
import pytest

from aibutton.actions import execute
from aibutton.ai_client import AIUnavailableError
from aibutton.config import LogAction, PromptAction, TimerToggleAction, WebhookAction
from aibutton.store import EventStore


class FakeAI:
    def __init__(self, answer=None, error=None):
        self.answer, self.error = answer, error
        self.prompts = []

    async def query(self, prompt):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.answer


@pytest.fixture
def store(tmp_path):
    s = EventStore(str(tmp_path / "events.db"))
    yield s
    s.close()


def _insert(store, kind, name, days_ago=0, duration_s=None):
    """Back-date a row by writing directly to the DB (log_event/toggle_timer
    always use "now")."""
    local_point = (
        datetime.now().astimezone().replace(hour=12, minute=0, second=0, microsecond=0)
        - timedelta(days=days_ago)
    )
    ts = local_point.astimezone(timezone.utc).isoformat()
    store._conn.execute(
        "INSERT INTO events (ts, kind, name, duration_s) VALUES (?, ?, ?, ?)",
        (ts, kind, name, duration_s),
    )
    store._conn.commit()


async def run(action, *, ai=None, store=None, transport=None):
    return await execute(
        action,
        trigger="short_press",
        mode_name="Test",
        ai=ai or FakeAI(answer="ok"),
        store=store,
        webhook_transport=transport,
    )


async def test_prompt_success(store):
    ai = FakeAI(answer="the answer")
    result = await run(PromptAction(prompt="ask me", label="L"), ai=ai, store=store)
    assert result.ok and result.message == "the answer"
    assert ai.prompts == ["ask me"]


async def test_prompt_ai_unavailable(store):
    ai = FakeAI(error=AIUnavailableError("all down"))
    result = await run(PromptAction(prompt="ask"), ai=ai, store=store)
    assert not result.ok
    assert "AI unavailable" in result.message


async def test_log_action_writes_and_reports(store):
    result = await run(LogAction(event="meds_taken"), store=store)
    assert result.ok
    assert result.message.startswith("Logged meds_taken at ")
    assert store.recent()[0][2] == "meds_taken"


async def test_log_action_shows_ordinal_when_logged_again_today(store):
    await run(LogAction(event="water"), store=store)
    result = await run(LogAction(event="water"), store=store)
    assert result.ok
    assert "(2nd today)" in result.message


async def test_log_action_shows_streak_when_logged_yesterday(store):
    _insert(store, "log", "water", days_ago=1)
    result = await run(LogAction(event="water"), store=store)
    assert result.ok
    assert "(2-day streak)" in result.message


async def test_log_action_shows_count_and_streak_together(store):
    _insert(store, "log", "water", days_ago=1)
    await run(LogAction(event="water"), store=store)
    result = await run(LogAction(event="water"), store=store)
    assert result.ok
    assert "(2nd today, 2-day streak)" in result.message


async def test_timer_toggle_start_then_stop(store):
    result = await run(TimerToggleAction(log_as="deep_work"), store=store)
    assert result.ok and result.message == "deep_work timer started"
    result = await run(TimerToggleAction(log_as="deep_work"), store=store)
    assert result.ok and result.message.startswith("deep_work stopped after ")


async def test_timer_toggle_shows_total_today_when_previous_sessions_exist(store):
    _insert(store, "timer_stop", "deep_work", duration_s=600)
    await run(TimerToggleAction(log_as="deep_work"), store=store)  # start
    result = await run(TimerToggleAction(log_as="deep_work"), store=store)  # stop
    assert result.ok
    assert result.message.startswith("deep_work stopped after ")
    assert "today)" in result.message


async def test_webhook_success_posts_context(store):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["json"] = request.read()
        seen["url"] = str(request.url)
        return httpx.Response(200)

    action = WebhookAction(url="https://hook.example/x", payload={"note": "hi"})
    result = await run(action, store=store, transport=httpx.MockTransport(handler))
    assert result.ok and "200" in result.message
    assert seen["url"] == "https://hook.example/x"
    body = seen["json"].decode()
    assert '"trigger": "short_press"' in body or '"trigger":"short_press"' in body
    assert "hi" in body


async def test_webhook_http_error_status(store):
    transport = httpx.MockTransport(lambda req: httpx.Response(500))
    result = await run(WebhookAction(url="https://hook.example/x"), store=store, transport=transport)
    assert not result.ok and "500" in result.message


async def test_webhook_unreachable(store):
    def handler(request):
        raise httpx.ConnectError("no route")

    result = await run(
        WebhookAction(url="https://hook.example/x"),
        store=store,
        transport=httpx.MockTransport(handler),
    )
    assert not result.ok
    assert "Webhook failed" in result.message
