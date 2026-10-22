"""Create a local Compose password once; never overwrite or display credentials."""

import secrets
from pathlib import Path


def create_env(path: Path) -> None:
    # Exclusive creation preserves an existing developer configuration.
    with path.open("x", encoding="utf-8") as stream:
        stream.write("# Generated local credentials. Do not commit.\n")
        stream.write(f"POSTGRES_PASSWORD={secrets.token_urlsafe(32)}\n")
        stream.write("MARKETOB_PORT=8000\n")


def main() -> None:
    destination = Path(__file__).resolve().parents[1] / ".env"
    try:
        create_env(destination)
    except FileExistsError:
        raise SystemExit(
            ".env already exists; preserved. Configure it locally if needed."
        ) from None
    print("Created .env with a random local database password. The value was not printed.")


if __name__ == "__main__":
    main()
