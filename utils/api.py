import shopify

def update_inventory(inv_id, location_id, sku, units):
    """
    Update inventory levels for a product
    """

    code = 429
    while code == 429:
        try:
            #import pdb; pdb.set_trace()
            shopify.InventoryLevel.set(inventory_item_id=inv_id,
                                       available=units,
                                       location_id=location_id)
            print("\t", sku, "updated to ", units, " units")
            code = 200

        except Exception as e:
            if e.code == 429:
                print("429 error, retrying...") #) #, waiting 5 seconds")
                        
            elif e.code == 500 or e.code == 502:
                print("500 error")
                pass
                                
            else:
                print("Error", e.code, e.message)
