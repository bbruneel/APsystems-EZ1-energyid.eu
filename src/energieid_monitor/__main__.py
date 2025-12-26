"""Entry point for running energieid_monitor as a module."""

import asyncio

from energieid_monitor import energyid


def main() -> None:
    """Main entry point for the application."""
    asyncio.run(energyid.main())


if __name__ == "__main__":
    main()
