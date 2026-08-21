import asyncio
import contextlib
import re
import time

from app.service.mongo_db.shared_models.db_monitoring_controller_model import HealthCheckResponse, MonitorStatus
from app.service.mongo_db.shared_models.db_ping_monitor_model import PingMonitorModel


class PingChecker:
    async def check(self, monitor: PingMonitorModel) -> HealthCheckResponse:
        response_time_ms = None
        success = False
        status = MonitorStatus.DOWN
        is_slow = False
        error = None
        timed_out = False
        try:
            process = await asyncio.create_subprocess_exec(
                "ping",
                "-c", "1",
                "-W", str(monitor.timeout),
                "--",
                monitor.host,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                output = stdout.decode()
                match = re.search(r"time=([\d.]+)", output)

                response_time_ms = int(float(match.group(1))) if match else None

                success = True
                status = MonitorStatus.UP

                if response_time_ms is not None and monitor.expected_response_time_ms is not None and response_time_ms > monitor.expected_response_time_ms:
                    is_slow = True

            else:
                response_time_ms = await self._tcp_reachability_time(
                    monitor.host,
                    monitor.timeout,
                )
                if response_time_ms is not None:
                    success = True
                    status = MonitorStatus.UP
                    is_slow = (
                        monitor.expected_response_time_ms is not None
                        and response_time_ms > monitor.expected_response_time_ms
                    )
                else:
                    error_output = stderr.decode().strip() or stdout.decode().strip()
                    error = (
                        "The target did not answer ICMP ping and no TCP connection "
                        f"could be established on ports 443, 53, or 80. {error_output}"
                    ).strip()

        except TimeoutError:
            response_time_ms = monitor.timeout * 1000
            timed_out = True
            error = f"The ping check did not complete within {monitor.timeout} seconds."

        except Exception as exc:
            error = f"The ping check failed: {exc}."

        return HealthCheckResponse(
            url=monitor.host,
            status=status,
            status_code=None,
            response_time_ms=response_time_ms,
            success=success,
            is_slow=is_slow,
            error=error,
            timed_out=timed_out,
        )

    async def close(self) -> None:
        return None

    @staticmethod
    async def _tcp_reachability_time(host: str, timeout: int) -> int | None:
        for port in (443, 53, 80):
            started = time.perf_counter()
            try:
                _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
            except (TimeoutError, OSError):
                continue
            try:
                return max(1, int((time.perf_counter() - started) * 1000))
            finally:
                writer.close()
                with contextlib.suppress(OSError):
                    await writer.wait_closed()
        return None
