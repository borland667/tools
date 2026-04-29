"""Entry point: `python -m enacom_mcp`."""
from enacom_mcp.server import mcp


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
