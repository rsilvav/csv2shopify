# csv2shopify

Repository for parsing a vendor's csv file into another csv in Shopify format.

## Install

Just run:

`pip install -r requirements.txt`

## Run

### Parsing csv file

For parsing vendor csv run:

`python3 to_shopify.py --vendor <VENDOR_NAME>`

Load the csv vendor file and the script will create a new csv with all the data in shopify format and also chunks that acomplish the size limit for shopify (15 Mb to date)

### Setting environment

Set a .env file and define ACCESS_TOKEN, SESSION_URL, VENDOR_URL, VENDOR_RAW_URL vars (see .env.example file)

### Updating Stocks

For updating shopify product stocks given a csv (in shopify format) execute:

`python split_csv.py --csv <CSV_FILE> --update-stock --vendor <VENDOR_NAME>`

Alternatively, for updating stocks from an online csv, you can run:

`python split_csv.py --update-stock --vendor <VENDOR_NAME>`
