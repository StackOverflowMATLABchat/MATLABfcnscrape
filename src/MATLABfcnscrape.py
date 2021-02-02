import json
import logging
import re
import typing as t
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException


BASE_URL_PREFIX = "https://www.mathworks.com/help/releases"
JSON_ROOT = Path("./JSONout")
URL_CACHE_FILENAME = "_url_cache.JSON"

CURRENT_RELEASE = "R2020b"
CURRENT_URL_CACHE = JSON_ROOT / CURRENT_RELEASE / URL_CACHE_FILENAME


def help_URL_builder(
    shortlink: str,
    release: str = CURRENT_RELEASE,
    prefix: str = "https://www.mathworks.com/help/releases",
    suffix: str = "referencelist.html?type=function&listtype=alpha",
) -> str:
    """
    Helper to build URL for alphabetical function list from the toolbox's shortlink.

    e.g. '<...>/help/releases/R2020b/stats/referencelist.html?type=function&listtype=alpha'
    from 'stats/index.html'
    """
    base_toolbox = shortlink.split("/")[0]
    return f"{prefix}/{release}/{base_toolbox}/{suffix}"


def scrape_toolbox_urls(release: str = CURRENT_RELEASE) -> None:
    """
    Generate a dictionary of toolboxes & link to their alphabetical function list.

    This URL cache is dumped to a `url_cache.JSON` file in the folder for the specified release.
    """
    base_url = f"{BASE_URL_PREFIX}/{release}/index.html"
    r = httpx.get(base_url, timeout=2)
    soup = BeautifulSoup(r.content, "html.parser")

    # Add base MATLAB manually
    grouped_dict = {"Base MATLAB": {"MATLAB": help_URL_builder("matlab")}}

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

    # Release directory is assumed to exist
    cache_filepath = JSON_ROOT / release / URL_CACHE_FILENAME
    with cache_filepath.open(mode="w") as fID:
        json.dump(grouped_dict, fID, indent="\t")


def load_URL_dict(url_cache: Path = CURRENT_URL_CACHE) -> t.Dict[str, str]:
    """
    Load URL dictionary from input JSON file.

    Expected input dict format a nested dict:
        Top level dict is MATLAB's "Family" group
        Next level is a dict of toolbox:URL KV-pair for each group

    Output is a single layer dict containing the toolbox:url KV-pairs
    """
    with url_cache.open(mode="r") as fID:
        tmp = json.load(fID)

    squeeze_gen = (tmp[grouping] for grouping in tmp.keys())
    return {k: v for d in squeeze_gen for k, v in d.items()}


def scrape_doc_page(url: str) -> t.List[str]:
    """
    Scrape functions from input MATLAB Doc Page URL.

    Object methods (foo.bar) and comments (leading %) are excluded

    Returns a list of function name strings, or an empty list if none are found (e.g. no permission)
    """
    with webdriver.Chrome() as wd:
        wd.implicitly_wait(7)  # Allow page to wait for elements to load
        wd.get(url)

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
                continue

            # Strip out anything encapsulated by parentheses or brackets
            function_name = re.sub(r"[\[\(\{][A-Za-z0-9,.]+[\]\)\}]", "", function_name).strip()
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


def write_Toolbox_JSON(
    fcn_list: t.List[str], toolbox_name: str, release: str = CURRENT_RELEASE
) -> None:
    """Write input toolbox function list to dest/toolboxname.JSON."""
    filepath = JSON_ROOT / release / f"{toolbox_name}.JSON"
    with filepath.open(mode="w") as fID:
        json.dump(fcn_list, fID, indent="\t")


def concatenate_fcns(release: str = CURRENT_RELEASE, fname: str = "_combined") -> None:
    """
    Generate concatenated function set from directory of JSON files and write to 'fname.JSON'.

    Assumes JSON file is a list of function name strings
    """
    release_root = JSON_ROOT / release
    fcn_set = set()
    for fcn_JSON in release_root.glob("*.JSON"):
        if fcn_JSON.name == URL_CACHE_FILENAME:
            # Ignore the release's URL cache
            continue

        with fcn_JSON.open(mode="r") as fID:
            fcn_set.update(json.load(fID))

    logging.info(f"Concatenated {len(fcn_set)} unique functions")
    out_filepath = JSON_ROOT / release / f"{fname}.JSON"
    with out_filepath.open(mode="w") as fID:
        json.dump(sorted(fcn_set, key=str.lower), fID, indent="\t")


def full_pipeline(release: str = CURRENT_RELEASE) -> None:
    # Create destination folder if it doesn't already exist
    json_path = JSON_ROOT / release
    json_path.mkdir(parents=True, exist_ok=True)

    scrape_toolbox_urls(release)  # Only need to run this once per version

    # toolbox_dict = load_URL_dict()
    # logging.info(f"Scraping {len(toolbox_dict)} toolboxes")
    # for toolbox, url in toolbox_dict.items():
    #     try:
    #         logging.info(f"Attempting to scrape {toolbox} functions")
    #         fcn_list = scrape_doc_page(url)
    #         if fcn_list is None:
    #             # No functions found, most likely because permission for the toolbox docs is denied
    #             logging.info(
    #                 f"Permission to view documentation for '{toolbox}' has been denied: {url}"
    #             )
    #         else:
    #             write_Toolbox_JSON(fcn_list, toolbox)
    #     except (httpx.TimeoutException, httpx.ConnectError):
    #         logging.info(f"Unable to access online docs for '{toolbox}': '{url}'")
    # else:
    #     concatenate_fcns()

if __name__ == "__main__":
    full_pipeline()
