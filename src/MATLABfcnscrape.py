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
FUNCTION_BLACKLIST = Path("./function_blacklist.JSON")

CURRENT_RELEASE = "R2020b"

# These releases have a different URL suffix for the toolbox function list
# These releases also have function lists that can be parsed directly from HTML
LEGACY_FN_LIST_RELEASES = {"R2018a", "R2017b", "R2017a", "R2016b", "R2016a", "R2015b"}

# These releases have different layouts of the documentation homepage
LEGACY_HELP_LAYOUT = {"R2018a", "R2017b", "R2017a", "R2016b"}
REALLY_OLD_HELP_LAYOUT = {"R2016a", "R2015b"}

URL_CACHE_DICT = t.Dict[str, t.Dict[str, str]]


def help_URL_builder(shortlink: str, release: str) -> str:
    """
    Helper to build URL for alphabetical function list from the toolbox's shortlink.

    e.g. '<...>/help/releases/R2020b/stats/referencelist.html?type=function&listtype=alpha'
    from 'stats/index.html'

    Currently there are 2 (incompatible) URL suffixes, the correct suffix is chosen based on the
    provided release & the list of "legacy" releases in `LEGACY_FN_LIST_RELEASES`.
    """
    if release in LEGACY_FN_LIST_RELEASES:
        suffix = "functionlist-alpha.html"
    else:
        suffix = "referencelist.html?type=function&listtype=alpha"

    base_toolbox = shortlink.split("/")[0]
    return f"{BASE_URL_PREFIX}/{release}/{base_toolbox}/{suffix}"


def _scrape_product_url(
    grouped_dict: URL_CACHE_DICT, soup: BeautifulSoup, release: str
) -> URL_CACHE_DICT:
    """
    Scrape list of URLs for the MATLAB product family.

    This is the current styling of the documentation homepage, with dropdown panels for each group
    of toolboxes. For each panel, there may be a second column for Simulink toolboxes, which are
    ignored.
    """
    # MATLAB products are grouped into individual panels
    product_groups = soup.findAll("div", {"class": "panel panel-default product_group off"})
    for group in product_groups:
        # Some are 1 column (all MATLAB), some are 2 (MATLAB & Simulink)
        # We're going to ignore any Simulink columns
        group_title = group.find("div", {"class": "panel-title"}).text
        toolbox_lists = group.findAll("ul", {"class": "list-unstyled add_list_spacing_3"})[0]
        grouped_dict[group_title] = {
            toolbox.text.replace(" ", ""): help_URL_builder(toolbox.a.get("href"), release)
            for toolbox in toolbox_lists.findAll("li")
        }

    return grouped_dict


def _scrape_product_url_legacy(
    grouped_dict: URL_CACHE_DICT, soup: BeautifulSoup, release: str
) -> URL_CACHE_DICT:
    """
    Scrape list of URLs for the MATLAB product family.

    This is the "legacy" styling for the documentation homepage, with a long table of groups of
    toolboxes. The MATLAB family of toolboxes should be contained to a single column, all other
    families are ignored.
    """
    # Find the panels on the page, the MATLAB family should be the first one, and is the only one
    # we care about
    product_families = soup.findAll(
        "div", {"class": "col-xs-12 col-sm-6 col-md-4 family_container off"}
    )
    for family in product_families:
        if "MATLAB" in family.find("div", {"class": "panel-heading"}).text:
            # Iterate through the MATLAB products
            product_groups = family.findAll("div", {"class": "product_group off"})
            for group in product_groups:
                group_title = group.find("h4", {"class": "add_bottom_rule"}).text
                toolbox_list = group.find("ul", {"class": "list-unstyled"})
                grouped_dict[group_title] = {
                    toolbox.text.replace(" ", ""): help_URL_builder(toolbox.a.get("href"), release)
                    for toolbox in toolbox_list.findAll("li")
                }

            # Ignore any other product families that are present
            break

    return grouped_dict


