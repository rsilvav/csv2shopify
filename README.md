# csv2shopify

Repository for parsing a vendor's csv file into another csv in Shopify format.

## Install

Just run:

`pip install -r requirements.txt`

## Run
For using it set the dotenv file and run:

`python3 to_shopify.py --vendor <vendor_name>`

Script will create a csv with all the data in shopify format and also chunks that acomplish the size limit for shopify (15 Mb to date)
