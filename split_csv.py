import csv
import sys
import argparse
import requests
import pandas as pd
import json
import shopify
import os
import numpy as np
import re
import time
import json
import string
import unicodedata
from dotenv import load_dotenv
from utils.save_chunks import save_chunks
from pathlib import Path


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

document = Path("./queries.graphql").read_text()

VENDOR_QUERY = '''
    query ($cursor: String) {
      products(first: %s, after: $cursor, query:"vendor:'%s'") {
        edges {
          cursor
          node {
            id
            title
            totalInventory
            handle
            tags
          }
        }
        pageInfo {
          hasNextPage
        }
      }
    }
    '''


META_QUERY = '''
    query ($cursor: String) {
      products(first: %s, after: $cursor, query:"vendor:'%s'") {
        edges {
          cursor
          node {
            id
            title
            handle
            metafields(first: 15) {
              edges {
                node {
                  id
                  key
                  value
                  namespace
                }
              }
            }
          }
        }
        pageInfo {
          hasNextPage
        }
      }
    }
    '''

def eliminar_unidad(texto):
    # Eliminar texto dentro de paréntesis y los paréntesis mismos
    return re.sub(r'\s*\([^)]*\)', '', texto)


def normalizar_cadena(cadena):
    if type(cadena) != str:
        return np.nan
    # Quitar acentos
    cadena_sin_acentos = ''.join(
        (c for c in unicodedata.normalize('NFD', cadena) if unicodedata.category(c) != 'Mn')
    )
    cadena_sin_acentos = cadena_sin_acentos.replace('Ø', 'o').replace('\xa0', '')
    caracteres_a_eliminar = string.punctuation + "►" + "…" + "°" + "-" + "−" + "\n"
    # Remover signos de puntuación y convertir a minúsculas
    return ''.join(caracter.lower() for caracter in cadena_sin_acentos if caracter not in caracteres_a_eliminar)
    #return ''.join(caracter.lower() for caracter in cadena_sin_acentos if caracter not in string.punctuation)


def is_number(n):
    # Esta expresión regular cubre enteros, flotantes y números negativos
    number_regex = re.compile(r'^-?\d+(?:\.\d+)?$')
    return bool(number_regex.match(n))


def make_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only-available", action="store_true")
    parser.add_argument("--vendor", type=str, required=True)
    parser.add_argument("--update-stock", action="store_true")
    parser.add_argument("--porcentaje", type=int, default=0)
    parser.add_argument("--metafields", action="store_true")
    parser.add_argument("--tags", action="store_true")
    parser.add_argument("--csv", type=str)
    return parser


def update_metafields(products, df, session, criteria):
    for xproduct in products:
        product = xproduct['node']
        prod_id = product["id"].split("/")[-1]
        title = product["title"]
        handle = product["handle"]
        metafields = product['metafields']['edges']

        meta_keys = []
        meta_vals = []

        for metafield in metafields:
            #meta_namespace = metafield.attributes["namespace"]
            meta_namespace = metafield['node']['namespace']
            
            if meta_namespace == "custom":
                meta_keys.append(metafield['node']["key"])
                meta_vals.append(metafield['node']["value"])
            
            else:
                xid = metafield['node']["id"].split("/")[-1]
                xmeta = shopify.Metafield.find(xid)
                xmeta.destroy()
                print(xmeta.attributes["key"], "metafield deleted",
                      title, meta_namespace)


        #meta_keys = [meta['node']["key"] for meta in metafields]
        #meta_vals = [meta['node']["value"] for meta in metafields]
        
        # Criteria can be handler or post_title
        _match = df[df[criteria] == handle]

        if len(_match) > 0:
            for i in range(20):
                i_names = "Attribute "+str(i + 1) + " name"
                i_vals = "Attribute "+str(i + 1) + " value(s)"
                key = _match[i_names].values[0]
                value = _match[i_vals].values[0]
                
                # Keys must not be nan
                if type(key) == float and np.isnan(key):
                    #print("skip 2")
                    continue

                elif eliminar_unidad(key) not in DEF_KEYS:
                    #print("skip 4", key)
                    continue
                
                #elif eliminar_unidad(key) == "Medidas" or eliminar_unidad(key) == "Luminosidad" or eliminar_unidad(key) == "Casquillo" or eliminar_unidad(key) == "Color":
                elif eliminar_unidad(key) != "Potencia":
                    #print("skip 4", key)
                    continue
                 
                elif not np.all(_match[i_vals] == _match[i_vals].values[0]):
                    #print("skip 3")
                    continue


                else:
                    # Eliminar unidad del string
                    key = eliminar_unidad(key)
                    
                    if criteria == "product_title" and type(value) == str:
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
                        #print(key)
                        if datatype != "string":
                            value = value.replace(" ", "")
                            value = value.replace(",", ".")
                            if datatype == "number_integer":
                                value = str(int(float(value)))
                                if value == "0":
                                    #print('skip 6', key,
                                    #      _match[i_vals].values[0])
                                    continue
                            
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
                            if prod_id == '8656677765446':
                                print(title, prod_id)
                                import pdb; pdb.set_trace()
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
        

