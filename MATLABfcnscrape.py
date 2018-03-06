import json
from pathlib import Path

import requests
from bs4 import BeautifulSoup

def loadURLdict(sourceJSON):
    """
    Load URL dictionary from input JSON file

    Expected dict format is key: toolbox name, value: alphabetical function list URL
    """
    with open(sourceJSON, mode='r') as fID:
        return json.load(fID)

def scrapedocpage(URL):
    """
    Scrape functions from input MATLAB Doc Page URL

    Object methods (foo.bar) and comments (leading %) are excluded

    Returns a list of function name strings
    """
    r = requests.get(URL, timeout=1)
    soup = BeautifulSoup(r.content, 'html.parser')

    tags = soup.find_all(attrs={'class': 'function'})
    # Exclude object methods (foo.bar) and comments (leading %, used in MATLAB Compiler)
    fcns = [tag.string for tag in tags if ('.' not in tag.string and '%' not in tag.string)]

    return fcns

def writeToolboxJSON(fcnlist, toolboxname, dest='./JSONout'):
    """
    Write input toolbox function list to dest/toolboxname.JSON
    """
    filepath = Path(dest) / f'{toolboxname}.JSON'
    with filepath.open('w') as fID:
        json.dump(fcnlist, fID)



if __name__ == "__main__":
    URLJSON = './fcnURL.JSON'
    toolboxdict = loadURLdict(URLJSON)
    for toolbox, URL in toolboxdict.items():
        try:
            fcnlist = scrapedocpage(URL)
            writeToolboxJSON(fcnlist, toolbox)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            print(f"Unable to access online docs for '{toolbox}': '{URL}'")
