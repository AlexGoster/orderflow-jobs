from datetime import UTC, datetime, timedelta
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import select

from app.celery_app import celery_app
from app.core.database import get_sync_session_factory
from app.models import DailyStat, Order, OrderStatus, TaskState, TaskStatus
from app.tasks import generate_invoice_pdf, recompute_daily_stats, send_order_email


async def _create_order(client: AsyncClient, auth_headers: dict[str, str]) -> int:
    product = await client.post(
        "/api/v1/products",
        json={"sku": "SKU-T", "name": "Notebook", "price": 500.0, "stock": 10},
    )
    resp = await client.post(
        "/api/v1/orders",
        headers=auth_headers,
        json={"items": [{"product_id": product.json()["id"], "quantity": 2}]},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_invoice_endpoint_returns_202_and_tracks_status(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    order_id = await _create_order(client, auth_headers)

    accepted = await client.post(f"/api/v1/orders/{order_id}/invoice", headers=auth_headers)
    assert accepted.status_code == 202
    body = accepted.json()
    assert body["task_id"]
    assert body["status_url"] == f"/api/v1/tasks/{body['task_id']}"

    status_resp = await client.get(f"/api/v1/tasks/{body['task_id']}", headers=auth_headers)
    assert status_resp.status_code == 200
    task = status_resp.json()
    assert task["status"] == TaskStatus.success.value
    assert task["attempts"] == 1
    assert task["finished_at"] is not None
    assert str(order_id) in str(task["result"])


async def test_invoice_file_is_written(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    order_id = await _create_order(client, auth_headers)
    result = generate_invoice_pdf.apply(kwargs={"order_id": order_id})

    path = Path(str(result.result["path"]))
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "ORDERFLOW / INVOICE" in content
    assert f"#{order_id}" in content


async def test_invoice_for_missing_order_is_tracked_as_failed(client: AsyncClient) -> None:
    result = generate_invoice_pdf.apply(kwargs={"order_id": 424242})
    assert result.failed()

    with get_sync_session_factory()() as session:
        state = session.scalar(
            select(TaskState).where(TaskState.name == "tasks.generate_invoice_pdf")
        )
    assert state is not None
    assert state.status == TaskStatus.failed
    assert state.error is not None


async def test_send_order_email_eager(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    order_id = await _create_order(client, auth_headers)

    result = send_order_email.apply(kwargs={"order_id": order_id})
    assert result.successful()
    payload = result.result
    assert payload["order_id"] == order_id
    assert payload["to"] == "user@example.com"
    assert payload["simulated"] is True

    listed = await client.get("/api/v1/tasks", headers=auth_headers)
    assert listed.status_code == 200
    names = {item["name"] for item in listed.json()}
    assert "tasks.send_order_email" in names


async def test_order_creation_enqueues_email(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    await _create_order(client, auth_headers)
    listed = await client.get("/api/v1/tasks", headers=auth_headers)
    email_tasks = [i for i in listed.json() if i["name"] == "tasks.send_order_email"]
    assert email_tasks, "создание заказа должно ставить письмо в очередь"
    assert email_tasks[0]["status"] == TaskStatus.success.value


async def test_recompute_daily_stats_upsert(client: AsyncClient) -> None:
    with get_sync_session_factory()() as session:
        stat = session.scalar(select(DailyStat))
        assert stat is None

    first = recompute_daily_stats.apply(kwargs={"day": "2026-01-15"})
    assert first.successful()
    assert first.result["orders"] == 0

    second = recompute_daily_stats.apply(kwargs={"day": "2026-01-15"})
    assert second.successful()

    with get_sync_session_factory()() as session:
        stats = list(session.scalars(select(DailyStat)))
    assert len(stats) == 1, "повторный запуск не должен создавать вторую строку"


async def test_cleanup_cancels_stale_pending_orders(client: AsyncClient) -> None:
    with get_sync_session_factory()() as session:
        order = Order(user_id=1, status=OrderStatus.pending, total=0)
        order.created_at = datetime.now(UTC) - timedelta(days=60)
        session.add(order)
        session.commit()
        order_id = order.id

    from app.tasks import cleanup_expired_orders

    result = cleanup_expired_orders.apply(kwargs={"older_than_days": 30})
    assert result.successful()
    assert result.result["cancelled"] >= 1

    with get_sync_session_factory()() as session:
        fresh = session.get(Order, order_id)
    assert fresh is not None
    assert fresh.status == OrderStatus.cancelled

    repeat = cleanup_expired_orders.apply(kwargs={"older_than_days": 30})
    assert repeat.successful()


async def test_task_not_found_returns_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/tasks/does-not-exist", headers=auth_headers)
    assert resp.status_code == 404


async def test_tasks_require_auth(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/tasks")).status_code == 401


async def test_beat_schedule_configuration(client: AsyncClient) -> None:
    schedule = celery_app.conf.beat_schedule
    assert "cleanup-expired-orders" in schedule
    assert "daily-orders-stats" in schedule
    assert schedule["cleanup-expired-orders"]["task"] == "tasks.cleanup_expired_orders"
    assert schedule["daily-orders-stats"]["task"] == "tasks.recompute_daily_stats"


async def test_retry_policy_is_configured(client: AsyncClient) -> None:
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_track_started is True
    task = celery_app.tasks["tasks.send_order_email"]
    assert task.max_retries == 5
    assert task.retry_backoff is True