def update_tags(products, df, vendor, criteria="post_title"):
    for product in products:
        title = product["title"]
        handle = product["handle"]
        prod_id = product["id"].split("/")[-1]
        #if criteria == "post_title":
        xmatch = df[df[criteria] == title]
        #else:
        #    xmatch = df[df[criteria] == handle]
        #print(product["tags"])
        if len(xmatch) > 0 and len(product["tags"]) == 0:
            #import pdb; pdb.set_trace()
            tags = xmatch["category_tree"].values[0]
            if type(tags) != str:
                continue
            tags = tags.replace(' -', ',')
            product = shopify.Product.find(str(prod_id))
            product.tags = tags
            product.save()
            print("tags updated", title, tags)
            

def retrieve_shopify(vendor): 
    # Configurar el token y la URL de la tienda
    # print(SHOP_URL, ACCESS_TOKEN)
    session = shopify.Session(SHOP_URL, token=ACCESS_TOKEN, version="2022-10")
    shopify.ShopifyResource.activate_session(session)
    locations = shopify.Location.find()
    location = locations[0] 
    return location.id, session


def retrieve_raw_vendor():
    names = ['post_title', 'sku', 'stock']
    n_attributes = 20
    # Read CSV from URL into DataFrame
    print(f"retrieving {args.venor} metafields from", VENDOR_RAW_URL)
    df_gt = pd.read_csv(VENDOR_RAW_URL, sep=';', usecols=range(60),
                        index_col=False)

    return df_gt


def get_new_products(d_products, df):
    df_unique = pd.unique(df['post_title'])
    df = df[~df['post_title'].isin(d_products.keys())]


    for title in df_gt['post_title'].unique():    
        xmatch = df_gt[df_gt['post_title'] == product.title]
        if len(xmatch) == 0:
            d_titles[product.title] = product.id
        else:
            print("title match", product.title, product.id)
    return d_titles
    

def update_shopify(products, df_shop, location_id, inventory):
    print("\tupdating Shopify stocks...")
    for xproduct in inventory:
        #print(xproduct)
        prod_id = xproduct["id"].split("/")[-1]
        var_sku = xproduct["sku"]
        var_levels = xproduct["inventoryItem"]["inventoryLevels"]
        var_stock = var_levels["edges"][0]["node"]["available"]
        inv_id = xproduct["inventoryItem"]["id"].split("/")[-1]
        sku_mask = df_shop['Variant SKU'] == var_sku
        _match = df_shop[sku_mask]["Variant Inventory Qty"] 

        if len(_match) > 0:
            match_stock = int(_match.values[0])
            prev_stock = var_stock
            sku = var_sku
            
            if match_stock == 0:
                if prev_stock == 0:
                    code = 429
                    while code == 429:
                        try:
                            shopify.InventoryLevel.set(inventory_item_id=inv_id,
                                                       available=2,
                                                       location_id=location_id)
                            print("\t", sku, "actualizado", 2, "unidades")
                            code = 200

                        except Exception as e:
                            if e.code == 429:
                                print("429 error, retrying...") #) #, waiting 5 seconds")

                            elif e.code == 500 or e.code == 502:
                                print("500 error")
                                pass
                                
                            else:
                                print(f"Ocurrió una excepción: {e}")    

            elif prev_stock != match_stock and match_stock != 0:
                if prev_stock == 0:
                    code = 429
                    while code == 429:
                        try:
                            shopify.InventoryLevel.set(inventory_item_id=inv_id,
                                                       available=match_stock,
                                                       location_id=location_id)
                            print("\t", sku, "updated", prev_stock, "to",
                                  match_stock)
                            code = 200

                        except Exception as e:
                            if e.code == 429:
                                print("429 error, retrying...") #) #, waiting 5 seconds")

                            elif e.code == 500 or e.code == 502:
                                print("500 error")
                                pass
                                
                            else:
                                print(f"Ocurrió una excepción: {e}")  


