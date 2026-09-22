"""Command-line entry points."""

from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from memory_ledger.api import create_app

app = typer.Typer(
    name="memory-ledger",
    help="Run the Memory Ledger API or its deterministic verification benchmark.",
    no_args_is_help=True,
)


@app.command()
def serve(
    database: Annotated[
        Path,
        typer.Option("--database", "-d", help="SQLite database path."),
    ] = Path("memory-ledger.db"),
    host: Annotated[str, typer.Option(help="Interface to bind.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535, help="Port to bind.")] = 8000,
) -> None:
    """Serve the HTTP API and interactive OpenAPI documentation."""
    uvicorn.run(create_app(database), host=host, port=port)


@app.command()
def benchmark(
    fixture_dir: Annotated[
        Path | None,
        typer.Option(help="Directory containing memories.json and queries.json."),
    ] = None,
) -> None:
    """Run the version-controlled deterministic verification fixture."""
    from memory_ledger.benchmark import print_benchmark

    result = print_benchmark(fixture_dir) if fixture_dir else print_benchmark()
    if not result.passed:
        raise typer.Exit(code=1)
