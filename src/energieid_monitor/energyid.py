import base64
import json
import time
from pathlib import Path
from typing import TypedDict

import aiohttp
from dotenv import load_dotenv
from loguru import logger

from energieid_monitor import common, inverter, logging_config, token_store

load_dotenv(override=True)


def _decode_jwt_exp(bearer_token: str) -> int:
    """Extract exp claim from JWT bearer token without verification."""
    # Remove "Bearer " prefix if present
    token = bearer_token.replace("Bearer ", "").strip()

    # JWT has 3 parts separated by dots: header.payload.signature
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT token format")

    # Decode the payload (second part)
    payload_encoded = parts[1]
    # Add padding if needed (JWT base64 encoding doesn't include padding)
    padding = "=" * (4 - len(payload_encoded) % 4)
    payload_decoded = base64.urlsafe_b64decode(payload_encoded + padding)
    payload = json.loads(payload_decoded)

    exp = payload.get("exp")
    if not exp:
        raise ValueError("JWT token does not contain exp claim")

    return int(exp)


class HelloTokens(TypedDict):
    """Tokens returned from the EnergyID hello endpoint."""

    bearer_token: str
    twin_id: str
    exp: int


class ProvisioningConfig(TypedDict):
    """Configuration for EnergyID device provisioning and API endpoints."""

    provisioning_key: str
    provisioning_secret: str
    device_id: str
    device_name: str
    hello_url: str
    webhook_url: str


def load_provisioning_config() -> ProvisioningConfig:
    """
    Load provisioning credentials and device metadata from the environment.
    """
    return {
        "provisioning_key": common._require_env("ENERGYID_KEY"),
        "provisioning_secret": common._require_env("ENERGYID_SECRET"),
        "device_id": common._require_env("ENERGYID_YOUR_DEVICE_ID"),
        "device_name": common._require_env("ENERGYID_YOUR_DEVICE_NAME"),
        "hello_url": common._require_env("ENERGYID_HELLO_URL"),
        "webhook_url": common._require_env("ENERGYID_WEBHOOK_URL"),
    }


async def call_hello(
    session: aiohttp.ClientSession, config: ProvisioningConfig
) -> HelloTokens:
    """
    Call the EnergyID hello endpoint and return bearer token + twin id + exp.
    """
    headers = {
        "Content-Type": "application/json",
        "X-Provisioning-Key": config["provisioning_key"],
        "X-Provisioning-Secret": config["provisioning_secret"],
    }
    payload = {"deviceId": config["device_id"], "deviceName": config["device_name"]}

    async with session.post(config["hello_url"], json=payload, headers=headers) as resp:
        if resp.status != 200:
            text = await resp.text()
            raise RuntimeError(f"Hello endpoint failed ({resp.status}): {text}")

        body = await resp.json()
        logger.debug(f"Hello response body: {body}")
        headers_dict = body.get("headers") or {}

        bearer_token = (
            headers_dict.get("authorization")
            or body.get("bearerToken")
            or body.get("ENERGYID_BEARER_TOKEN")
        )
        twin_id = (
            headers_dict.get("x-twin-id")
            or body.get("twinId")
            or body.get("ENERGYID_TWIN_ID")
        )

        if not bearer_token or not twin_id:
            raise RuntimeError("Hello response missing bearer token or twin id")

        # Extract exp from JWT token
        exp = _decode_jwt_exp(bearer_token)

        masked_token = logging_config.mask_token(bearer_token)
        logger.debug(f"Extracted: bearer={masked_token}, twin={twin_id}, exp={exp}")

        return {"bearer_token": bearer_token, "twin_id": twin_id, "exp": exp}


