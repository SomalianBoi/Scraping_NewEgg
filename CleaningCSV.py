import csv
import os

input_files = [
    "products_1.csv",
    "products_2.csv",
    "products_3.csv",
    "products_4.csv",
    "products_5.csv",
]

output_file = "newegg_products.csv"


def is_new_product(line):
    return line.startswith("https://")


def is_header_line(line):
    return line.startswith("URL,Name")


all_products = []
current_lines = []

for input_file in input_files:
    if not os.path.exists(input_file):
        print(f"File not found: {input_file}")
        continue

    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or is_header_line(line):
                continue

            if is_new_product(line):
                if current_lines:
                    full_line = " ".join(current_lines)
                    current_lines = []

                    try:
                        reader = csv.reader([full_line])
                        fields = next(reader)
                        if len(fields) >= 6:
                            url = fields[0].strip()
                            title = fields[1].strip()
                            price = f"{fields[2].strip()}$"

                            raw_rating = fields[3].strip()
                            rating = raw_rating if raw_rating.lower() == "no rating" else f"{raw_rating} out of 5"

                            seller = f"Seller is {fields[4].strip()}"
                            description = " ".join(fields[5:]).replace("\n", " ").strip()
                            all_products.append([url, title, price, rating, seller, description])
                    except Exception as e:
                        print(f"Skipping malformed entry: {full_line}\n{e}")

                current_lines = [line]
            else:
                current_lines.append(line)


    if current_lines:
        full_line = " ".join(current_lines)
        current_lines = []
        try:
            reader = csv.reader([full_line])
            fields = next(reader)
            if len(fields) >= 6:
                url = fields[0].strip()
                title = fields[1].strip()
                price = f"{fields[2].strip()}$"

                raw_rating = fields[3].strip()
                rating = raw_rating if raw_rating.lower() == "no rating" else f"{raw_rating} out of 5"

                seller = f"Seller is {fields[4].strip()}"
                description = " ".join(fields[5:]).replace("\n", " ").strip()
                all_products.append([url, title, price, rating, seller, description])
        except Exception as e:
            print(f"Skipping malformed entry: {full_line}\n{e}")


with open(output_file, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["URL", "Title", "Price", "Rating", "Seller", "Description"])
    writer.writerows(all_products)

print(f"Done! {len(all_products)} clean products saved to '{output_file}'.")
