import os
from app.ocr.image_preprocessor import preprocess_image

def preprocess_images_in_dir(
    input_dir: str,
    output_dir: str = None
):
    processed_paths = []

    for filename in os.listdir(input_dir):
        if filename.lower().endswith((".png", ".jpg", ".jpeg")):
            image_path = os.path.join(input_dir, filename)
            processed_path = preprocess_image(image_path, output_dir)
            processed_paths.append(processed_path)

    return processed_paths
