import os
import pandas as pd

def save_chunks(df, max_file_size, filename_prefix):
    # Empieza con un chunk que es aproximadamente 1/2 del tamaño total
    chunk_size = int(len(df) * 0.6)
    while pd.isnull(df.iloc[chunk_size]["Title"]):
        chunk_size -= 1
    # chunk_size -= 1
    chunks = [df.iloc[i:i + chunk_size] for i in range(0, len(df), chunk_size)]
    for idx, chunk in enumerate(chunks):
        temp_filename = f"{filename_prefix}_temp_{idx}.csv"
        chunk.to_csv(temp_filename, index=False)

        # Verifica el tamaño del archivo y ajústalo si es necesario
        while os.path.getsize(temp_filename) > max_file_size:
            chunk_size = int(0.9 * chunk_size)  # Reduce el tamaño del chunk en un 10%
            os.remove(temp_filename)  # Elimina el archivo que es demasiado grande
            chunk = df.iloc[idx * chunk_size:(idx + 1) * chunk_size]
            chunk.to_csv(temp_filename, index=False)

        # Renombra el archivo final
        final_filename = f"{filename_prefix}_{idx}.csv"
        if os.path.exists(final_filename):
            os.remove(final_filename)
        os.rename(temp_filename, final_filename)
        print(f"Guardado {final_filename}")
