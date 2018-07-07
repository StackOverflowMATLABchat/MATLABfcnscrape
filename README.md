# MATLABfcnscrape
Scrape MATLAB's documentation for all function names and output to JSON files for external use

A JSON file is output per toolbox. All unique functions are also consolidated into a single JSON.

## Notes
* Only those toolboxes under the 'MATLAB Family' are considered at this time: https://www.mathworks.com/help/index.html
* Several toolboxes are inaccessible by some users due to licensing restrictions
  * See [this issue](https://github.com/StackOverflowMATLABchat/MATLABfcnscrape/issues/2) for more information