def _scrape_product_url_vold(soup: BeautifulSoup, release: str) -> URL_CACHE_DICT:
    """
    Scrape list of URLs for the MATLAB product family.

    This is the "very old" styling for the documentation homepage, with a single panel listing of
    all toolboxes. There is no grouping of toolboxes for this styling.  Toolboxes with "Simulink" in
    the name are ignored.
    """
    product_panel = soup.find("div", {"class": "doc_families_container"})
    group_title = "All Products"  # Toolbox listing has no groups
    toolbox_list = product_panel.find("ul", {"class": "list-unstyled"})

    # Use an explicit loop, simulink filtering makes the dict comp difficult to follow
    grouped_dict: URL_CACHE_DICT = {group_title: {}}
    for toolbox in toolbox_list.findAll("li"):
        deblanked = toolbox.text.replace(" ", "")
        if "Simulink" in deblanked:
            continue

        grouped_dict[group_title][deblanked] = help_URL_builder(toolbox.a.get("href"), release)

    return grouped_dict


def scrape_toolbox_urls(release: str) -> None:
    """
    Generate a dictionary of toolboxes & link to their alphabetical function list.

    This URL cache is dumped to a `url_cache.JSON` file in the folder for the specified release.
    """
    base_url = f"{BASE_URL_PREFIX}/{release}/index.html"
    r = httpx.get(base_url, timeout=2)
    soup = BeautifulSoup(r.content, "html.parser")

    # Add base MATLAB manually
    grouped_dict = {"Base MATLAB": {"MATLAB": help_URL_builder("matlab", release)}}

    # There are currently 3 different layouts for MATLAB's listing of toolboxes on their
    # documentation homepage.
    if release in LEGACY_HELP_LAYOUT:
        grouped_dict = _scrape_product_url_legacy(grouped_dict, soup, release)
    elif release in REALLY_OLD_HELP_LAYOUT:
        # Since everything is grouped into a single panel, we don't need to add base MATLAB manually
        grouped_dict = _scrape_product_url_vold(soup, release)
    else:
        grouped_dict = _scrape_product_url(grouped_dict, soup, release)

    # Release directory is assumed to exist
    cache_filepath = JSON_ROOT / release / URL_CACHE_FILENAME
    with cache_filepath.open(mode="w") as fID:
        json.dump(grouped_dict, fID, indent="\t")


def load_URL_dict(release: str) -> t.Dict[str, str]:
    """
    Load the toolbox URL cache for the provided MATLAB release.

    Expected input dict format a nested dict:
        Top level dict is MATLAB's "Family" group
        Next level is a dict of toolbox:URL KV-pair for each group

    Output is a single layer dict containing the toolbox:url KV-pairs
    """
    url_cache = JSON_ROOT / release / URL_CACHE_FILENAME
    with url_cache.open(mode="r") as fID:
        tmp = json.load(fID)

    # For easier reading are dumped as they are grouped on MATLAB's documentation homepage, we can
    # denest this into a single layer for parsing
    squeeze_gen = (tmp[grouping] for grouping in tmp.keys())
    return {k: v for d in squeeze_gen for k, v in d.items()}


def load_function_blacklist(blacklist_filepath: Path = FUNCTION_BLACKLIST) -> t.Set[str]:
    """
    Load the function blacklist from the specified JSON file.

    The specified JSON file is assumed to contain a list of function names (as strings) to exclude
    from toolbox parsing.
    """
    with blacklist_filepath.open("r") as f:
        function_blacklist = json.load(f)

    # Convert to set for better lookup
    return set(function_blacklist)


