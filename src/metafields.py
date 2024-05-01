import os
import requests
from dotenv import load_dotenv
import re
import numpy as np
import json
import shopify


MAX_FILE_SIZE = 15 * 10**6
load_dotenv()
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
SESSION_URL = os.getenv("SESSION_URL")
SHOP_URL = SESSION_URL + '/admin'
VENDOR_URL = os.getenv("VENDOR_URL")
VENDOR_RAW_URL = os.getenv("VENDOR_RAW_URL")
HEADERS = {"Content-Type": "application/json",
           "X-Shopify-Access-Token": ACCESS_TOKEN}
GRAPHQL_URL = f'{SESSION_URL}/admin/api/2022-04/graphql.json'
META_BL = ["Medidas", "Color", "Regulable"]

def remove_unit(texto):
    # Eliminar texto dentro de paréntesis y los paréntesis mismos
    return re.sub(r'\s*\([^)]*\)', '', texto)

def retrieve_metafields(product_ids, limite=250):
    query = """
    query($ids: [ID!]!) {
      nodes(ids: $ids) {
        ... on Product {
          title
          handle
          id
          metafields(first: 250) {
            edges {
              node {
                key
                value
                namespace
              }
            }
          }
        }
      }
    }
    """
    metafields = []
    data = {}
    for i_products in range(0, len(product_ids), limite):
        ids = product_ids[i_products:i_products + limite]
        ids = [id["id"] for id in ids]
        variables = {'ids': ids}
        payload = {'query': query, 'variables': variables}
        response = requests.post(f'{SESSION_URL}/admin/api/2022-04/graphql.json',
                                 headers=HEADERS, json=payload)

        data = response.json()
        # Retry until it works
        while "errors" in data.keys():
            import pdb; pdb.set_trace()
            print("\t throttled")
            response = requests.post(f'{SESSION_URL}/admin/api/2022-04/graphql.json',
                                     headers=HEADERS, json=payload)
            data = response.json()
        metafields_i = data['data']['nodes']
        metafields.extend(metafields_i)
        #print("\t", len(metafields))
    return metafields



def update_metafields(products, df, session, DEF_KEYS, DEF_TYPES, criteria):
    """
    Matches online products with online products and update metafields
    if they are different

    Parameters
    ----------
    products: list
        List of dicts

    df: object
        Pandas dataframe of offline product metafields

    session:


    criteria: str
        Criteria for matching online dict and offline dataframe

    """

    for product in products:
        if product is None:
            continue
        prod_id = product["id"].split("/")[-1]
        title = product["title"]
        handle = product["handle"]
        metafields = product['metafields']['edges']
        meta_keys = []
        meta_vals = []

        for metafield in metafields:
            meta_namespace = metafield['node']['namespace']

            if meta_namespace == "custom":
                #for simplicity, only namespace allowed is "custom"
                meta_keys.append(metafield['node']["key"])
                meta_vals.append(metafield['node']["value"])

        # Criteria can be handler or post_title
        if criteria == "post_title":
            _match = df[df[criteria] == title]

        else:
            _match = df[df[criteria] == handle]

        if len(_match) > 0:
            for i in range(20):
                i_names = "Attribute "+str(i + 1) + " name"
                i_vals = "Attribute "+str(i + 1) + " value(s)"
                key = _match[i_names].values[0]
                value = _match[i_vals].values[0]

                # Keys must not be nan
                if type(key) == float and np.isnan(key):
                    continue

                elif remove_unit(key) not in DEF_KEYS:
                    continue

                elif remove_unit(key) in META_BL:
                    continue

                elif not np.all(_match[i_vals] == _match[i_vals].values[0]):
                    continue


                else:
                    key = remove_unit(key)

                    if criteria == "post_title" and type(value) == str:
                        split = value.split(":")
                        if len(split) <= 2:
                            value = split[0]
                            if value == "":
                                continue


                    meta_dict = {"value":value,
                                 "key": key,
                                 "namespace": "custom",
                                 "type": "string",}


                    # Load only defined metafields
                    if key in DEF_KEYS:
                        i_def_type = DEF_KEYS.index(key)
                        datatype = DEF_TYPES[i_def_type]
                        meta_dict["type"] = datatype
                        if datatype != "string":
                            if type(value) == float:
                                value = str(value)
                            value = value.replace(" ", "")
                            value = value.replace(",", ".")
                            int_cond = datatype == "number_integer"
                            if int_cond:
                                value = str(int(float(value)))
                                if value == "0":
                                    #print('skip 6', key,
                                    #      _match[i_vals].values[0])
                                    continue

                            elif datatype == "number_decimal":
                                 value = str(float(value))

                            elif datatype == "weight":
                                aux_dict = {"value": str(value),
                                            "unit": "g"}
                                value = json.dumps(aux_dict)

                            meta_dict["value"] = value


                    # If there is a previous value for the metafield
                    if key in meta_keys:
                        i_meta = meta_keys.index(key)
                        prev_val = meta_vals[i_meta]
                        if prev_val == value:
                            continue
                        elif key in DEF_KEYS and datatype == "weight":
                            prev_val = json.loads(prev_val)["value"]
                            prev_val = float(prev_val)
                            str_weight = json.loads(value)["value"]
                            if prev_val == float(str_weight):
                                continue

                    elif type(value) == float:
                        if np.isnan(value):
                            #print("skip 5")
                            continue

                    code = 429
                    while code == 429:
                        try:
                            product = shopify.Product.find(prod_id)
                            res = product.add_metafield(shopify.Metafield(meta_dict))
                            print("\tmetafields updated", product.title, key, value, res)
                            code = 200

                        except Exception as e:
                            if e.code == 429:
                                print("429 error, retrying...") #) #, waiting 5 seconds")

                            elif e.code == 500 or e.code == 502:
                                print("500 error")
                                pass

                            else:
                                print(f"Ocurrió una excepción: {e}")

        else:
            print("no match", title, handle)
            #continue
