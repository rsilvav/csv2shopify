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
from utils.api import update_inventory
from pathlib import Path
from io import StringIO
from utils.download import download_csv
from src.metafields import retrieve_metafields, update_metafields
from src.stocks import retrieve_stocks


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
document2 = Path("./queries2.graphql").read_text()

#meta_bl = ["Medidas", "Color", "Regulable"]

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
            metafields(first: 50) {
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


def update_tags(products, df, vendor, criteria="post_title"):
    """
    Matches online products with online products and fill tags field if
    it's empty

    Parameters
    ----------
    products: list
        List of dicts

    df: object
        Pandas dataframe of offline products

    vendor: string
        Vendor name

    criteria: str
        Criteria for matching online dict and offline dataframe

    """

    for product in products:
        title = product["title"]
        handle = product["handle"]
        prod_id = product["id"].split("/")[-1]
        xmatch = df[df[criteria] == title]
        if len(product["tags"]) == 0:
            if len(xmatch) > 0:
                tags = xmatch["category_tree"].values[0]
                if type(tags) != str:
                    continue
                tags = tags.replace(' -', ',')
                product = shopify.Product.find(str(prod_id))
                product.tags = tags
                product.save()
                print("tags updated", title, tags)

            else:
                pdb.set_trace()
            

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
    print(f"retrieving {args.vendor} metafields from", VENDOR_RAW_URL)
    io = download_csv(VENDOR_RAW_URL)
    df_gt = pd.read_csv(io, sep=';', usecols=range(60), index_col=False)

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
        if xproduct is None:
            continue
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
            
            if match_stock == prev_stock and prev_stock == 0:
                update_inventory(inv_id, location_id, sku, 2)

            elif prev_stock != match_stock:
                if match_stock > 0:
                    update_inventory(inv_id, location_id, sku, match_stock)



def retrieve_products(vendor, limit=250, cursor=None):
    # La consulta GraphQL para obtener productos
    graphql_query = VENDOR_QUERY % (limit, vendor)
    has_next_page = True
    # Ciclo para manejar la paginación
    data = {}
    count = 0
    #while tiene_siguiente_pagina:
    while has_next_page:
    #if has_next_page:
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
        has_next_page = products['pageInfo']['hasNextPage']
        cursor = edges[-1]["cursor"]
        yield [edge['node'] for edge in edges]
        #for edge in edges:
        #    productos.append(edge['node'])
        #    yield edge['node']
        #    cursor = edge['cursor']
    #yield productos
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
    """
    Compares the current (old/online) products list with the new/offline one,
    deleting online products that are not matched
    
    Parameters
    ----------
    products: list
        List of products' dicts

    df_shop: Object
        Pandas dataframe of offline products

    location_id:

    Returns
    -------
    list:
        IDs list of matched products
    """
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
    #print(len(product_ids))
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
        #csv_data = requests.get(VENDOR_URL)
        #io = StringIO(csv_data.text)
        io = download_csv(VENDOR_URL)
        df_shop = pd.read_csv(io, on_bad_lines='skip')
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

        for old_shopify in retrieve_products(limit=250, vendor=args.vendor):
            if args.update_stock:
                print("\tCHECKING STOCK")
                old_shopify = check_stock(old_shopify, df_shop, location_id)
                print("\tRETRIEVING VARIANTS")
                old_shopify = obtener_variantes(old_shopify)
                print(f"\tCHECKING {len(old_shopify)} VARIANTS")
                variants = check_variants(old_shopify, df_shop)
                print("\tRETRIEVING INVENTORY LEVELS")
                print("\tUPDATE STOCKS")
                for inv_chunk in retrieve_stocks(variants):
                    update_shopify(variants, df_shop, location_id, inv_chunk)
        
            
            if args.metafields or args.tags:
                if args.metafields:
                    print("\tRETRIEVING METAFIELDS")
                    metafields = retrieve_metafields(old_shopify)
                    #update_meta(vendor_df, args.vendor, criteria)
                    update_metafields(metafields, vendor_df, session,
                                      DEF_KEYS, DEF_TYPES, criteria)

                if args.tags and not args.csv:
                    print("UPDATE TAGS")
                    update_tags(old_shopify, vendor_df, args.vendor)