def filter_functions(function_list: t.List[str], function_blacklist: t.List[str]) -> t.List[str]:
    """Run a series of filters over the raw scrape of a toolbox's list of functions."""
    filtered_functions = []
    for function_name in function_list:
        # Blacklist filters
        if re.findall(r"[%:]", function_name):
            # Ignore lines with '%' or ':'
            continue

        if re.match(r"^ocv", function_name):
            # Ignore OpenCV C++ commands
            continue

        if function_name in function_blacklist:
            # Ignore blacklisted function names
            continue

        # Strip out anything encapsulated by parentheses or brackets
        function_name = re.sub(r"[\[\(\{][A-Za-z0-9,.]+[\]\)\}]", "", function_name).strip()

        # "Modification" filters
        if "," in function_name:
            # Split up functions on lines with commas
            filtered_functions.extend([thing.strip() for thing in function_name.split(",")])
        elif "." in function_name:
            # Skip regex filter for object methods
            filtered_functions.append(function_name)
        else:
            # Otherwise apply a simple regex filter for the first word on a line
            tmp = re.findall(r"^\w+", function_name)
            if tmp:
                filtered_functions.append(tmp[0])


def _scrape_doc_page_html(url: str) -> t.List[str]:
    """Scrape the toolbox function list for a MATLAB release with static documentation serving."""
    r = httpx.get(url, timeout=2)
    soup = BeautifulSoup(r.content, "html.parser")

    functions = soup.findAll("code", {"class": "function"})
    return [function.text for function in functions]


def _scrape_doc_page_browser(url: str) -> t.List[str]:
    """Scrape the toolbox function list for a MATLAB release with dynamic documentation serving."""
    with webdriver.Chrome() as wd:
        wd.implicitly_wait(7)  # Allow page to wait for elements to load
        wd.get(url)

        try:
            function_table = wd.find_element_by_xpath('//*[@id="reflist_content"]')
            rows = function_table.find_elements_by_tag_name("tr")
            logging.info(f"Found {len(rows)} functions")
        except NoSuchElementException:
            # Could not get element, either a timeout or lack of permissions
            return []

        # Iterate through tags & dump straight to a list
        return [row.find_element_by_tag_name("a").text for row in rows]


def scrape_doc_page(url: str, release: str) -> t.List[str]:
    """
    Scrape functions from input MATLAB Doc Page URL.

    Object methods (foo.bar) and comments (leading %) are excluded

    Returns a list of function name strings, or an empty list if none are found (e.g. no permission)
    """
    if release in LEGACY_FN_LIST_RELEASES:
        raw_functions = _scrape_doc_page_html(url)
    else:
        raw_functions = _scrape_doc_page_browser(url)

    return raw_functions


def write_Toolbox_JSON(fcn_list: t.List[str], toolbox_name: str, release: str) -> None:
    """Write input toolbox function list to dest/toolboxname.JSON."""
    filepath = JSON_ROOT / release / f"{toolbox_name}.JSON"
    with filepath.open(mode="w") as fID:
        json.dump(fcn_list, fID, indent="\t")


def concatenate_fcns(release: str) -> None:
    """
    Generate concatenated function set from directory of JSON files and write to '_combined.JSON'.

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
    out_filepath = JSON_ROOT / release / "_combined.JSON"
    with out_filepath.open(mode="w") as fID:
        json.dump(sorted(fcn_set, key=str.lower), fID, indent="\t")


def scraping_pipeline(release: str = CURRENT_RELEASE) -> None:
    """
    Run the full scraping pipeline for the current release.

    NOTE: The URL cache for the specified release must be generated before calling this helper.
    """
    function_blacklist = load_function_blacklist()

    toolbox_dict = load_URL_dict(release)
    logging.info(f"Scraping {len(toolbox_dict)} toolboxes")
    for toolbox, url in toolbox_dict.items():
        try:
            logging.info(f"Attempting to scrape {toolbox} functions")
            raw_functions = scrape_doc_page(url, release)
            if not raw_functions:
                # No functions found, most likely because permission for the toolbox docs is denied
                # Toolboxes may also be public-facing and have no functions on the page
                logging.info(f"No functions found for '{toolbox}': {url}")
            else:
                out_functions = filter_functions(raw_functions, function_blacklist)
                write_Toolbox_JSON(out_functions, toolbox, release)
        except (httpx.TimeoutException, httpx.ConnectError):
            logging.info(f"Unable to access online docs for '{toolbox}': '{url}'")
    else:
        concatenate_fcns(release)
