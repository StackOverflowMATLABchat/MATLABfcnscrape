# MATLABfcnscrape
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Code style: black](https://img.shields.io/badge/code%20style-black-black)](https://github.com/psf/black)

Scrape MATLAB's documentation for (hopefully) all function names and output to JSON files for your reading pleasure.

For each MATLAB release, a JSON file is output per toolbox and all unique functions are consolidated into a single JSON.

## Caveats
* For TOS compliance, only public facing documentation is accessed
  * See [this issue](https://github.com/StackOverflowMATLABchat/MATLABfcnscrape/issues/2) for additional information
* These listings are not guaranteed to be comprehensive
  * The filtering mechanism is continually being improved in order to provide the best possible listing of "actual" functions without requiring significant manual intervention

## MATLABfcnscrape CLI
Assuming `MATLABfcnscrape` is installed in the current environment, it can be invoked directly from the command line:


<!-- [[[cog
# Generate code fence using `cog -r README.md`
import cog
from subprocess import PIPE, run
out = run(["fcnscrape"], stdout=PIPE, encoding="ascii")
cli_help = out.stdout
cog.out(
    f"```\n$ fcnscrape\n{cli_help}\n```"
)
]]] -->
```
$ fcnscrape
Usage: fcnscrape [OPTIONS] COMMAND [ARGS]...

  Scrape MATLAB's online documentation for all function names.

Options:
  --install-completion  Install completion for the current shell.
  --show-completion     Show completion for the current shell, to copy it or
                        customize the installation.
  --help                Show this message and exit.

Commands:
  run  Run the documentation scraping pipeline for the specified release.

```
<!-- [[[end]]] -->

### `fcnscrape run`
Invokes the main scraping pipeline
#### Input Parameters
| Parameter                                  | Description            | Default                |
|--------------------------------------------|------------------------|------------------------|
| `--force-new-cache / --no-force-new-cache` | Force URL cache update | `--no-force-new-cache` |


## Repository Tags
In addition to tags for releases of the tool, tags are also added to commits adding (or updating) listings for specific releases. Initial releases are tagged as the major version, e.g. `R2020b`, with any updates tagged with a dash suffix, e.g. (`R2020b-1`)