def retrieve_products(vendor, limit=250, cursor=None):
    # La consulta GraphQL para obtener productos
    graphql_query = VENDOR_QUERY % (limit, vendor)
    tiene_siguiente_pagina = True
    # Ciclo para manejar la paginación
    data = {}
    count = 0
    while tiene_siguiente_pagina:
        payload = {
            'query': graphql_query,
            'variables': {'cursor': cursor}
        }
        response = requests.post(GRAPHQL_URL, headers=HEADERS, json=payload)
        data = response.json()
        # Retry until it works
        while "errors" in data.keys():
            # print("\t throttled")
            response = requests.post(graphql_url, headers=HEADERS,
                                     json=payload)
            data = response.json()

        products = data['data']['products']
        edges = products['edges']

        count += len(edges)
        print(count, "products loaded")
        tiene_siguiente_pagina = products['pageInfo']['hasNextPage']
        cursor = edges[-1]["cursor"]
        yield [edge['node'] for edge in edges]
        #for edge in edges:
            #productos.append(edge['node'])
            #yield edge['node']
            #cursor = edge['cursor']
    #return productos

def delete_product(prod_id):
    try:
        product = shopify.Product.find(str(prod_id))
        product.destroy()
        print(f"Producto con ID {prod_id} ha sido borrado.")
    except Exception as e:
        print(f"Error al borrar el producto: {e}")


def check_variants(products, df_shop):
    # print("updating Shopify products...")
    inventory = []
    norm_handles = df_shop['Handle'].apply(normalizar_cadena)
    for xproduct in products:
        prod_id = xproduct["id"].split("/")[-1]
        product_title = xproduct["title"]
        product_handle = xproduct["handle"]
        product_vars = xproduct["variants"]["edges"]
        product_stock = xproduct["totalInventory"] 
        handle_mask = norm_handles == normalizar_cadena(product_handle)
        _match = df_shop[handle_mask]

        if len(_match) > 0:
            match_stock = np.nansum(_match['Variant Inventory Qty'])
            n_variants = len(pd.unique(_match["Variant SKU"].dropna()))

            
            if n_variants != len(product_vars):
                print("Variant number mismatch, deleting product",
                      product_handle)
                #product.destroy()
                delete_product(prod_id)
                continue

            # Stock 0 en la planilla 
            # elif match_stock == 0:
            #    if product_stock == 2*n_variants:
            #        continue

            for variant in product_vars:
                prev_stock = variant["node"]["inventoryQuantity"]
                sku = variant["node"]["sku"]
                variant_id = variant["node"]["id"]
                
                if normalizar_cadena(product_handle) == normalizar_cadena(sku):
                    print("\t Wrong SKU detected, deleting product", product.title)
                    product.destroy()
                    break

                sku_norm = normalizar_cadena(sku)
                column_norm = _match['Variant SKU'].apply(normalizar_cadena)
                stock_mask = column_norm == sku_norm
                match_sku = _match[stock_mask]

                if len(match_sku) == 0:
                    print("SKU missmatch, deleting product", product_handle,
                          sku)
                    #import pdb; pdb.set_trace()
                    #product.destroy()
                    delete_product(prod_id)
                    break

            #print(product_title, product_stock, match_stock)
            inventory.append(variant_id)
    # print("\t", len(inventory), "products to update")
    return inventory


