"""Oxidant CLI entry point."""

import typer

app = typer.Typer(
    name="oxidant",
    help="Agentic TypeScript-to-Rust translation harness.",
    no_args_is_help=True,
)


@app.command()
def translate(
    source: str = typer.Argument(..., help="Path to a .ts file or corpus name"),
    out: str = typer.Option("output/", "--out", "-o", help="Output directory"),
    corpus: bool = typer.Option(False, "--corpus", help="Treat source as a corpus name"),
) -> None:
    """Translate TypeScript source to Rust."""
    typer.echo(f"oxidant: translation pipeline not yet implemented (source={source!r})")
    raise typer.Exit(1)


if __name__ == "__main__":
    app()
