import shopify
from pathlib import Path
import json

document2 = Path("./queries2.graphql").read_text()


def retrieve_stocks(inventory_item_ids, limite=250):
    """
    Given a list of item ids, calls the API to retrieve stocks

    Parameters
    ----------
    inventory_item_ids: list
        List of ids

    limit: int
        Max number of items to retrieve


    Yields
    -------
    products_i: 
        List of dicts of the requested products
    """

    products = []
    data = {}
    for i_products in range(0, len(inventory_item_ids), limite):
        ids = inventory_item_ids[i_products:i_products + limite]
        response = shopify.GraphQL().execute(query=document2,
                                             variables={"ids": ids},
                                             operation_name="IQuery",
                                             )
        data = json.loads(response)
        while "errors" in data.keys():
            print("\t throttled")
            response = requests.post(f'{SESSION_URL}/admin/api/2022-04/graphql.json',
                                     headers=HEADERS, json=payload)
            data = response.json()
        products_i = data['data']['nodes']
        yield products_i