async def get_or_refresh_token(
    session: aiohttp.ClientSession,
    config: ProvisioningConfig,
    db_path: str | Path = token_store.DEFAULT_DB_PATH,
) -> token_store.StoredToken:
    """
    Get a valid token from cache or fetch a new one if missing/expired/expiring soon.
    """
    await token_store.ensure_db(db_path)
    cached = await token_store.get_latest_token(db_path)

    if cached and token_store.is_token_valid(cached):
        logger.info("Using cached token (valid)")
        return cached

    logger.info(
        "Fetching new token from hello endpoint (cache miss or expired/expiring)"
    )
    hello_response = await call_hello(session, config)
    new_token: token_store.StoredToken = {
        "bearer_token": hello_response["bearer_token"],
        "twin_id": hello_response["twin_id"],
        "exp": hello_response["exp"],
    }
    await token_store.store_token(new_token, db_path)
    logger.info("New token stored in database")
    return new_token


async def post_webhook_in(
    session: aiohttp.ClientSession,
    bearer_token: str,
    twin_id: str,
    pv_value: float,
    timestamp: int,
    config: ProvisioningConfig,
) -> dict:
    """
    Send measurement payload to webhook-in using hello tokens.
    """
    headers = {
        "Content-Type": "application/json",
        "authorization": bearer_token,
        "x-twin-id": twin_id,
    }
    payload = {"ts": str(timestamp), "pv": pv_value}

    async with session.post(
        config["webhook_url"], json=payload, headers=headers
    ) as resp:
        text = await resp.text()
        if resp.status != 200:
            raise RuntimeError(f"Webhook-in failed ({resp.status}): {text}")

        # Try to parse JSON if provided, otherwise return text.
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"status": resp.status, "body": text}


async def _fetch_live_pv_output(inverter_client: inverter.APsystemsEZ1M) -> float:
    """
    Read the live PV output in watts from the inverter, convert it to
    kilowatts, and return the converted value.
    """
    logger.info("Fetching live PV output")
    output_watts = await inverter.read_total_output_value(inverter_client)
    # output_watts = 0.0 # TODO: Replace with actual output watts
    output_kw = output_watts / 1000.0
    logger.info(f"Output watts: {output_watts}, Output kilowatts: {output_kw}")
    return output_kw


async def _fetch_total_energy_lifetime(
    inverter_client: inverter.APsystemsEZ1M,
) -> float:
    """
    Read the lifetime PV energy in kilowatt-hours from the inverter.
    """
    logger.info("Fetching lifetime PV energy (kWh)")
    total_energy = await inverter.fetch_total_energy_lifetime(inverter_client)
    return float(total_energy)


async def run_energyid_flow() -> None:
    """
    Full flow: load env, get cached or refreshed tokens, read inverter PV, post webhook-in.
    """
    inverter_config = inverter.load_inverter_config()
    inverter_client = inverter.initialize(inverter_config["ip_address"])

    config = load_provisioning_config()

    async with aiohttp.ClientSession() as session:
        tokens = await get_or_refresh_token(session, config)
        # Fetch and log live PV output watts
        await _fetch_live_pv_output(inverter_client)
        # Fetch lifetime PV energy in kilowatt-hours to pass to the webhook
        pv_value = await _fetch_total_energy_lifetime(inverter_client)
        timestamp = int(time.time())
        webhook_response = await post_webhook_in(
            session,
            bearer_token=tokens["bearer_token"],
            twin_id=tokens["twin_id"],
            pv_value=pv_value,
            timestamp=timestamp,
            config=config,
        )

    masked_bearer = logging_config.mask_token(tokens["bearer_token"])
    logger.info("Tokens acquired (cached or fresh)")
    logger.debug(
        f"Token details - bearer: {masked_bearer}, twin: {tokens['twin_id']}, exp: {tokens['exp']}"
    )
    logger.info(f"Webhook-in response: {webhook_response}")


async def main() -> None:
    # Initialize logging configuration
    logging_config.setup_logging()
    try:
        await run_energyid_flow()
    except Exception:  # noqa: BLE001
        logger.exception("EnergyID flow failed")
