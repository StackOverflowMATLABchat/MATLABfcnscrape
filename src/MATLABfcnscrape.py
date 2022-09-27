import json
import logging
import re
import typing as t
from collections import abc, defaultdict, deque
from pathlib import Path
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

BASE_URL_PREFIX = "https://www.mathworks.com/help/releases"
REFLIST_URL_PREFIX = "https://www.mathworks.com/help/search/reflist/doccenter/en"

JSON_ROOT = Path("./JSONout")
URL_CACHE_FILENAME = "_url_cache.JSON"
FUNCTION_BLACKLIST = Path("./function_blacklist.JSON")

CURRENT_RELEASE = "R2022a"

# These releases have a different URL suffix for the toolbox function list
# These releases also have function lists that can be parsed directly from HTML
LEGACY_FN_LIST_RELEASES = {"R2018a", "R2017b", "R2017a", "R2016b", "R2016a", "R2015b"}

NON_CODE_FCN = {"R2016a", "R2015b"}  # Functions are not wrapped in code blocks

URL_CACHE_DICT = t.Dict[str, t.Dict[str, str]]


def help_url_builder(help_location: str, release: str) -> str:
    """
    Helper to build URL for alphabetical function list from the toolbox's help location.

    Currently there are 2 (incompatible) URL suffixes, the correct suffix is chosen based on the
    provided release & the list of "legacy" releases in `LEGACY_FN_LIST_RELEASES`.
    """
    if release in LEGACY_FN_LIST_RELEASES:
        suffix = "functionlist-alpha.html"
        return f"{BASE_URL_PREFIX}/{release}/{help_location}/{suffix}"
    else:
        # Newer MATLAB releases have an API endpoint that provides JSON
        params = {"type": "function", "listtype": "alpha", "product": help_location}
        suffix = urlencode(params)
        return f"{REFLIST_URL_PREFIX}/{release}?{suffix}"


def scrape_toolbox_urls(release: str) -> None:
    """
    Generate a dictionary of toolboxes & link to their alphabetical function list.

    This URL cache is dumped to a `url_cache.JSON` file in the folder for the specified release.
    """
    # MATLAB publishes an XML for each release containing a mapping of their products
    base_url = f"{BASE_URL_PREFIX}/{release}/docset.xml"
    r = httpx.get(base_url, timeout=2)
    soup = BeautifulSoup(r.content, "lxml")

    # Use a lambda concoction to allow for branching sub-dictionaries
    grouped_dict: dict[str, dict] = defaultdict(lambda: defaultdict(dict))
    products = soup.findAll("product")
    for product in products:
        display_name = product.find("display-name").text
        help_location = product.find("help-location").text
        short_name = product.find("short-name").text

        # Don't attempt to access the text, these may be None for older releases
        product_family = product.find("family")
        product_group = product.find("group")

        # Short blacklist for non-toolboxes
        if short_name == "install":
            continue
        if product_family and product_family.text == "webonlyproducts":
            continue

        help_url = help_url_builder(help_location, release)

        # R2016a and R2015b don't have product family information so toolboxes will be in one dict
        # All other versions are grouped by family (e.g. MATLAB, Simulink) and then by product group
        if not product_family and not product_group:
            grouped_dict["all products"][display_name] = help_url
        elif not product_group:
            grouped_dict[product_family.text][display_name] = help_url
        else:
            pretty_group = product_group.text.replace("-", " ").title()
            grouped_dict[product_family.text][pretty_group][display_name] = help_url

    # Release directory is assumed to exist
    cache_filepath = JSON_ROOT / release / URL_CACHE_FILENAME
    with cache_filepath.open(mode="w") as fID:
        json.dump(grouped_dict, fID, indent="\t")


def _url_denester(url_cache_dict: dict) -> t.Iterator[tuple[str, str]]:
    """Denest the structured URL cache format into its toolbox name, URL pairs."""
    dict_queue = deque((url_cache_dict,))

    # Use a stack queue to iterate through an arbitrary number of nested dictionary layers
    # Once we reach a non-dict value we can assume that we have a toolbox name, URL k,v pair and
    # yield it
    while dict_queue:
        for k, v in dict_queue[-1].items():
            if isinstance(v, dict):
                dict_queue.append(dict_queue[-1].pop(k))
                break
            else:
                yield k, v
        else:
            # Dump the dictionary once it's been exhausted
            dict_queue.pop()


def load_url_dict(release: str) -> dict[str, str]:
    """
    Load the toolbox URL cache for the provided MATLAB release.

    Output is a single layer dict containing the toolbox:url KV-pairs
    """
    url_cache = JSON_ROOT / release / URL_CACHE_FILENAME
    with url_cache.open(mode="r") as fID:
        tmp = json.load(fID)

    return {k: v for k, v in _url_denester(tmp)}


def load_function_blacklist(blacklist_filepath: Path = FUNCTION_BLACKLIST) -> set[str]:
    """
    Load the function blacklist from the specified JSON file.

    The specified JSON file is assumed to contain a list of function names (as strings) to exclude
    from toolbox parsing.
    """
    with blacklist_filepath.open("r") as f:
        function_blacklist = json.load(f)

    # Convert to set for better lookup
    return set(function_blacklist)


def filter_functions(
    function_list: abc.Collection[str], function_blacklist: abc.Collection[str]
) -> list[str]:
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

    return filtered_functions


def _scrape_doc_page_html(url: str, release: str) -> list[str]:
    """Scrape the toolbox function list for a MATLAB release with static documentation serving."""
    r = httpx.get(url, timeout=2)
    soup = BeautifulSoup(r.content, "html.parser")

    if release in NON_CODE_FCN:
        # The very old releases do not wrap function names in code tags
        functions = soup.findAll("td", {"class": {"term"}})
    else:
        functions = soup.findAll("code")

    return [function.text for function in functions]


def _scrape_doc_page_json(url: str) -> list[str]:
    """Scrape the toolbox function list for a MATLAB release with a valid reflist API endpoint."""
    r = httpx.get(url, timeout=10)

    # Catch reflists that aren't being served (likely licensed blocked)
    if r.status_code == httpx.codes.OK:
        raw_function_list = r.json()
    else:
        return []

    # Toolboxes may or may not group the functions.
    # If they're grouped, there will be an additional "grouped-leaf-items" list layer of the
    # function leaves
    all_functions = []
    if not raw_function_list["category"].get("grouped-leaf-items", None):
        all_functions.extend(
            [function["name"] for function in raw_function_list["category"]["leaf-items"]]
        )
    else:
        for category in raw_function_list["category"]["grouped-leaf-items"]:
            all_functions.extend([function["name"] for function in category["leaf-items"]])

    return all_functions


def scrape_doc_page(url: str, release: str) -> list[str]:
    """
    Scrape functions from input MATLAB Doc Page URL.

    Comments (leading %) are excluded

    Returns a list of function name strings, or an empty list if none are found (e.g. no permission)
    """
    if release in LEGACY_FN_LIST_RELEASES:
        # Pass the release since there are multiple legacy HTML formats
        raw_functions = _scrape_doc_page_html(url, release)
    else:
        raw_functions = _scrape_doc_page_json(url)

    return raw_functions


def write_Toolbox_JSON(fcn_list: list[str], toolbox_name: str, release: str) -> None:
    """Write input toolbox function list to dest/toolboxname.JSON."""
    toolbox_name = toolbox_name.replace(" ", "")  # I don't like spaces in filenames
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
    toolbox_dict = load_url_dict(release)

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

    concatenate_fcns(release)
