import json

import requests
from bs4 import BeautifulSoup

def scrapedocpage(URL):
    """
    Scrape functions from input MATLAB Doc Page URL

    Object methods (foo.bar) and comments (leading %) are excluded

    Returns a list of function name strings
    """
    r = requests.get(URL)
    soup = BeautifulSoup(r.content, 'html.parser')

    tags = soup.find_all(attrs={'class': 'function'})
    # Exclude object methods (foo.bar) and comments (leading %, used in MATLAB Compiler)
    fcns = [tag.string for tag in tags if ('.' not in tag.string and '%' not in tag.string)]

    return fcns