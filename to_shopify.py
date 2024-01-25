import sys
import csv
import argparse
import pandas as pd
from utils.save_chunks import save_chunks
import tkinter as tk
from tkinter import filedialog

MAX_FILE_SIZE = 15 * 10**6

fieldnames = ["Handle", "Title", "Body (HTML)", "Vendor", "Type", "Tags",
              "Published", "Option1 Name", "Option1 Value", "Variant SKU",
              "Variant Grams", "Variant Inventory Tracker",
              "Variant Inventory Qty", "Variant Inventory Policy",
              "Variant Fulfillment Service", "Variant Price",
              "Variant Compare At Price", "Variant Requires Shipping",
              "Variant Taxable", "Image Src", "Image Alt Text", "Image Src 1",
              "Image Alt Text 1", "Image Src 2", "Image Alt Text 2",
              "Image Src 3", "Image Alt Text 3", "Image Src 4",
              "Image Alt Text 4", "Image Src 5", "Image Alt Text 5",
              "Image Src 6", "Image Alt Text 6", "Image Src 7",
              "Image Alt Text 7", "Status", "Option2 Name", "Option2 Value",
              "Option3 Name", "Option3 Value"]


# Add additional images for the product
image_columns = ["imagenGaleria1", "imagenGaleria2", "imagenGaleria3",
                 "imagenEsquema", "imagenLuminica", "imagenInstalacion",
                 "imagenInstalacion2"]


def make_parser():
    parser = argparse.ArgumentParser()
    #parser.add_argument("--csv", type=str, required=True)
    parser.add_argument("--vendor", type=str, required=True)
    parser.add_argument("--porcentaje", type=int, default=45)
    parser.add_argument("--metafields", action="store_true")
    return parser

def convertir_a_float(numero_str):
    sin_puntos = numero_str.replace(".", "")
    con_punto_decimal = sin_puntos.replace(",", ".")
    return float(con_punto_decimal)

def float_a_formato_original(numero_float):
    parte_entera = int(numero_float)
    parte_decimal = int(round((numero_float - parte_entera) * 100))
    formato_entero = "{:,}".format(parte_entera).replace(",", ".")
    formato_decimal = "{:02}".format(parte_decimal)
    return "{},{}".format(formato_entero, formato_decimal)

def convert_csv(input_file, output_prefix, vendor,
                porcentaje=45):
    

    with open(input_file, 'r', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        metafields = {}
        for header in reader.fieldnames:
            split_header = header.split("-")
            if len(split_header) > 1:
                raw_name = "-".join(split_header[1:]).strip()
                metafields[header] = raw_name
        
        
        if args.metafields:
            fieldnames_meta = ["sku", "handle"]
            for i_attr in range(35):
                fieldnames_meta.append("Attribute " + str(i_attr + 1) + " name")
                fieldnames_meta.append("Attribute " + str(i_attr + 1) + " value(s)")

            outfile_meta = open("metafields.csv", "w", newline='', encoding='utf-8')
            writer_meta = csv.DictWriter(outfile_meta, fieldnames=fieldnames_meta)
            writer_meta.writeheader()


        file_count = 1
        product_count = 0
        filename = f"{output_prefix}.csv"
        outfile_name = open(filename, "w", newline='', encoding='utf-8')
        writer = csv.DictWriter(outfile_name, fieldnames=fieldnames)
        writer.writeheader()
        
        for row in reader:
            peso = row["13 - Peso (Kg)"]
            if peso == "":  # Check if the "Peso (Kg)" field is empty
                peso = "0"

            alt_text = row["descripcionCorta"]
            if len(alt_text) > 512:
                alt_text = alt_text[:512]

            precio = row["precio"]
            precio = convertir_a_float(precio)
            precio = float_a_formato_original(precio*(100+porcentaje)/100)

            color = row["color"]
            if not color:
                color = "Sin color"
            handle = row["producto"].replace(" ", "-").lower()

            list_keys = list(metafields.keys())


            new_row = {
                "Handle": handle,
                "Title": row["titulo"],
                "Body (HTML)": row["subtitulo"],
                "Vendor": vendor,
                "Type": row["familia"],
                "Tags": f"{row['familia']},{row['subfamilia']}",
                "Published": "TRUE",  # or "FALSE" if you want to keep it unpublished
                "Option1 Name": "Color",
                "Option1 Value": color,
                "Option2 Name": "",
                "Option2 Value": "",
                "Option3 Name": "",
                "Option3 Value": "",
                "Variant SKU": row["id"],
                "Variant Grams": str(int(float(peso) * 1000)),
                "Variant Inventory Tracker": "shopify",
                "Variant Inventory Qty": row["stock"],
                "Variant Inventory Policy": "deny",  # deny or continue based on your preference
                "Variant Fulfillment Service": "manual",
                "Variant Price": row["PVP recomendado"],
                "Variant Compare At Price": precio,
                "Variant Requires Shipping": "TRUE",  # or "FALSE" based on your products
                "Variant Taxable": "TRUE",  # or "FALSE" based on your products
                "Image Src": row["imagen"],
                "Image Alt Text": alt_text,
                "Status": "active"
            }

            if args.metafields:
                new_metarow = {"sku": row["id"], "handle": handle}
                i_label = 0
                for attr in list_keys:
                    attr_value = row[attr]
                    if attr_value:
                        # print("\t", attr)
                        attr_name = metafields[attr]
                        new_metarow["Attribute " + str(i_label + 1) + " name"] = attr_name
                        new_metarow["Attribute " + str(i_label + 1) + " value(s)"] = attr_value
                        i_label += 1
                writer_meta.writerow(new_metarow)

            writer.writerow(new_row)


            # Add additional images for the product
            for image_column in image_columns:
                if row[image_column]:  # Check if the image column has a value
                    image_row = {
                        "Handle": handle,
                        "Image Src": row[image_column],
                        "Image Alt Text": alt_text
                    }
                    writer.writerow(image_row)

    df_shop = pd.read_csv(filename)
    filename_prefix = vendor
    save_chunks(df_shop, MAX_FILE_SIZE, filename_prefix)


if __name__ == "__main__":
    parser = make_parser()
    args = parser.parse_args()
    root = tk.Tk()
    root.withdraw()
    ruta_archivo = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
    if ruta_archivo:
        output_path = args.vendor
        convert_csv(ruta_archivo, output_path, args.vendor, args.porcentaje)
    else:
        print("No se seleccionó ningún archivo.")

    root.destroy()
