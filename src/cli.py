import re

import typer
from MATLABfcnscrape import (
    CURRENT_RELEASE,
    JSON_ROOT,
    URL_CACHE_FILENAME,
    scrape_toolbox_urls,
    scraping_pipeline,
)


scrape_cli = typer.Typer()


def is_valid_release(release: str) -> bool:
    """Check that the provided release string matches the expected format (e.g. `'R2020b'`)."""
    exp = r"R\d{4}[ab]"
    return bool(re.match(exp, release))


@scrape_cli.callback(invoke_without_command=True, no_args_is_help=True)
def main(ctx: typer.Context) -> None:
    """Scrape MATLAB's online documentation for all function names."""
    # Provide a callback for the base invocation to display the help text & exit.
    pass


@scrape_cli.command()
def run(
    release: str = typer.Argument(CURRENT_RELEASE, help="MATLAB version to scrape"),
    force_new_cache: bool = typer.Option(False, help="Force URL cache update."),
) -> None:
    """Run the documentation scraping pipeline for the specified release."""
    if not is_valid_release(release):
        raise ValueError(f"Invalid release specified: '{release}'")

    cache_filepath = JSON_ROOT / release / URL_CACHE_FILENAME
    if not cache_filepath.exists() or force_new_cache:
        scrape_toolbox_urls(release)

    scraping_pipeline(release)
