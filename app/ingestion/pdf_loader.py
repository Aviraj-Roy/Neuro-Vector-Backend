import os
from typing import List
from pdf2image import convert_from_path

POPPLER_PATH = r"C:\poppler\Library\bin"


def pdf_to_images(pdf_path: str, output_dir: str = "uploads") -> List[str]:
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    images = convert_from_path(
        pdf_path=pdf_path,
        poppler_path=POPPLER_PATH
    )

    image_paths = []
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]

    for i, image in enumerate(images):
        image_path = os.path.join(output_dir, f"{base_name}_page_{i + 1}.png")
        image.save(image_path, "PNG")
        image_paths.append(image_path)

    return image_paths
