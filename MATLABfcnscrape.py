import re
import json
import time
import logging
from pathlib import Path

import requests
from bs4 import BeautifulSoup


# Force UTC Timestamps
# From the logging cookbook: https://docs.python.org/3/howto/logging-cookbook.html
class UTCFormatter(logging.Formatter):
    converter = time.gmtime


logformat = "%(asctime)s %(levelname)s:%(module)s:%(message)s"
dateformat = "%Y-%m-%d %H:%M:%S"
logging.basicConfig(
    filename="./log/scrape.log",
    filemode="a",
    level=logging.INFO,
    format=logformat,
    datefmt=dateformat,
)


def load_URL_dict(source_JSON: str = "./fcnURL.JSON") -> dict:
    """
    Load URL dictionary from input JSON file

    Expected input dict format a nested dict:
        Top level dict is MATLAB's "Family" group
        Next level is a dict of toolbox:URL KV-pair for each group

    Output is a single layer dict containing the toolbox:url KV-pairs
    """
    source_JSON = Path(source_JSON)
    with source_JSON.open(mode="r") as fID:
        tmp = json.load(fID)

    squeeze_gen = (tmp[grouping] for grouping in tmp.keys())
    return {k: v for d in squeeze_gen for k, v in d.items()}


def scrape_doc_page(URL: str) -> list[str]:
    """
    Scrape functions from input MATLAB Doc Page URL

    Object methods (foo.bar) and comments (leading %) are excluded

    Returns a list of function name strings, or an empty list if none are found (e.g. no permission)
    """
    r = requests.get(URL, timeout=2)
    soup = BeautifulSoup(r.content, "html.parser")

    tags = soup.find_all(attrs={"class": "function"})

    # Iterate through tags & apply filters before appending to function list
    fcns = []
    for tag in tags:
        line = tag.string
        # Blacklist filters
        if re.findall(r"[%:]", line):
            # Ignore lines with '%' or ':'
            continue
        if re.match(r"^ocv", line):
            # Ignore OpenCV C++ commands
            continue
        elif "ColorSpec" in line or "LineSpec" in line:
            # Ignore ColorSpec and LineSpec
            # TODO: Add JSON function blacklist
            continue

        # Strip out anything encapsulated by parentheses or brackets
        line = re.sub(r"[[({][A-Za-z0-9,.]+[])}]", "", line).strip()
        # "Modification" filters
        if "," in line:
            # Split up functions on lines with commas
            [fcns.append(thing.strip()) for thing in line.split(",")]
        elif "." in line:
            # Skip regex filter for object methods
            fcns.append(line)
        else:
            # Otherwise apply a simple regex filter for the first word on a line
            tmp = re.findall(r"^\w+", line)
            if tmp:
                fcns.append(tmp[0])

    return fcns


def write_Toolbox_JSON(fcn_list: list, toolbox_name: str, json_path: str = "./JSONout"):
    """
    Write input toolbox function list to dest/toolboxname.JSON
    """
    json_path = Path(json_path)
    # Create destination folder if it doesn't already exist
    json_path.mkdir(parents=True, exist_ok=True)

    filepath = json_path / f"{toolbox_name}.JSON"
    with filepath.open(mode="w") as fID:
        json.dump(fcn_list, fID, indent="\t")


def concatenate_fcns(json_path: str = "./JSONout", fname: str = "_combined"):
    """
    Generate concatenated function set from directory of JSON files and write to 'fname.JSON'

    Assumes JSON file is a list of function name strings
    """
    json_path = Path(json_path)
    out_filepath = json_path / f"{fname}.JSON"

    fcn_set = set()
    for fcn_JSON in json_path.glob("*.JSON"):
        with fcn_JSON.open(mode="r") as fID:
            fcn_set.update(json.load(fID))

    logging.info(f"Concatenated {len(fcn_set)} unique functions")
    with out_filepath.open(mode="w") as fID:
        json.dump(sorted(fcn_set, key=str.lower), fID, indent="\t")


def scrape_toolboxes(
    URL: str = "https://www.mathworks.com/help/index.html",
    json_path: str = ".",
    fname: str = "fcnURL",
) -> dict:
    """
    Generate a dictionary of toolboxes & link to the alphabetical function list

    Dictionary is dumped to JSON/fname.JSON
    """
    r = requests.get(URL, timeout=2)
    soup = BeautifulSoup(r.content, "html.parser")

    # Get first header that matches 'MATLAB', this should be our 'MATLAB Family' column
    # For some reason soup.find_all('h2', string=re.compile('MATLAB')) returns an empty list
    # Generator approach from SO: https://stackoverflow.com/a/7006873/2748311
    matlab_header = next(
        (t for t in soup.find_all("h2") if t.find(text=re.compile("MATLAB"))), None
    )

    # Get to column div from the header, this is 2 levels above
    matlab_column = matlab_header.parent.parent

    # Iterate through MATLAB's groupings (does not include base MATLAB) and pull toolboxes & links
    grouped_dict = {}
    # Add base MATLAB manually
    grouped_dict["Base Matlab"] = {
        "MATLAB": "https://www.mathworks.com/help/matlab/functionlist-alpha.html"
    }
    for grouping in matlab_column.find_all("h4"):
        grouped_dict[grouping.text] = {
            list_item.text.replace(" ", ""): help_URL_builder(list_item.a.get("href"))
            for list_item in grouping.parent.find_all("li")
        }

    json_path = Path(json_path)
    out_filepath = json_path / f"{fname}.JSON"
    with out_filepath.open(mode="w") as fID:
        json.dump(grouped_dict, fID, indent="\t")


def help_URL_builder(
    shortlink: str,
    prefix: str = "https://www.mathworks.com/help/",
    suffix: str = "/functionlist-alpha.html",
) -> str:
    """
    Helper to build URL for alphabetical function list from the toolbox's shortlink

    e.g. 'https://www.mathworks.com/help/stats/functionlist-alpha.html' from 'stats/index.html'

    Returns a string
    """
    return prefix + shortlink.split("/")[0] + suffix


if __name__ == "__main__":
    out_path = "./JSONout/R2018a"

    scrape_toolboxes()
    toolbox_dict = load_URL_dict()
    logging.info(f"Scraping {len(toolbox_dict)} toolboxes")
    logging.info(f"Writing results to: {out_path}")
    for toolbox, URL in toolbox_dict.items():
        try:
            fcn_list = scrape_doc_page(URL)
            if len(fcn_list) == 0:
                # No functions found, most likely because permission for the toolbox docs is denied
                logging.info(
                    f"Permission to view documentation for '{toolbox}' has been denied: {URL}"
                )
            else:
                write_Toolbox_JSON(fcn_list, toolbox, out_path)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            # TODO: Add a retry pipeline, verbosity of exception
            logging.info(f"Unable to access online docs for '{toolbox}': '{URL}'")
    else:
        concatenate_fcns(out_path)
