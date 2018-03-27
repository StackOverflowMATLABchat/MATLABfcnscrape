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

logformat = '%(asctime)s %(levelname)s:%(module)s:%(message)s'
dateformat = '%Y-%m-%d %H:%M:%S'
logging.basicConfig(filename='./log/scrape.log', filemode='a', level=logging.INFO, 
                    format=logformat, datefmt=dateformat
                    )

def loadURLdict(sourceJSON='./fcnURL.JSON'):
    """
    Load URL dictionary from input JSON file

    Expected input dict format a nested dict:
        Top level dict is MATLAB's "Family" group
        Next level is a dict of toolbox:URL KV-pair for each group

    Output is a single layer dict containing the toolbox:url KV-pairs
    """
    sourceJSON = Path(sourceJSON)
    with sourceJSON.open(mode='r') as fID:
        tmp = json.load(fID)

    squeezegen = (tmp[grouping] for grouping in tmp.keys())
    return {k: v for d in squeezegen for k, v in d.items()}

def scrapedocpage(URL):
    """
    Scrape functions from input MATLAB Doc Page URL

    Object methods (foo.bar) and comments (leading %) are excluded

    Returns a list of function name strings, or an empty list if none are found (e.g. no permission for toolbox)
    """
    r = requests.get(URL, timeout=2)
    soup = BeautifulSoup(r.content, 'html.parser')

    tags = soup.find_all(attrs={'class': 'function'})
    
    # Iterate through tags & apply filters before appending to function list
    fcns = []
    for tag in tags:
        line = tag.string
        # Blacklist filters
        if re.findall(r'[%:]', line):
            # Ignore lines with '%' or ':'
            continue
        if re.match(r'^ocv', line):
            # Ignore OpenCV C++ commands
            continue
        elif 'ColorSpec' in line or 'LineSpec' in line:
            # Ignore ColorSpec and LineSpec
            # TODO: Add JSON function blacklist
            continue

        # Strip out anything encapsulated by parentheses or brackets
        line = re.sub(r'[[({][A-Za-z0-9,.]+[])}]', '', line).strip()
        # "Modification" filters
        if ',' in line:
            # Split up functions on lines with commas
            [fcns.append(thing.strip()) for thing in line.split(',')]
        elif '.' in line:
            # Skip regex filter for object methods
            fcns.append(line)
        else:
            # Otherwise apply a simple regex filter for the first word on a line
            tmp = re.findall('^\w+', line)
            if tmp:
                fcns.append(tmp[0])

    return fcns

def writeToolboxJSON(fcnlist, toolboxname, JSONpath='./JSONout'):
    """
    Write input toolbox function list to dest/toolboxname.JSON
    """
    JSONpath = Path(JSONpath)
    JSONpath.mkdir(parents=True, exist_ok=True)  # Create destination folder if it doesn't already exist
    
    filepath = JSONpath / f'{toolboxname}.JSON'
    with filepath.open(mode='w') as fID:
        json.dump(fcnlist, fID, indent="\t")

def concatenatefcns(JSONpath='./JSONout', fname='_combined'):
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
        json.dump(sorted(fcnset, key=str.lower), fID, indent="\t")

def scrapetoolboxes(URL="https://www.mathworks.com/help/index.html", JSONpath = '.', fname='fcnURL'):
    """
    Generate a dictionary of toolboxes & link to the alphabetical function list

    Dictionary is dumped to JSON/fname.JSON
    """
    r = requests.get(URL, timeout=2)
    soup = BeautifulSoup(r.content, 'html.parser')

    # Get first header that matches 'MATLAB', this should be our 'MATLAB Family' column
    # For some reason soup.find_all('h2', string=re.compile('MATLAB')) returns an empty list
    # Generator approach from SO: https://stackoverflow.com/a/7006873/2748311
    matlabheader = next((t for t in soup.find_all('h2') if t.find(text=re.compile('MATLAB'))), None)

    # Get to column div from the header, this is 2 levels above
    matlabcolumn = matlabheader.parent.parent

    # Iterate through MATLAB's groupings (does not include base MATLAB) and pull toolboxes & links by group
    # Build lambda to strip spaces out of the toolbox names
    namelambda = lambda x: x.replace(" ", "")

    groupeddict = {}
    # Add base MATLAB manually
    groupeddict['Base Matlab'] = {'MATLAB': "https://www.mathworks.com/help/matlab/functionlist-alpha.html"}
    for grouping in matlabcolumn.find_all('h4'):
        groupeddict[grouping.text] = {namelambda(listitem.text): helpURLbuilder(listitem.a.get('href'))for listitem in grouping.parent.find_all('li')}

    JSONpath = Path(JSONpath)
    outfilepath = JSONpath / f'{fname}.JSON'
    with outfilepath.open(mode='w') as fID:
        json.dump(groupeddict, fID, indent="\t")

def helpURLbuilder(shortlink, prefix="https://www.mathworks.com/help/", suffix="/functionlist-alpha.html"):
    """
    Helper to build URL for alphabetical function list from the toolbox's shortlink

    e.g. 'https://www.mathworks.com/help/stats/functionlist-alpha.html' from 'stats/index.html'

    Returns a string
    """
    return prefix + shortlink.split('/')[0] + suffix


if __name__ == "__main__":
    outpath = './JSONout/R2018a'

    scrapetoolboxes()
    toolboxdict = loadURLdict()
    logging.info(f"Scraping {len(toolboxdict)} toolboxes")
    logging.info(f"Writing results to: {outpath}")
    for toolbox, URL in toolboxdict.items():
        try:
            fcnlist = scrapedocpage(URL)
            if len(fcnlist) == 0:
                # No functions found, most likely because permission for the toolbox documentation is denied
                logging.info(f"Permission to view documentation for '{toolbox}' has been denied: {URL}")
            else:
                writeToolboxJSON(fcnlist, toolbox, outpath)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            # TODO: Add a retry pipeline, verbosity of exception
            logging.info(f"Unable to access online docs for '{toolbox}': '{URL}'")
    else:
        concatenatefcns(outpath)