# MATLABfcnscrape
Scrape MATLAB's documentation for all valid function names and output to JSON files for external use

A JSON file is output per toolbox, along with one concatenated JSON

## Notes
Object methods (e.g. `cdflib.close`) are ignored for the JSON output

Duplicates are removed in the concatenated JSON file