def check_stock(products, df_shop, location_id):
    # print("Checking Shopify products...")
    product_ids = []
    norm_handles = df_shop['Handle'].apply(normalizar_cadena)
    for xproduct in products:
        prod_id = xproduct["id"].split("/")[-1]
        product_title = xproduct["title"]
        product_handle = xproduct["handle"]
        product_stock = xproduct["totalInventory"] 
        handle_mask = norm_handles == normalizar_cadena(product_handle)
        _match = df_shop[handle_mask]

        if len(_match) > 0:
            match_stock = np.nansum(_match['Variant Inventory Qty'])
            n_variants = len(pd.unique(_match["Variant SKU"].dropna()))

            
            # Los stocks coinciden
            if match_stock == product_stock and match_stock > 0:
                continue

            # El stock lo concentra una unica variante
            elif product_stock == match_stock + 2*(n_variants - 1) and product_stock > 0:
                continue

            # Stock 0 en la planilla, rellenado con 2 unidades
            elif match_stock == 0:
                if product_stock == 2*n_variants:
                    continue


            product_ids.append(xproduct["id"])

        else:
            print("Shopify product not found", product_handle, "deleting...")
            try:
                product = shopify.Product.find(str(prod_id))
                product.destroy()
                print(f"Producto con ID {prod_id} ha sido borrado.")
            except Exception as e:
                print(f"Error al borrar el producto: {e}")

        # product_ids.append(xproduct["id"])

    return product_ids


def obtener_stocks(inventory_item_ids, limite=250):
    query2 = """
    query($ids: [ID!]!) {
      nodes(ids: $ids) {
        ... on ProductVariant {
          id
          sku
          inventoryItem {
            id
            inventoryLevels(first: 1) {
              edges {
                node {
                  available  # Stock disponible
                }
              }
            }
          }
        }
      }
    }
    """
    products = []
    data = {}
    for i_products in range(0, len(inventory_item_ids), limite):
        ids = inventory_item_ids[i_products:i_products + limite]
        variables = {'ids': ids}
        payload = {'query': query2, 'variables': variables}
        response = requests.post(f'{SESSION_URL}/admin/api/2022-04/graphql.json',
                                 headers=HEADERS, json=payload)

        data = response.json()
        # Retry until it works
        while "errors" in data.keys():
            print("\t throttled")
            response = requests.post(f'{SESSION_URL}/admin/api/2022-04/graphql.json',
                                     headers=HEADERS, json=payload)
            data = response.json()
        products_i = data['data']['nodes']
        products.extend(products_i)
        print("\t", len(products))
    return products


def obtener_variantes(product_ids, limite=230):
    query = """
    query($ids: [ID!]!) {
      nodes(ids: $ids) {
        ... on Product {
          title
          handle
          id
          totalInventory
          tags
          variants(first: 250) {
            edges {
              node {
                id
                title
                inventoryQuantity
                sku
              }
            }
          }
        }
      }
    }
    """
    products = []
    cursor = None
    data = {}
    for i_products in range(0, len(product_ids), limite):
        ids = product_ids[i_products:i_products + limite]
        variables = {'ids': ids}
        payload = {'query': query, 'variables': variables}
        response = requests.post(f'{SESSION_URL}/admin/api/2022-04/graphql.json',
                                 headers=HEADERS, json=payload)

        data = response.json()
        # Retry until it works
        while "errors" in data.keys():
            print("\t throttled")
            response = requests.post(f'{SESSION_URL}/admin/api/2022-04/graphql.json',
                                     headers=HEADERS, json=payload)
            data = response.json()
        products_i = data['data']['nodes']
        products.extend(products_i)
        # print("\t", len(products))
    return products


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
        print("\t", len(metafields))
    return metafields


