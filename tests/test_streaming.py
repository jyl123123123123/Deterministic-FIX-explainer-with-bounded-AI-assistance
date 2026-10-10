import asyncio

import pytest

from fix_explainer import StreamConfig, StreamSimulator


def test_stream_config_enforces_product_rate_bounds() -> None:
    with pytest.raises(ValueError, match="count"):
        StreamConfig(count=999)
    with pytest.raises(ValueError, match="rate"):
        StreamConfig(rate=9)
    with pytest.raises(ValueError, match="rate"):
        StreamConfig(rate=101)


def test_stream_replays_in_order_and_can_be_stopped() -> None:
    async def scenario() -> None:
        received: list[int] = []

        async def handler(message) -> None:
            received.append(message.sequence)

        simulator = StreamSimulator(handler)
        run = simulator.start(StreamConfig(count=1000, rate=100))
        await asyncio.sleep(0.04)
        await simulator.stop(run.run_id)

        assert received
        assert received == list(range(1, len(received) + 1))
        assert simulator.status(run.run_id)["status"] == "STOPPED"
        assert simulator.status(run.run_id)["processed"] == len(received)

    asyncio.run(scenario())


def test_stream_rejects_concurrent_runs_and_reports_handler_failure() -> None:
    async def scenario() -> None:
        async def handler(message) -> None:
            if message.sequence == 1:
                raise RuntimeError("consumer failed")

        simulator = StreamSimulator(handler)
        first = simulator.start(StreamConfig(count=1000, rate=100))
        with pytest.raises(RuntimeError, match="already active"):
            simulator.start(StreamConfig(count=1000, rate=100))
        with pytest.raises(RuntimeError, match="consumer failed"):
            await simulator.wait(first.run_id)
        assert simulator.status(first.run_id)["status"] == "FAILED"
        assert simulator.status(first.run_id)["error"] == "consumer failed"

    asyncio.run(scenario())
