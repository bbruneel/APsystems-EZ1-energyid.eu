import asyncio
import socket
from typing import TypedDict

import aiohttp
from APsystemsEZ1 import APsystemsEZ1M
from dotenv import load_dotenv
from loguru import logger

from energyid_monitor import common

load_dotenv(override=True)


class InverterConfig(TypedDict):
    """Configuration for the EZ1 microinverter connection."""

    ip_address: str


def load_inverter_config() -> InverterConfig:
    """
    Load inverter configuration from environment variables.
    Falls back to default IP if EZ1_IP_ADDRESS is not set.
    """
    return {
        "ip_address": common._require_env("EZ1_IP_ADDRESS", default="192.168.0.100"),
    }


def initialize(ip_address: str) -> APsystemsEZ1M:
    """
    Create and return an EZ1 microinverter client for the given IP.
    """
    inverter = APsystemsEZ1M(ip_address=ip_address)
    logger.info(f"Initialized EZ1 microinverter client for {ip_address}")
    return inverter


async def fetch_basic_data(inverter: APsystemsEZ1M) -> None:
    """
    Retrieve and print basic inverter data.
    """
    info = await inverter.get_device_info()
    if info:
        logger.info("Device info retrieved")
        logger.debug(
            f"Device details - deviceId: {info.deviceId}, devVer: {info.devVer}, "
            f"ssid: {info.ssid}, ipAddr: {info.ipAddr}, "
            f"minPower: {info.minPower}, maxPower: {info.maxPower}"
        )
    else:
        logger.warning("No device info received (is the inverter reachable?)")


async def fetch_total_output(inverter: APsystemsEZ1M) -> None:
    """
    Retrieve and print the combined output (p1 + p2).
    """
    total_output = await inverter.get_total_output()
    if total_output is not None:
        logger.info(f"Total output (W): {total_output}")
    else:
        logger.warning("No output data received (is the inverter reachable?)")


async def fetch_total_energy_today(inverter: APsystemsEZ1M) -> None:
    """
    Retrieve and print the total energy generated today (e1 + e2).
    """
    total_energy = await inverter.get_total_energy_today()
    if total_energy is not None:
        logger.info(f"Total energy today (kWh): {total_energy}")
    else:
        logger.warning("No energy data received (is the inverter reachable?)")


async def fetch_total_energy_lifetime(inverter: APsystemsEZ1M) -> float:
    """
    Retrieve and print the lifetime energy generated (e1 + e2).
    """
    # Let connection errors bubble up to be handled at a higher level
    total_energy = await inverter.get_total_energy_lifetime()
    if total_energy is None:
        raise RuntimeError(
            "No lifetime energy data received (is the inverter reachable?)"
        )

    logger.info(f"Total lifetime energy (kWh): {total_energy}")
    return float(total_energy)


async def read_total_output_value(inverter: APsystemsEZ1M) -> float:
    """
    Retrieve combined output (p1 + p2); return 0.0 if no value is reported.
    """
    try:
        output = await inverter.get_total_output()
    except (
        asyncio.TimeoutError,
        aiohttp.ClientError,
        socket.gaierror,
        ConnectionError,
    ) as exc:
        inverter_ip = getattr(inverter, "ip_address", "unknown")
        # Swallow connectivity issues and treat as zero output.
        logger.warning(f"Connection to {inverter_ip} failed or timed out: {exc}")
        return 0.0

    return float(output) if output is not None else 0.0


async def main() -> None:
    """
    Initialize an EZ1 microinverter client using the local API.
    Set EZ1_IP_ADDRESS env var to your inverter's LAN IP.
    """
    config = load_inverter_config()
    inverter = initialize(config["ip_address"])

    try:
        # Fetch and print basic device data
        await fetch_basic_data(inverter)
        # Fetch and print combined output power
        await fetch_total_output(inverter)
        # Fetch and print total energy generated today
        await fetch_total_energy_today(inverter)
        # Fetch and print total lifetime energy generated
        await fetch_total_energy_lifetime(inverter)
    except (
        asyncio.TimeoutError,
        aiohttp.ClientError,
        socket.gaierror,
        ConnectionError,
    ) as exc:
        logger.error(f"Connection to {config['ip_address']} failed or timed out: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
