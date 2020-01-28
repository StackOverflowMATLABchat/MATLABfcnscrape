import re
import json
import time
import typing
import logging
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException

logging.Formatter.converter = time.gmtime  # Force UTC timestamp
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


def scrape_doc_page(URL: str) -> typing.List[str]:
    """
    Scrape functions from input MATLAB Doc Page URL

    Object methods (foo.bar) and comments (leading %) are excluded

    Returns a list of function name strings, or an empty list if none are found (e.g. no permission)
    """
    with webdriver.Chrome() as wd:
        wd.implicitly_wait(7)  # Allow page to wait for elements to load
        wd.get(URL)

        try:
            function_table = wd.find_element_by_xpath('//*[@id="reflist_content"]')
            rows = function_table.find_elements_by_tag_name("tr")
            logging.info(f"Found {len(rows)} functions")
        except NoSuchElementException:
            # Could not get element, either a timeout or lack of permissions
            return

        # Iterate through tags & apply filters before appending to function list
        fcns = []
        for row in rows:
            function_name = row.find_element_by_tag_name("a").text
            # Blacklist filters
            if re.findall(r"[%:]", function_name):
                # Ignore lines with '%' or ':'
                continue
            if re.match(r"^ocv", function_name):
                # Ignore OpenCV C++ commands
                continue
            elif "ColorSpec" in function_name or "LineSpec" in function_name:
                # Ignore ColorSpec and LineSpec
                # TODO: Add JSON function blacklist
                continue

            # Strip out anything encapsulated by parentheses or brackets
            function_name = re.sub(r"[[({][A-Za-z0-9,.]+[])}]", "", function_name).strip()
            # "Modification" filters
            if "," in function_name:
                # Split up functions on lines with commas
                [fcns.append(thing.strip()) for thing in function_name.split(",")]
            elif "." in function_name:
                # Skip regex filter for object methods
                fcns.append(function_name)
            else:
                # Otherwise apply a simple regex filter for the first word on a line
                tmp = re.findall(r"^\w+", function_name)
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


def scrape_toolbox_urls(
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

    grouped_dict = {}
    # Add base MATLAB manually
    grouped_dict["Base Matlab"] = {
        "MATLAB": "https://www.mathworks.com/help/matlab/referencelist.html?type=function&listtype=alpha"  # noqa
    }

    # MATLAB products are grouped into individual panels
    product_groups = soup.findAll("div", {"class": "panel panel-default product_group off"})
    for group in product_groups:
        # Some are 1 column (all MATLAB), some are 2 (MATLAB & Simulink)
        # We're going to ignore any Simulink columns
        group_title = group.find("div", {"class": "panel-title"}).text
        toolbox_lists = group.findAll("ul", {"class": "list-unstyled add_list_spacing_3"})[0]
        grouped_dict[group_title] = {
            toolbox.text.replace(" ", ""): help_URL_builder(toolbox.a.get("href"))
            for toolbox in toolbox_lists.findAll("li")
        }

    json_path = Path(json_path)
    out_filepath = json_path / f"{fname}.JSON"
    with out_filepath.open(mode="w") as fID:
        json.dump(grouped_dict, fID, indent="\t")


def help_URL_builder(
    shortlink: str,
    prefix: str = "https://www.mathworks.com/help/",
    suffix: str = "/referencelist.html?type=function&listtype=alpha",
) -> str:
    """
    Helper to build URL for alphabetical function list from the toolbox's shortlink

    e.g. 'https://www.mathworks.com/help/stats/referencelist.html?type=function&listtype=alpha'
    from 'stats/index.html'

    Returns a string
    """
    return prefix + shortlink.split("/")[0] + suffix


if __name__ == "__main__":
    out_path = "./JSONout/R2019b"

    # scrape_toolbox_urls()
    toolbox_dict = load_URL_dict()
    logging.info(f"Scraping {len(toolbox_dict)} toolboxes")
    logging.info(f"Writing results to: {out_path}")
    for toolbox, URL in toolbox_dict.items():
        try:
            logging.info(f"Attempting to scrape {toolbox} functions")
            fcn_list = scrape_doc_page(URL)
            if fcn_list is None:
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
