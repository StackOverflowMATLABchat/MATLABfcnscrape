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

logformat = '%(asctime)s %(levelname)s:%(module)s:%(message)s'
dateformat = '%Y-%m-%d %H:%M:%S'
logging.basicConfig(filename='./log/scrape.log', filemode='a', level=logging.INFO, 
                    format=logformat, datefmt=dateformat
                    )

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

    # TODO: Filtering on OPC (e.g. foo (opcda))
    # TODO: Filtering on base MATLAB (e.g. ColorSpec, LineSpec), probably have to do a blacklist
    # TODO: Filter on Computer Vision (e.g. take out C++ syntax, ocvCvRectToBoundingBox_{DataType}), probably have to do a blacklist

    return fcns

def writeToolboxJSON(fcnlist, toolboxname, JSONpath='./JSONout'):
    """
    Write input toolbox function list to dest/toolboxname.JSON
    """
    JSONpath = Path(JSONpath)
    JSONpath.mkdir(parents=True, exist_ok=True)  # Create destination folder if it doesn't already exist
    
    filepath = JSONpath / f'{toolboxname}.JSON'
    with filepath.open(mode='w') as fID:
        json.dump(fcnlist, fID)

def concatenatefcns(JSONpath='./JSONout', fname='combined'):
    """
    Generate concatenated function set from directory of JSON files and write to 'fname.JSON'

    Assumes JSON file is a list of function name strings 
    """
    JSONpath = Path(JSONpath)
    outfilepath = JSONpath / f'{fname}.JSON'

    fcnset = set()
    for fcnJSON in JSONpath.glob('*.JSON'):
        with fcnJSON.open(mode='r') as fID:
            fcnset.update(json.load(fID))
    
    logging.info(f"Concatenated {len(fcnset)} unique functions")
    with outfilepath.open(mode='w') as fID:
        json.dump(sorted(fcnset), fID)


if __name__ == "__main__":
    URLJSON = './fcnURL.JSON'
    outpath = './JSONout/R2018a'
    toolboxdict = loadURLdict(URLJSON)
    logging.info(f"Scraping {len(toolboxdict)} toolboxes")
    logging.info(f"Writing results to: {outpath}")
    for toolbox, URL in toolboxdict.items():
        try:
            fcnlist = scrapedocpage(URL)
            writeToolboxJSON(fcnlist, toolbox, outpath)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            # TODO: Add a retry pipeline
            logging.info(f"Unable to access online docs for '{toolbox}': '{URL}'")
    else:
        concatenatefcns(outpath)