def update_meta(df, vendor, criteria, limite=50, cursor=None):
    # La consulta GraphQL para obtener productos
    graphql_query = META_QUERY % (limite, vendor)
    tiene_siguiente_pagina = True
    # Ciclo para manejar la paginación
    data = {}
    retrieved = 0
    while tiene_siguiente_pagina:
        payload = {
            'query': graphql_query,
            'variables': {'cursor': cursor}
        }
        #response = requests.post(GRAPHQL_URL, headers=HEADERS, json=payload)
        #data = response.json()
        # Retry until it works
        data = {'errors': 0}
        while "errors" in data.keys():
            # print("\t throttled")
            # import pdb; pdb.set_trace()
            response = requests.post(GRAPHQL_URL, headers=HEADERS,
                                     json=payload)
            data = response.json()

        # data = response.json()
        # import pdb; pdb.set_trace()
        products = data['data']['products']
        edges = products['edges']
        #for edge in edges:
            #productos.append(edge['node'])
            #cursor = edge['cursor']
            # metafields = edge['node']['metafields']
        cursor = edges[-1]['cursor']
        update_metafields(edges, df, session, criteria) #, vendor=vendor)
        retrieved += len(edges)    
        print("\t", retrieved)
        tiene_siguiente_pagina = products['pageInfo']['hasNextPage']
    #return productos


if __name__ == "__main__":
    parser = make_parser()
    args = parser.parse_args()
    folder_path = 'conflicts'
    # Verifica si la carpeta existe
    if not os.path.exists(folder_path):
        # Si no existe, crea la carpeta
        os.makedirs(folder_path)

    # Read CSV from URL into DataFrame
   
    if not args.csv:
        criteria = "post_title"
        print_str = "Retrieving products from"
        print(print_str, VENDOR_URL)
        # Read CSV from URL into DataFrame
        df_shop = pd.read_csv(VENDOR_URL, on_bad_lines='skip')
        if args.metafields or args.tags:
            print("RETRIEVING METAFIELDS AND TAGS")
            vendor_df = retrieve_raw_vendor()
            
    else:
        criteria = "handle"
        print("Retrieving products from", args.csv)
        df_shop = pd.read_csv(args.csv)
        if args.metafields:
            vendor_df = pd.read_csv("metafields.csv")
        
    
    df_shop['Vendor'] = args.vendor
    filename_prefix = args.vendor
    save_chunks(df_shop, MAX_FILE_SIZE, filename_prefix)
    n_products = len(pd.unique(df_shop["Handle"].dropna()))
    print(n_products, "products to upload")

    if args.update_stock or args.metafields or args.tags:
        print("retrieving Shopify catalog...")
        location_id, session = retrieve_shopify(args.vendor)
        response = shopify.GraphQL().execute(
                query=document,
                operation_name="MetafieldDefinitionsQuery",
                )

        response = json.loads(response)
        definitions = response["data"]["metafieldDefinitions"]["edges"]
        DEF_KEYS = [x["node"]["key"] for x in definitions]
        DEF_TYPES = [x["node"]["type"]["name"] for x in definitions]


        #old_shopify = obtener_productos_vendor(vendor=args.vendor)
        for old_shopify in retrieve_products(limit=250, vendor=args.vendor):
            # continue 
            if args.update_stock:
                print("\tCHECKING STOCK")
                old_shopify = check_stock(old_shopify, df_shop, location_id)
                print("\tRETRIEVING VARIANTS")
                old_shopify = obtener_variantes(old_shopify)
                print(f"\tCHECKING {len(old_shopify)} VARIANTS")
                variants = check_variants(old_shopify, df_shop)
                print("\tRETRIEVING INVENTORY LEVELS")
                inventory = obtener_stocks(variants)
                print("\tUPDATE STOCKS")
                update_shopify(variants, df_shop, location_id, inventory)
        
            
            if args.metafields or args.tags:
                if args.metafields:
                    print("RETRIEVING METAFIELDS")
                    metafields = retrieve_metafields(old_shopify)
                    update_meta(vendor_df, args.vendor, criteria)
                    #update_metafields(old_shopify, vendor_df, session=session,
                    #                  vendor=args.vendor)

                if args.tags and not args.csv:
                    print("UPDATE TAGS")
                    update_tags(old_shopify, vendor_df, args.vendor)
