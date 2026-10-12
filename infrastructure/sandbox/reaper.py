"""空闲回收 + 启动扫残骸。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from infrastructure.sandbox.broker import get_sandbox_broker
from infrastructure.sandbox.session_store import load_all
from shared.timeutil import BEIJING

_log = logging.getLogger(__name__)


async def sweep_and_reap_forever(interval_sec: int = 60) -> None:
    """后台任务：恢复落盘会话，并按 idle_sec 回收。"""
    broker = get_sandbox_broker()
    for sess in load_all():
        if sess.status == "running":
            broker.restore(sess)
            _log.info(
                "sandbox.reaper.restore session=%s tenant=%s",
                sess.id,
                sess.tenant_id,
            )

    while True:
        await asyncio.sleep(interval_sec)
        now = datetime.now(BEIJING)
        for sess in list(broker.iter_running()):
            try:
                last = datetime.fromisoformat(sess.last_active_at)
                if last.tzinfo is None:
                    last = last.replace(tzinfo=BEIJING)
            except Exception:  # noqa: BLE001
                continue
            if now - last > timedelta(seconds=sess.limits.idle_sec):
                _log.info("sandbox.reaper.idle session=%s", sess.id)
                try:
                    await broker.release(
                        session_id=sess.id, tenant_id=sess.tenant_id
                    )
                except Exception as exc:  # noqa: BLE001
                    _log.warning("sandbox.reaper.fail %s", exc)
